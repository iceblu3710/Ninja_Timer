/*
  Dynasty Ninja Timer companion firmware for M5Stack StamPLC / M5Stamp PLC MQTT.

  Required Arduino libraries:
    M5StamPLC
    PubSubClient
    ArduinoJson

  MQTT topics:
    dynasty/timer/io/<device_id>/event
    dynasty/timer/io/<device_id>/heartbeat
    dynasty/timer/io/<device_id>/state
    dynasty/timer/io/<device_id>/cmd
*/

#include <Arduino.h>
#include <ArduinoJson.h>
#include <M5StamPLC.h>
#include <PubSubClient.h>
#include <WiFi.h>

static const char *WIFI_SSID = "CHANGE_ME";
static const char *WIFI_PASSWORD = "CHANGE_ME";
static const char *MQTT_HOST = "192.168.1.10";
static const uint16_t MQTT_PORT = 1883;
static const char *MQTT_USERNAME = "";
static const char *MQTT_PASSWORD = "";
static const char *MQTT_TOPIC_PREFIX = "dynasty/timer/io";
static const char *DEVICE_ID = "m5stamp-main";

static const uint32_t HEARTBEAT_INTERVAL_MS = 1000;
static const uint16_t INPUT_DEBOUNCE_MS = 25;
static const bool INPUT_ACTIVE_HIGH = true;

struct InputDef {
  const char *name;
  uint8_t channel;
  const char *activeState;
  const char *inactiveState;
  bool stableActive;
  bool lastReading;
  uint32_t changedAt;
};

struct RelayDef {
  const char *name;
  uint8_t channel;
  bool logicalOn;
  uint32_t pulseEndsAt;
};

InputDef inputs[] = {
  {"START", 0, "DOWN", "UP", false, false, 0},
  {"FINISH", 1, "DOWN", "UP", false, false, 0},
  {"ARM", 2, "DOWN", "UP", false, false, 0},
  {"RESET", 3, "DOWN", "UP", false, false, 0},
  {"MANUAL_STOP", 4, "DOWN", "UP", false, false, 0},
  {"DELETE_LAST", 5, "DOWN", "UP", false, false, 0},
  {"BEAM", 6, "BLOCKED", "CLEAR", false, false, 0},
  {"ESTOP", 7, "OPEN", "CLOSED", false, false, 0},
};

RelayDef relays[] = {
  {"HORN", 0, false, 0},
  {"GREEN", 1, false, 0},
  {"RED", 2, false, 0},
  {"FX", 3, false, 0},
};

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
uint32_t sequenceNumber = 0;
uint32_t lastHeartbeatAt = 0;

String topicFor(const char *suffix) {
  String topic = String(MQTT_TOPIC_PREFIX);
  topic += "/";
  topic += DEVICE_ID;
  topic += "/";
  topic += suffix;
  return topic;
}

void publishJson(const char *suffix, JsonDocument &doc, bool retained = false, int qos = 1) {
  (void)qos;
  char buffer[384];
  size_t length = serializeJson(doc, buffer, sizeof(buffer));
  mqtt.publish(topicFor(suffix).c_str(), reinterpret_cast<const uint8_t *>(buffer), length, retained);
}

void publishEvent(const char *inputName, const char *state) {
  sequenceNumber++;
  StaticJsonDocument<256> doc;
  doc["type"] = "EVT";
  doc["device_id"] = DEVICE_ID;
  doc["seq"] = sequenceNumber;
  doc["event"] = inputName;
  doc["input"] = inputName;
  doc["state"] = state;
  doc["timestamp_ms"] = millis();
  publishJson("event", doc);
}

void publishHeartbeat() {
  const uint32_t now = millis();
  if (now - lastHeartbeatAt < HEARTBEAT_INTERVAL_MS) {
    return;
  }
  lastHeartbeatAt = now;
  sequenceNumber++;
  StaticJsonDocument<192> doc;
  doc["type"] = "HEARTBEAT";
  doc["device_id"] = DEVICE_ID;
  doc["seq"] = sequenceNumber;
  doc["timestamp_ms"] = now;
  doc["wifi_rssi"] = WiFi.RSSI();
  publishJson("heartbeat", doc, false, 0);
}

RelayDef *findRelay(const String &target) {
  if (target == "CHIME") {
    return findRelay("HORN");
  }
  if (target == "START_LIGHT") {
    return findRelay("GREEN");
  }
  if (target == "SMOKE" || target == "CROWD") {
    return findRelay("FX");
  }
  for (RelayDef &relay : relays) {
    if (target == relay.name) {
      return &relay;
    }
  }
  return nullptr;
}

void setRelay(RelayDef &relay, bool on) {
  relay.logicalOn = on;
  relay.pulseEndsAt = 0;
  M5StamPLC.writePlcRelay(relay.channel, on);
}

void pulseRelay(RelayDef &relay, uint32_t durationMs) {
  relay.logicalOn = true;
  relay.pulseEndsAt = millis() + (durationMs == 0 ? 1 : durationMs);
  M5StamPLC.writePlcRelay(relay.channel, true);
}

void setAllRelays(bool on) {
  for (RelayDef &relay : relays) {
    setRelay(relay, on);
  }
}

void publishCommandAck(const char *commandId, bool ok, const char *message) {
  StaticJsonDocument<256> doc;
  doc["type"] = "ACK";
  doc["device_id"] = DEVICE_ID;
  doc["command_id"] = commandId;
  doc["ok"] = ok;
  doc["message"] = message;
  doc["timestamp_ms"] = millis();
  publishJson("state", doc);
}

void handleCommand(char *payload, unsigned int length) {
  StaticJsonDocument<256> doc;
  DeserializationError error = deserializeJson(doc, payload, length);
  if (error) {
    publishCommandAck("", false, "invalid json");
    return;
  }

  const char *commandId = doc["command_id"] | "";
  String target = String(doc["device"] | "");
  String action = String(doc["action"] | "");
  uint32_t valueMs = doc["value_ms"] | 200;
  target.toUpperCase();
  action.toUpperCase();

  if (target == "ALL") {
    if (action == "OFF") {
      setAllRelays(false);
      publishCommandAck(commandId, true, "all relays off");
      return;
    }
    if (action == "ON") {
      setAllRelays(true);
      publishCommandAck(commandId, true, "all relays on");
      return;
    }
  }

  RelayDef *relay = findRelay(target);
  if (relay == nullptr) {
    publishCommandAck(commandId, false, "unknown relay target");
    return;
  }

  if (action == "ON") {
    setRelay(*relay, true);
    publishCommandAck(commandId, true, "relay on");
  } else if (action == "OFF") {
    setRelay(*relay, false);
    publishCommandAck(commandId, true, "relay off");
  } else if (action == "PULSE") {
    pulseRelay(*relay, valueMs);
    publishCommandAck(commandId, true, "relay pulse started");
  } else {
    publishCommandAck(commandId, false, "unknown relay action");
  }
}

void mqttCallback(char *topic, byte *payload, unsigned int length) {
  String expected = topicFor("cmd");
  if (String(topic) == expected) {
    handleCommand(reinterpret_cast<char *>(payload), length);
  }
}

void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
  }
}

void connectMqtt() {
  while (!mqtt.connected()) {
    String clientId = String(DEVICE_ID) + "-" + String((uint32_t)ESP.getEfuseMac(), HEX);
    bool ok;
    if (strlen(MQTT_USERNAME) > 0) {
      ok = mqtt.connect(clientId.c_str(), MQTT_USERNAME, MQTT_PASSWORD);
    } else {
      ok = mqtt.connect(clientId.c_str());
    }
    if (ok) {
      mqtt.subscribe(topicFor("cmd").c_str(), 1);
      StaticJsonDocument<192> doc;
      doc["type"] = "READY";
      doc["device_id"] = DEVICE_ID;
      doc["seq"] = sequenceNumber;
      doc["timestamp_ms"] = millis();
      publishJson("state", doc, true, 1);
    } else {
      delay(1000);
    }
  }
}

void scanInputs() {
  const uint32_t now = millis();
  for (InputDef &input : inputs) {
    bool rawActive = M5StamPLC.readPlcInput(input.channel) == INPUT_ACTIVE_HIGH;
    if (rawActive != input.lastReading) {
      input.lastReading = rawActive;
      input.changedAt = now;
    }
    if ((now - input.changedAt) >= INPUT_DEBOUNCE_MS && rawActive != input.stableActive) {
      input.stableActive = rawActive;
      publishEvent(input.name, input.stableActive ? input.activeState : input.inactiveState);
    }
  }
}

void updateRelayPulses() {
  const uint32_t now = millis();
  for (RelayDef &relay : relays) {
    if (relay.pulseEndsAt != 0 && static_cast<int32_t>(now - relay.pulseEndsAt) >= 0) {
      setRelay(relay, false);
    }
  }
}

void setup() {
  Serial.begin(115200);
  M5StamPLC.begin();
  for (InputDef &input : inputs) {
    input.lastReading = M5StamPLC.readPlcInput(input.channel) == INPUT_ACTIVE_HIGH;
    input.stableActive = input.lastReading;
    input.changedAt = millis();
  }
  for (RelayDef &relay : relays) {
    setRelay(relay, false);
  }
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
}

void loop() {
  connectWifi();
  connectMqtt();
  mqtt.loop();
  scanInputs();
  updateRelayPulses();
  publishHeartbeat();
}
