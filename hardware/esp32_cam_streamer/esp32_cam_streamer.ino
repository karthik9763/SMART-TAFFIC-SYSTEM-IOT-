/*
 * ESP32-CAM MJPEG Video Streamer for Smart Traffic System
 * 
 * Hardware Required:
 * - ESP32-CAM AI-Thinker Module
 * - FTDI USB-to-TTL Serial Adapter (3.3V / 5V)
 * - 5V 2A DC Power Supply
 * 
 * Instructions:
 * 1. Install ESP32 board support in Arduino IDE (https://dl.espressif.com/dl/package_esp32_index.json)
 * 2. Select Board: "AI Thinker ESP32-CAM"
 * 3. Set PSRAM: "Enabled"
 * 4. Update SSID and PASSWORD with your Wi-Fi details.
 * 5. Connect GPIO 0 to GND while flashing. Disconnect GPIO 0 after flashing to run.
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include "esp_http_server.h"

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
#define DEVICE_MODE "simulation"
#define MQTT_TOPIC_PREFIX "traffic"
#endif

constexpr char FIRMWARE_VERSION[] = "1.0.0";

// AI-THINKER ESP32-CAM Pin Configuration
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t stream_httpd = NULL;
httpd_handle_t capture_httpd = NULL;
WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
volatile bool motionPending = false;
uint32_t lastMotionAt = 0;
uint32_t lastMqttAttemptAt = 0;
uint32_t lastStatusAt = 0;
uint32_t lastFingerprintAt = 0;
uint32_t telemetrySequence = 0;
uint32_t previousFingerprint = 0;

String topicFor(const char *suffix) {
  return String(MQTT_TOPIC_PREFIX) + "/" + DEVICE_ID + "/" + suffix;
}

void publishCameraEvent(const char *suffix, const char *messageText) {
  if (!mqttClient.connected()) {
    return;
  }
  StaticJsonDocument<512> message;
  message["device_id"] = DEVICE_ID;
  message["device_token"] = DEVICE_TOKEN;
  message["firmware_version"] = FIRMWARE_VERSION;
  message["mode"] = DEVICE_MODE;
  message["camera_url"] = "http://" + WiFi.localIP().toString() + ":81/stream";
  if (messageText != NULL) {
    message["alert_type"] = "Motion Detected";
    message["severity"] = "Warning";
    message["message"] = messageText;
  }
  char payload[512];
  size_t length = serializeJson(message, payload, sizeof(payload));
  if (!mqttClient.publish(topicFor(suffix).c_str(), payload, length)) {
    Serial.printf("[MQTT] Could not publish camera topic %s\n", suffix);
  }
}

void publishCameraStatus() {
  if (!mqttClient.connected()) {
    return;
  }
  StaticJsonDocument<512> status;
  status["device_id"] = DEVICE_ID;
  status["device_token"] = DEVICE_TOKEN;
  status["sequence"] = telemetrySequence++;
  status["uptime_seconds"] = millis() / 1000;
  status["vehicle_count"] = 0;
  status["direction_a_to_b"] = 0;
  status["direction_b_to_a"] = 0;
  status["sensor_a"] = false;
  status["sensor_b"] = false;
  status["mode"] = DEVICE_MODE;
  status["firmware_version"] = FIRMWARE_VERSION;
  char payload[512];
  const size_t length = serializeJson(status, payload, sizeof(payload));
  if (!mqttClient.publish(topicFor("status").c_str(), payload, length)) {
    Serial.println("[MQTT] Could not publish camera heartbeat.");
  }
}

void checkMotion(camera_fb_t *frame) {
  const uint32_t now = millis();
  if (frame == NULL || frame->len < 64 || now - lastFingerprintAt < 1000) {
    return;
  }
  lastFingerprintAt = now;

  uint32_t fingerprint = 2166136261UL;
  const size_t sampleCount = 64;
  for (size_t index = 0; index < sampleCount; ++index) {
    const size_t position = (index * frame->len) / sampleCount;
    fingerprint = (fingerprint ^ frame->buf[position]) * 16777619UL;
  }
  if (previousFingerprint != 0 &&
      fingerprint != previousFingerprint &&
      now - lastMotionAt > 5000) {
    motionPending = true;
    lastMotionAt = now;
  }
  previousFingerprint = fingerprint;
}

esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t * fb = NULL;
  esp_err_t res = ESP_OK;
  size_t _jpg_buf_len = 0;
  uint8_t * _jpg_buf = NULL;
  char part_buf[64];

  res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
  if (res != ESP_OK) {
    return res;
  }

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("Camera capture failed");
      res = ESP_FAIL;
    } else {
      _jpg_buf_len = fb->len;
      _jpg_buf = fb->buf;
      checkMotion(fb);
    }
    if (res == ESP_OK) {
      size_t hlen = snprintf((char *)part_buf, 64, _STREAM_PART, _jpg_buf_len);
      res = httpd_resp_send_chunk(req, (const char *)part_buf, hlen);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
    }
    if (fb) {
      esp_camera_fb_return(fb);
      fb = NULL;
      _jpg_buf = NULL;
    }
    if (res != ESP_OK) {
      break;
    }
  }
  return res;
}

esp_err_t capture_handler(httpd_req_t *req) {
  camera_fb_t *frame = esp_camera_fb_get();
  if (frame == NULL) {
    httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Camera capture failed");
    return ESP_FAIL;
  }
  httpd_resp_set_type(req, "image/jpeg");
  esp_err_t result = httpd_resp_send(req, (const char *)frame->buf, frame->len);
  esp_camera_fb_return(frame);
  return result;
}

void startCameraServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 81;

  httpd_uri_t stream_uri = {
    .uri       = "/stream",
    .method    = HTTP_GET,
    .handler   = stream_handler,
    .user_ctx  = NULL
  };

  Serial.printf("Starting stream server on port: '%d'\n", config.server_port);
  if (httpd_start(&stream_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
  } else {
    Serial.println("[Camera] Could not start the MJPEG server.");
  }

  httpd_config_t captureConfig = HTTPD_DEFAULT_CONFIG();
  captureConfig.server_port = 80;
  captureConfig.ctrl_port = 32769;
  httpd_uri_t capture_uri = {
    .uri = "/capture",
    .method = HTTP_GET,
    .handler = capture_handler,
    .user_ctx = NULL
  };
  if (httpd_start(&capture_httpd, &captureConfig) == ESP_OK) {
    httpd_register_uri_handler(capture_httpd, &capture_uri);
  } else {
    Serial.println("[Camera] Could not start the JPEG capture server.");
  }
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println();

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  
  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA; // 640x480
    config.jpeg_quality = 12;
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_CIF;
    config.jpeg_quality = 15;
    config.fb_count = 1;
  }

  // Camera init
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x", err);
    return;
  }

  // Connect Wi-Fi
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.println("WiFi connected");
  
  startCameraServer();

  Serial.print("Camera Stream Ready! Use 'http://");
  Serial.print(WiFi.localIP());
  Serial.println(":81/stream' in Smart Traffic Dashboard");
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setBufferSize(640);
}

void loop() {
  const uint32_t now = millis();
  if (WiFi.status() == WL_CONNECTED && !mqttClient.connected() &&
      now - lastMqttAttemptAt >= 5000) {
    lastMqttAttemptAt = now;
    const bool connected = MQTT_USERNAME[0] == '\0'
        ? mqttClient.connect(DEVICE_ID)
        : mqttClient.connect(DEVICE_ID, MQTT_USERNAME, MQTT_PASSWORD);
    if (connected) {
      Serial.println("[MQTT] Connected.");
      publishCameraEvent("camera", NULL);
      publishCameraStatus();
    } else {
      Serial.printf("[MQTT] Connection failed (state %d).\n", mqttClient.state());
    }
  }
  mqttClient.loop();

  if (motionPending) {
    motionPending = false;
    Serial.println("[Camera] Possible motion detected; publishing alert.");
    publishCameraEvent("alert", "Possible motion detected in the camera stream.");
  }
  if (mqttClient.connected() && now - lastStatusAt >= 30000) {
    lastStatusAt = now;
    publishCameraEvent("camera", NULL);
    publishCameraStatus();
  }
  delay(20);
}
