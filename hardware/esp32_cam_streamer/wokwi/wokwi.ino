#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#define WIFI_SSID "Wokwi-GUEST"
#define WIFI_PASSWORD ""
#define MQTT_HOST "192.168.1.10"
#define MQTT_PORT 1883
#define MQTT_USERNAME ""
#define MQTT_PASSWORD ""
#define DEVICE_ID "wokwi-camera-01"
#define DEVICE_TOKEN ""
#define MQTT_TOPIC_PREFIX "traffic"
#endif

constexpr uint8_t MOTION_PIN = 18;
constexpr uint8_t STATUS_LED_PIN = 2;
constexpr uint32_t DEBOUNCE_MS = 40;
constexpr uint32_t STATUS_INTERVAL_MS = 30000;

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
bool lastButtonReading = HIGH;
bool stableButtonReading = HIGH;
uint32_t buttonChangedAt = 0;
uint32_t lastWifiAttemptAt = 0;
uint32_t lastMqttAttemptAt = 0;
uint32_t lastStatusAt = 0;
uint32_t sequenceNumber = 0;

String topicFor(const char *suffix) {
  return String(MQTT_TOPIC_PREFIX) + "/" + DEVICE_ID + "/" + suffix;
}

void publishStatus() {
  if (!mqttClient.connected()) {
    return;
  }
#if ARDUINOJSON_VERSION_MAJOR >= 7
  JsonDocument status;
#else
  StaticJsonDocument<512> status;
#endif
  status["device_id"] = DEVICE_ID;
  status["device_token"] = DEVICE_TOKEN;
  status["sequence"] = sequenceNumber++;
  status["uptime_seconds"] = millis() / 1000;
  status["vehicle_count"] = 0;
  status["direction_a_to_b"] = 0;
  status["direction_b_to_a"] = 0;
  status["sensor_a"] = !stableButtonReading;
  status["sensor_b"] = false;
  status["mode"] = "simulation";
  status["firmware_version"] = "1.0.0-sim";
  char payload[512];
  const size_t length = serializeJson(status, payload, sizeof(payload));
  mqttClient.publish(topicFor("status").c_str(), payload, length);
  Serial.println("[Camera simulation] Status published.");
}

void publishEvent(const char *suffix, bool isAlert) {
  if (!mqttClient.connected()) {
    Serial.printf("[Camera simulation] MQTT offline; skipped %s event.\n", suffix);
    return;
  }
#if ARDUINOJSON_VERSION_MAJOR >= 7
  JsonDocument event;
#else
  StaticJsonDocument<512> event;
#endif
  event["device_id"] = DEVICE_ID;
  event["device_token"] = DEVICE_TOKEN;
  event["sequence"] = sequenceNumber;
  event["camera_url"] = "wokwi://camera-not-emulated";
  if (isAlert) {
    event["alert_type"] = "Motion Detected";
    event["severity"] = "Warning";
    event["message"] = "Motion button pressed in Wokwi simulation.";
  }
  char payload[512];
  const size_t length = serializeJson(event, payload, sizeof(payload));
  mqttClient.publish(topicFor(suffix).c_str(), payload, length);
  Serial.printf("[Camera simulation] Published %s event.\n", suffix);
}

void connectWiFi() {
  const uint32_t now = millis();
  if (WiFi.status() == WL_CONNECTED || now - lastWifiAttemptAt < 5000) {
    return;
  }
  lastWifiAttemptAt = now;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[WiFi] Connecting to %s\n", WIFI_SSID);
}

void connectMqtt() {
  const uint32_t now = millis();
  if (mqttClient.connected() || WiFi.status() != WL_CONNECTED ||
      now - lastMqttAttemptAt < 5000) {
    return;
  }
  lastMqttAttemptAt = now;
  const bool connected = MQTT_USERNAME[0] == '\0'
      ? mqttClient.connect(DEVICE_ID)
      : mqttClient.connect(DEVICE_ID, MQTT_USERNAME, MQTT_PASSWORD);
  if (connected) {
    Serial.println("[MQTT] Camera simulation connected.");
    publishEvent("camera", false);
    publishStatus();
  } else {
    Serial.printf("[MQTT] Connect failed (state %d).\n", mqttClient.state());
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(MOTION_PIN, INPUT_PULLUP);
  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, LOW);
  buttonChangedAt = millis();
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setBufferSize(640);
  Serial.println("Wokwi camera-event simulator ready; camera images are not emulated.");
  connectWiFi();
}

void loop() {
  const uint32_t now = millis();
  connectWiFi();
  connectMqtt();
  mqttClient.loop();

  const bool reading = digitalRead(MOTION_PIN);
  if (reading != lastButtonReading) {
    lastButtonReading = reading;
    buttonChangedAt = now;
  }
  if (reading != stableButtonReading && now - buttonChangedAt >= DEBOUNCE_MS) {
    stableButtonReading = reading;
    if (stableButtonReading == LOW) {
      digitalWrite(STATUS_LED_PIN, HIGH);
      publishEvent("alert", true);
      publishStatus();
    } else {
      digitalWrite(STATUS_LED_PIN, LOW);
    }
  }

  if (now - lastStatusAt >= STATUS_INTERVAL_MS) {
    lastStatusAt = now;
    publishStatus();
  }
  delay(5);
}
