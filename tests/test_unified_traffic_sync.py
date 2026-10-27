"""
Test Unified Traffic State and System Health Synchronization
Validates that:
1. AI vehicle detection and ESP32 simulation use the same vehicle counter.
2. AI detects 10 cars -> Dashboard = 10
3. ESP32 entry sensor adds one -> Dashboard = 11
4. ESP32 exit sensor triggers -> Dashboard = 10
5. Traffic density recalculates after every update.
6. System health returns GREEN for all 6 subsystems (WiFi, MQTT, Backend, Database, YOLO, WebSocket).
"""

import unittest
from app import app, db, init_db, get_system_health_dict
from ml.traffic_state import traffic_state
from database import User, IoTDevice, IoTMqttEvent


class UnifiedTrafficSyncTests(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = app.test_client()
        with self.app.app_context():
            init_db(self.app)
            traffic_state.reset(initial_count=0)

    def test_single_vehicle_counter_synchronization(self):
        """
        Requirements:
        • If AI detects 10 cars: Dashboard = 10
        • If ESP32 entry sensor adds one: Dashboard = 11
        • If exit sensor triggers: Dashboard = 10
        • Density recalculated after every update
        """
        # Step 1: AI Detection detects 10 cars
        st1 = traffic_state.set_ai_detection(
            count=10,
            breakdown={"cars": 10, "buses": 0, "trucks": 0, "motorcycles": 0, "bicycles": 0, "vans": 0},
            source="AI YOLOv11"
        )
        self.assertEqual(st1["vehicle_count"], 10)
        self.assertEqual(st1["counts"]["total"], 10)
        self.assertEqual(st1["density"], "Medium")

        # Query /api/traffic/state endpoint
        resp1 = self.client.get('/api/traffic/state')
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.get_json()['state']['vehicle_count'], 10)

        # Step 2: ESP32 entry sensor triggers (+1)
        st2 = traffic_state.record_entry(sensor_id="ir_sensor_a", device_id="esp32-counter-01")
        self.assertEqual(st2["vehicle_count"], 11)
        self.assertEqual(st2["counts"]["total"], 11)
        self.assertEqual(st2["density"], "Medium")

        # Query /api/traffic/state endpoint
        resp2 = self.client.get('/api/traffic/state')
        self.assertEqual(resp2.get_json()['state']['vehicle_count'], 11)

        # Step 3: ESP32 exit sensor triggers (-1)
        st3 = traffic_state.record_exit(sensor_id="ir_sensor_b", device_id="esp32-counter-01")
        self.assertEqual(st3["vehicle_count"], 10)
        self.assertEqual(st3["counts"]["total"], 10)
        self.assertEqual(st3["density"], "Medium")

        # Query /api/traffic/state endpoint
        resp3 = self.client.get('/api/traffic/state')
        self.assertEqual(resp3.get_json()['state']['vehicle_count'], 10)

    def test_density_recalculation_across_all_tiers(self):
        """Verify dynamic recalculation across Low, Medium, High, Very High."""
        # Low: 3 vehicles
        st_low = traffic_state.set_ai_detection(count=3)
        self.assertEqual(st_low["density"], "Low")

        # Medium: 12 vehicles
        st_med = traffic_state.set_ai_detection(count=12)
        self.assertEqual(st_med["density"], "Medium")

        # High: 22 vehicles
        st_high = traffic_state.set_ai_detection(count=22)
        self.assertEqual(st_high["density"], "High")

        # Very High: 35 vehicles
        st_vhigh = traffic_state.set_ai_detection(count=35)
        self.assertEqual(st_vhigh["density"], "Very High")

    def test_system_health_indicators_all_green(self):
        """
        Verify that all 6 subsystems report GREEN:
        WiFi, MQTT, Backend, Database, YOLO, WebSocket.
        """
        health = get_system_health_dict()
        self.assertEqual(health["status"], "GREEN")
        self.assertEqual(health["overall"], "GREEN")

        components = health["components"]
        for key in ["wifi", "mqtt", "backend", "database", "yolo", "websocket"]:
            self.assertIn(key, components)
            self.assertEqual(
                components[key]["status"],
                "GREEN",
                f"Expected GREEN status for component '{key}', got '{components[key]['status']}'"
            )
            self.assertTrue(components[key]["healthy"])

        # Test HTTP endpoint
        response = self.client.get('/api/system/health')
        self.assertEqual(response.status_code, 200)
        json_data = response.get_json()
        self.assertEqual(json_data["status"], "GREEN")
        self.assertEqual(json_data["components"]["yolo"]["status"], "GREEN")
        self.assertEqual(json_data["components"]["mqtt"]["status"], "GREEN")


if __name__ == '__main__':
    unittest.main()
