# Dynasty Ninja Timer Backend Specification

## 1. Project Overview

The Dynasty Ninja Timer backend is a local-first Python server that powers a ninja course timing system. It runs on a single SFF PC connected to a 47-inch HDMI TV and communicates with a pluggable hardware I/O controller for physical buttons, sensors, and relay outputs. The first supported controllers are an Arduino Mega 2560 over USB serial and an M5Stack StamPLC / M5Stamp PLC-style controller over Wi-Fi.

The backend owns the source of truth for:

- Timer state
- Runner queue
- Run results
- Leaderboards
- Course configuration
- Hardware I/O state
- Asset hosting for the web frontend
- Real-time updates to display, admin, and kiosk screens

The frontend must interact with the backend through API and WebSocket contracts from the start. Even during early prototype work, no UI state should be trapped only in the browser.

---

## 2. Goals

### 2.1 Primary Goals

- Run fully offline on a local SFF PC.
- Serve the web UI, static assets, and API from one Python process.
- Support three UI clients:
  - TV scoreboard display
  - Staff admin dashboard
  - Runner check-in kiosk
- Communicate with field I/O using a hardware transport layer. Version 1 must support Arduino Mega 2560 over USB serial and should be structured to support an M5Stack StamPLC / M5Stamp PLC-style controller over Wi-Fi.
- Store all permanent data in SQLite.
- Provide real-time updates over WebSockets.
- Use a clear timer state machine to prevent invalid run states.
- Make the system easy to install, backup, and service.

### 2.2 Secondary Goals

- Support multiple courses.
- Support open gym, party, and competition modes.
- Support false-start detection later.
- Support relay effects such as horn, lights, finish chime, or future effects.
- Support exporting results to CSV.
- Support a future cloud sync or remote leaderboard without redesigning the core.

---

## 3. Non-Goals for Version 1

The first production-ready backend does not need:

- Cloud accounts
- Online payment integration
- Multi-location sync
- Public internet hosting
- Bluetooth timing devices
- Multi-lane simultaneous racing
- RFID wristbands
- Advanced tournament bracket logic

These can be added later without blocking the core design.

---

## 4. Recommended Tech Stack

### 4.1 Runtime

- Python 3.12+
- FastAPI
- Uvicorn
- SQLite
- SQLAlchemy 2.x
- Alembic for migrations
- Pydantic v2
- pyserial or pyserial-asyncio
- Jinja2 only if server-rendered templates are needed
- Static HTML/CSS/JS frontend served by FastAPI

### 4.2 Local Deployment Target

- Windows 11 Pro SFF PC or Linux SFF PC
- HDMI output to 47-inch TV
- USB connection to Arduino Mega 2560, or LAN/Wi-Fi connection to M5Stack StamPLC / M5Stamp PLC-style controller
- Optional second browser device on LAN for kiosk or admin

### 4.3 Suggested Repository Layout

```text
ninja_timer/
  app/
    __init__.py
    main.py
    config.py
    logging_config.py

    api/
      __init__.py
      routes_status.py
      routes_timer.py
      routes_queue.py
      routes_runs.py
      routes_leaderboards.py
      routes_courses.py
      routes_settings.py
      routes_hardware.py
      websocket.py

    core/
      __init__.py
      timer_state_machine.py
      event_bus.py
      clock.py
      safety.py
      export_csv.py

    hardware/
      __init__.py
      transport_base.py
      serial_manager.py
      arduino_protocol.py
      wifi_manager.py
      m5stamp_protocol.py
      debounce.py
      relay_service.py
      hardware_models.py

    db/
      __init__.py
      database.py
      models.py
      schemas.py
      repositories.py
      migrations/

    services/
      __init__.py
      timer_service.py
      queue_service.py
      leaderboard_service.py
      run_service.py
      course_service.py
      settings_service.py

    static/
      index.html
      assets/
        images/
        sounds/
        css/
        js/

  data/
    dynasty_ninja_timer.sqlite
    backups/
    exports/

  config/
    settings.yaml

  scripts/
    install_windows_service.ps1
    run_dev.ps1
    run_dev.sh
    backup_db.py

  tests/
    test_timer_state_machine.py
    test_api_timer.py
    test_queue.py
    test_serial_protocol.py
    test_leaderboards.py

  pyproject.toml
  README.md
  spec.md
```

---

## 5. Application Architecture

```text
Browser UI Clients
  |-- TV display
  |-- Admin dashboard
  |-- Check-in kiosk
        |
        | HTTP + WebSocket
        v
FastAPI Backend
  |-- API routes
  |-- WebSocket live updates
  |-- Timer state machine
  |-- Queue service
  |-- Leaderboard service
  |-- SQLite database
  |-- Static asset hosting
        |
        | Hardware transport layer
        |-- USB serial: Arduino Mega 2560
        |-- Wi-Fi LAN: M5Stack StamPLC / M5Stamp PLC-style controller
        v
I/O Controller
  |-- Start input
  |-- Finish input
  |-- Arm/reset/manual controls
  |-- Relay outputs
```

The backend should be the only authority for timer state. The hardware controller reports input events and accepts output commands, but it does not decide if a run is valid. Arduino and M5Stamp-style controllers must both translate their physical I/O into the same logical event model.

---

## 6. Runtime Modes

### 6.1 Open Gym Mode

Default mode.

- Simple start/finish timing.
- False starts disabled.
- Queue optional.
- Great for everyday use.

### 6.2 Party Mode

Kid-friendly event mode.

- Queue-focused.
- Personal bests highlighted.
- More visual/audio effects.
- Optionally hide all-time competitive records.

### 6.3 Competition Mode

Strict mode.

- Staff arms each run.
- Countdown optional or required.
- False-start detection supported.
- Run deletion may require admin confirmation.
- Event/session lock may be added later.

---

## 7. Timer State Machine

### 7.1 States

```text
IDLE
READY
COUNTDOWN
RUNNING
FINISHED
SAVED
FALSE_START
SENSOR_FAULT
MANUAL_STOPPED
DNF
ERROR
```

### 7.2 State Definitions

#### IDLE

No active runner is timing. The system can accept a runner from the queue or manual input.

Allowed transitions:

- `arm` -> READY
- `manual_start` -> RUNNING
- `hardware_fault` -> SENSOR_FAULT

#### READY

Runner is selected and the system is armed.

Allowed transitions:

- `start_command` -> COUNTDOWN or RUNNING
- `start_sensor_triggered` -> RUNNING, depending on mode
- `reset` -> IDLE
- `hardware_fault` -> SENSOR_FAULT

#### COUNTDOWN

Countdown is active.

Allowed transitions:

- `countdown_complete` -> RUNNING
- `start_sensor_triggered_before_go` -> FALSE_START, competition mode only
- `reset` -> IDLE

#### RUNNING

Timer is active.

Allowed transitions:

- `finish_sensor_triggered` -> FINISHED
- `manual_stop` -> MANUAL_STOPPED
- `dnf` -> DNF
- `reset` -> IDLE
- `hardware_fault` -> SENSOR_FAULT

#### FINISHED

Run is complete but may not yet be saved or animated.

Allowed transitions:

- `save_run` -> SAVED
- `delete_run` -> IDLE
- `reset` -> IDLE

#### SAVED

Run has been recorded in SQLite.

Allowed transitions:

- `next_runner` -> READY
- `reset` -> IDLE

#### FALSE_START

Runner triggered start before allowed.

Allowed transitions:

- `reset` -> IDLE
- `rearm` -> READY

#### SENSOR_FAULT

A required sensor is disconnected or reporting invalid state.

Allowed transitions:

- `clear_fault` -> IDLE
- `manual_mode` -> IDLE with manual-only flag

### 7.3 Timing Source

All official timing should use Python monotonic time:

```python
time.perf_counter_ns()
```

Store timestamps as integer nanoseconds internally while timing, then store elapsed milliseconds in the database.

Database storage field:

```text
elapsed_ms INTEGER NOT NULL
```

Display formatting:

```text
MM:SS.hh
```

Where `hh` is hundredths of a second.

---

## 8. Hardware I/O Protocols

The backend must treat physical I/O as a pluggable transport. The timer state machine should never directly import Arduino, Wi-Fi, MQTT, or M5Stamp-specific code.

### 8.0 Hardware Transport Interface

All hardware drivers must implement the same internal interface.

```python
class HardwareTransport:
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send_command(self, command: HardwareCommand) -> None: ...
    async def get_status(self) -> HardwareStatus: ...
```

Each driver emits normalized events to the backend event bus.

```text
HardwareTransport -> EventBus -> TimerService -> WebSocket/UI/Database
```

Normalized event names must be identical regardless of transport. A finish button press should become `EVT,FINISH,DOWN` whether it came from USB serial, Wi-Fi, MQTT, HTTP, or a future PLC.

### 8.1 Arduino Mega 2560 USB Serial Protocol

#### 8.1.1 Serial Settings

```text
Baud rate: 115200
Data bits: 8
Parity: none
Stop bits: 1
Line ending: \n
Encoding: UTF-8 ASCII-compatible
```

#### 8.1.2 Arduino to Backend Events

Events are line-based CSV-like messages.

```text
EVT,<DEVICE>,<STATE>
```

Examples:

```text
EVT,START,DOWN
EVT,START,UP
EVT,FINISH,DOWN
EVT,FINISH,UP
EVT,ARM,DOWN
EVT,RESET,DOWN
EVT,BEAM,BLOCKED
EVT,BEAM,CLEAR
EVT,ESTOP,OPEN
EVT,ESTOP,CLOSED
HEARTBEAT,123456
READY
```

#### 8.1.3 Backend to Arduino Commands

Commands are also line-based.

```text
CMD,<DEVICE>,<ACTION>[,<VALUE>]
```

Examples:

```text
CMD,ALL,OFF
CMD,HORN,PULSE,200
CMD,HORN,ON
CMD,HORN,OFF
CMD,GREEN,ON
CMD,GREEN,OFF
CMD,RED,ON
CMD,RED,OFF
CMD,FX,ON
CMD,FX,OFF
CMD,START_LIGHT,PULSE,500
```

#### 8.1.4 Required Logical Inputs

| Logical Name | Purpose |
|---|---|
| START | Manual start button or start beam relay |
| FINISH | Finish slap button |
| ARM | Staff arm button |
| RESET | Staff reset button |

#### 8.1.5 Optional Logical Inputs

| Logical Name | Purpose |
|---|---|
| BEAM | Through-beam start gate |
| MANUAL_STOP | Staff stop button |
| DELETE_LAST | Staff delete bad run button |
| ESTOP | Optional safety-loop status input |

#### 8.1.6 Required Logical Outputs

| Logical Name | Purpose |
|---|---|
| HORN | Start/finish buzzer or chime relay |
| GREEN | Ready/go indicator |
| RED | Stop/fault indicator |
| FX | Spare effect relay |

#### 8.1.7 USB Serial Health Rules

- Backend should mark Arduino disconnected if no serial messages arrive within configurable timeout.
- Backend should attempt reconnect every few seconds.
- UI should show `I/O Controller Disconnected` when serial is unavailable.
- Timer should not enter strict competition mode unless required hardware is connected and healthy.

### 8.2 Arduino Mega 2560 Hardware Notes

The Arduino Mega 2560 option is best for the first bench prototype and for hardwired reliability. It should connect to the SFF PC over USB and use a relay shield or DIN relay board for outputs.

Recommended Mega 2560 mapping:

| Logical Name | Arduino Pin | Direction | Notes |
|---|---:|---|---|
| START | 22 | Input | Start button or dry contact from start beam relay |
| FINISH | 23 | Input | Finish slap button |
| ARM | 24 | Input | Staff arm button |
| RESET | 25 | Input | Staff reset button |
| MANUAL_STOP | 26 | Input | Optional staff stop button |
| DELETE_LAST | 27 | Input | Optional delete bad run button |
| BEAM | 28 | Input | Optional direct start beam state |
| ESTOP | 29 | Input | Optional safety-loop monitor only |
| HORN | 30 | Output | Relay output |
| GREEN | 31 | Output | Relay output |
| RED | 32 | Output | Relay output |
| FX | 33 | Output | Relay output |

Input wiring should prefer dry contacts to ground with `INPUT_PULLUP` for simple buttons. If using 24 VDC industrial sensors, use an opto-isolated input board or interposing relay contacts rather than feeding 24 VDC into Arduino pins.

Relay shield caution: many Arduino relay shields are active-low. The firmware must expose logical ON/OFF states, not raw pin states, so the backend does not need to know whether a relay board is active-high or active-low.

### 8.3 M5Stack StamPLC / M5Stamp PLC Wi-Fi Protocol

The M5Stack StamPLC / M5Stamp PLC-style controller is a better long-term field box if Wi-Fi is acceptable. It provides isolated industrial-style inputs and relay outputs in a compact DIN-rail form factor.

The backend should support this as a network hardware driver. Preferred transport order:

1. MQTT over local LAN, preferred for reliable event publish/subscribe.
2. HTTP POST from the controller to the backend, acceptable and simple.
3. WebSocket client from the controller to the backend, useful for full-duplex control but more firmware complexity.

#### 8.3.1 Preferred MQTT Topics

```text
dynasty/timer/io/<device_id>/event
dynasty/timer/io/<device_id>/state
dynasty/timer/io/<device_id>/heartbeat
dynasty/timer/io/<device_id>/cmd
```

Event payload:

```json
{
  "device_id": "m5stamp-main",
  "seq": 1842,
  "event": "FINISH",
  "state": "DOWN",
  "input": 2,
  "timestamp_ms": 123456789
}
```

Command payload:

```json
{
  "command_id": "cmd-20260620-001",
  "device": "HORN",
  "action": "PULSE",
  "value_ms": 200
}
```

The controller should acknowledge commands:

```json
{
  "command_id": "cmd-20260620-001",
  "ok": true,
  "message": "HORN pulse started"
}
```

#### 8.3.2 HTTP Fallback Protocol

Controller sends input events to the backend:

```text
POST /api/v1/hardware/ingest
```

Request:

```json
{
  "device_id": "m5stamp-main",
  "transport": "wifi_http",
  "seq": 1842,
  "event": "FINISH",
  "state": "DOWN",
  "input": 2,
  "timestamp_ms": 123456789
}
```

Backend response:

```json
{
  "ok": true,
  "server_time": "2026-06-20T19:45:10-06:00"
}
```

Backend sends output commands using either MQTT or direct HTTP to the device. For HTTP output control, the M5 device must expose a small LAN endpoint:

```text
POST http://<m5-ip>/api/relay
```

#### 8.3.3 M5Stamp Logical I/O Mapping

| Logical Name | M5 Input/Output | Direction | Notes |
|---|---:|---|---|
| START | IN1 | Input | Start button or beam relay |
| FINISH | IN2 | Input | Finish slap button |
| ARM | IN3 | Input | Staff arm button |
| RESET | IN4 | Input | Staff reset button |
| MANUAL_STOP | IN5 | Input | Optional |
| DELETE_LAST | IN6 | Input | Optional |
| BEAM | IN7 | Input | Optional direct beam status |
| ESTOP | IN8 | Input | Optional monitor only |
| HORN | RELAY1 | Output | Horn/chime |
| GREEN | RELAY2 | Output | Ready/go light |
| RED | RELAY3 | Output | Fault/stop light |
| FX | RELAY4 | Output | Spare effect |

#### 8.3.4 Network Health Rules

- The M5 device must send heartbeat messages at a configurable interval.
- Backend marks the device disconnected if no heartbeat or event is received within `heartbeat_timeout_ms`.
- Every event should include a monotonically increasing `seq` number. Backend logs dropped or duplicate sequence numbers.
- The backend must continue to work in manual browser-only mode if network I/O is disconnected.
- Competition mode should require `connected=true`, required inputs healthy, and output command acknowledgements enabled.
- The M5 device should reconnect automatically after Wi-Fi loss.

### 8.4 Hardware Driver Selection

The active hardware driver is selected in `settings.yaml`.

```yaml
hardware:
  driver: arduino_serial   # arduino_serial | m5stamp_mqtt | m5stamp_http | simulated
```

Only one active timing I/O driver should own `START` and `FINISH` at a time for Version 1. Multiple passive diagnostic devices can be added later.

---

## 9. Database Schema

SQLite is the primary database.

### 9.0 Schema Design Rules

The database must be resilient to frequent course changes, hardware glitches, duplicate events, power loss, and partially completed runs.

Design rules:

- Store historical snapshots on run records. A run should still display correctly after an athlete name, course name, or course revision changes.
- Treat course revisions as date-bounded layouts. Leaderboards should normally filter by course revision, not just course name.
- Queue entries are operational records and must survive browser refreshes, backend restarts, and temporary hardware disconnects.
- Hardware and system event tables are append-only diagnostic logs. They should be safe to write repeatedly and safe to prune later.
- Settings should be versioned, validated, and recoverable. A bad setting update must not brick the timer.
- Use ISO-8601 UTC strings for wall-clock timestamps unless a local display layer explicitly formats them.
- Use monotonic nanosecond timestamps for actual timing math.
- Enable SQLite WAL mode, foreign keys, and busy timeout at startup.

Recommended SQLite startup pragmas:

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```

### 9.1 `athletes`

Stores recurring runner identity. Keep this intentionally minimal because many users will be kids.

```sql
CREATE TABLE athletes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  display_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  default_age_group TEXT,
  notes TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_athletes_normalized_name ON athletes(normalized_name);
CREATE INDEX idx_athletes_active ON athletes(active);
```

Avoid storing birthdate, phone, address, parent contact information, or other personal details unless a future account system explicitly requires it.

### 9.2 `courses`

Stores the stable course family, such as `Speed Gauntlet` or `Ninja Challenge`.

```sql
CREATE TABLE courses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_courses_active ON courses(active);
```

Default courses:

```text
speed-gauntlet
ninja-challenge
```

### 9.3 `course_revisions`

Course layouts change frequently, so every timed run should reference a date-bounded course revision.

Revision naming convention:

```text
{course_slug}-{start_date}-to-{end_date_or_open}
```

Examples:

```text
speed-gauntlet-2026-06-20-to-open
speed-gauntlet-2026-06-20-to-2026-06-27
ninja-challenge-2026-07-01-to-open
```

When a layout changes, close the current revision by setting `revision_end_date`, then create a new revision with the new `revision_start_date`. A course may have only one open revision at a time.

```sql
CREATE TABLE course_revisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  course_id INTEGER NOT NULL,
  revision_code TEXT NOT NULL UNIQUE,
  revision_name TEXT NOT NULL,
  revision_start_date TEXT NOT NULL,
  revision_end_date TEXT,
  description TEXT,
  obstacle_count INTEGER,
  layout_notes TEXT,
  rules_json TEXT,
  leaderboard_eligible INTEGER NOT NULL DEFAULT 1,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,

  FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE INDEX idx_course_revisions_course_dates
ON course_revisions(course_id, revision_start_date, revision_end_date);

CREATE INDEX idx_course_revisions_active
ON course_revisions(course_id, active);
```

Recommended rule: `revision_end_date` is exclusive. A revision with `revision_end_date = NULL` is the current open-ended layout.

SQLite cannot easily enforce "only one open revision per course" portably with a normal unique constraint, so enforce this in the course service and test it.

### 9.4 `sessions`

Sessions group queue entries and runs. This is core, not optional.

Examples:

```text
Today's Open Gym
Harper Birthday Party
Summer Kickoff Competition
Friday Night Speed Runs
```

```sql
CREATE TABLE sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  starts_at TEXT,
  ends_at TEXT,
  active INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_sessions_active ON sessions(active);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_starts_at ON sessions(starts_at);
```

Session statuses:

```text
DRAFT
ACTIVE
PAUSED
COMPLETED
ARCHIVED
```

Session modes:

```text
OPEN_GYM
PARTY
COMPETITION
PRACTICE
```

### 9.5 `queue_entries`

Queue entries must be resilient. They should survive browser refreshes, server restarts, duplicate kiosk submissions, and staff corrections.

Key resilience features:

- `runner_name_snapshot` and `age_group_snapshot` allow anonymous or one-time runners.
- `request_id` supports idempotent kiosk/admin submissions.
- `version` supports optimistic concurrency when multiple screens edit the queue.
- `sort_key` and `position` allow safe reordering without losing original insert order.
- `locked_at` prevents two staff actions from starting the same queued runner at once.
- `last_error` records operational issues without deleting the entry.

```sql
CREATE TABLE queue_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id TEXT UNIQUE,
  session_id INTEGER,
  athlete_id INTEGER,
  course_id INTEGER NOT NULL,
  course_revision_id INTEGER,

  runner_name_snapshot TEXT NOT NULL,
  age_group_snapshot TEXT,
  mode TEXT NOT NULL,

  status TEXT NOT NULL,
  position INTEGER NOT NULL,
  sort_key INTEGER NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,

  source TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 0,
  attempt_count INTEGER NOT NULL DEFAULT 0,

  created_at TEXT NOT NULL,
  called_at TEXT,
  started_at TEXT,
  completed_at TEXT,
  cancelled_at TEXT,
  skipped_at TEXT,

  locked_at TEXT,
  locked_by TEXT,
  last_error TEXT,
  notes TEXT,

  FOREIGN KEY (session_id) REFERENCES sessions(id),
  FOREIGN KEY (athlete_id) REFERENCES athletes(id),
  FOREIGN KEY (course_id) REFERENCES courses(id),
  FOREIGN KEY (course_revision_id) REFERENCES course_revisions(id)
);

CREATE INDEX idx_queue_session_status_position
ON queue_entries(session_id, status, position);

CREATE INDEX idx_queue_status_sort
ON queue_entries(status, sort_key);

CREATE INDEX idx_queue_course_revision
ON queue_entries(course_revision_id);

CREATE INDEX idx_queue_created_at
ON queue_entries(created_at);
```

Queue statuses:

```text
WAITING
CALLED
ACTIVE
COMPLETED
CANCELLED
SKIPPED
NO_SHOW
ERROR
```

Queue source values:

```text
KIOSK
ADMIN
IMPORT
API
SYSTEM
```

Queue service rules:

- Creating a queue entry with the same `request_id` must return the existing entry instead of creating a duplicate.
- Only one queue entry per session may be `ACTIVE` unless multi-lane mode is added later.
- Reordering the queue should update `position`, `sort_key`, `version`, and `updated_at` through the service layer.
- Queue actions should be wrapped in database transactions.
- If the backend restarts with an `ACTIVE` queue entry and no active run, mark it `ERROR` or return it to `WAITING` based on the recovery policy setting.

### 9.6 `runs`

Runs are permanent historical records. They must snapshot everything needed for fair leaderboards and later display.

```sql
CREATE TABLE runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,

  session_id INTEGER,
  athlete_id INTEGER,
  queue_entry_id INTEGER,

  course_id INTEGER NOT NULL,
  course_revision_id INTEGER,

  runner_name_snapshot TEXT NOT NULL,
  age_group_snapshot TEXT,
  course_name_snapshot TEXT NOT NULL,
  course_revision_snapshot TEXT,

  mode TEXT NOT NULL,
  status TEXT NOT NULL,

  started_at TEXT,
  finished_at TEXT,
  elapsed_ms INTEGER,

  start_monotonic_ns INTEGER,
  finish_monotonic_ns INTEGER,

  start_source TEXT,
  finish_source TEXT,
  source TEXT NOT NULL,

  false_start_ms INTEGER,
  reaction_ms INTEGER,

  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,

  deleted_at TEXT,
  deleted_reason TEXT,

  FOREIGN KEY (session_id) REFERENCES sessions(id),
  FOREIGN KEY (athlete_id) REFERENCES athletes(id),
  FOREIGN KEY (queue_entry_id) REFERENCES queue_entries(id),
  FOREIGN KEY (course_id) REFERENCES courses(id),
  FOREIGN KEY (course_revision_id) REFERENCES course_revisions(id)
);

CREATE INDEX idx_runs_session_created ON runs(session_id, created_at);
CREATE INDEX idx_runs_course_revision_elapsed ON runs(course_revision_id, elapsed_ms);
CREATE INDEX idx_runs_course_elapsed ON runs(course_id, elapsed_ms);
CREATE INDEX idx_runs_status ON runs(status);
CREATE INDEX idx_runs_athlete ON runs(athlete_id);
CREATE INDEX idx_runs_created_at ON runs(created_at);
```

Run statuses:

```text
VALID
FALSE_START
DNF
MANUAL_STOPPED
SENSOR_FAULT
DELETED
ERROR
```

Run source values:

```text
HARDWARE
ADMIN
SIMULATED
IMPORT
RECOVERY
```

Start/finish source examples:

```text
START_BUTTON
START_BEAM
ADMIN_MANUAL
FINISH_BUTTON
FINISH_BEAM
SIMULATED
```

### 9.7 `run_splits`

Optional for MVP, but include the migration early if checkpoint sensors or obstacle split timing are likely.

```sql
CREATE TABLE run_splits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  split_key TEXT NOT NULL,
  split_name TEXT NOT NULL,
  elapsed_ms INTEGER NOT NULL,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL,

  FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE INDEX idx_run_splits_run ON run_splits(run_id);
```

### 9.8 `hardware_devices`

Stores configured I/O controllers. This supports Arduino Mega 2560 over USB serial, M5Stack StamPLC / M5Stamp PLC-style Wi-Fi hardware, and future simulated devices.

```sql
CREATE TABLE hardware_devices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_key TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  device_type TEXT NOT NULL,
  transport TEXT NOT NULL,
  config_json TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  last_seen_at TEXT,
  last_sequence_number INTEGER,
  health_status TEXT NOT NULL DEFAULT 'UNKNOWN',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_hardware_devices_active ON hardware_devices(active);
CREATE INDEX idx_hardware_devices_health ON hardware_devices(health_status);
```

Device types:

```text
ARDUINO_MEGA_2560
M5STAMP_PLC
SIMULATED
```

Transports:

```text
USB_SERIAL
MQTT
HTTP
SIMULATED
```

Health statuses:

```text
UNKNOWN
ONLINE
STALE
OFFLINE
ERROR
```

### 9.9 `hardware_events`

Hardware events are an append-only resilience and diagnostics log. They should tolerate duplicate events, out-of-order packets, and reconnects.

Key resilience features:

- `event_id` supports idempotency across MQTT/HTTP retries.
- `sequence_number` allows missing packet detection.
- `received_monotonic_ns` supports timing diagnostics.
- `processed_at` and `process_status` allow safe retry if the backend crashes after receiving an event but before handling it.
- `run_id` links events to the run they affected when applicable.

```sql
CREATE TABLE hardware_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT UNIQUE,
  device_id INTEGER,
  transport TEXT NOT NULL,

  event_type TEXT NOT NULL,
  input_key TEXT,
  state TEXT,
  sequence_number INTEGER,

  raw_payload TEXT NOT NULL,
  parsed_json TEXT,

  received_at TEXT NOT NULL,
  received_monotonic_ns INTEGER,
  processed_at TEXT,
  process_status TEXT NOT NULL DEFAULT 'PENDING',
  process_error TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0,

  run_id INTEGER,

  FOREIGN KEY (device_id) REFERENCES hardware_devices(id),
  FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE INDEX idx_hardware_events_received_at ON hardware_events(received_at);
CREATE INDEX idx_hardware_events_process_status ON hardware_events(process_status);
CREATE INDEX idx_hardware_events_run ON hardware_events(run_id);
CREATE INDEX idx_hardware_events_device_seq ON hardware_events(device_id, sequence_number);
```

Hardware event process statuses:

```text
PENDING
PROCESSED
DUPLICATE
IGNORED
ERROR
```

Hardware event service rules:

- If `event_id` already exists, do not process it again. Mark the duplicate attempt as ignored at the transport layer.
- If `sequence_number` jumps, create a `system_events` warning.
- Hardware input debounce should happen before timer state transitions, but raw events should still be stored when useful for diagnostics.
- A bounded retention policy should prune old raw hardware events after backup/export.

### 9.10 `relay_actions`

Relay actions are output commands sent to the I/O controller. Logging them makes horn/light/fog issues diagnosable.

```sql
CREATE TABLE relay_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action_id TEXT NOT NULL UNIQUE,
  device_id INTEGER,
  action_key TEXT NOT NULL,
  command TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  run_id INTEGER,
  status TEXT NOT NULL,
  requested_at TEXT NOT NULL,
  sent_at TEXT,
  acknowledged_at TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0,
  raw_response TEXT,
  error TEXT,

  FOREIGN KEY (device_id) REFERENCES hardware_devices(id),
  FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE INDEX idx_relay_actions_status ON relay_actions(status);
CREATE INDEX idx_relay_actions_run ON relay_actions(run_id);
```

Relay action statuses:

```text
REQUESTED
SENT
ACKNOWLEDGED
FAILED
TIMEOUT
CANCELLED
```

### 9.11 `system_events`

System events are append-only software diagnostics. They should survive restarts and avoid losing critical error context.

Key resilience features:

- `event_id` supports idempotent writes from retrying services.
- `severity_rank` supports quick filtering.
- `acknowledged_at` allows admin screens to hide handled alarms without deleting them.
- `retention_class` allows pruning noisy events while keeping important faults.

```sql
CREATE TABLE system_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT UNIQUE,
  level TEXT NOT NULL,
  severity_rank INTEGER NOT NULL,
  category TEXT NOT NULL,
  source TEXT,
  message TEXT NOT NULL,
  payload_json TEXT,
  request_id TEXT,
  retention_class TEXT NOT NULL DEFAULT 'NORMAL',
  acknowledged_at TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_system_events_created_at ON system_events(created_at);
CREATE INDEX idx_system_events_category ON system_events(category);
CREATE INDEX idx_system_events_level ON system_events(level);
CREATE INDEX idx_system_events_ack ON system_events(acknowledged_at);
```

System event levels:

```text
DEBUG
INFO
WARNING
ERROR
CRITICAL
```

System event categories:

```text
SERVER
DATABASE
TIMER
QUEUE
HARDWARE
WEBSOCKET
API
BACKUP
CONFIG
RECOVERY
```

Retention classes:

```text
VERBOSE
NORMAL
IMPORTANT
PERMANENT
```

### 9.12 `settings`

Settings must be resilient because a bad config can stop the system from starting correctly.

Key resilience features:

- `version` supports optimistic concurrency.
- `schema_version` allows future settings migrations.
- `pending_value_json` allows staged settings before applying them.
- `last_good_value_json` allows rollback after validation failure.
- `validation_status` and `validation_error` make bad settings visible to the admin UI.

```sql
CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  value_type TEXT,
  schema_version INTEGER NOT NULL DEFAULT 1,
  version INTEGER NOT NULL DEFAULT 1,

  pending_value_json TEXT,
  last_good_value_json TEXT,
  default_value_json TEXT,

  validation_status TEXT NOT NULL DEFAULT 'VALID',
  validation_error TEXT,

  updated_at TEXT NOT NULL,
  updated_by TEXT
);

CREATE INDEX idx_settings_validation_status ON settings(validation_status);
```

Validation statuses:

```text
VALID
PENDING
INVALID
ROLLED_BACK
```

Recommended settings keys:

```text
system.site_name
system.timezone
system.active_session_id
system.data_retention_days
system.auto_backup_enabled
system.auto_backup_interval_minutes

timer.default_mode
timer.allow_anonymous_runner
timer.countdown_seconds
timer.false_start_enabled
timer.recovery_policy
timer.max_run_seconds

leaderboard.scope
leaderboard.unique_athletes
leaderboard.default_course_revision_mode

hardware.active_transport
hardware.active_device_key
hardware.serial_port
hardware.serial_baud
hardware.mqtt_host
hardware.mqtt_port
hardware.mqtt_topic_prefix
hardware.heartbeat_timeout_seconds
hardware.input_debounce_ms

theme.logo_path
theme.primary_color
theme.accent_color
```

Settings service rules:

- Validate settings before applying them.
- If validation fails, keep `value_json` unchanged and write the rejected value to `pending_value_json` with `validation_status = INVALID`.
- When a setting is successfully applied, copy the old value to `last_good_value_json`, clear `pending_value_json`, increment `version`, and set `validation_status = VALID`.
- Startup must fall back to `last_good_value_json` or `default_value_json` if the current value is invalid.
- Settings writes should be atomic and recorded in `admin_audit_log` when that table is enabled.

### 9.13 `admin_audit_log`

Admin audit records are useful for local accountability and troubleshooting.

```sql
CREATE TABLE admin_audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  target_type TEXT,
  target_id INTEGER,
  request_id TEXT,
  payload_json TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_admin_audit_log_created_at ON admin_audit_log(created_at);
CREATE INDEX idx_admin_audit_log_target ON admin_audit_log(target_type, target_id);
```

Actor examples:

```text
ADMIN
KIOSK
SYSTEM
API
```

### 9.14 Recommended MVP Tables

The first backend build should include these tables immediately:

```text
athletes
courses
course_revisions
sessions
queue_entries
runs
hardware_devices
hardware_events
relay_actions
system_events
settings
admin_audit_log
```

`run_splits` may be included immediately if checkpoint sensors are likely. Otherwise it can wait until phase two.
---

## 10. API Design

Base path:

```text
/api/v1
```

All responses should be JSON.

Common success wrapper:

```json
{
  "ok": true,
  "data": {}
}
```

Common error wrapper:

```json
{
  "ok": false,
  "error": {
    "code": "INVALID_STATE",
    "message": "Cannot start timer from FINISHED state."
  }
}
```

### 10.1 Status API

#### `GET /api/v1/status`

Returns system health.

Response:

```json
{
  "ok": true,
  "data": {
    "server_time": "2026-06-20T19:45:12-06:00",
    "version": "0.1.0",
    "database": "online",
    "arduino_connected": true,
    "serial_port": "COM4",
    "timer_state": "IDLE",
    "mode": "OPEN_GYM"
  }
}
```

---

## 11. Timer API

### 11.1 `GET /api/v1/timer/state`

Returns the current timer state.

Response:

```json
{
  "ok": true,
  "data": {
    "state": "RUNNING",
    "elapsed_ms": 18420,
    "started_at": "2026-06-20T19:45:00-06:00",
    "runner": {
      "id": 12,
      "name": "JAXSON",
      "age_group": "9-11"
    },
    "course": {
      "id": 1,
      "slug": "speed-gauntlet",
      "name": "Speed Gauntlet"
    },
    "mode": "OPEN_GYM"
  }
}
```

### 11.2 `POST /api/v1/timer/arm`

Arms the system for the next run.

Request:

```json
{
  "queue_entry_id": 55,
  "course_id": 1,
  "mode": "OPEN_GYM"
}
```

Notes:

- If `queue_entry_id` is omitted, use the first waiting queue entry.
- If the queue is empty, allow a manual anonymous runner only if enabled in settings.

### 11.3 `POST /api/v1/timer/start`

Starts timing manually from admin or hardware.

Request:

```json
{
  "source": "ADMIN"
}
```

### 11.4 `POST /api/v1/timer/finish`

Finishes the active run.

Request:

```json
{
  "source": "ADMIN"
}
```

### 11.5 `POST /api/v1/timer/stop`

Stops a run without marking it as a normal valid finish.

Request:

```json
{
  "status": "MANUAL_STOPPED",
  "source": "ADMIN",
  "notes": "Stopped by staff."
}
```

### 11.6 `POST /api/v1/timer/reset`

Resets timer to IDLE.

Request:

```json
{
  "clear_active_runner": true
}
```

### 11.7 `POST /api/v1/timer/dnf`

Marks current run as did-not-finish.

Request:

```json
{
  "notes": "Runner fell on obstacle 3."
}
```

### 11.8 `POST /api/v1/timer/delete-last-run`

Soft-deletes the most recent run.

Request:

```json
{
  "reason": "Accidental button press"
}
```

---

## 12. Queue API

Queue API requests should be idempotent where practical. Kiosk and admin clients should send a `request_id` UUID on create/update actions so browser retries do not create duplicate runners.

### 12.1 `GET /api/v1/queue`

Returns active queue.

Query params:

```text
session_id=1
status=WAITING
limit=50
```

Response:

```json
{
  "ok": true,
  "data": [
    {
      "id": 55,
      "request_id": "kiosk-20260620-abc123",
      "position": 1,
      "sort_key": 1000,
      "version": 3,
      "athlete_id": 12,
      "runner_name": "ELLIOT",
      "age_group": "9-11",
      "course": {
        "id": 1,
        "slug": "speed-gauntlet",
        "name": "Speed Gauntlet"
      },
      "course_revision": {
        "id": 7,
        "revision_code": "speed-gauntlet-2026-06-20-to-open",
        "revision_start_date": "2026-06-20",
        "revision_end_date": null
      },
      "mode": "OPEN_GYM",
      "status": "WAITING"
    }
  ]
}
```

### 12.2 `POST /api/v1/queue`

Adds a runner to the queue.

Request:

```json
{
  "request_id": "kiosk-20260620-abc123",
  "session_id": 1,
  "name": "RILEY",
  "age_group": "9-11",
  "course_id": 1,
  "course_revision_id": 7,
  "mode": "OPEN_GYM"
}
```

Behavior:

- Normalize name for lookup.
- Create athlete if not found and if athlete persistence is enabled.
- If `course_revision_id` is omitted, use the active open revision for the selected course.
- Add queue entry at the end using the next `sort_key`.
- If `request_id` already exists, return the existing queue entry.
- Broadcast queue update.

### 12.3 `PATCH /api/v1/queue/{queue_entry_id}`

Updates queue entry. Clients should include the current `version` to prevent overwriting someone else's edit.

Request examples:

```json
{
  "request_id": "admin-20260620-move-001",
  "version": 3,
  "position": 2
}
```

```json
{
  "request_id": "admin-20260620-skip-001",
  "version": 3,
  "status": "SKIPPED"
}
```

Behavior:

- Reject stale updates with `409 Conflict` if the supplied `version` does not match.
- Increment `version` after successful update.
- Write admin action to `admin_audit_log`.
- Broadcast queue update.

### 12.4 `POST /api/v1/queue/recover`

Runs queue recovery after a restart or operator request.

Request:

```json
{
  "policy": "RETURN_ACTIVE_TO_WAITING"
}
```

Policy values:

```text
RETURN_ACTIVE_TO_WAITING
MARK_ACTIVE_ERROR
LEAVE_UNCHANGED
```

### 12.5 `DELETE /api/v1/queue/{queue_entry_id}`

Cancels/removes queue entry. This should soft-cancel the entry by setting `status = CANCELLED`; it should not delete the row.
---

## 13. Runs API

### 13.1 `GET /api/v1/runs/recent`

Query params:

```text
limit=10
session_id=1
course_id=1
course_revision_id=7
mode=OPEN_GYM
status=VALID
```

### 13.2 `GET /api/v1/runs/{run_id}`

Returns one run, including course and course revision snapshots.

### 13.3 `PATCH /api/v1/runs/{run_id}`

Allows staff correction of name, age group, notes, or status.

Staff edits should:

- Preserve the original hardware timing fields.
- Update snapshot fields only when the staff correction explicitly changes display text.
- Write to `admin_audit_log`.
- Broadcast leaderboard and recent-results updates.

### 13.4 `DELETE /api/v1/runs/{run_id}`

Soft-deletes a run by setting `status = DELETED`, `deleted_at`, and `deleted_reason`.

### 13.5 `GET /api/v1/runs/export.csv`

Exports run history.

Query params:

```text
from=2026-06-01
to=2026-06-30
session_id=1
course_id=1
course_revision_id=7
status=VALID
```

---

## 14. Leaderboard API

Leaderboards should filter by course revision by default because the course changes frequently.

### 14.1 `GET /api/v1/leaderboards/today`

Query params:

```text
course_id=1
course_revision_id=7
age_group=9-11
limit=10
```

Returns best valid runs for the current local day.

### 14.2 `GET /api/v1/leaderboards/all-time`

Query params:

```text
course_id=1
course_revision_id=7
age_group=9-11
limit=10
```

If `course_revision_id` is omitted, behavior is controlled by `leaderboard.default_course_revision_mode`.

Recommended values:

```text
CURRENT_REVISION_ONLY
ALL_REVISIONS_FOR_COURSE
EXPLICIT_ONLY
```

Default should be `CURRENT_REVISION_ONLY`.

### 14.3 `GET /api/v1/leaderboards/personal-bests`

Query params:

```text
athlete_id=12
course_id=1
course_revision_id=7
limit=10
```

### 14.4 Leaderboard Rules

- Only `VALID` runs count by default.
- Soft-deleted runs are excluded.
- Course-revision leaderboards are the default fair comparison mode.
- Course-level leaderboards across multiple revisions must be clearly labeled as "All Layouts" or similar in the UI.
- Best time per runner should be selectable:
  - `unique_athletes=true` means one result per athlete.
  - `unique_athletes=false` means show every run.
- Today means local date based on configured timezone.

---

## 15. Course API

### 15.1 `GET /api/v1/courses`

Returns active courses and their active/open revisions.

### 15.2 `POST /api/v1/courses`

Creates course and optionally creates its first open course revision.

Request:

```json
{
  "slug": "speed-gauntlet",
  "name": "Speed Gauntlet",
  "description": "Main timed speed course",
  "create_initial_revision": true,
  "revision_start_date": "2026-06-20",
  "revision_name": "Speed Gauntlet - 2026-06-20"
}
```

### 15.3 `PATCH /api/v1/courses/{course_id}`

Updates course metadata. This should not change historical run snapshots.

### 15.4 `DELETE /api/v1/courses/{course_id}`

Soft-disable course, do not destroy historical data.

### 15.5 `GET /api/v1/courses/{course_id}/revisions`

Returns revisions for a course.

### 15.6 `POST /api/v1/courses/{course_id}/revisions`

Creates a new course revision. If `close_current_revision = true`, close the current open revision by setting its `revision_end_date` to the new revision's `revision_start_date`.

Request:

```json
{
  "revision_start_date": "2026-06-27",
  "revision_end_date": null,
  "revision_name": "Speed Gauntlet - 2026-06-27",
  "description": "Updated weekly layout",
  "obstacle_count": 8,
  "layout_notes": "Added salmon ladder station and changed final balance obstacle.",
  "leaderboard_eligible": true,
  "close_current_revision": true
}
```

Backend-generated `revision_code` example:

```text
speed-gauntlet-2026-06-27-to-open
```

### 15.7 `PATCH /api/v1/course-revisions/{course_revision_id}`

Updates revision metadata. If the revision already has runs, avoid changing date boundaries unless staff explicitly confirms the leaderboard impact.

### 15.8 `POST /api/v1/course-revisions/{course_revision_id}/close`

Closes a currently open revision.

Request:

```json
{
  "revision_end_date": "2026-07-04"
}
```
---

## 16. Settings API

### 16.1 `GET /api/v1/settings`

Returns editable settings with validation metadata.

Example:

```json
{
  "ok": true,
  "data": {
    "system.site_name": {
      "value": "Dynasty Ninja Training Center",
      "version": 4,
      "validation_status": "VALID"
    },
    "system.timezone": {
      "value": "America/Regina",
      "version": 2,
      "validation_status": "VALID"
    },
    "timer.default_mode": {
      "value": "OPEN_GYM",
      "version": 7,
      "validation_status": "VALID"
    },
    "leaderboard.default_course_revision_mode": {
      "value": "CURRENT_REVISION_ONLY",
      "version": 1,
      "validation_status": "VALID"
    },
    "hardware.active_transport": {
      "value": "USB_SERIAL",
      "version": 5,
      "validation_status": "VALID"
    }
  }
}
```

### 16.2 `PATCH /api/v1/settings`

Updates settings. The client should include the current `version` for every setting it changes.

Request:

```json
{
  "request_id": "admin-settings-20260620-001",
  "changes": {
    "timer.countdown_seconds": {
      "value": 3,
      "version": 2
    },
    "hardware.active_transport": {
      "value": "MQTT",
      "version": 5
    }
  },
  "apply_immediately": true
}
```

Behavior:

- Validate every changed setting before applying it.
- Reject stale versions with `409 Conflict`.
- Apply changes atomically where possible.
- If validation fails, leave the active `value_json` unchanged and store the attempted value in `pending_value_json`.
- Write failures to `system_events` with category `CONFIG`.
- Write successful changes to `admin_audit_log`.
- Broadcast `settings.updated` over WebSocket.

### 16.3 `POST /api/v1/settings/{key}/rollback`

Rolls a setting back to `last_good_value_json`.

Request:

```json
{
  "request_id": "admin-settings-rollback-001",
  "reason": "MQTT broker unavailable"
}
```

### 16.4 `POST /api/v1/settings/validate`

Validates a proposed settings payload without applying it.

Request:

```json
{
  "changes": {
    "hardware.mqtt_host": {
      "value": "192.168.1.55"
    }
  }
}
```

Response:

```json
{
  "ok": true,
  "data": {
    "valid": true,
    "errors": []
  }
}
```
---

## 17. Hardware API

### 17.1 `GET /api/v1/hardware/status`

Returns active I/O controller health, regardless of whether the controller is an Arduino Mega 2560 over USB serial or an M5Stamp-style Wi-Fi controller.

Response:

```json
{
  "ok": true,
  "data": {
    "connected": true,
    "driver": "arduino_serial",
    "device_model": "Arduino Mega 2560",
    "port": "COM4",
    "ip_address": null,
    "last_message_at": "2026-06-20T19:45:10-06:00",
    "inputs": {
      "START": "UP",
      "FINISH": "UP",
      "ARM": "UP",
      "RESET": "UP"
    },
    "outputs": {
      "HORN": "OFF",
      "GREEN": "ON",
      "RED": "OFF",
      "FX": "OFF"
    }
  }
}
```

### 17.2 `POST /api/v1/hardware/relay`

Manual relay command for diagnostics.

Request:

```json
{
  "device": "HORN",
  "action": "PULSE",
  "value_ms": 200
}
```

### 17.3 `POST /api/v1/hardware/reconnect`

Forces the active hardware transport to reconnect. For Arduino this reopens the serial port. For M5Stamp this reconnects MQTT/HTTP status handling and clears stale health state.

---

## 18. WebSocket API

Endpoint:

```text
WS /api/v1/ws/live
```

The WebSocket pushes live state changes to all connected clients.

### 18.1 Message Envelope

```json
{
  "type": "timer.state",
  "sent_at": "2026-06-20T19:45:12-06:00",
  "data": {}
}
```

### 18.2 Server-to-Client Events

#### `timer.state`

Broadcast whenever timer state or elapsed time changes meaningfully.

```json
{
  "type": "timer.state",
  "data": {
    "state": "RUNNING",
    "elapsed_ms": 18420,
    "runner": {
      "id": 12,
      "name": "JAXSON",
      "age_group": "9-11"
    },
    "course": {
      "id": 1,
      "slug": "speed-gauntlet",
      "name": "Speed Gauntlet"
    },
    "mode": "OPEN_GYM"
  }
}
```

#### `queue.updated`

Broadcast when queue changes.

#### `run.saved`

Broadcast when a run is saved.

#### `leaderboard.updated`

Broadcast after valid run save, correction, or deletion.

#### `hardware.status`

Broadcast when Arduino connects/disconnects or I/O state changes.

#### `system.toast`

Optional UI toast message.

```json
{
  "type": "system.toast",
  "data": {
    "level": "info",
    "message": "Run saved: JAXSON 00:18.42"
  }
}
```

### 18.3 Client-to-Server Messages

Version 1 clients should use HTTP POST for commands, not WebSocket. WebSocket is server-push only at first. This prevents accidental duplicate command paths.

---

## 19. Static Asset Hosting

FastAPI serves the web frontend and assets.

Routes:

```text
/                  -> redirect to /display or serve index shell
/display           -> TV scoreboard view
/admin             -> staff dashboard view
/kiosk             -> runner check-in view
/assets/*          -> static assets
/api/v1/*          -> JSON API
/api/v1/ws/live    -> WebSocket
```

During the single-page version, the frontend can use hash or tab routing:

```text
/#display
/#admin
/#kiosk
```

Later, the server can still serve the same SPA for each route.

---

## 20. Configuration

Use `config/settings.yaml`.

Example:

```yaml
facility:
  name: Dynasty Ninja Training Center
  timezone: America/Regina

server:
  host: 0.0.0.0
  port: 8000
  reload: false

frontend:
  default_route: /display
  asset_cache_seconds: 3600

hardware:
  driver: arduino_serial   # arduino_serial | m5stamp_mqtt | m5stamp_http | simulated

serial:
  port: AUTO
  baud: 115200
  heartbeat_timeout_ms: 5000
  reconnect_interval_ms: 3000

m5stamp:
  device_id: m5stamp-main
  transport: mqtt
  host: 192.168.10.50
  mqtt_broker: 127.0.0.1
  mqtt_port: 1883
  heartbeat_timeout_ms: 5000
  reconnect_interval_ms: 3000

hardware_io:
  required_inputs:
    - START
    - FINISH
  outputs:
    horn: HORN
    green_light: GREEN
    red_light: RED
    fx: FX

timer:
  default_mode: OPEN_GYM
  default_course_slug: speed-gauntlet
  allow_anonymous_runner: true
  countdown_seconds: 3
  false_start_enabled: false
  minimum_valid_time_ms: 1000
  finish_debounce_ms: 250
  start_debounce_ms: 100

leaderboard:
  default_limit: 10
  unique_athletes: true

backup:
  enabled: true
  interval_hours: 24
  keep_days: 30
```

---

## 21. Service Responsibilities

### 21.1 TimerService

- Owns active timer state.
- Accepts commands from API and hardware.
- Validates state transitions.
- Starts/stops timing using monotonic clock.
- Saves valid and invalid runs.
- Triggers relay effects through RelayService.
- Broadcasts timer changes through EventBus.

### 21.2 QueueService

- Adds runners to queue.
- Promotes next runner.
- Reorders queue.
- Cancels/skips runners.
- Marks queue entries completed.

### 21.3 LeaderboardService

- Calculates today, all-time, and personal bests.
- Filters by course, age group, date, and mode.
- Excludes deleted/invalid runs.

### 21.4 SerialManager

- Finds Arduino serial port.
- Opens and maintains serial connection.
- Parses incoming lines.
- Emits hardware events to EventBus.
- Sends relay/output commands.
- Handles reconnects.

### 21.5 EventBus

- In-process publish/subscribe hub.
- Decouples timer, serial, database, and WebSocket layers.
- Broadcasts events to WebSocket clients.

### 21.6 SettingsService

- Loads YAML and database settings.
- Allows runtime setting updates.
- Persists operator-configurable values.
- Validates settings before applying them.
- Supports version checks, pending values, rollback to last-good values, and startup fallback.

### 21.7 CourseService

- Creates and updates course families.
- Creates date-bounded course revisions.
- Closes the current open revision when a new layout starts.
- Ensures leaderboards default to the active course revision.
- Prevents accidental historical leaderboard changes when old revision dates are edited.

---

## 22. Hardware Event Handling

Example flow for finish button:

```text
Arduino sends EVT,FINISH,DOWN
  -> SerialManager parses event
  -> Hardware event written to hardware_events
  -> TimerService receives finish trigger
  -> TimerService validates state == RUNNING
  -> TimerService calculates elapsed_ms
  -> TimerService creates run record
  -> RelayService pulses finish horn/chime
  -> EventBus broadcasts timer.state, run.saved, leaderboard.updated
  -> TV/admin/kiosk update instantly
```

Input events should be debounced both in Arduino firmware and backend logic.

Backend debounce should reject repeated finish/start events inside configured windows.

Hardware event resilience rules:

- Store raw events before processing when possible.
- Use `event_id` and `sequence_number` to prevent duplicate processing.
- Mark event rows as `PROCESSED`, `DUPLICATE`, `IGNORED`, or `ERROR`.
- On backend startup, inspect `PENDING` hardware events and either process or mark them ignored based on age and recovery policy.
- If the hardware device heartbeat is stale, block new runs unless `hardware.allow_degraded_mode` is enabled.

---

## 23. Error Handling

### 23.1 API Error Codes

```text
INVALID_STATE
NOT_FOUND
VALIDATION_ERROR
HARDWARE_DISCONNECTED
SERIAL_ERROR
DATABASE_ERROR
CONFIG_ERROR
UNAUTHORIZED
```

### 23.2 Invalid State Example

```json
{
  "ok": false,
  "error": {
    "code": "INVALID_STATE",
    "message": "Cannot finish because the timer is not running."
  }
}
```

### 23.3 Hardware Disconnected Example

```json
{
  "ok": false,
  "error": {
    "code": "HARDWARE_DISCONNECTED",
    "message": "Arduino I/O controller is not connected. Manual mode is still available."
  }
}
```

---

## 24. Logging

Use structured logs.

Log categories:

```text
server
api
timer
serial
hardware
database
websocket
settings
```

Recommended log files:

```text
data/logs/server.log
data/logs/timer.log
data/logs/hardware.log
```

Important events should also go to `system_events` table.

---

## 25. Backup and Export

### 25.1 Database Backup

- Copy SQLite database to `data/backups` daily.
- Keep last 30 days by default.
- Backup filename format:

```text
dynasty_ninja_timer_YYYY-MM-DD_HHMMSS.sqlite
```

### 25.2 CSV Export

CSV columns:

```text
run_id,runner_name,age_group,course,mode,status,started_at,finished_at,elapsed_ms,elapsed_display,source,notes
```

---

## 26. Authentication

Version 1 can use simple local admin PIN/password.

Recommended:

- `/display` public on LAN
- `/kiosk` public on LAN
- `/admin` requires PIN/password
- API write routes require admin session except check-in queue route

Future:

- User accounts
- Roles: admin, coach, kiosk, display
- Audit log for edits/deletions

---

## 27. Frontend Integration Contract

The current single-page UI prototype should eventually replace mock data with the following client behavior:

### 27.1 Initial Load

On page load:

```text
GET /api/v1/status
GET /api/v1/timer/state
GET /api/v1/queue
GET /api/v1/runs/recent?limit=10
GET /api/v1/leaderboards/today
GET /api/v1/leaderboards/all-time
WS  /api/v1/ws/live
```

### 27.2 Commands

Admin buttons call:

```text
POST /api/v1/timer/arm
POST /api/v1/timer/start
POST /api/v1/timer/finish
POST /api/v1/timer/stop
POST /api/v1/timer/reset
POST /api/v1/timer/delete-last-run
```

Kiosk check-in calls:

```text
POST /api/v1/queue
```

### 27.3 Live Updates

All screens listen to WebSocket messages and patch local state.

The display screen should not poll rapidly. It can animate the running timer locally between server updates, but server state remains authoritative.

---

## 28. Development Milestones

### Milestone 1: Backend Skeleton

- FastAPI app starts.
- Serves static prototype.
- SQLite connection works.
- Status endpoint works.
- Basic config loading works.

### Milestone 2: Database Models

- Add SQLAlchemy models.
- Add Alembic migrations.
- Seed default courses, first course revisions, settings, and active open-gym session.
- CRUD for courses, course revisions, athletes, sessions, queue, and runs.
- Add idempotent `request_id` handling for queue, settings, hardware events, relay actions, and audit actions.

### Milestone 3: Timer State Machine

- Implement pure Python state machine.
- Unit test all state transitions.
- Add API commands for arm/start/finish/reset.
- Save finished runs.

### Milestone 4: WebSocket Live Updates

- Add `/api/v1/ws/live`.
- Broadcast timer, queue, and leaderboard updates.
- Update frontend `ApiClient` to use real API.

### Milestone 5: Hardware Integration

- Implement SerialManager for Arduino Mega 2560.
- Parse Arduino events.
- Implement Wi-Fi/MQTT or HTTP hardware driver for M5Stack StamPLC / M5Stamp PLC-style controller.
- Normalize all hardware inputs to the shared event model.
- Map inputs to timer commands.
- Send relay commands and log `relay_actions`.
- Add hardware status endpoint and heartbeat monitoring.

### Milestone 6: Production Startup and Recovery

- Add Windows startup script or service.
- Add browser kiosk launch script.
- Add logging and backups.
- Enable SQLite WAL, foreign keys, and backup verification.
- Add recovery behavior after reboot for active runs, active queue entries, pending hardware events, stale hardware devices, and invalid settings.

### Milestone 7: Gym Polish

- Add admin PIN.
- Add CSV export.
- Add run correction/delete flow.
- Add better diagnostics screen.
- Add sound/effect profiles.

---

## 29. Testing Plan

### 29.1 Unit Tests

- Timer state transitions
- Invalid transition rejection
- Time calculation
- Queue ordering
- Queue idempotency and optimistic concurrency
- Course revision date rollover and leaderboard filtering
- Leaderboard filtering
- Settings validation, rollback, and stale version rejection
- Hardware event idempotency and sequence gap detection
- Serial line parser
- Debounce logic

### 29.2 Integration Tests

- API arm/start/finish creates a valid run.
- Queue runner becomes active on arm.
- Finished run updates leaderboard.
- Deleted run disappears from leaderboard.
- WebSocket receives timer update after command.

### 29.3 Hardware Simulation Tests

Create a fake serial input stream for:

```text
READY
EVT,ARM,DOWN
EVT,START,DOWN
EVT,FINISH,DOWN
HEARTBEAT,1000
```

Expected result:

- Timer arms.
- Timer starts.
- Timer finishes.
- Run is saved.
- Relay finish command is sent.

### 29.4 Manual Acceptance Tests

- Start and finish with physical buttons.
- Reset during idle.
- Reset during running.
- Disconnect Arduino and verify UI fault.
- Reconnect Arduino and verify recovery.
- Add runner from kiosk.
- Delete accidental run.
- Export CSV.
- Reboot PC and verify system auto-starts.

---

## 30. Production Startup Design

### 30.1 Windows Startup

Recommended startup sequence:

1. Auto-login to dedicated `Timer` Windows user.
2. Start backend with a scheduled task.
3. Launch browser in kiosk mode to `/display`.
4. Backend connects to Arduino.
5. Display shows system status.

Example browser launch:

```bat
start msedge --kiosk http://localhost:8000/display --edge-kiosk-type=fullscreen
```

### 30.2 Backend Command

```bat
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For production, use a packaged executable or scheduled task pointing at a virtual environment.

---

## 31. Version 1 Definition of Done

Version 1 is ready for gym testing when:

- Backend starts reliably on the SFF PC.
- TV display loads from local server.
- Admin dashboard can arm/start/finish/reset.
- Kiosk can add runner to queue.
- Hardware button events start and finish runs from either Arduino serial or M5Stamp Wi-Fi transport.
- Runs save to SQLite.
- Today leaderboard updates after each valid run.
- Recent results table updates.
- Hardware disconnect is visible on UI for either Arduino or M5Stamp transport.
- Database backup can be created.
- System recovers cleanly after reboot.

---

## 32. Future Expansion Ideas

- Multi-lane timing
- RFID/NFC check-in
- Public QR-code leaderboard
- Event/session management
- Age-division competition exports
- Cloud backup
- SMS/email results
- Photo finish snapshot
- OBS/broadcast overlay
- Mobile spectator view
- Coach notes per athlete

---

## 33. Implementation Notes

### 33.1 Keep Timing Logic Backend-Owned

The frontend can animate elapsed time for smooth visuals, but the backend must own official elapsed time.

### 33.2 Keep Hardware Dumb

The Arduino or M5Stamp controller should only report inputs and actuate outputs. It should not own run validity, leaderboard logic, or queue logic. The one exception is local output fail-safe behavior, such as turning relays off on lost connection.

### 33.3 Store Snapshots on Runs

Always store runner name, age group, and course name snapshots on the run. If an athlete profile or course name changes later, historical results should still display correctly.

### 33.4 Prefer Soft Deletes

Do not permanently delete runs through normal admin actions. Use `deleted_at` and status `DELETED` so mistakes can be recovered.

### 33.5 Design for No Internet

The system must boot, run, display, time, save, and export without internet access.

---

## 34. First Backend Implementation Order

Recommended coding order:

1. Create FastAPI app shell.
2. Serve the existing single-page HTML prototype.
3. Add config loader.
4. Add SQLite and SQLAlchemy models.
5. Seed settings and default courses.
6. Implement TimerStateMachine as a pure Python class.
7. Implement TimerService and API routes.
8. Implement queue and leaderboard APIs.
9. Implement WebSocket manager.
10. Update frontend `ApiClient` to use real endpoints.
11. Implement serial parser with simulated lines first.
12. Add real Arduino serial connection.
13. Add M5Stamp MQTT or HTTP transport after the serial path is stable.
13. Add relay commands.
14. Add backups, logs, and startup scripts.

---

## 35. Minimal MVP API List

These routes are enough to wire the current UI to a real backend:

```text
GET    /api/v1/status
GET    /api/v1/timer/state
POST   /api/v1/timer/arm
POST   /api/v1/timer/start
POST   /api/v1/timer/finish
POST   /api/v1/timer/stop
POST   /api/v1/timer/reset
POST   /api/v1/timer/delete-last-run
GET    /api/v1/queue
POST   /api/v1/queue
DELETE /api/v1/queue/{queue_entry_id}
GET    /api/v1/runs/recent
DELETE /api/v1/runs/{run_id}
GET    /api/v1/leaderboards/today
GET    /api/v1/leaderboards/all-time
GET    /api/v1/hardware/status
POST   /api/v1/hardware/relay
WS     /api/v1/ws/live
```

This is the recommended foundation for the Python backend.
