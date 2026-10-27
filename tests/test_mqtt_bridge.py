import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server import mqtt_bridge


class MqttBridgeTests(unittest.TestCase):
    def make_message(self, topic, payload):
        return SimpleNamespace(
            topic=topic,
            payload=json.dumps(payload).encode('utf-8'),
            mid=1,
            qos=1,
        )

    @patch('server.mqtt_bridge.HTTP.post')
    def test_forwards_status_without_repeating_device_token_in_body(self, post):
        post.return_value = Mock(status_code=201, text='')
        message = self.make_message('traffic/counter-1/status', {
            'device_id': 'counter-1',
            'device_token': 'secret-token',
            'sequence': 4,
        })

        self.assertTrue(mqtt_bridge._handle_message(message))
        args, kwargs = post.call_args
        self.assertTrue(args[0].endswith('/api/iot/telemetry'))
        self.assertNotIn('device_token', kwargs['json'])
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer secret-token')

    @patch('server.mqtt_bridge.HTTP.post')
    def test_retries_when_flask_is_temporarily_unreachable(self, post):
        import requests

        post.side_effect = requests.ConnectionError('unavailable')
        message = self.make_message('traffic/counter-1/count', {
            'device_id': 'counter-1',
            'device_token': 'secret-token',
        })

        self.assertFalse(mqtt_bridge._handle_message(message))

    @patch('server.mqtt_bridge.HTTP.post')
    def test_discards_permanently_rejected_message(self, post):
        post.return_value = Mock(status_code=401, text='invalid token')
        message = self.make_message('traffic/counter-1/alert', {
            'device_id': 'counter-1',
            'device_token': 'bad-token',
        })

        self.assertTrue(mqtt_bridge._handle_message(message))


if __name__ == '__main__':
    unittest.main()
