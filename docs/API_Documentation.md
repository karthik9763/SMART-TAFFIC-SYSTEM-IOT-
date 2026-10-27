# REST API and MQTT Contract

All browser dashboard endpoints use the existing Flask session. Browser POST
requests require `X-CSRF-Token` (or a form `csrf_token`) obtained from
`GET /api/auth/session`. Device endpoints authenticate with the one-time token
created when an administrator registers a device.

## Browser endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/auth/session` | Current user and CSRF token |
| GET | `/api/dashboard/summary` | Vehicle, density, camera, device, and alert totals |
| GET | `/api/traffic_data` | Recent persisted traffic history |
| GET | `/api/iot/devices` | Registered device status and counts |
| GET | `/api/iot/mqtt/events` | Latest 50 stored device events |
| POST | `/api/predict` | Rule-based or explicitly trusted density estimate |
| POST | `/api/predict_image` | Detect and classify an uploaded traffic image |
| GET | `/api/sample-images` | List available original project sample images |
| POST | `/api/sample-images/<filename>/predict` | Run the image detector on a selected project sample |
| GET | `/api/reports/traffic.csv` | Export traffic, prediction, and telemetry records |

## Device registration and telemetry

An administrator registers a device with `POST /api/iot/devices`. The response
contains a one-time `device_token`; store it in a private device configuration
file. Device mode must be `simulation` or `physical` and match the firmware
payload.

`POST /api/iot/telemetry` accepts a JSON body with `device_id`, `sequence`,
`uptime_seconds`, cumulative `vehicle_count`, cumulative directional counts,
boolean `sensor_a` and `sensor_b`, `mode`, and `firmware_version`. Supply the
device token as a Bearer authorization value. Sequences, counters, device
mode, rate, and token are validated before persistence.

## MQTT topics

Topic shape is `traffic/<device_id>/<event>`, with event one of `entry`,
`exit`, `count`, `status`, `camera`, or `alert`. JSON payloads include
`device_id` and `device_token`. A `status` payload follows the telemetry
contract above. Other event payloads are stored after device-token validation;
the token is removed from the stored event body.

The bridge subscribes to `traffic/+/+`. Status messages are submitted to
`POST /api/iot/telemetry`; entry, exit, count, camera, and alert messages go
to `POST /api/iot/mqtt/event`. The event endpoint only accepts topics whose
device id matches the registered sender. Allowed alert types are Heavy
Traffic, Camera Offline, Accident, Road Block, and Motion Detected.

MQTT is an optional transport. For deployments on untrusted networks, enable
TLS and broker ACLs so devices can publish only under their own device topic.
The device token is application-level authentication and must not be sent
through an unauthenticated public broker.
