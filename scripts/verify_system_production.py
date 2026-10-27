import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path
import requests

BASE_URL = "http://127.0.0.1:5000"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
REPORT_FILE = LOGS_DIR / "startup_test_report.json"
INFERENCE_LOG_FILE = LOGS_DIR / "inference.log"

report = {
    "timestamp": datetime.utcnow().isoformat() + "Z",
    "summary": {"total": 0, "passed": 0, "failed": 0},
    "results": {}
}

def record_test(module, test_name, passed, details=""):
    report["summary"]["total"] += 1
    if passed:
        report["summary"]["passed"] += 1
        status_str = "PASS"
    else:
        report["summary"]["failed"] += 1
        status_str = "FAIL"

    if module not in report["results"]:
        report["results"][module] = []

    report["results"][module].append({
        "test": test_name,
        "status": status_str,
        "details": details
    })
    print(f"[{status_str}] [{module}] {test_name}: {details}")

import socket
import subprocess

def ensure_server_running():
    def is_running():
        try:
            with socket.create_connection(("127.0.0.1", 5000), timeout=1):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    if is_running():
        return None

    print("[Auto-Start] Starting Smart Traffic Flask Server on http://127.0.0.1:5000...")
    local_python = PROJECT_ROOT / ".python" / "python.exe"
    python_exe = str(local_python) if local_python.exists() else sys.executable
    server_proc = subprocess.Popen(
        [python_exe, str(PROJECT_ROOT / "run.py")],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    for _ in range(30):
        if is_running():
            print("[Auto-Start] Server is online and responding.")
            time.sleep(1)
            return server_proc
        time.sleep(1)

    print("[Auto-Start Warning] Server did not respond within 30 seconds.")
    return server_proc


def run_tests():
    print("=" * 65)
    print("  PRODUCTION SMART TRAFFIC AI COMPREHENSIVE VERIFICATION SUITE")
    print("=" * 65)

    server_proc = ensure_server_running()
    try:
        _execute_test_suite()
    finally:
        if server_proc:
            print("[Clean-up] Shutting down auto-started server instance...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except Exception:
                server_proc.kill()


def _execute_test_suite():
    s = requests.Session()

    # 1. Authentication
    login_res = s.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": "123456"})
    is_logged_in = login_res.status_code == 200 and "token" in login_res.json()
    token = login_res.json().get("token") if is_logged_in else None
    record_test("Authentication", "Admin JWT Login", is_logged_in, f"Status: {login_res.status_code}")

    headers = {"Authorization": f"Bearer {token}"} if token else {}

    # Find sample traffic test image
    traffic_img_path = PROJECT_ROOT / "static" / "uploads" / "upload_20260921_135957_0fdd4c01.jpg"
    if not traffic_img_path.exists():
        sample_images = sorted(
            list(Path(PROJECT_ROOT / "static" / "uploads").glob("upload_*.jpg")),
            key=lambda p: p.stat().st_size,
            reverse=True
        )
        traffic_img_path = sample_images[0] if sample_images else None
    test_img_path = traffic_img_path

    # 2. Image Upload & YOLO Detection (Fast, Balanced, High Accuracy)
    if test_img_path and test_img_path.exists():
        for mode in ["fast", "balanced", "high_accuracy"]:
            with open(test_img_path, "rb") as f:
                r = s.post(
                    f"{BASE_URL}/api/predict_image",
                    files={"traffic_image": f},
                    data={"mode": mode},
                    headers=headers
                )
            passed = r.status_code == 200 and r.json().get("success") is True
            data = r.json() if passed else {}
            counts = data.get("counts", {})
            total_v = counts.get("total", 0)
            breakdown_sum = sum([
                counts.get("cars", 0),
                counts.get("buses", 0),
                counts.get("trucks", 0),
                counts.get("motorcycles", 0),
                counts.get("bicycles", 0),
                counts.get("vans", 0)
            ])
            correct_sum = total_v == breakdown_sum and total_v > 0
            record_test(
                "YOLO Detection",
                f"Inference Mode: {mode.upper()}",
                passed and correct_sum,
                f"Count={total_v}, BreakdownSum={breakdown_sum}, Model={data.get('analytics', {}).get('model')}"
            )

        # 3. Density Engine & Lane Occupancy
        with open(test_img_path, "rb") as f:
            r = s.post(
                f"{BASE_URL}/api/predict_image",
                files={"traffic_image": f},
                data={"mode": "balanced"},
                headers=headers
            )
        data = r.json() if r.status_code == 200 else {}
        density_obj = data.get("density", {})
        density_level = density_obj.get("level", "")
        occupancy_rate = density_obj.get("occupancy_rate", 0.0)

        valid_density = density_level in ["Low", "Medium", "High", "Very High"]
        record_test("Density Engine", "Density Recalculation", valid_density, f"Level: {density_level}, Congestion: {density_obj.get('congestion_pct')}%")
        
        valid_occupancy = occupancy_rate > 0.0
        record_test("Lane Occupancy", "Non-Zero Lane Occupancy", valid_occupancy, f"Lane Occupancy: {occupancy_rate}%")

    # 4. Standardized API Format
    with open(test_img_path, "rb") as f:
        r = s.post(f"{BASE_URL}/api/predict_image", files={"traffic_image": f}, headers=headers)
    resp_data = r.json() if r.status_code == 200 else {}
    has_keys = all(k in resp_data for k in ["success", "detections", "counts", "density", "analytics"])
    record_test("Backend API", "Consistent JSON API Contract", has_keys, f"Keys: {list(resp_data.keys())}")

    # 5. Dashboard Telemetry & Auto-Update
    telemetry_res = s.get(f"{BASE_URL}/api/telemetry/1", headers=headers)
    t_data = telemetry_res.json() if telemetry_res.status_code == 200 else {}
    record_test("Dashboard", "Live Telemetry Synchronization", telemetry_res.status_code == 200 and t_data.get("count", 0) > 0, f"Live Count: {t_data.get('count')}, Density: {t_data.get('density')}")

    # 6. Simulation Controls (Start, Pause, Resume, Reset)
    start_res = s.post(f"{BASE_URL}/api/simulation/control", json={"action": "start"}, headers=headers)
    record_test("Simulation", "Simulation Start", start_res.status_code == 200 and start_res.json().get("simulation", {}).get("running") is True, "Simulation Running")

    pause_res = s.post(f"{BASE_URL}/api/simulation/control", json={"action": "pause"}, headers=headers)
    record_test("Simulation", "Simulation Pause", pause_res.status_code == 200 and pause_res.json().get("simulation", {}).get("paused") is True, "Simulation Paused")

    resume_res = s.post(f"{BASE_URL}/api/simulation/control", json={"action": "resume"}, headers=headers)
    record_test("Simulation", "Simulation Resume", resume_res.status_code == 200 and resume_res.json().get("simulation", {}).get("paused") is False, "Simulation Resumed")

    step_res = s.post(f"{BASE_URL}/api/simulation/step", headers=headers)
    record_test("Simulation", "Simulation Clock Step", step_res.status_code == 200, "Clock Stepped 1s")

    reset_res = s.post(f"{BASE_URL}/api/simulation/control", json={"action": "reset"}, headers=headers)
    record_test("Simulation", "Simulation Reset", reset_res.status_code == 200 and reset_res.json().get("simulation", {}).get("running") is False, "Simulation Reset")

    # 7. Traffic Signals & Emergency Preemption
    lights_res = s.get(f"{BASE_URL}/api/simulation/traffic_lights")
    lights_ok = lights_res.status_code == 200 and "traffic_lights" in lights_res.json()
    record_test("Traffic Lights", "Adaptive Traffic Signals Query", lights_ok, f"Signals: {lights_res.json().get('traffic_lights', {}).get('signals') if lights_ok else 'None'}")

    emerg_res = s.post(f"{BASE_URL}/api/simulation/emergency", json={"vehicle_type": "Ambulance", "lane": "North"}, headers=headers)
    emerg_ok = emerg_res.status_code == 200 and emerg_res.json().get("simulation", {}).get("traffic_lights", {}).get("emergency_preemption") is True
    record_test("Emergency Preemption", "Emergency Wave Dispatch", emerg_ok, "North Signal Preempted to GREEN")

    # 8. MQTT & IoT Integration
    mqtt_dev_res = s.get(f"{BASE_URL}/api/iot/devices", headers=headers)
    record_test("MQTT & IoT", "IoT Device Query", mqtt_dev_res.status_code == 200, f"Devices count: {len(mqtt_dev_res.json().get('devices', []))}")

    # 9. Logging Verification
    log_exists = INFERENCE_LOG_FILE.exists()
    log_content = INFERENCE_LOG_FILE.read_text(encoding="utf-8") if log_exists else ""
    required_stages = [
        "model loaded", "image received", "preprocessing", "inference",
        "postprocessing", "density calculation", "dashboard update", "API response"
    ]
    all_logged = all(f"[{stage}]" in log_content for stage in required_stages)
    record_test("Logging", "Comprehensive logs/inference.log", log_exists and all_logged, f"Verified all 8 required pipeline stages in {INFERENCE_LOG_FILE.name}")

    # Save final report to JSON
    with open(REPORT_FILE, "w", encoding="utf-8") as rf:
        json.dump(report, rf, indent=2)

    print("=" * 65)
    print(f"  TOTAL TESTS: {report['summary']['total']} | PASSED: {report['summary']['passed']} | FAILED: {report['summary']['failed']}")
    print(f"  Report saved to: {REPORT_FILE}")
    print("=" * 65)

    if report["summary"]["failed"] > 0:
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
