# ESP32-CAM streamer

The ESP32-CAM firmware starts an MJPEG stream at
`http://<camera-ip>:81/stream` and a single JPEG capture endpoint at
`http://<camera-ip>/capture`. It announces the stream URL and publishes
possible-motion alerts to `traffic/<DEVICE_ID>/camera` and
`traffic/<DEVICE_ID>/alert`.

The motion notice is a lightweight change-detection heuristic over sampled
JPEG bytes, not a trained accident detector. Use the Flask image/video
detector for vehicle classification. Wokwi does not currently provide an
ESP32-CAM/OV2640 target. The Wokwi project therefore runs a separate ESP32
DevKit camera-event simulator: pressing MOTION publishes a simulated motion
event, and the LED shows the simulated motion input. It does
not produce images or a live MJPEG stream. Validate OV2640 capture and
streaming on a physical module.

## Build and flash

Install the Espressif ESP32 core and the libraries in `libraries.txt`. Copy
`secrets.example.h` to `secrets.h`, then configure Wi-Fi, MQTT broker, and
device registration values. Build from this directory:

```powershell
arduino-cli core update-index
arduino-cli core install esp32:esp32
arduino-cli lib install ArduinoJson PubSubClient
arduino-cli compile --fqbn esp32:esp32:esp32cam --output-dir build .
```

The serial monitor uses 115200 baud. Connect GPIO 0 to GND only while flashing;
disconnect it and reset the board to run the camera. For a physical device,
set `DEVICE_MODE` to `physical` in `secrets.h` and register the matching
device in the dashboard.

## Wokwi

Install the same ArduinoJson and PubSubClient libraries. From this directory,
build the simulator sketch (not the physical camera firmware):

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32 --output-dir build wokwi
```

For broker-connected simulation, copy `wokwi/secrets.example.h` to
`wokwi/secrets.h` and configure the registered device token there.
Open this directory in Wokwi or VS Code with the Wokwi extension and start
the simulator. `wokwi.toml` points to the simulated firmware. Press MOTION to
test the event path. To test MQTT against Flask, register the simulator's
device ID and token in `wokwi/secrets.h`. Wokwi uses virtual Wi-Fi; the broker
must be reachable through a Wokwi network gateway or from its virtual network.
The simulator cannot address the host computer via `localhost`.
