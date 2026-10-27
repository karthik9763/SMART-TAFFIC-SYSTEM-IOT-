import json
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

import app as traffic_app
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash
from app import HAS_CV2, app, db, process_traffic_image
from database import init_db, IoTDevice, IoTMqttEvent, IoTTelemetry, Prediction, TrafficRecord


class MqttApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI='sqlite://',
            DEVICE_MINIMUM_INTERVAL_SECONDS=0,
        )
        try:
            from server.mqtt_service import mqtt_service
            mqtt_service.stop()
        except Exception:
            pass
        with app.app_context():
            db.create_all()

    def setUp(self):
        with app.app_context():
            db.session.remove()
            IoTTelemetry.query.delete()
            IoTMqttEvent.query.delete()
            IoTDevice.query.filter_by(device_id='test-counter-01').delete()
            Prediction.query.delete()
            TrafficRecord.query.delete()
            init_db(app)
            db.session.add(IoTDevice(
                device_id='test-counter-01',
                intersection_id='junction-1',
                lane_id='north',
                mode='simulation',
                token_hash=generate_password_hash('test-device-token'),
                registered_by='test'
            ))
            db.session.commit()
        self.client = app.test_client()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            IoTTelemetry.query.delete()
            IoTMqttEvent.query.delete()
            IoTDevice.query.filter_by(device_id='test-counter-01').delete()
            init_db(app)
            db.session.commit()

    def test_mqtt_event_is_saved_without_device_token(self):
        payload = {
            'device_id': 'test-counter-01',
            'device_token': 'test-device-token',
            'sequence': 3,
            'vehicle_count': 2,
        }
        response = self.client.post('/api/iot/mqtt/event', json={
            'device_id': 'test-counter-01',
            'device_token': 'test-device-token',
            'topic': 'traffic/test-counter-01/count',
            'payload': payload,
        })

        self.assertEqual(response.status_code, 201)
        with app.app_context():
            event = IoTMqttEvent.query.filter_by(device_id='test-counter-01').order_by(IoTMqttEvent.id.desc()).first()
            self.assertIsNotNone(event)
            self.assertEqual(event.topic, 'traffic/test-counter-01/count')
            self.assertNotIn('device_token', json.loads(event.payload_json))

    def test_mqtt_event_rejects_invalid_device_token(self):
        response = self.client.post('/api/iot/mqtt/event', json={
            'device_id': 'test-counter-01',
            'device_token': 'wrong-token',
            'topic': 'traffic/test-counter-01/count',
            'payload': {'device_id': 'test-counter-01'},
        })
        self.assertEqual(response.status_code, 401)

    def test_mqtt_event_rejects_topic_for_another_device(self):
        response = self.client.post('/api/iot/mqtt/event', json={
            'device_id': 'test-counter-01',
            'device_token': 'test-device-token',
            'topic': 'traffic/other-device/count',
            'payload': {'device_id': 'test-counter-01'},
        })
        self.assertEqual(response.status_code, 400)

    def test_telemetry_endpoint_persists_authenticated_status(self):
        payload = {
            'device_id': 'test-counter-01',
            'sequence': 0,
            'uptime_seconds': 1,
            'vehicle_count': 0,
            'direction_a_to_b': 0,
            'direction_b_to_a': 0,
            'sensor_a': False,
            'sensor_b': False,
            'mode': 'simulation',
            'firmware_version': '1.0.0',
        }
        response = self.client.post(
            '/api/iot/telemetry',
            json=payload,
            headers={'Authorization': 'Bearer test-device-token'},
        )

        self.assertEqual(response.status_code, 201)
        with app.app_context():
            self.assertEqual(IoTTelemetry.query.count(), 1)

    def test_react_apis_share_session_and_csrf_protection(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1
            session['username'] = 'operator'
            session['role'] = 'User'

        session_response = self.client.get('/api/auth/session')
        self.assertEqual(session_response.status_code, 200)
        csrf_token = session_response.get_json()['csrf_token']
        prediction_response = self.client.post('/api/predict', json={
            'vehicle_count': 6,
            'occupancy_rate': 25,
            'avg_speed': 40,
        }, headers={'X-CSRF-Token': csrf_token})
        self.assertEqual(prediction_response.status_code, 200)

    def test_react_operations_route_serves_built_client_or_explains_build(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1
            session['username'] = 'operator'
            session['role'] = 'User'
        response = self.client.get('/operations')
        expected_status = 200 if Path(app.static_folder, 'react', 'index.html').exists() else 503
        self.assertEqual(response.status_code, expected_status)
        response.close()

    def test_sample_images_lists_only_original_uploads(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 1
            session['username'] = 'operator'
            session['role'] = 'User'

        response = self.client.get('/api/sample-images')
        self.assertEqual(response.status_code, 200)
        samples = response.get_json()['samples']
        self.assertTrue(samples)
        self.assertTrue(all(sample['filename'].startswith('upload_') for sample in samples))
        self.assertNotIn('device_token', response.get_data(as_text=True))

    def test_sample_prediction_uses_the_existing_image_pipeline(self):
        sample_path = next(Path(app.config['UPLOAD_FOLDER']).glob('upload_*.jpg'))
        csrf_token = 'sample-image-test-token'
        with self.client.session_transaction() as session:
            session['user_id'] = 1
            session['username'] = 'operator'
            session['role'] = 'User'
            session['csrf_token'] = csrf_token
        prediction = Mock()
        prediction.to_dict.return_value = {
            'vehicle_count': 2,
            'predicted_density': 'Low',
            'annotated_image_path': 'static/uploads/annotated_sample.jpg',
        }
        with patch('app.process_traffic_image', return_value=(prediction, None)) as process_image:
            response = self.client.post(
                f'/api/sample-images/{sample_path.name}/predict',
                headers={'X-CSRF-Token': csrf_token}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['prediction']['vehicle_count'], 2)
        self.assertEqual(process_image.call_count, 1)
        self.assertEqual(process_image.call_args.args[0].filename, sample_path.name)

    def test_sample_prediction_rejects_path_traversal(self):
        csrf_token = 'sample-image-test-token'
        with self.client.session_transaction() as session:
            session['user_id'] = 1
            session['username'] = 'operator'
            session['role'] = 'User'
            session['csrf_token'] = csrf_token

        response = self.client.post(
            '/api/sample-images/upload_%2e%2e%2fsecrets.jpg/predict',
            headers={'X-CSRF-Token': csrf_token}
        )
        self.assertEqual(response.status_code, 400)

    @unittest.skipUnless(HAS_CV2, 'OpenCV is required for image pipeline tests')
    def test_image_prediction_persists_without_a_registered_camera(self):
        upload_dir = Path(app.config['UPLOAD_FOLDER'])
        files_before = set(upload_dir.glob('*.jpg'))
        image = traffic_app.np.zeros((16, 16, 3), dtype=traffic_app.np.uint8)
        encoded_image = traffic_app.cv2.imencode('.jpg', image)[1].tobytes()
        telemetry = {
            'count': 0,
            'cars': 0,
            'buses': 0,
            'trucks': 0,
            'motorcycles': 0,
            'bicycles': 0,
            'autorickshaws': 0,
            'vans': 0,
            'occupancy': 0,
            'density_level': 'LOW',
            'density_pct': 0,
            'quality_warning': None,
            'confidence_score': None,
            'detection_method': 'yolo',
        }
        try:
            with app.app_context(), patch.object(
                traffic_app.detector, 'process_frame', return_value=(image, telemetry)
            ):
                prediction, error = process_traffic_image(
                    FileStorage(stream=BytesIO(encoded_image), filename='sample.jpg')
                )
                self.assertIsNone(error)
                self.assertIsNotNone(prediction)
                self.assertEqual(Prediction.query.count(), 1)
                self.assertEqual(TrafficRecord.query.count(), 0)
        finally:
            for path in set(upload_dir.glob('*.jpg')) - files_before:
                path.unlink(missing_ok=True)


class WokwiDiagramTests(unittest.TestCase):
    project_root = Path(__file__).resolve().parents[1]

    def test_ir_counter_diagram_has_expected_gpio_connections(self):
        diagram_path = self.project_root / 'hardware' / 'esp32_ir_counter' / 'diagram.json'
        diagram = json.loads(diagram_path.read_text(encoding='utf-8'))
        destinations = {connection[1] for connection in diagram['connections']}
        self.assertIn('esp:18', destinations)
        self.assertIn('esp:19', destinations)
        self.assertIn('esp:2', {connection[0] for connection in diagram['connections']})
        self.assertEqual(len({part['id'] for part in diagram['parts']}), len(diagram['parts']))

    def test_camera_wokwi_diagram_uses_supported_esp32_and_simulates_motion(self):
        diagram_path = self.project_root / 'hardware' / 'esp32_cam_streamer' / 'diagram.json'
        diagram = json.loads(diagram_path.read_text(encoding='utf-8'))
        self.assertTrue(any(part['type'] == 'board-esp32-devkit-c-v4' for part in diagram['parts']))
        self.assertTrue(any(part['id'] == 'motion' for part in diagram['parts']))


if __name__ == '__main__':
    unittest.main()
