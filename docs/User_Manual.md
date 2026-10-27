# Smart Traffic System — User & Administrator Manual

## 1. Quick Installation & Launch Guide

### Prerequisites
- Operating System: Windows 10/11, macOS, or Linux.
- Python 3.10 or higher.
- Web Browser: Google Chrome, Microsoft Edge, or Mozilla Firefox.

### Step-by-Step Execution
1. Open a terminal / command prompt in the project root directory `c:\Users\Karthik\OneDrive\Desktop\Dnn`.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env`, then set a unique `SECRET_KEY` and the
   bootstrap administrator values. Configure these environment values before
   starting the server.
4. Run the starter script:
   ```bash
   python run.py
   ```
5. Open your web browser and navigate to:
   **`http://127.0.0.1:5000`**
6. To use the React operations dashboard, build it with
   `npm --prefix client install` and `npm --prefix client run build`, sign in,
   then open **React Operations** from the sidebar.

---

## 2. Administrator and Operator Accounts

There are no built-in default credentials. When
`BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_EMAIL`, and
`BOOTSTRAP_ADMIN_PASSWORD` are set before the first launch, the application
creates that administrator account. Use its credentials to sign in and add
operator accounts. Keep the bootstrap password private and change the
environment value after initial setup.

---

## 3. Operations Guide

### 3.1 Live Monitoring
- Go to **Live Monitor** in the left sidebar.
- Use the camera selector dropdown to switch between:
  - Demo Traffic Video (Default offline mode)
  - Expressway Toll Plaza (Simulated stream)
  - ESP32-CAM IoT Feed (`http://192.168.1.100:81/stream`)
  - USB Webcam (Device Index 0)
- View real-time bounding boxes around detected vehicles and live count counters.

### 3.2 Predict from an available image
- Open **React Operations** from the sidebar after signing in.
- In **Predict from an image**, choose an available project image and click
  **Predict selected image**. The annotated result, estimated density,
  vehicle breakdown, occupancy, inference time, and detector method appear
  below the form.
- To analyze your own image instead, choose a JPEG or PNG and click
  **Predict uploaded image**.
- The bundled upload examples in the current project are synthetic colored
  block samples rather than real road-camera photographs. For meaningful
  traffic predictions, upload a clear image containing real vehicles.

### 3.3 Report Export
- Go to **Reports**.
- Export saved traffic data as CSV.
- Use the printable report view to print a report. PDF download generation
  is not currently implemented.

### 3.4 Alert Management
- Go to **Alerts & System Logs**.
- Review active heavy congestion alerts.
- Click **Dismiss** to acknowledge an alert.

### 3.5 MQTT devices and Wokwi
- Register each ESP32 in **IoT Devices** and copy its one-time device token.
- Keep Wi-Fi, broker, device ID, mode, and token in an untracked `secrets.h`.
- Run Mosquitto and `python -m server.mqtt_bridge` for MQTT ingestion.
- Open `hardware/esp32_ir_counter` in Wokwi to simulate two IR sensors.
- The camera Wokwi project simulates camera-status and motion-alert MQTT
  events; image capture and MJPEG streaming require a physical ESP32-CAM.
- See [API Documentation](./API_Documentation.md) and the hardware READMEs for
  payload, pinout, and simulator details.
