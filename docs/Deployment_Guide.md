# Deployment and Configuration Guide

## Local deployment

1. Install Python dependencies with `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and configure a unique secret key and
   administrator credentials.
3. Build the browser client using `npm --prefix client install` and
   `npm --prefix client run build`.
4. Run the Flask application with `python run.py`.
5. Optionally create a Mosquitto password file and start the local broker:
   ```powershell
   docker run --rm -it --entrypoint sh -v "${PWD}\deployment\mosquitto:/mosquitto/config" eclipse-mosquitto:2 -c "mosquitto_passwd -c /mosquitto/config/passwords smart-traffic-bridge && mosquitto_passwd /mosquitto/config/passwords wokwi-counter-01 && mosquitto_passwd /mosquitto/config/passwords wokwi-camera-01 && chmod 644 /mosquitto/config/passwords"
   docker compose up -d mosquitto
   ```
   Configure the bridge password in `.env` and each per-device password in
   `secrets.h`. The broker ACL requires a device MQTT username to match its
   registered device ID.
6. Run `python -m server.mqtt_bridge`.
7. Register each ESP32 device in the authenticated IoT Devices page and place
   its token in an untracked local `secrets.h`.

The Flask service must be reachable from the MQTT bridge at
`MQTT_API_BASE_URL`. Physical ESP32 devices must be able to reach the broker
address in their own `secrets.h`; `127.0.0.1` refers to the device itself, not
the developer's computer. Wokwi uses virtual networking and needs an
appropriate Wokwi network gateway for a host-local broker.

## Environment variables

See `.env.example` for the complete development template. Important values:

- `SECRET_KEY`: required unique random signing key in production.
- `DATABASE_URL`: SQLAlchemy URL; SQLite is the local default.
- `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_EMAIL`,
  `BOOTSTRAP_ADMIN_PASSWORD`: optional one-time bootstrap administrator.
- `MQTT_BROKER_HOST`, `MQTT_BROKER_PORT`: broker reachable by the bridge.
- `MQTT_BROKER_USERNAME`, `MQTT_BROKER_PASSWORD`: broker credentials.
- `MQTT_TLS`: set to `true` to enable broker TLS verification.
- `MQTT_API_BASE_URL`: Flask API address reachable by the bridge.

## Production considerations

Do not run Flask's development server with debug mode on the public internet.
Deploy behind a production WSGI server and TLS-terminating reverse proxy,
restrict database and broker network access, provision secrets through the
hosting platform, and use database backups and schema migrations. SQLite is
appropriate for local/single-process use; concurrent production workloads
should use a managed database and a migration strategy.
PostgreSQL and MySQL drivers are included; use SQLAlchemy URLs such as
`postgresql+psycopg://...` or `mysql+pymysql://...`. Existing deployments
should validate schema migrations before switching database engines.

Cloud deployment to Render, Railway, or Vercel requires service-specific
configuration and credentials that are not included in this repository.
Vercel does not host this Flask/SQLite application as a durable database
service without an external database. Google Maps and emergency routing also
require coordinates and an API/provider configuration; they are not enabled
by this project configuration.
