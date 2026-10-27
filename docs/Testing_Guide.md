# Testing Guide

## Python checks

From the project root:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app.py database.py server tests
```

The API tests use an in-memory SQLite database and cover authenticated MQTT
event ingestion, secret redaction, and telemetry validation.

## React checks

```powershell
npm --prefix client install
npm --prefix client run build
```

Run the Flask server and open `/operations` after signing in to verify the
summary, traffic chart, device list, CSV download, prediction form, image
upload, and camera preview.

## MQTT integration

Start Mosquitto, the Flask service, and `python -m server.mqtt_bridge`.
Register a simulation device, configure its private firmware `secrets.h`,
then verify that the device heartbeat appears in the dashboard and that its
events are listed under Recent MQTT events. Invalid tokens must be rejected.

## Wokwi and physical hardware

Build the IR sketch with Arduino CLI, open `hardware/esp32_ir_counter` in
Wokwi, and press ENTRY then EXIT; repeat in reverse order. Check serial output,
vehicle totals, and LED behavior. Build the camera-event simulator using the
instructions in `hardware/esp32_cam_streamer/README.md`; press MOTION to test
the MQTT alert path. To validate MQTT, configure a broker reachable from the
Wokwi network. Flash the camera firmware to a physical AI-Thinker module to
test OV2640 initialization, `/capture`, `/stream`, and physical-camera MQTT
events. Wokwi does not substitute for testing the physical camera.

## Validation report

The automated test and build outcomes for a change are reported in the
associated engineering task. Hardware, broker, model-accuracy, and cloud
deployment results must be recorded from the actual target environment; they
cannot be inferred from source validation.
