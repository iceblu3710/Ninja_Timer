# Dynasty Ninja Timer Feature Roadmap for Co-Agent Generation

This roadmap translates `spec.md` and the `prototype/` assets into executable feature slices for parallel or sequential co-agent work. It assumes the backend remains authoritative for timer state, queue state, hardware state, run storage, leaderboards, and WebSocket broadcasts.

## Product Anchors

- Local-first timing system running from one Python process on an SFF PC.
- FastAPI serves API, WebSocket, and frontend static assets.
- SQLite is the permanent source of truth.
- Official timing uses backend monotonic time, not browser time.
- Hardware controllers are dumb I/O adapters. Arduino serial and M5Stamp-style Wi-Fi transports normalize to the same event model.
- UI has three primary operating surfaces from the prototypes:
  - TV scoreboard display
  - Staff admin dashboard
  - Runner check-in kiosk
- The existing HTML prototype already has an `ApiClient` boundary and mock data that should be replaced incrementally with real API calls and WebSocket updates.

## Roadmap Strategy

Build the system in vertical slices, not isolated layers. Each phase should leave the app runnable from the browser, even if some services are backed by simulated data.

Recommended co-agent sequence:

1. Foundation Agent: project scaffold, config, app boot, static hosting.
2. Data Agent: SQLite schema, migrations, seed data, repositories.
3. Timer Agent: state machine, timer service, API commands.
4. Frontend Integration Agent: replace prototype mocks with real API and WebSocket state.
5. Hardware Agent: simulated hardware first, then Arduino serial, then M5Stamp Wi-Fi.
6. Operations Agent: logs, backups, auth, startup scripts, recovery.
7. QA Agent: unit, integration, hardware simulation, and manual acceptance coverage.

## Phase 0: Repository and Prototype Intake

Goal: make the current prototype and spec easy for future agents to consume.

Tasks:

- Preserve `spec.md` as the contract source.
- Move or copy `prototype/dynasty_ninja_timer_ui_showcase.html` into the future static asset path without changing behavior.
- Keep the three PNG prototype references available as visual acceptance references for display, admin, and kiosk polish.
- Document the active routes:
  - `/display`
  - `/admin`
  - `/kiosk`
  - `/api/v1/*`
  - `/api/v1/ws/live`

Acceptance criteria:

- A developer can open the prototype locally and identify the three required screens.
- The roadmap and spec clearly agree that no official timer state lives only in browser memory.

## Phase 1: Backend Skeleton and Static Hosting

Goal: a runnable FastAPI app that serves the UI shell and responds to health checks.

Primary files to generate:

- `app/main.py`
- `app/config.py`
- `app/logging_config.py`
- `app/api/routes_status.py`
- `app/static/`
- `config/settings.yaml`
- `pyproject.toml`
- `scripts/run_dev.ps1`

Feature tasks:

- Create FastAPI app factory or module-level `app`.
- Serve static assets through FastAPI.
- Redirect `/` to `/display`.
- Serve the same frontend shell at `/display`, `/admin`, and `/kiosk`.
- Add `GET /api/v1/status`.
- Load settings from `config/settings.yaml`.
- Create data directories on startup: `data/`, `data/backups/`, `data/exports/`, `data/logs/`.

Acceptance criteria:

- `python -m uvicorn app.main:app --reload` starts successfully.
- `/api/v1/status` returns app, config, database placeholder, and hardware placeholder status.
- `/display`, `/admin`, and `/kiosk` load the prototype shell from the backend.

Suggested tests:

- Status endpoint smoke test.
- Static route smoke test.
- Config default loading test.

## Phase 2: Database Core

Goal: durable SQLite storage for the entities needed by the MVP UI and timer flow.

Primary files to generate:

- `app/db/database.py`
- `app/db/models.py`
- `app/db/schemas.py`
- `app/db/repositories.py`
- `app/db/migrations/`
- `app/services/course_service.py`
- `app/services/queue_service.py`
- `app/services/run_service.py`
- `app/services/leaderboard_service.py`

MVP tables:

- `athletes`
- `courses`
- `course_revisions`
- `sessions`
- `queue_entries`
- `runs`
- `hardware_devices`
- `hardware_events`
- `relay_actions`
- `system_events`
- `settings`
- `admin_audit_log`

Feature tasks:

- Enable SQLite WAL, foreign keys, and busy timeout at startup.
- Add SQLAlchemy 2.x models and Alembic migrations.
- Seed default courses:
  - `speed-gauntlet`
  - `ninja-challenge`
- Seed first open course revision for each default course.
- Seed active Open Gym session.
- Store run snapshots for runner name, age group, course name, mode, and course revision.
- Add idempotent request handling where the spec requires `request_id`.

Acceptance criteria:

- Database initializes from empty disk.
- Restarting the app does not duplicate seed records.
- Queue entries survive backend restart.
- Runs remain displayable after related athlete or course metadata changes.

Suggested tests:

- Migration smoke test.
- Seed idempotency test.
- Course revision open-revision service test.
- Queue persistence test.

## Phase 3: Timer State Machine and Timer API

Goal: a pure, tested timer state model exposed through HTTP commands.

Primary files to generate:

- `app/core/timer_state_machine.py`
- `app/core/clock.py`
- `app/services/timer_service.py`
- `app/api/routes_timer.py`
- `tests/test_timer_state_machine.py`
- `tests/test_api_timer.py`

Feature tasks:

- Implement states:
  - `IDLE`
  - `READY`
  - `COUNTDOWN`
  - `RUNNING`
  - `FINISHED`
  - `SAVED`
  - `FALSE_START`
  - `SENSOR_FAULT`
  - `MANUAL_STOPPED`
  - `DNF`
  - `ERROR`
- Implement commands:
  - `arm`
  - `start`
  - `finish`
  - `stop`
  - `reset`
  - `dnf`
  - `delete-last-run`
- Use `time.perf_counter_ns()` for elapsed timing.
- Save finished runs with `elapsed_ms`.
- Reject invalid state transitions with structured API errors.
- Support manual browser-only mode when hardware is disconnected.

Acceptance criteria:

- `POST /api/v1/timer/arm` moves `IDLE -> READY`.
- `POST /api/v1/timer/start` moves valid ready/manual flows to `RUNNING`.
- `POST /api/v1/timer/finish` creates a run and updates recent runs.
- Invalid finish while idle returns `INVALID_STATE`.
- Reset returns to `IDLE` without corrupting saved run history.

Suggested tests:

- All allowed transitions.
- Representative invalid transitions.
- Monotonic elapsed calculation.
- API arm/start/finish creates a valid run.

## Phase 4: Queue, Runs, and Leaderboards API

Goal: make the admin, display, and kiosk screens useful with real backend data.

Primary files to generate:

- `app/api/routes_queue.py`
- `app/api/routes_runs.py`
- `app/api/routes_leaderboards.py`
- `app/api/routes_courses.py`

Feature tasks:

- Add minimal MVP API routes:
  - `GET /api/v1/queue`
  - `POST /api/v1/queue`
  - `DELETE /api/v1/queue/{queue_entry_id}`
  - `GET /api/v1/runs/recent`
  - `DELETE /api/v1/runs/{run_id}`
  - `GET /api/v1/leaderboards/today`
  - `GET /api/v1/leaderboards/all-time`
- Promote next queued runner on arm or explicit next-runner flow.
- Soft-delete runs and exclude deleted runs from leaderboards.
- Support leaderboard filters by course, revision, age group, date, and mode where practical.
- Return response shapes that match the prototype `ApiClient` expectations or adapt the frontend client in the same slice.

Acceptance criteria:

- Kiosk can add a runner.
- Admin queue updates from persisted data.
- Display shows current runner, next up, recent runs, today best, and all-time best.
- Deleting a run removes it from leaderboards without hard deletion.

Suggested tests:

- Queue add/delete/list.
- Finished run updates leaderboard.
- Deleted run disappears from leaderboard.
- Personal best logic, if included in this phase.

## Phase 5: WebSocket Live Updates and Frontend API Wiring

Goal: replace mock prototype state with real backend state while preserving the visual direction of the prototypes.

Primary files to generate or edit:

- `app/core/event_bus.py`
- `app/api/websocket.py`
- `app/static/js/api_client.js`
- `app/static/js/state.js`
- `app/static/js/display.js`
- `app/static/js/admin.js`
- `app/static/js/kiosk.js`

Feature tasks:

- Add `WS /api/v1/ws/live`.
- Broadcast:
  - `timer.state`
  - `queue.updated`
  - `run.saved`
  - `leaderboard.updated`
  - `hardware.status`
  - `system.toast`
- Replace `new ApiClient({ mock: true })` with real API mode.
- On initial load, call:
  - `GET /api/v1/status`
  - `GET /api/v1/timer/state`
  - `GET /api/v1/queue`
  - `GET /api/v1/runs/recent?limit=10`
  - `GET /api/v1/leaderboards/today`
  - `GET /api/v1/leaderboards/all-time`
  - `WS /api/v1/ws/live`
- Let the display animate elapsed time locally only while `state == RUNNING`, correcting from server state on each update.

Prototype alignment notes:

- Keep the high-contrast purple, gold, and black brand direction from the PNG prototypes.
- The TV display should prioritize runner name, timer, state, course, age group, mode, today best, all-time best, last runs, and next up.
- The admin dashboard should prioritize control buttons, live preview, queue, recent results, course/mode/effects controls, and diagnostics.
- The kiosk should prioritize name input, age group, course selection, join queue, up-next, current leaderboard, and personal bests.

Acceptance criteria:

- A command from admin changes the display without refresh.
- A kiosk queue join appears on admin and display without refresh.
- Saved run updates recent results and leaderboards without polling.
- WebSocket reconnect logic restores state after temporary disconnect.

Suggested tests:

- WebSocket receives timer update after command.
- WebSocket receives queue update after kiosk join.
- Frontend smoke test with real API mode.

## Phase 6: Simulated Hardware Adapter

Goal: validate the hardware architecture before using physical devices.

Primary files to generate:

- `app/hardware/transport_base.py`
- `app/hardware/hardware_models.py`
- `app/hardware/debounce.py`
- `app/hardware/simulated_transport.py`
- `app/services/hardware_service.py`
- `app/services/relay_service.py`
- `app/api/routes_hardware.py`

Feature tasks:

- Define `HardwareTransport` interface.
- Define normalized events such as `EVT,START,DOWN` and `EVT,FINISH,DOWN`.
- Add backend debounce for start and finish inputs.
- Add `GET /api/v1/hardware/status`.
- Add `POST /api/v1/hardware/relay`.
- Add `POST /api/v1/hardware/reconnect`.
- Add a simulated driver selected by `settings.yaml`.
- Log hardware events and relay actions.

Acceptance criteria:

- Simulated `ARM`, `START`, and `FINISH` events drive the timer.
- Duplicate start/finish events inside debounce windows are ignored.
- Hardware status broadcasts over WebSocket.
- Relay commands are recorded even when simulated.

Suggested tests:

- Hardware event parser/normalizer tests.
- Debounce tests.
- Simulated hardware arm/start/finish integration test.

## Phase 7: Arduino Serial Integration

Goal: support the first physical bench prototype over USB serial.

Primary files to generate:

- `app/hardware/serial_manager.py`
- `app/hardware/arduino_protocol.py`
- `tests/test_serial_protocol.py`

Feature tasks:

- Connect with baud `115200`, line ending `\n`, UTF-8 compatible text.
- Parse Arduino messages:
  - `READY`
  - `HEARTBEAT,<value>`
  - `EVT,<DEVICE>,<STATE>`
- Send relay commands:
  - `CMD,HORN,PULSE,200`
  - `CMD,GREEN,ON`
  - `CMD,RED,OFF`
  - `CMD,ALL,OFF`
- Implement reconnect loop.
- Mark disconnected when heartbeat/messages are stale.
- Block strict competition mode when required hardware is unavailable.

Acceptance criteria:

- Physical or fake serial stream can arm, start, finish, and save a run.
- Disconnect appears in hardware status and UI.
- Reconnect clears stale disconnected status.
- Relay command output is visible in serial logs or fake transport assertions.

Suggested tests:

- Serial line parser.
- Fake serial stream integration.
- Heartbeat stale/disconnect test.
- Command formatting test.

## Phase 8: M5Stamp Wi-Fi Integration

Goal: add the long-term network field-box transport without changing timer logic.

Primary files to generate:

- `app/hardware/wifi_manager.py`
- `app/hardware/m5stamp_protocol.py`

Feature tasks:

- Implement either MQTT first or HTTP fallback first, based on available local infrastructure.
- Normalize M5Stamp events into the same internal event model as Arduino.
- Track `device_id`, `seq`, heartbeat, duplicate/gap detection, and command acknowledgement.
- Add settings for M5 host, broker, port, heartbeat timeout, reconnect interval.
- Ensure only one active timing I/O driver owns `START` and `FINISH` in Version 1.

Acceptance criteria:

- M5 events drive the same timer flows as Arduino events.
- Duplicate sequence numbers are logged and ignored.
- Heartbeat loss sets hardware disconnected.
- Manual browser-only mode still works when Wi-Fi hardware is disconnected.

Suggested tests:

- JSON event parser.
- Sequence duplicate/gap detection.
- HTTP ingest route, if HTTP fallback is implemented.
- MQTT topic/payload contract tests, if MQTT is implemented.

## Phase 9: Admin Settings, Auth, Diagnostics, and Course Operations

Goal: make staff operations serviceable in a gym environment.

Primary files to generate:

- `app/api/routes_settings.py`
- `app/services/settings_service.py`
- auth/session helpers
- diagnostics frontend view or admin panel expansion

Feature tasks:

- Add local admin PIN/password for `/admin` and API write routes.
- Keep `/display` and `/kiosk` public on LAN.
- Add settings API:
  - `GET /api/v1/settings`
  - `PATCH /api/v1/settings`
  - `POST /api/v1/settings/{key}/rollback`
  - `POST /api/v1/settings/validate`
- Validate settings before applying.
- Store pending invalid values and last-good values.
- Add diagnostics for hardware, database, WebSocket clients, backups, and last system events.
- Add course and course revision management sufficient for weekly layout changes.

Acceptance criteria:

- Staff can change countdown, mode defaults, hardware driver, and facility info safely.
- Bad settings are rejected or quarantined without bricking startup.
- Admin actions are written to audit log.
- Diagnostics screen can identify disconnected hardware and stale heartbeat.

Suggested tests:

- Settings stale version conflict.
- Settings rollback.
- Auth required for write routes.
- Course revision close-and-create flow.

## Phase 10: Production Startup, Recovery, Export, and Backup

Goal: make the system reliable on the target SFF PC.

Primary files to generate:

- `scripts/install_windows_service.ps1`
- `scripts/run_dev.ps1`
- `scripts/run_dev.sh`
- `scripts/backup_db.py`
- startup documentation in `README.md`

Feature tasks:

- Add structured logs for server, timer, hardware, database, websocket, and settings.
- Add daily SQLite backup to `data/backups`.
- Add CSV export route.
- Add recovery behavior after reboot for:
  - active queue entries
  - active sessions
  - interrupted runs
  - pending hardware events
  - stale hardware devices
  - invalid settings
- Add Windows startup sequence docs:
  - dedicated `Timer` user
  - scheduled task for backend
  - browser kiosk launch to `/display`

Acceptance criteria:

- Backend starts after reboot and serves display.
- Active queue is still available after reboot.
- Interrupted running timer recovers to a safe non-running state with an audit/system event.
- Backup can be created and verified.
- CSV export includes required columns.

Suggested tests:

- Backup creation test.
- CSV export test.
- Startup recovery service test.
- Manual reboot acceptance checklist.

## Co-Agent Work Packages

Use these as independent prompts or tickets.

### Agent A: App Foundation

Scope:

- Create FastAPI app structure.
- Add config loader.
- Serve static prototype.
- Add status route.

Inputs:

- `spec.md` sections 4, 5, 19, 20, 28, 34, 35.
- `prototype/dynasty_ninja_timer_ui_showcase.html`.

Done when:

- Local dev server runs.
- `/display`, `/admin`, `/kiosk`, and `/api/v1/status` work.

### Agent B: Persistence

Scope:

- SQLAlchemy models, migrations, seed data, repositories.

Inputs:

- `spec.md` section 9.

Done when:

- Empty SQLite database initializes and seed data is idempotent.

### Agent C: Timer Core

Scope:

- Pure timer state machine.
- Timer service.
- Timer API.

Inputs:

- `spec.md` sections 7, 11, 21, 22, 33.

Done when:

- API arm/start/finish creates a persisted run with tested state transitions.

### Agent D: Queue and Leaderboards

Scope:

- Queue API, runs API, leaderboard API.
- Recent results and soft delete behavior.

Inputs:

- `spec.md` sections 12, 13, 14, 27, 35.

Done when:

- Kiosk queue joins and leaderboard updates use real persisted data.

### Agent E: WebSocket and Frontend Wiring

Scope:

- WebSocket endpoint.
- Event bus.
- Replace prototype mock client with real API client.

Inputs:

- `spec.md` sections 18, 19, 27.
- Prototype HTML script block.
- PNG references for visual targets.

Done when:

- Admin, display, and kiosk screens update live without refresh.

### Agent F: Hardware Simulation and Arduino

Scope:

- Transport interface.
- Simulated transport.
- Arduino serial manager and protocol.
- Relay service.

Inputs:

- `spec.md` sections 8, 17, 22, 29.3.

Done when:

- Fake serial stream and Arduino-compatible messages can complete a run.

### Agent G: M5Stamp Transport

Scope:

- M5Stamp HTTP or MQTT transport.
- Sequence and heartbeat handling.

Inputs:

- `spec.md` section 8.3.

Done when:

- M5Stamp events normalize to the same timer service events as Arduino.

### Agent H: Operations and Gym Readiness

Scope:

- Admin PIN.
- Settings API.
- Logs.
- Backups.
- CSV export.
- Startup scripts.
- Recovery behavior.

Inputs:

- `spec.md` sections 16, 24, 25, 26, 30, 31.

Done when:

- Version 1 definition of done is satisfied for local gym testing.

## Cross-Cutting Rules for All Agents

- Do not duplicate timer authority in frontend code.
- Do not let hardware drivers import or own timer state-machine logic.
- Do not hard-delete runs from normal admin flows.
- Do not store unnecessary child personal data.
- Do not introduce internet-only dependencies for runtime operation.
- Keep response envelopes and error codes consistent across APIs.
- Add tests near each feature slice instead of postponing all testing to the end.
- Prefer simulated hardware before requiring real physical hardware.

## Minimum MVP Build Order

1. FastAPI app shell and static prototype hosting.
2. SQLite database with seed courses, revision, session, queue, and runs.
3. Timer state machine and timer API.
4. Queue, recent runs, and leaderboard API.
5. WebSocket live updates.
6. Prototype `ApiClient` switched from mock to real API.
7. Simulated hardware transport.
8. Arduino serial transport.
9. Settings, auth, backups, CSV export, startup scripts.
10. M5Stamp transport after Arduino path is stable, unless Wi-Fi hardware is the immediate deployment target.

## Version 1 Gym-Test Definition

The system is ready for first gym testing when:

- Backend starts reliably on the local SFF PC.
- TV display loads from local server.
- Admin dashboard can arm, start, finish, stop, reset, and delete last run.
- Kiosk can add runners to the queue.
- Hardware or simulated hardware can start and finish runs.
- Runs save to SQLite.
- Today leaderboard and recent results update after each valid run.
- Hardware disconnect is visible in the UI.
- Database backup can be created.
- Reboot recovery returns the system to a safe operational state.
