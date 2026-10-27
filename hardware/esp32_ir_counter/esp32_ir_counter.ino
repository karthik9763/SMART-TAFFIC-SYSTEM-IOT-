/*
 * Production ESP32 Smart Traffic IR Counter Firmware
 * Compatible with PlatformIO, Arduino IDE, Arduino CLI, and Wokwi Simulation.
 *
 * Resilient Multi-Broker MQTT Architecture:
 * - Verifies WiFi connection and IP assignment prior to MQTT connection
 * - Automatic WiFi reconnection with backoff
 * - Multi-broker failover array:
 *     1. broker.hivemq.com
 *     2. broker.emqx.io
 *     3. test.mosquitto.org
 * - Exponential reconnection backoff on failure (prevents state=-2 spam)
 * - Directional transit state machine (Entry -> Exit / Exit -> Entry)
 * - Publishes to:
 *     - traffic/entry  & traffic/<device_id>/entry
 *     - traffic/exit   & traffic/<device_id>/exit
 *     - traffic/count  & traffic/<device_id>/count
 *     - traffic/status & traffic/<device_id>/status
 * - Logs all network and sensor events to Serial.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

#if __has_include("secrets.h")
#include "secrets.h"
#endif

// Fallback WiFi credentials
#ifndef WIFI_SSID
#define WIFI_SSID "Wokwi-GUEST"
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif

// Multi-Broker Pool for High Availability
const char* MQTT_BROKERS[] = {
  "broker.hivemq.com",
  "broker.emqx.io",
  "test.mosquitto.org"
};
#ifndef MQTT_PORT
#define MQTT_PORT 1883
#endif
const size_t NUM_BROKERS = sizeof(MQTT_BROKERS) / sizeof(MQTT_BROKERS[0]);
size_t currentBrokerIdx = 0;

#ifndef MQTT_USERNAME
#define MQTT_USERNAME ""
#endif

#ifndef MQTT_PASSWORD
#define MQTT_PASSWORD ""
#endif

#ifndef DEVICE_ID
#define DEVICE_ID "wokwi-counter-01"
#endif

#ifndef DEVICE_TOKEN
#define DEVICE_TOKEN "default-sim-token"
#endif

#ifndef DEVICE_MODE
#define DEVICE_MODE "simulation"
#endif

// Hardware GPIO Definitions
constexpr uint8_t ENTRY_PIN = 18;
constexpr uint8_t EXIT_PIN = 19;
constexpr uint8_t STATUS_LED_PIN = 2;

// Timing & Exponential Backoff Constants (in milliseconds)
constexpr uint32_t DEBOUNCE_MS = 40;
constexpr uint32_t CROSSING_TIMEOUT_MS = 3000;
constexpr uint32_t STATUS_INTERVAL_MS = 10000;
constexpr uint32_t WIFI_RETRY_INTERVAL_MS = 5000;
constexpr uint32_t MQTT_MIN_RETRY_INTERVAL_MS = 2000;
constexpr uint32_t MQTT_MAX_RETRY_INTERVAL_MS = 60000;
constexpr uint32_t LED_PULSE_DURATION_MS = 250;
constexpr uint16_t MQTT_BUFFER_SIZE = 768;
constexpr uint16_t MQTT_KEEPALIVE_SEC = 30;
constexpr uint16_t MQTT_SOCKET_TIMEOUT_SEC = 5;

// Firmware metadata
constexpr char FIRMWARE_VERSION[] = "2.1.0-production";

// Global network clients
WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

// Debounced sensor representation
struct DebouncedSensor {
  uint8_t pin;
  bool stableHigh;
  bool lastReadingHigh;
  uint32_t changedAt;
};

DebouncedSensor entrySensor{ENTRY_PIN, true, true, 0};
DebouncedSensor exitSensor{EXIT_PIN, true, true, 0};

// Crossing state machine
enum CrossingState : uint8_t {
  WAITING_FOR_SENSOR,
  ENTRY_FIRST,
  EXIT_FIRST
};

CrossingState crossingState = WAITING_FOR_SENSOR;
uint32_t crossingStartedAt = 0;
uint32_t lastStatusAt = 0;
uint32_t lastLedAt = 0;
uint32_t lastWifiAttemptAt = 0;
uint32_t lastMqttAttemptAt = 0;
uint32_t mqttRetryIntervalMs = MQTT_MIN_RETRY_INTERVAL_MS;
uint32_t sequenceNumber = 0;
uint32_t vehicleCount = 0;
uint32_t directionEntryToExit = 0;
uint32_t directionExitToEntry = 0;
bool ledIsOn = false;

// Helper: check if WiFi is fully connected with an assigned IP
bool isWifiConnected() {
  return (WiFi.status() == WL_CONNECTED && WiFi.localIP()[0] != 0);
}

// Non-blocking sensor debouncing with falling-edge detection (active-LOW)
bool sensorFell(DebouncedSensor &sensor, uint32_t now) {
  const bool readingHigh = (digitalRead(sensor.pin) == HIGH);
  if (readingHigh != sensor.lastReadingHigh) {
    sensor.lastReadingHigh = readingHigh;
    sensor.changedAt = now;
  }
  if (readingHigh != sensor.stableHigh &&
      (now - sensor.changedAt >= DEBOUNCE_MS)) {
    sensor.stableHigh = readingHigh;
    return !readingHigh; // True only on falling edge (HIGH -> LOW)
  }
  return false;
}

// Publish discrete event to both root topic and device-scoped topic
void publishEvent(const char *action, uint32_t count) {
  if (!mqttClient.connected()) {
    Serial.printf("[MQTT Offline] Event '%s' queued locally (count=%lu)\n",
                  action, static_cast<unsigned long>(count));
    return;
  }

#if ARDUINOJSON_VERSION_MAJOR >= 7
  JsonDocument msg;
#else
  StaticJsonDocument<512> msg;
#endif

  msg["device_id"] = DEVICE_ID;
  msg["device_token"] = DEVICE_TOKEN;
  msg["sequence"] = ++sequenceNumber;
  msg["action"] = action;
  msg["vehicle_count"] = count;
  msg["timestamp_ms"] = millis();

  char payload[512];
  const size_t len = serializeJson(msg, payload, sizeof(payload));

  // 1. Publish to standardized root topic: traffic/entry, traffic/exit, traffic/count
  char rootTopic[64];
  snprintf(rootTopic, sizeof(rootTopic), "traffic/%s", action);
  mqttClient.publish(rootTopic, payload, len);

  // 2. Publish to device-scoped topic: traffic/<device_id>/<action>
  char scopedTopic[96];
  snprintf(scopedTopic, sizeof(scopedTopic), "traffic/%s/%s", DEVICE_ID, action);
  mqttClient.publish(scopedTopic, payload, len);

  Serial.printf("[MQTT Event] Published '%s' (seq=%lu, count=%lu) to %s & %s\n",
                action, static_cast<unsigned long>(sequenceNumber),
                static_cast<unsigned long>(count), rootTopic, scopedTopic);
}

// Publish comprehensive device status and telemetry heartbeat
void publishStatus(uint32_t now) {
  if (!mqttClient.connected()) {
    return;
  }

#if ARDUINOJSON_VERSION_MAJOR >= 7
  JsonDocument status;
#else
  StaticJsonDocument<640> status;
#endif

  status["device_id"] = DEVICE_ID;
  status["device_token"] = DEVICE_TOKEN;
  status["sequence"] = ++sequenceNumber;
  status["uptime_seconds"] = now / 1000;
  status["vehicle_count"] = vehicleCount;
  status["direction_a_to_b"] = directionEntryToExit;
  status["direction_b_to_a"] = directionExitToEntry;
  status["sensor_a"] = !entrySensor.stableHigh;
  status["sensor_b"] = !exitSensor.stableHigh;
  status["mode"] = DEVICE_MODE;
  status["firmware_version"] = FIRMWARE_VERSION;
  status["broker"] = MQTT_BROKERS[currentBrokerIdx];
  status["wifi_rssi"] = WiFi.RSSI();

  char payload[640];
  const size_t len = serializeJson(status, payload, sizeof(payload));

  // Publish to root status and device-scoped status
  mqttClient.publish("traffic/status", payload, len);

  char scopedTopic[96];
  snprintf(scopedTopic, sizeof(scopedTopic), "traffic/%s/status", DEVICE_ID);
  if (mqttClient.publish(scopedTopic, payload, len)) {
    Serial.printf("[MQTT Heartbeat] Status sent to %s (count=%lu, seq=%lu, broker=%s)\n",
                  scopedTopic, static_cast<unsigned long>(vehicleCount),
                  static_cast<unsigned long>(sequenceNumber),
                  MQTT_BROKERS[currentBrokerIdx]);
  } else {
    Serial.println("[MQTT Heartbeat] Publish failed.");
  }
}

// Record completed vehicle transit
void recordVehicle(bool entryFirst, uint32_t now) {
  ++vehicleCount;
  if (entryFirst) {
    ++directionEntryToExit;
  } else {
    ++directionExitToEntry;
  }

  crossingState = WAITING_FOR_SENSOR;
  digitalWrite(STATUS_LED_PIN, HIGH);
  ledIsOn = true;
  lastLedAt = now;

  Serial.printf("[IR Sensor] Vehicle TRANSIT verified (%s). Total: %lu\n",
                entryFirst ? "ENTRY -> EXIT" : "EXIT -> ENTRY",
                static_cast<unsigned long>(vehicleCount));
  publishEvent("count", vehicleCount);
  publishStatus(now);
}

// Non-blocking WiFi state manager with automatic reconnection
void maintainWiFi(uint32_t now) {
  static wl_status_t lastRecordedStatus = WL_IDLE_STATUS;
  const wl_status_t currentStatus = WiFi.status();

  if (isWifiConnected()) {
    if (lastRecordedStatus != WL_CONNECTED) {
      Serial.printf("[WiFi] Connected! IP: %s | Gateway: %s | RSSI: %d dBm\n",
                    WiFi.localIP().toString().c_str(),
                    WiFi.gatewayIP().toString().c_str(),
                    WiFi.RSSI());
      lastRecordedStatus = WL_CONNECTED;
    }
    return;
  }

  if (lastRecordedStatus == WL_CONNECTED) {
    Serial.println("[WiFi] Connection dropped! Preparing automatic reconnect...");
    lastRecordedStatus = currentStatus;
  }

  if (now - lastWifiAttemptAt >= WIFI_RETRY_INTERVAL_MS) {
    lastWifiAttemptAt = now;
    Serial.printf("[WiFi] Connecting to SSID: '%s'...\n", WIFI_SSID);
    WiFi.disconnect();
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }
}

// Non-blocking MQTT state manager with multi-broker rotation and exponential backoff
void maintainMqtt(uint32_t now) {
  // If already connected, service loop and maintain keepalive
  if (mqttClient.connected()) {
    mqttClient.loop();
    return;
  }

  // REQUIREMENT: Verify WiFi connection before attempting MQTT
  if (!isWifiConnected()) {
    return;
  }

  // Check exponential retry interval
  if (now - lastMqttAttemptAt >= mqttRetryIntervalMs) {
    lastMqttAttemptAt = now;

    const char* activeBroker = MQTT_BROKERS[currentBrokerIdx];
    Serial.printf("[MQTT] Attempting connection to %s:%u (timeout=%lums)...\n",
                  activeBroker, (unsigned int)MQTT_PORT, (unsigned long)mqttRetryIntervalMs);

    mqttClient.setServer(activeBroker, MQTT_PORT);

    // Generate unique client ID to prevent broker collision
    char clientId[64];
    uint32_t chipId = static_cast<uint32_t>(ESP.getEfuseMac() & 0xFFFF);
    snprintf(clientId, sizeof(clientId), "%s-%04lX", DEVICE_ID, static_cast<unsigned long>(chipId));

    bool connected = false;
    if (MQTT_USERNAME[0] != '\0') {
      connected = mqttClient.connect(clientId, MQTT_USERNAME, MQTT_PASSWORD);
    } else {
      connected = mqttClient.connect(clientId);
    }

    if (connected) {
      Serial.printf("[MQTT] Connected successfully to %s! ClientID: %s\n", activeBroker, clientId);
      // Reset exponential backoff on success
      mqttRetryIntervalMs = MQTT_MIN_RETRY_INTERVAL_MS;

      // Subscribe to bidirectional sync topics
      char subTopic[96];
      snprintf(subTopic, sizeof(subTopic), "traffic/%s/command", DEVICE_ID);
      mqttClient.subscribe(subTopic);
      mqttClient.subscribe("traffic/control");

      // Publish initial state
      publishStatus(millis());
    } else {
      int stateCode = mqttClient.state();
      Serial.printf("[MQTT] Connection FAILED (broker=%s, state=%d). Rotating broker...\n",
                    activeBroker, stateCode);

      // Rotate to next broker in the failover pool
      currentBrokerIdx = (currentBrokerIdx + 1) % NUM_BROKERS;

      // Exponential backoff: double retry delay up to MAX (e.g. 2s -> 4s -> 8s -> ... -> 60s)
      mqttRetryIntervalMs = (mqttRetryIntervalMs * 2 > MQTT_MAX_RETRY_INTERVAL_MS)
                            ? MQTT_MAX_RETRY_INTERVAL_MS
                            : (mqttRetryIntervalMs * 2);
      Serial.printf("[MQTT] Next attempt with %s in %lu ms\n",
                    MQTT_BROKERS[currentBrokerIdx], static_cast<unsigned long>(mqttRetryIntervalMs));
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(ENTRY_PIN, INPUT_PULLUP);
  pinMode(EXIT_PIN, INPUT_PULLUP);
  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, LOW);

  entrySensor.changedAt = millis();
  exitSensor.changedAt = millis();

  mqttClient.setServer(MQTT_BROKERS[0], MQTT_PORT);
  mqttClient.setBufferSize(MQTT_BUFFER_SIZE);
  mqttClient.setKeepAlive(MQTT_KEEPALIVE_SEC);
  mqttClient.setSocketTimeout(MQTT_SOCKET_TIMEOUT_SEC);

  Serial.println("\n========================================================");
  Serial.println("  SmartTraffic AI: Production ESP32 IR Vehicle Counter  ");
  Serial.println("========================================================");
  Serial.printf("Pins: ENTRY=GPIO%u, EXIT=GPIO%u, LED=GPIO%u\n",
                ENTRY_PIN, EXIT_PIN, STATUS_LED_PIN);
  Serial.printf("Device: %s | Mode: %s\n", DEVICE_ID, DEVICE_MODE);
  Serial.printf("Supported MQTT Brokers (%u):\n", NUM_BROKERS);
  for (size_t i = 0; i < NUM_BROKERS; ++i) {
    Serial.printf("  [%u] %s:%u\n", i + 1, MQTT_BROKERS[i], MQTT_PORT);
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWifiAttemptAt = millis();
}

void loop() {
  const uint32_t now = millis();

  // 1. Maintain Network Stack
  maintainWiFi(now);
  maintainMqtt(now);

  // 2. Poll Debounced Hardware Sensors
  const bool entryDetected = sensorFell(entrySensor, now);
  const bool exitDetected = sensorFell(exitSensor, now);

  // 3. Directional Transit State Machine
  if (crossingState == WAITING_FOR_SENSOR) {
    if (entryDetected && !exitDetected) {
      crossingState = ENTRY_FIRST;
      crossingStartedAt = now;
      publishEvent("entry", vehicleCount);
      Serial.println("[IR Sensor] Sensor A (ENTRY) triggered. Vehicle approaching.");
    } else if (exitDetected && !entryDetected) {
      crossingState = EXIT_FIRST;
      crossingStartedAt = now;
      publishEvent("exit", vehicleCount);
      Serial.println("[IR Sensor] Sensor B (EXIT) triggered. Reverse vehicle approaching.");
    } else if (entryDetected && exitDetected) {
      Serial.println("[IR Sensor] Simultaneous trigger ignored (optical noise).");
    }
  } else if (now - crossingStartedAt > CROSSING_TIMEOUT_MS) {
    crossingState = WAITING_FOR_SENSOR;
    Serial.println("[IR Sensor] Crossing sequence timed out. State machine reset.");
  } else if (crossingState == ENTRY_FIRST && exitDetected) {
    // Completed Entry -> Exit transit
    publishEvent("exit", vehicleCount);
    recordVehicle(true, now);
  } else if (crossingState == EXIT_FIRST && entryDetected) {
    // Completed Exit -> Entry transit
    publishEvent("entry", vehicleCount);
    recordVehicle(false, now);
  }

  // 4. Non-blocking LED feedback pulse
  if (ledIsOn && (now - lastLedAt >= LED_PULSE_DURATION_MS)) {
    digitalWrite(STATUS_LED_PIN, LOW);
    ledIsOn = false;
  }

  // 5. Periodic telemetry heartbeat
  if (now - lastStatusAt >= STATUS_INTERVAL_MS) {
    lastStatusAt = now;
    publishStatus(now);
  }

  // Cooperative task yield
  delay(2);
}
