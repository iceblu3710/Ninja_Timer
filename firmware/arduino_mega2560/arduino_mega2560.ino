/*
  Dynasty Ninja Timer companion firmware for Arduino Mega 2560.

  Serial contract:
    Arduino -> backend: READY
                       HEARTBEAT,<seq>
                       EVT,<INPUT>,<STATE>,<seq>
    Backend -> Arduino: CMD,<TARGET>,ON
                       CMD,<TARGET>,OFF
                       CMD,<TARGET>,PULSE,<duration_ms>
*/

#include <Arduino.h>

static const uint32_t SERIAL_BAUD = 115200;
static const uint32_t HEARTBEAT_INTERVAL_MS = 1000;
static const uint16_t INPUT_DEBOUNCE_MS = 25;
static const bool RELAY_ACTIVE_LOW = true;
static const bool SEND_COMMAND_ACKS = false;

struct InputDef {
  const char *name;
  uint8_t pin;
  const char *activeState;
  const char *inactiveState;
  bool activeLow;
  bool stableActive;
  bool lastReading;
  uint32_t changedAt;
};

struct RelayDef {
  const char *name;
  uint8_t pin;
  bool logicalOn;
  uint32_t pulseEndsAt;
};

InputDef inputs[] = {
  {"START", 22, "DOWN", "UP", true, false, false, 0},
  {"FINISH", 23, "DOWN", "UP", true, false, false, 0},
  {"ARM", 24, "DOWN", "UP", true, false, false, 0},
  {"RESET", 25, "DOWN", "UP", true, false, false, 0},
  {"MANUAL_STOP", 26, "DOWN", "UP", true, false, false, 0},
  {"DELETE_LAST", 27, "DOWN", "UP", true, false, false, 0},
  {"BEAM", 28, "BLOCKED", "CLEAR", true, false, false, 0},
  {"ESTOP", 29, "OPEN", "CLOSED", true, false, false, 0},
};

RelayDef relays[] = {
  {"HORN", 30, false, 0},
  {"GREEN", 31, false, 0},
  {"RED", 32, false, 0},
  {"FX", 33, false, 0},
};

uint32_t sequenceNumber = 0;
uint32_t lastHeartbeatAt = 0;
String serialLine;

void writeRelayPin(RelayDef &relay) {
  const bool rawOn = RELAY_ACTIVE_LOW ? LOW : HIGH;
  const bool rawOff = RELAY_ACTIVE_LOW ? HIGH : LOW;
  digitalWrite(relay.pin, relay.logicalOn ? rawOn : rawOff);
}

void setRelay(RelayDef &relay, bool on) {
  relay.logicalOn = on;
  relay.pulseEndsAt = 0;
  writeRelayPin(relay);
}

void pulseRelay(RelayDef &relay, uint32_t durationMs) {
  relay.logicalOn = true;
  relay.pulseEndsAt = millis() + (durationMs == 0 ? 1 : durationMs);
  writeRelayPin(relay);
}

void publishEvent(const char *name, const char *state) {
  sequenceNumber++;
  Serial.print(F("EVT,"));
  Serial.print(name);
  Serial.print(',');
  Serial.print(state);
  Serial.print(',');
  Serial.println(sequenceNumber);
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

void setAllRelays(bool on) {
  for (RelayDef &relay : relays) {
    setRelay(relay, on);
  }
}

void handleCommand(String line) {
  line.trim();
  line.toUpperCase();
  if (!line.startsWith("CMD,")) {
    return;
  }

  int firstComma = line.indexOf(',');
  int secondComma = line.indexOf(',', firstComma + 1);
  int thirdComma = line.indexOf(',', secondComma + 1);
  if (firstComma < 0 || secondComma < 0) {
    return;
  }

  String target = line.substring(firstComma + 1, secondComma);
  String action = thirdComma < 0 ? line.substring(secondComma + 1) : line.substring(secondComma + 1, thirdComma);
  uint32_t durationMs = thirdComma < 0 ? 200 : line.substring(thirdComma + 1).toInt();

  if (target == "ALL") {
    if (action == "OFF") {
      setAllRelays(false);
    } else if (action == "ON") {
      setAllRelays(true);
    }
  } else {
    RelayDef *relay = findRelay(target);
    if (relay == nullptr) {
      return;
    }
    if (action == "ON") {
      setRelay(*relay, true);
    } else if (action == "OFF") {
      setRelay(*relay, false);
    } else if (action == "PULSE") {
      pulseRelay(*relay, durationMs);
    }
  }

  if (SEND_COMMAND_ACKS) {
    Serial.print(F("ACK,"));
    Serial.println(line);
  }
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    char ch = static_cast<char>(Serial.read());
    if (ch == '\n') {
      handleCommand(serialLine);
      serialLine = "";
    } else if (ch != '\r' && serialLine.length() < 96) {
      serialLine += ch;
    }
  }
}

void scanInputs() {
  const uint32_t now = millis();
  for (InputDef &input : inputs) {
    const bool rawActive = digitalRead(input.pin) == (input.activeLow ? LOW : HIGH);
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

void sendHeartbeat() {
  const uint32_t now = millis();
  if (now - lastHeartbeatAt >= HEARTBEAT_INTERVAL_MS) {
    lastHeartbeatAt = now;
    sequenceNumber++;
    Serial.print(F("HEARTBEAT,"));
    Serial.println(sequenceNumber);
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  for (InputDef &input : inputs) {
    pinMode(input.pin, INPUT_PULLUP);
    input.lastReading = digitalRead(input.pin) == (input.activeLow ? LOW : HIGH);
    input.stableActive = input.lastReading;
    input.changedAt = millis();
  }
  for (RelayDef &relay : relays) {
    pinMode(relay.pin, OUTPUT);
    setRelay(relay, false);
  }
  Serial.println(F("READY"));
}

void loop() {
  readSerialCommands();
  scanInputs();
  updateRelayPulses();
  sendHeartbeat();
}
