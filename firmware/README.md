# Dynasty Ninja Timer Firmware

This directory contains companion firmware for the app hardware contracts.

## Arduino Mega 2560

Open `arduino_mega2560/arduino_mega2560.ino` in the Arduino IDE and select an Arduino Mega 2560 board at `115200` baud.

Default inputs use `INPUT_PULLUP`, so dry contacts should close to ground:

| Logical input | Pin |
|---|---:|
| START | 22 |
| FINISH | 23 |
| ARM | 24 |
| RESET | 25 |
| MANUAL_STOP | 26 |
| DELETE_LAST | 27 |
| BEAM | 28 |
| ESTOP | 29 |

Default relay outputs:

| Logical output | Pin |
|---|---:|
| HORN / CHIME | 30 |
| GREEN / START_LIGHT | 31 |
| RED | 32 |
| FX / SMOKE / CROWD | 33 |

If your relay board is active-high, change `RELAY_ACTIVE_LOW` to `false`.

## M5Stack StamPLC / M5Stamp PLC MQTT

Open `m5stamp_plc_mqtt/m5stamp_plc_mqtt.ino` in the Arduino IDE with the M5Stack board package installed. M5Stack's StamPLC Arduino docs require the `M5StamPLC`, `M5Unified`, and `M5GFX` libraries; this sketch also uses `PubSubClient` and `ArduinoJson`.

Set these constants before uploading:

```cpp
WIFI_SSID
WIFI_PASSWORD
MQTT_HOST
MQTT_PORT
MQTT_USERNAME
MQTT_PASSWORD
DEVICE_ID
```

The sketch publishes:

```text
dynasty/timer/io/<device_id>/event
dynasty/timer/io/<device_id>/heartbeat
dynasty/timer/io/<device_id>/state
```

It subscribes to:

```text
dynasty/timer/io/<device_id>/cmd
```

Default input mapping is `IN1..IN8` to `START`, `FINISH`, `ARM`, `RESET`, `MANUAL_STOP`, `DELETE_LAST`, `BEAM`, and `ESTOP`. Default relay mapping is `RELAY1..RELAY4` to `HORN`, `GREEN`, `RED`, and `FX`.
