"""Forward authenticated ESP32 MQTT messages to the Flask REST API."""

import json
import logging
import os
import signal
import threading

import paho.mqtt.client as mqtt
import requests
from dotenv import load_dotenv


load_dotenv()
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger('traffic.mqtt')

API_BASE_URL = os.environ.get('MQTT_API_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')
BROKER_HOST = os.environ.get('MQTT_BROKER_HOST', '127.0.0.1')
BROKER_PORT = int(os.environ.get('MQTT_BROKER_PORT', '1883'))
BROKER_USERNAME = os.environ.get('MQTT_BROKER_USERNAME', '')
BROKER_PASSWORD = os.environ.get('MQTT_BROKER_PASSWORD', '')
CLIENT_ID = os.environ.get('MQTT_CLIENT_ID', 'smart-traffic-api-bridge')
STOP = threading.Event()

HTTP = requests.Session()
HTTP.headers.update({'Content-Type': 'application/json'})


def _handle_message(message):
    """Validate and relay a message; return False to retry transient errors."""
    topic_parts = message.topic.split('/')
    if len(topic_parts) != 3 or topic_parts[0] != 'traffic':
        logger.warning('Ignoring unexpected MQTT topic: %s', message.topic)
        return True

    device_id, suffix = topic_parts[1:]
    try:
        payload = json.loads(message.payload.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning('Ignoring invalid JSON on MQTT topic %s', message.topic)
        return True

    if not isinstance(payload, dict) or payload.get('device_id') != device_id:
        logger.warning('Ignoring malformed MQTT payload on %s', message.topic)
        return True

    device_token = payload.get('device_token')
    if not isinstance(device_token, str) or not device_token:
        logger.warning('Ignoring MQTT message without a device token: %s', message.topic)
        return True

    if suffix == 'status':
        endpoint = '/api/iot/telemetry'
        body = {key: value for key, value in payload.items() if key != 'device_token'}
    elif suffix in ('entry', 'exit', 'count', 'camera', 'alert'):
        endpoint = '/api/iot/mqtt/event'
        body = {
            'device_id': device_id,
            'device_token': device_token,
            'topic': message.topic,
            'payload': payload,
        }
    else:
        logger.warning('Ignoring unsupported MQTT topic: %s', message.topic)
        return True

    try:
        response = HTTP.post(
            API_BASE_URL + endpoint,
            json=body,
            headers={'Authorization': f'Bearer {device_token}'},
            timeout=5
        )
    except requests.RequestException:
        logger.exception('Could not forward MQTT message topic=%s', message.topic)
        return False
    if response.status_code not in (200, 201):
        logger.warning(
            'Flask API rejected MQTT message topic=%s status=%s body=%s',
            message.topic,
            response.status_code,
            response.text[:300]
        )
        return 400 <= response.status_code < 500
    logger.info('Persisted MQTT message topic=%s', message.topic)
    return True


def _on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        logger.error('MQTT broker connection failed: %s', reason_code)
        return
    client.subscribe('traffic/+/+', qos=1)
    logger.info('Connected to MQTT broker %s:%d', BROKER_HOST, BROKER_PORT)


def _on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    if reason_code.is_failure:
        logger.warning('Unexpected MQTT disconnect: %s', reason_code)


def _on_message(client, userdata, message):
    if _handle_message(message) and message.qos:
        result, _ = client.ack(message.mid, message.qos)
        if result != mqtt.MQTT_ERR_SUCCESS:
            logger.error('Could not acknowledge MQTT message topic=%s', message.topic)


def main():
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=CLIENT_ID,
        protocol=mqtt.MQTTv311
    )
    if BROKER_USERNAME:
        client.username_pw_set(BROKER_USERNAME, BROKER_PASSWORD)
    if os.environ.get('MQTT_TLS', 'false').lower() == 'true':
        client.tls_set()

    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.manual_ack_set(True)

    def request_stop(signum, frame):
        logger.info('Stopping MQTT bridge.')
        STOP.set()
        client.disconnect()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    logger.info('Connecting to MQTT broker %s:%d', BROKER_HOST, BROKER_PORT)
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()
    STOP.wait()
    client.loop_stop()


if __name__ == '__main__':
    main()
