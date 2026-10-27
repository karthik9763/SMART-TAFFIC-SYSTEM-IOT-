"""
Unified Traffic State Manager
Single source of truth for AI detection and IoT ESP32 sensor simulation.
Ensures vehicle counters and traffic density stay strictly synchronized across:
- YOLOv11 AI detection
- ESP32 entry / exit sensor pulses
- Traffic signal adaptive timing
- Dashboard widgets & charts (via WebSocket / Socket.IO)
- Database persistence
"""

import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional
from ml.logger import log_event


class TrafficStateManager:
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(TrafficStateManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        with self._lock:
            self.total_vehicles: int = 0
            self.entry_count: int = 0
            self.exit_count: int = 0
            self.density_level: str = "Low"
            self.occupancy_pct: float = 0.0
            self.congestion_pct: float = 0.0
            self.recommended_speed: int = 60
            self.last_source: str = "initial"
            self.last_update_time: datetime = datetime.utcnow()

            self.breakdown: Dict[str, int] = {
                "cars": 0,
                "buses": 0,
                "trucks": 0,
                "motorcycles": 0,
                "bicycles": 0,
                "vans": 0,
            }

            self._listeners: List[Callable[[dict], None]] = []
            self._initialized = True
            log_event("traffic_state", "Unified TrafficStateManager initialized")

    def register_listener(self, callback: Callable[[dict], None]):
        """Register a callback invoked whenever the traffic state updates."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def unregister_listener(self, callback: Callable[[dict], None]):
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify_listeners(self):
        """Invoke all registered listeners with the latest state snapshot."""
        state = self.get_state()
        for callback in list(self._listeners):
            try:
                callback(state)
            except Exception as e:
                log_event("traffic_state", f"Listener notification error: {e}")

    def _recalculate_density_and_metrics(self):
        """
        Recalculate density level, lane occupancy, and congestion based on total vehicles.
        Low: 0-5
        Medium: 6-14
        High: 15-25
        Very High: 26+
        """
        count = self.total_vehicles

        # Lane occupancy percentage
        if count == 0:
            self.occupancy_pct = 0.0
        else:
            self.occupancy_pct = round(min(98.5, max(1.5, count * 3.6)), 1)

        # Density tier & Congestion index strictly matching DENSITY_THRESHOLDS
        if count <= 5:
            self.density_level = "Low"
            self.congestion_pct = round(min(25.0, count * 4.5 + self.occupancy_pct * 0.15), 1)
            self.recommended_speed = 60
        elif count <= 14:
            self.density_level = "Medium"
            self.congestion_pct = round(26.0 + (count - 5) * 3.2 + self.occupancy_pct * 0.1, 1)
            self.recommended_speed = 45
        elif count <= 25:
            self.density_level = "High"
            self.congestion_pct = round(56.0 + (count - 14) * 2.5 + self.occupancy_pct * 0.05, 1)
            self.recommended_speed = 25
        else:
            self.density_level = "Very High"
            self.congestion_pct = round(min(100.0, 85.0 + (count - 25) * 0.7), 1)
            self.recommended_speed = 15

        self.last_update_time = datetime.utcnow()

    def set_ai_detection(
        self,
        count: int,
        breakdown: Optional[Dict[str, int]] = None,
        confidence: float = 0.85,
        occupancy: Optional[float] = None,
        source: str = "AI YOLOv11"
    ) -> dict:
        """
        Synchronize state when AI detector runs inference on a camera frame.
        Example: If AI detects 10 cars -> Dashboard = 10.
        """
        with self._lock:
            self.total_vehicles = max(0, int(count))
            self.last_source = source

            if breakdown:
                # Normalize keys to lowercase
                self.breakdown = {
                    "cars": breakdown.get("cars", breakdown.get("Car", 0)),
                    "buses": breakdown.get("buses", breakdown.get("Bus", 0)),
                    "trucks": breakdown.get("trucks", breakdown.get("Truck", 0)),
                    "motorcycles": breakdown.get("motorcycles", breakdown.get("Motorcycle", 0)),
                    "bicycles": breakdown.get("bicycles", breakdown.get("Bicycle", 0)),
                    "vans": breakdown.get("vans", breakdown.get("Van", 0)),
                }
            else:
                self.breakdown = {
                    "cars": self.total_vehicles,
                    "buses": 0,
                    "trucks": 0,
                    "motorcycles": 0,
                    "bicycles": 0,
                    "vans": 0,
                }

            self._recalculate_density_and_metrics()
            if occupancy is not None and occupancy > 0:
                self.occupancy_pct = round(float(occupancy), 1)

            log_event(
                "traffic_state",
                f"AI Detection sync: total={self.total_vehicles}, density={self.density_level}, source={source}"
            )
            self._notify_listeners()
            return self.get_state()

    def record_entry(
        self,
        sensor_id: str = "entry_sensor",
        device_id: str = "esp32-counter-01",
        hardware_count: Optional[int] = None
    ) -> dict:
        """
        Record a vehicle entry event (e.g. ESP32 IR Sensor A).
        Example: If count was 10, adding one -> Dashboard = 11.
        """
        with self._lock:
            self.total_vehicles += 1
            self.entry_count += 1
            self.breakdown["cars"] = self.breakdown.get("cars", 0) + 1
            self.last_source = f"ESP32 Entry ({device_id}/{sensor_id})"

            self._recalculate_density_and_metrics()
            log_event(
                "traffic_state",
                f"Vehicle ENTRY (+1): new_total={self.total_vehicles}, density={self.density_level}, device={device_id}"
            )
            self._notify_listeners()
            return self.get_state()

    def record_exit(
        self,
        sensor_id: str = "exit_sensor",
        device_id: str = "esp32-counter-01",
        hardware_count: Optional[int] = None
    ) -> dict:
        """
        Record a vehicle exit event (e.g. ESP32 IR Sensor B).
        Example: If count was 11, exit sensor triggers -> Dashboard = 10.
        """
        with self._lock:
            self.total_vehicles = max(0, self.total_vehicles - 1)
            self.exit_count += 1
            if self.breakdown.get("cars", 0) > 0:
                self.breakdown["cars"] -= 1
            self.last_source = f"ESP32 Exit ({device_id}/{sensor_id})"

            self._recalculate_density_and_metrics()
            log_event(
                "traffic_state",
                f"Vehicle EXIT (-1): new_total={self.total_vehicles}, density={self.density_level}, device={device_id}"
            )
            self._notify_listeners()
            return self.get_state()

    def update_from_counter(
        self,
        vehicle_count: int,
        device_id: str = "esp32-counter-01"
    ) -> dict:
        """Synchronize absolute count from ESP32 telemetry."""
        with self._lock:
            self.total_vehicles = max(0, int(vehicle_count))
            self.breakdown["cars"] = self.total_vehicles
            self.last_source = f"ESP32 Counter Sync ({device_id})"

            self._recalculate_density_and_metrics()
            log_event("traffic_state", f"ESP32 Counter Sync: total={self.total_vehicles}")
            self._notify_listeners()
            return self.get_state()

    def reset(self, initial_count: int = 0) -> dict:
        """Reset state cleanly to initial baseline."""
        with self._lock:
            self.total_vehicles = max(0, int(initial_count))
            self.entry_count = 0
            self.exit_count = 0
            self.breakdown = {k: 0 for k in self.breakdown}
            self.breakdown["cars"] = self.total_vehicles
            self.last_source = "reset"
            self._recalculate_density_and_metrics()
            log_event("traffic_state", f"Traffic state reset to {self.total_vehicles}")
            self._notify_listeners()
            return self.get_state()

    def get_state(self) -> dict:
        """Return the authoritative, synchronized traffic state dictionary."""
        with self._lock:
            return {
                "vehicle_count": self.total_vehicles,
                "density": self.density_level,
                "density_level": self.density_level,
                "occupancy": self.occupancy_pct,
                "occupancy_pct": self.occupancy_pct,
                "congestion_pct": self.congestion_pct,
                "recommended_speed": self.recommended_speed,
                "entry_count": self.entry_count,
                "exit_count": self.exit_count,
                "breakdown": dict(self.breakdown),
                "counts": {
                    "total": self.total_vehicles,
                    "cars": self.breakdown.get("cars", self.total_vehicles),
                    "buses": self.breakdown.get("buses", 0),
                    "trucks": self.breakdown.get("trucks", 0),
                    "motorcycles": self.breakdown.get("motorcycles", 0),
                    "bicycles": self.breakdown.get("bicycles", 0),
                    "vans": self.breakdown.get("vans", 0),
                },
                "last_source": self.last_source,
                "timestamp": self.last_update_time.isoformat() + "Z",
            }


# Global singleton instance
traffic_state = TrafficStateManager()
