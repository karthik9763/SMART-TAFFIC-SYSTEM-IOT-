"""
Automated firmware build & sync script for Wokwi simulation.
Builds both esp32_ir_counter and esp32_cam_streamer sketches with PlatformIO
and copies artifacts to all expected Wokwi locations.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def run_pio_build(project_dir):
    print(f"[Build] Building PlatformIO project at: {project_dir}")
    python_exe = sys.executable
    cmd = [python_exe, "-m", "platformio", "run", "-d", str(project_dir)]
    res = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[Error] Build failed:\n{res.stderr or res.stdout}")
        return False
    print("[Build] Build succeeded!")
    return True

def sync_artifacts():
    print("[Sync] Synchronizing firmware binaries across Wokwi paths...")
    
    # Check external build dir for cam streamer
    cam_src = Path("C:/Users/Karthik/.pio_build/esp32_cam/esp32dev")
    if cam_src.exists():
        cam_build = BASE_DIR / "hardware" / "esp32_cam_streamer" / "build"
        cam_build.mkdir(parents=True, exist_ok=True)
        for target in ["wokwi.ino.bin", "firmware.bin"]:
            shutil.copy2(cam_src / "firmware.bin", cam_build / target)
        for target in ["wokwi.ino.elf", "firmware.elf"]:
            shutil.copy2(cam_src / "firmware.elf", cam_build / target)
        if (cam_src / "bootloader.bin").exists():
            shutil.copy2(cam_src / "bootloader.bin", cam_build / "bootloader.bin")
        if (cam_src / "partitions.bin").exists():
            shutil.copy2(cam_src / "partitions.bin", cam_build / "partitions.bin")

        # Copy to root build dir as fallback
        root_build = BASE_DIR / "build"
        root_build.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cam_src / "firmware.bin", root_build / "wokwi.ino.bin")
        shutil.copy2(cam_src / "firmware.elf", root_build / "wokwi.ino.elf")

    # Sync IR counter build
    ir_src = BASE_DIR / "hardware" / "esp32_ir_counter" / ".pio" / "build" / "esp32dev"
    if ir_src.exists():
        ir_build = BASE_DIR / "hardware" / "esp32_ir_counter" / "build"
        ir_build.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ir_src / "firmware.bin", ir_build / "wokwi.ino.bin")
        shutil.copy2(ir_src / "firmware.bin", ir_build / "firmware.bin")
        shutil.copy2(ir_src / "firmware.elf", ir_build / "wokwi.ino.elf")
        shutil.copy2(ir_src / "firmware.elf", ir_build / "firmware.elf")

    print("[Sync] Completed synchronization successfully.")

if __name__ == "__main__":
    sync_artifacts()
