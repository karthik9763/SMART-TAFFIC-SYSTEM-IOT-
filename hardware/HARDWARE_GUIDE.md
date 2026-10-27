# IoT Hardware Assembly & Flashing Guide

## 1. ESP32-CAM Video Streamer Setup

### Required Components
- **ESP32-CAM AI-Thinker Module**
- **FTDI USB-to-TTL Adapter** (set jumper to 3.3V or 5V as per module spec)
- **Female-to-Female Jumper Wires**
- **5V 2A DC Micro-USB Power Supply**

### Wiring Pinout Diagram (Flashing Mode)

| ESP32-CAM Pin | FTDI Adapter Pin | Description |
| :--- | :--- | :--- |
| **5V** | **VCC (5V)** | Power Input |
| **GND** | **GND** | Ground |
| **U0TX (GPIO 1)** | **RXD** | Transmit |
| **U0RX (GPIO 3)** | **TXD** | Receive |
| **GPIO 0** | **GND** | *Must connect to GND to enter Bootloader/Flashing mode* |

> [!IMPORTANT]
> After uploading code via Arduino IDE, **disconnect GPIO 0 from GND** and press the **RESET** button on the back of the ESP32-CAM to switch into Execution Mode.

---

## 2. Arduino IDE Configuration Steps
1. Open **Arduino IDE**.
2. Go to **File -> Preferences** and add the following URL to *Additional Boards Manager URLs*:
   `https://dl.espressif.com/dl/package_esp32_index.json`
3. Go to **Tools -> Board -> Boards Manager**, search for `esp32` by Espressif, and click **Install**.
4. Select **Tools -> Board -> AI Thinker ESP32-CAM**.
5. Set **PSRAM -> Enabled**.
6. Set **Flash Frequency -> 80MHz**.
7. Open `hardware/esp32_cam_streamer/esp32_cam_streamer.ino`.
8. Update `ssid` and `password` with your local Wi-Fi credentials.
9. Click **Upload**.

---

## 3. Integrating ESP32-CAM Stream with Flask Dashboard
1. Open the Serial Monitor at `115200 baud`.
2. Copy the IP address output by the ESP32-CAM, e.g., `http://192.168.1.100:81/stream`.
3. In the Smart Traffic Web Dashboard:
   - Navigate to **Settings -> Camera Endpoints**.
   - Update Camera #3 URL to `http://192.168.1.100:81/stream`.
   - Go to **Live Monitor** and select Camera #3 to view the real-time IoT video stream.

## 4. Simulating the ESP32 IR Counter with Wokwi & PlatformIO

The Wokwi simulation project is in `hardware/esp32_ir_counter`. It simulates an
ESP32 DevKit-C V4 with two debounced pushbuttons representing active-low IR beam sensors:
- **ENTRY Sensor**: GPIO 18 (internal pull-up enabled, button shorts to GND)
- **EXIT Sensor**: GPIO 19 (internal pull-up enabled, button shorts to GND)
- **Status LED**: GPIO 2 (driven through a 220Ω resistor, 250ms pulse on valid transit)

The firmware is fully non-blocking and automatically handles bidirectional traffic, sequence numbering, and telemetry over MQTT (defaults to `broker.hivemq.com:1883` for simulator compatibility).

### Build and Run with PlatformIO (Recommended)
1. Build the firmware from the project folder or root:
   ```powershell
   pio run -d hardware/esp32_ir_counter
   ```
   This generates `.pio/build/esp32dev/firmware.bin` and `.pio/build/esp32dev/firmware.elf`.
2. Open `hardware/esp32_ir_counter/diagram.json` in VS Code with the Wokwi extension.
3. Click the green **▶ Start Simulation** button (or press `F1` and run `Wokwi: Start Simulator`).
4. Click **ENTRY**, then **EXIT** to record a vehicle moving from A to B. Click **EXIT**, then **ENTRY** for B to A.

### Build with Arduino CLI (Alternative)
1. Install the Espressif ESP32 board core and libraries:
   ```powershell
   arduino-cli core update-index
   arduino-cli core install esp32:esp32
   arduino-cli lib install ArduinoJson PubSubClient
   ```
2. Compile the sketch:
   ```powershell
   arduino-cli compile --fqbn esp32:esp32:esp32 --output-dir hardware/esp32_ir_counter/build hardware/esp32_ir_counter
   ```

## 5. ESP32-CAM Wokwi project and MQTT

The camera project is in `hardware/esp32_cam_streamer`. Its Wokwi diagram
describes the ESP32-CAM board and virtual Wi-Fi, and its firmware/build files
are documented in that folder's README. Wokwi does not replace validating the
OV2640 sensor, image capture, or MJPEG stream on a physical ESP32-CAM.

The physical streamer exposes `http://<camera-ip>:81/stream` (MJPEG) and
`http://<camera-ip>/capture` (single JPEG). Copy its `secrets.example.h` to
`secrets.h` and configure broker/device values. MQTT devices publish to
`traffic/<device-id>/<event>` topics; the Flask bridge validates registered
device tokens before saving telemetry and events. See the root README for
running Mosquitto and the bridge.
