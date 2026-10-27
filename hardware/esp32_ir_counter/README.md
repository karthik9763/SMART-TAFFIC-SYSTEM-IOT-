# ESP32 Two-Sensor IR Vehicle Counter

An intelligent, non-blocking ESP32-based bidirectional vehicle counting system with real-time MQTT telemetry, JSON payload generation, debounced active-low IR sensor emulation, and status LED feedback. Fully configured and tested for **PlatformIO**, **Wokwi Simulator**, **VS Code**, **Arduino CLI**, and **Arduino IDE**.

---

## 1. Project Overview & Architecture

### System Operation
- **Active-Low IR Sensors**: Simulated in Wokwi by pushbuttons `ENTRY` (GPIO 18) and `EXIT` (GPIO 19). Internal pull-ups hold inputs `HIGH`; a vehicle crossing pulls the pin `LOW`.
- **Bidirectional Transit Detection**:
  - `ENTRY` pressed then `EXIT` pressed within 3000 ms = Transit from **A to B** (`entry-to-exit`).
  - `EXIT` pressed then `ENTRY` pressed within 3000 ms = Transit from **B to A** (`exit-to-entry`).
  - Incomplete transit or timeout (> 3000 ms) automatically resets the state machine without counting.
  - Simultaneous presses on both sensors are rejected as ambient electrical/mechanical noise.
- **Visual Feedback**: GPIO 2 drives a status LED through a 220Ω resistor, pulsing `HIGH` for 250 ms upon every verified vehicle transit.
- **Non-Blocking Execution**: FreeRTOS-cooperative main loop never blocks with synchronous delays. WiFi and MQTT connection state machines handle reconnects asynchronously in the background.
- **Telemetry & Payloads**:
  - Events published to `traffic/<DEVICE_ID>/entry`, `traffic/<DEVICE_ID>/exit`, and `traffic/<DEVICE_ID>/count`.
  - Periodic telemetry status (uptime, sensor states, total counts, bidirectional tallies) published every 10 seconds to `traffic/<DEVICE_ID>/status`.
  - Payload formatting is fully compatible with both **ArduinoJson v6 and v7**.

---

## 2. Pinout & Hardware Specification

| ESP32 Pin | Function | Wokwi Part | Wiring Description |
| :--- | :--- | :--- | :--- |
| **GPIO 18** | Entry Sensor (IR) | `entry` pushbutton | Connected to Pin 2.l; Pin 1.l connected to GND |
| **GPIO 19** | Exit Sensor (IR) | `exit` pushbutton | Connected to Pin 2.l; Pin 1.l connected to GND |
| **GPIO 2** | Status LED | `status-led` | Connected through 220Ω resistor to Anode (A); Cathode (C) to GND |
| **GND** | System Ground | Common Ground | Common return for pushbuttons and LED cathode |
| **3.3V / 5V** | Power | ESP32 DevKit V4 | USB powered or external regulated 5V DC supply |

---

## 3. Quick Start: Wokwi Simulator in VS Code

1. Ensure the **Wokwi** VS Code extension is installed (`wokwi.wokwi-vscode`).
2. Open this directory or the root repository in VS Code.
3. Build the firmware binary using PlatformIO:
   ```powershell
   pio run -d hardware/esp32_ir_counter
   ```
4. Open `hardware/esp32_ir_counter/diagram.json` or press **F1** / **Ctrl+Shift+P** and select **Wokwi: Start Simulator**.
5. Click the green **▶ Start Simulation** button.
6. **Simulate a vehicle**:
   - Click **ENTRY**, then click **EXIT** to count a vehicle traveling Direction A → B.
   - Click **EXIT**, then click **ENTRY** to count a vehicle traveling Direction B → A.
   - Watch the serial monitor (115200 baud) for vehicle counts, sequence numbers, and MQTT status.

---

## 4. Building with PlatformIO

PlatformIO is the recommended build system. Configuration is stored in `platformio.ini`.

### Build Firmware
```powershell
# From hardware/esp32_ir_counter:
pio run

# From repository root:
pio run -d hardware/esp32_ir_counter
```

### Clean Build Output
```powershell
pio run -t clean
```

### Flash to Physical Board
```powershell
pio run -t upload
pio device monitor -b 115200
```

---

## 5. Building with Arduino CLI

```powershell
# Update core index and install ESP32 platform
arduino-cli core update-index
arduino-cli core install esp32:esp32

# Install library dependencies
arduino-cli lib install ArduinoJson PubSubClient

# Compile sketch to build folder
arduino-cli compile --fqbn esp32:esp32:esp32 --output-dir build hardware/esp32_ir_counter
```

---

## 6. Building with Arduino IDE

1. Open Arduino IDE.
2. In **File -> Preferences**, verify ESP32 board manager URL:
   `https://dl.espressif.com/dl/package_esp32_index.json`
3. In **Tools -> Board**, select **ESP32 Dev Module**.
4. In **Sketch -> Include Library -> Manage Libraries**, install:
   - `ArduinoJson` (v6 or v7)
   - `PubSubClient` (v2.8+)
5. Open `hardware/esp32_ir_counter/esp32_ir_counter.ino`.
6. Select your COM port and click **Upload**.

---

## 7. MQTT Configuration & Topics

The default configuration connects to the public HiveMQ broker (`broker.hivemq.com:1883`) for instant out-of-the-box Wokwi simulation without requiring local broker port forwarding.

### Configuration (`secrets.h`)
```c
#define WIFI_SSID "Wokwi-GUEST"
#define WIFI_PASSWORD ""
#define MQTT_HOST "broker.hivemq.com"
#define MQTT_PORT 1883
#define DEVICE_ID "wokwi-counter-01"
#define DEVICE_TOKEN "replace-with-token-from-device-registration"
```

### Topic Hierarchy
| Topic | Purpose | Payload Example |
| :--- | :--- | :--- |
| `traffic/wokwi-counter-01/entry` | Entry beam break event | `{"device_id":"...","vehicle_count":0,"sequence":1}` |
| `traffic/wokwi-counter-01/exit` | Exit beam break event | `{"device_id":"...","vehicle_count":0,"sequence":2}` |
| `traffic/wokwi-counter-01/count` | Vehicle count verified | `{"device_id":"...","vehicle_count":1,"sequence":3}` |
| `traffic/wokwi-counter-01/status` | Heartbeat & full telemetry | `{"device_id":"...","uptime_seconds":10,"vehicle_count":1,"direction_a_to_b":1,...}` |

---

## 8. Troubleshooting Guide

| Issue | Root Cause | Solution |
| :--- | :--- | :--- |
| **`firmware binary build/xxx.bin not found`** | `wokwi.toml` pointed to missing `build/` directory | Project converted to PlatformIO; `wokwi.toml` now points to `.pio/build/esp32dev/firmware.bin` |
| **`MQTT connection failed (rc=-2)`** | Simulator tried reaching unreachable LAN IP (`192.168.x.x`) | Updated `MQTT_HOST` to public broker `broker.hivemq.com` |
| **StaticJsonDocument compile warnings** | ArduinoJson v7 deprecates StaticJsonDocument | Code updated with `#if ARDUINOJSON_VERSION_MAJOR >= 7` dual compatibility |
| **Missed counts during network reconnect** | WiFi connect loop used blocking `delay(250)` for 15s | Converted to non-blocking `maintainWiFi()` state machine |
| **Frequent broker disconnections** | Duplicate client IDs collided on public broker | Firmware now formats unique client ID `wokwi-counter-01-XXXX` based on ESP32 eFuse MAC |
