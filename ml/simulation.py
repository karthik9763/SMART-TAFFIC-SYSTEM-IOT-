import time
import math
import random
import threading
from datetime import datetime
from pathlib import Path

from ml.logger import log_event

class TrafficSignalSimulator:
    """
    Adaptive Traffic Light Simulator for 4-way intersection (North/South vs East/West).
    Adapts green phase duration dynamically according to traffic density:
    - Low: 15s green
    - Medium: 30s green
    - High: 45s green
    - Very High: 60s green
    Supports emergency vehicle preemption (instant green wave).
    """
    def __init__(self):
        self.phase = "NS_GREEN"  # NS_GREEN, NS_YELLOW, EW_GREEN, EW_YELLOW
        self.phase_elapsed = 0
        self.yellow_duration = 4
        self.emergency_active = False
        self.emergency_lane = None
        self.signals = {
            "north": "GREEN",
            "south": "GREEN",
            "east": "RED",
            "west": "RED"
        }

    def get_green_duration(self, density_level):
        mapping = {
            "Low": 15,
            "Medium": 30,
            "High": 45,
            "Very High": 60,
            "Critical": 60
        }
        return mapping.get(density_level, 30)

    def trigger_emergency(self, lane="North"):
        self.emergency_active = True
        self.emergency_lane = lane.capitalize()
        if self.emergency_lane in ["North", "South"]:
            self.phase = "NS_GREEN"
            self.signals = {"north": "GREEN", "south": "GREEN", "east": "RED", "west": "RED"}
        else:
            self.phase = "EW_GREEN"
            self.signals = {"north": "RED", "south": "RED", "east": "GREEN", "west": "GREEN"}
        self.phase_elapsed = 0
        log_event("simulation", f"Traffic Signal Preemption triggered for emergency on {self.emergency_lane} lane")

    def clear_emergency(self):
        self.emergency_active = False
        self.emergency_lane = None

    def tick(self, seconds=1, density_level="Medium"):
        if self.emergency_active:
            self.phase_elapsed += seconds
            if self.phase_elapsed >= 15:  # Preemption clears after 15s
                self.clear_emergency()
            return

        green_dur = self.get_green_duration(density_level)
        self.phase_elapsed += seconds

        if self.phase == "NS_GREEN":
            if self.phase_elapsed >= green_dur:
                self.phase = "NS_YELLOW"
                self.phase_elapsed = 0
                self.signals = {"north": "YELLOW", "south": "YELLOW", "east": "RED", "west": "RED"}
        elif self.phase == "NS_YELLOW":
            if self.phase_elapsed >= self.yellow_duration:
                self.phase = "EW_GREEN"
                self.phase_elapsed = 0
                self.signals = {"north": "RED", "south": "RED", "east": "GREEN", "west": "GREEN"}
        elif self.phase == "EW_GREEN":
            if self.phase_elapsed >= green_dur:
                self.phase = "EW_YELLOW"
                self.phase_elapsed = 0
                self.signals = {"north": "RED", "south": "RED", "east": "YELLOW", "west": "YELLOW"}
        elif self.phase == "EW_YELLOW":
            if self.phase_elapsed >= self.yellow_duration:
                self.phase = "NS_GREEN"
                self.phase_elapsed = 0
                self.signals = {"north": "GREEN", "south": "GREEN", "east": "RED", "west": "RED"}

    def reset(self):
        self.phase = "NS_GREEN"
        self.phase_elapsed = 0
        self.emergency_active = False
        self.emergency_lane = None
        self.signals = {"north": "GREEN", "south": "GREEN", "east": "RED", "west": "RED"}


class VehicleGenerator:
    """Stochastic traffic arrival generator supporting 6 target classes."""
    def __init__(self):
        self.vehicle_classes = ["Car", "Bus", "Truck", "Motorcycle", "Bicycle", "Van"]
        self.weights = [0.65, 0.08, 0.07, 0.10, 0.04, 0.06]

    def generate(self, intensity=1.0):
        """Generates a batch of vehicles based on current traffic intensity."""
        mean_arrivals = max(1, int(4 * intensity))
        count = random.randint(max(1, mean_arrivals - 2), mean_arrivals + 3)
        generated = random.choices(self.vehicle_classes, weights=self.weights, k=count)
        
        breakdown = {k: 0 for k in self.vehicle_classes}
        for v in generated:
            breakdown[v] += 1
        return count, breakdown


class ESP32Simulator:
    """Emulates ESP32 with dual IR sensors measuring directional traffic."""
    def __init__(self, device_id="esp32-counter-01"):
        self.device_id = device_id
        self.sequence = 0
        self.uptime_seconds = 0
        self.total_vehicles = 0
        self.direction_a_to_b = 0
        self.direction_b_to_a = 0
        self.sensor_a = False
        self.sensor_b = False

    def tick(self, vehicles_passed=1, seconds=1):
        self.uptime_seconds += seconds
        self.sequence += 1
        if vehicles_passed > 0:
            a_to_b = random.randint(0, vehicles_passed)
            b_to_a = vehicles_passed - a_to_b
            self.direction_a_to_b += a_to_b
            self.direction_b_to_a += b_to_a
            self.total_vehicles += vehicles_passed
            self.sensor_a = True
            self.sensor_b = True
        else:
            self.sensor_a = False
            self.sensor_b = False

    def get_telemetry(self, flow_per_minute=0.0, density="Low"):
        return {
            "device_id": self.device_id,
            "sequence": self.sequence,
            "uptime_seconds": self.uptime_seconds,
            "total_vehicle_count": self.total_vehicles,
            "interval_vehicle_count": self.direction_a_to_b + self.direction_b_to_a,
            "direction_a_to_b": self.direction_a_to_b,
            "direction_b_to_a": self.direction_b_to_a,
            "sensor_a": self.sensor_a,
            "sensor_b": self.sensor_b,
            "flow_per_minute": flow_per_minute,
            "density": density,
            "mode": "simulation",
            "firmware_version": "2.1.0-sim"
        }

    def reset(self):
        self.sequence = 0
        self.uptime_seconds = 0
        self.total_vehicles = 0
        self.direction_a_to_b = 0
        self.direction_b_to_a = 0
        self.sensor_a = False
        self.sensor_b = False


class EmergencyVehicleSimulator:
    """Simulates emergency vehicle arrivals (Ambulance, Fire, Police)."""
    def __init__(self):
        self.active = False
        self.vehicle_type = None
        self.lane = None
        self.seconds_remaining = 0

    def trigger(self, vehicle_type="Ambulance", lane="North", duration=15):
        self.active = True
        self.vehicle_type = vehicle_type
        self.lane = lane
        self.seconds_remaining = duration
        log_event("simulation", f"EMERGENCY VEHICLE DISPATCHED: {vehicle_type} approaching {lane} junction")

    def tick(self, seconds=1):
        if self.active:
            self.seconds_remaining -= seconds
            if self.seconds_remaining <= 0:
                self.active = False
                self.vehicle_type = None
                self.lane = None

    def reset(self):
        self.active = False
        self.vehicle_type = None
        self.lane = None
        self.seconds_remaining = 0


class SimulationManager:
    """
    Central Simulation Master Controller managing all synchronized simulation modules:
    - Traffic Signals
    - ESP32 / IoT
    - MQTT
    - Vehicle Generator
    - Emergency Vehicles
    - Realtime Dashboard Sync
    - Timer (Start, Pause, Resume, Reset)
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SimulationManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.running = False
        self.paused = False
        self.elapsed_seconds = 0
        self.time_scale = 1.0
        self._lock = threading.Lock()
        self._thread = None
        self._stop_event = threading.Event()

        # Sub-simulators
        self.signal_sim = TrafficSignalSimulator()
        self.vehicle_gen = VehicleGenerator()
        self.esp32_sim = ESP32Simulator()
        self.emergency_sim = EmergencyVehicleSimulator()

        # Telemetry State
        self.current_density = "Medium"
        self.current_congestion_pct = 42.0
        self.current_occupancy = 25.0
        self.current_vehicle_count = 12
        self.current_breakdown = {
            "Car": 8, "Bus": 1, "Truck": 1, "Motorcycle": 1, "Bicycle": 0, "Van": 1
        }
        self.recent_events = []

    def start(self):
        with self._lock:
            if self.running and not self.paused:
                return
            if self.paused:
                self.paused = False
                log_event("simulation", "Simulation Resumed")
                return

            self.running = True
            self.paused = False
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            log_event("simulation", "Simulation Started")

    def pause(self):
        with self._lock:
            if self.running:
                self.paused = True
                log_event("simulation", "Simulation Paused")

    def resume(self):
        self.start()

    def reset(self):
        with self._lock:
            self.running = False
            self.paused = False
            self._stop_event.set()
            self.elapsed_seconds = 0
            self.signal_sim.reset()
            self.esp32_sim.reset()
            self.emergency_sim.reset()
            self.current_density = "Low"
            self.current_congestion_pct = 15.0
            self.current_occupancy = 8.0
            self.current_vehicle_count = 3
            self.current_breakdown = {
                "Car": 2, "Bus": 0, "Truck": 0, "Motorcycle": 1, "Bicycle": 0, "Van": 0
            }
            self.recent_events.clear()
            log_event("simulation", "Simulation Reset to initial state")

    def trigger_emergency(self, vehicle_type="Ambulance", lane="North"):
        with self._lock:
            self.emergency_sim.trigger(vehicle_type=vehicle_type, lane=lane)
            self.signal_sim.trigger_emergency(lane=lane)
            self.recent_events.append({
                "time": datetime.utcnow().strftime("%H:%M:%S"),
                "event": f"EMERGENCY: {vehicle_type} on {lane} Lane",
                "type": "emergency"
            })

    def _run_loop(self):
        while not self._stop_event.is_set():
            if not self.paused:
                self.step(1)
            time.sleep(1.0 / max(0.1, self.time_scale))

    def step(self, seconds=1):
        with self._lock:
            self.elapsed_seconds += seconds

            # 1. Generate traffic arrivals
            # Diurnal curve: simulates rush hour variation
            hour = (8 + (self.elapsed_seconds // 60)) % 24
            intensity = 0.5 + 0.5 * math.sin((hour - 6) / 24.0 * 2 * math.pi)
            intensity = max(0.3, min(1.8, intensity))

            count, breakdown = self.vehicle_gen.generate(intensity)
            self.current_vehicle_count = count
            self.current_breakdown = breakdown

            # 2. Compute Occupancy and Density
            # Formula: 6 vehicles = ~18% occupancy; 25 vehicles = ~75% occupancy
            self.current_occupancy = round(min(98.0, max(2.0, count * 3.5 + random.uniform(-1.5, 2.5))), 1)

            if count <= 5 and self.current_occupancy < 20:
                self.current_density = "Low"
                self.current_congestion_pct = round(count * 5.0 + self.current_occupancy * 0.2, 1)
            elif count <= 14 and self.current_occupancy < 45:
                self.current_density = "Medium"
                self.current_congestion_pct = round(30.0 + (count - 5) * 3.5 + self.current_occupancy * 0.1, 1)
            elif count <= 25 and self.current_occupancy < 70:
                self.current_density = "High"
                self.current_congestion_pct = round(65.0 + (count - 14) * 2.0 + self.current_occupancy * 0.05, 1)
            else:
                self.current_density = "Very High"
                self.current_congestion_pct = round(min(100.0, 88.0 + (count - 25) * 0.8), 1)

            # 3. Step Traffic Signal Simulator
            self.signal_sim.tick(seconds=seconds, density_level=self.current_density)

            # 4. Step ESP32 Simulator
            flow_per_minute = round(count * (60.0 / max(1, seconds)), 1)
            self.esp32_sim.tick(vehicles_passed=count, seconds=seconds)

            # 5. Step Emergency Simulator
            self.emergency_sim.tick(seconds=seconds)

    def get_status(self):
        with self._lock:
            return {
                "running": self.running,
                "paused": self.paused,
                "elapsed_seconds": self.elapsed_seconds,
                "time_scale": self.time_scale,
                "density": {
                    "level": self.current_density,
                    "congestion_pct": self.current_congestion_pct,
                    "occupancy": self.current_occupancy,
                },
                "counts": {
                    "total": self.current_vehicle_count,
                    "cars": self.current_breakdown.get("Car", 0),
                    "buses": self.current_breakdown.get("Bus", 0),
                    "trucks": self.current_breakdown.get("Truck", 0),
                    "motorcycles": self.current_breakdown.get("Motorcycle", 0),
                    "bicycles": self.current_breakdown.get("Bicycle", 0),
                    "vans": self.current_breakdown.get("Van", 0)
                },
                "traffic_lights": {
                    "phase": self.signal_sim.phase,
                    "phase_elapsed": self.signal_sim.phase_elapsed,
                    "signals": self.signal_sim.signals,
                    "emergency_preemption": self.signal_sim.emergency_active,
                    "emergency_lane": self.signal_sim.emergency_lane
                },
                "esp32_iot": self.esp32_sim.get_telemetry(
                    flow_per_minute=round(self.current_vehicle_count * 12.0, 1),
                    density=self.current_density
                ),
                "emergency": {
                    "active": self.emergency_sim.active,
                    "vehicle_type": self.emergency_sim.vehicle_type,
                    "lane": self.emergency_sim.lane,
                    "seconds_remaining": self.emergency_sim.seconds_remaining
                },
                "recent_events": self.recent_events[-10:]
            }

simulation_manager = SimulationManager()
