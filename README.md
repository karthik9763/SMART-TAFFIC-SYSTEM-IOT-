# Smart Traffic Density Prediction and Monitoring

An existing Flask traffic-monitoring application extended with an ESP32 MQTT
bridge, Wokwi-ready IR counter, ESP32-CAM firmware, and a React operations
dashboard. The original Flask dashboard and REST API remain available.

## Current capabilities

- Flask web application with password-hashed accounts, roles, and CSRF
  protection for browser POST requests.
- SQLite persistence through Flask-SQLAlchemy; database URLs can be changed
  with `DATABASE_URL` for a compatible SQLAlchemy database.
- OpenCV/YOLO vehicle detection for uploaded traffic images and rule-based or
  explicitly trusted density classification.
- Traffic history, device registration, telemetry, alerts, and CSV export.
- React/Vite operations UI at `/operations` for authenticated dashboard
  statistics, devices, recent MQTT events, density estimation, image analysis,
  CSV export, and a configurable MJPEG preview.
- ESP32 IR counter (GPIO 18/19, status LED GPIO 2) with debouncing,
  bidirectional crossing detection, MQTT events, and telemetry.
- ESP32-CAM MJPEG stream, JPEG capture endpoint, camera announcements, and
  heuristic motion notices over MQTT.
- Wokwi circuit/configuration files for the IR counter and a camera-event
  simulator using a supported ESP32 DevKit.

Features requiring infrastructure not supplied here (for example, a Google
Maps API key, road coordinates, a routing provider, cloud deployment
credentials, or a real camera scene) are not represented as live features.
Device locations currently use text identifiers rather than geospatial
coordinates.

## Run the Flask application

Python 3.10 or newer is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set a unique `SECRET_KEY`, bootstrap administrator password, and other local
settings in `.env`. Do not commit `.env`. The app loads environment variables
from the process; use your shell or deployment environment to export them.

```powershell
python run.py
```

Open `http://127.0.0.1:5000`. The Flask-rendered pages remain available. After
building the React client, sign in and open **React Operations** from the
sidebar or visit `/operations`.

The React client is also available separately for development. With Flask
running, use a browser on the same host to sign in to Flask first, then:

```powershell
npm --prefix client install
npm --prefix client run dev
```

Open the Vite URL shown in the terminal. For production-style Flask serving,
build the client instead:

```powershell
npm --prefix client run build
```

The build is written to `static/react`, which is intentionally ignored by Git.
Rebuild it when React source changes.

## Run MQTT locally

Start a Mosquitto broker on a trusted local network, set
`MQTT_BROKER_HOST`, `MQTT_BROKER_PORT`, and optional credentials in the Flask
environment, then start the bridge in a second terminal:

```powershell
docker run --rm -it --entrypoint sh -v "${PWD}\deployment\mosquitto:/mosquitto/config" eclipse-mosquitto:2 -c "mosquitto_passwd -c /mosquitto/config/passwords smart-traffic-bridge && mosquitto_passwd /mosquitto/config/passwords wokwi-counter-01 && mosquitto_passwd /mosquitto/config/passwords wokwi-camera-01 && chmod 644 /mosquitto/config/passwords"
docker compose up -d mosquitto
python -m server.mqtt_bridge
```

The bridge subscribes to `traffic/+/+` and forwards authenticated device
messages to the existing Flask telemetry endpoint. Start Flask before the
bridge. Use TLS
and broker authentication for any network beyond a trusted local development
environment. Set `MQTT_BROKER_USERNAME=smart-traffic-bridge` and its password
in `.env`; set the matching per-device MQTT usernames/passwords in the private
`secrets.h` files. The broker ACL permits the bridge to read events and each
device to publish only to its own topic (the MQTT username must match the
device ID). Never publish device tokens to a public broker.

Register each device from the authenticated **IoT Devices** page. Copy its
one-time token into that device's local `secrets.h` (copy the matching
`secrets.example.h` first). Keep the local file private; `.gitignore` excludes
it.

## Wokwi and ESP32

Each hardware folder contains its own `README.md`, `diagram.json`,
`wokwi.toml`, and `libraries.txt`. Follow the hardware-specific build steps:

- [ESP32 IR counter](hardware/esp32_ir_counter/README.md)
- [ESP32-CAM streamer and Wokwi camera-event simulator](hardware/esp32_cam_streamer/README.md)
- [Hardware assembly and flashing guide](hardware/HARDWARE_GUIDE.md)

Wokwi can exercise the IR counter logic using the entry/exit buttons. Use the
network gateway or a broker reachable from the simulator to test MQTT. The
ESP32-CAM camera sensor and live stream still require physical hardware.

## API and project documentation

- [REST API and MQTT topic contract](docs/API_Documentation.md)
- [Deployment and configuration](docs/Deployment_Guide.md)
- [Testing guide and current validation](docs/Testing_Guide.md)
- [Software requirements](docs/SRS_Document.md)
- [Data-flow and UML diagrams](docs/Diagrams_UML_DFD.md)
- [User manual](docs/User_Manual.md)
- [Hardware guide](hardware/HARDWARE_GUIDE.md)

## Known scope boundaries

The project does not include a production-hosted broker, a Google Maps
credential, verified road coordinates/emergency routing, a live accident
classifier, or cloud account provisioning. The ESP32-CAM motion alert is a
change-detection heuristic; it is not a trained incident detector. Model
accuracy and latency depend on the supplied weights and hardware.
