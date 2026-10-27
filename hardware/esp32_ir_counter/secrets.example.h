#pragma once

// Wi-Fi configuration for Wokwi simulation / physical ESP32
#define WIFI_SSID "Wokwi-GUEST"
#define WIFI_PASSWORD ""

// Public Wokwi-compatible MQTT Broker (or replace with your server IP for LAN deployment)
#define MQTT_HOST "broker.hivemq.com"
#define MQTT_PORT 1883
#define MQTT_USERNAME ""
#define MQTT_PASSWORD ""

// Device identifiers
#define DEVICE_ID "wokwi-counter-01"
#define DEVICE_TOKEN "replace-with-token-from-device-registration"
#define DEVICE_MODE "simulation"
#define MQTT_TOPIC_PREFIX "traffic"
