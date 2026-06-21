# Dynasty Ninja Timer

Local-first timing backend for Dynasty Ninja courses. The project provides a FastAPI app with browser-based display, admin, and kiosk pages, plus SQLite persistence for courses, sessions, queue entries, runs, hardware events, settings, and audit logs.

## Current Features

- FastAPI application served from `app.main:app`
- Static UI pages for display, admin, and kiosk workflows
- `/api/v1/status` health endpoint with app, config, database, and hardware status
- `/api/v1/auth/login` local admin PIN session endpoint
- `/api/v1/settings` validated settings API with version checks and rollback
- `/api/v1/ops/backups`, `/api/v1/ops/logs/{filename}`, and `/api/v1/ops/system-events`
  for local gym operations
- SQLite database initialization with WAL-friendly pragmas
- Idempotent seed data for default courses and an active Open Gym session
- Queue-entry service with request-id idempotency
- CSV run export using the V1 operations column contract
- Alembic migration scaffold for persistence schema management
- Pytest coverage for database initialization, SQLite pragmas, and queue persistence

## Requirements

- Python 3.12 or newer
- PowerShell for the included development launcher on Windows

## Setup

From the repository root:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Run The App

Use the included development script:

```powershell
.\scripts\run_dev.ps1
```

For local production-style gym testing without auto-reload:

```powershell
.\scripts\run_prod.ps1
```

The display kiosk helper launches Microsoft Edge fullscreen:

```powershell
.\scripts\launch_display_kiosk.ps1
```

To register the backend at Windows logon for the current user:

```powershell
.\scripts\register_startup_task.ps1
```

To run on a different port:

```powershell
.\scripts\run_dev.ps1 -Port 9000
```

You can also start Uvicorn directly:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Once running, open:

- Display: <http://localhost:8000/display>
- Admin: <http://localhost:8000/admin>
- Kiosk: <http://localhost:8000/kiosk>
- Status API: <http://localhost:8000/api/v1/status>

The root route, `/`, serves the display page.

## Configuration

Runtime settings are loaded from [config/settings.yaml](config/settings.yaml). Environment variables can override a few defaults before the YAML file is merged:

- `DEBUG`: enables debug mode when set to `true`
- `PORT`: default server port used by settings
- `RELOAD`: enables reload mode when set to `true`
- `ADMIN_PIN`: local admin PIN for protected operations
- `ADMIN_TOKEN_SECRET`: secret used to sign admin session tokens
- `ADMIN_SESSION_SECONDS`: admin token lifetime
- `BACKUP_RETENTION_DAYS`: database backup retention window

For any real gym deployment, change the default `ADMIN_PIN` before exposing admin pages or APIs on the LAN. The app logs a warning when the development PIN is still active.

The default database is:

```text
sqlite:///./data/dynasty_ninja_timer.sqlite
```

Data directories are created automatically under `data/` when the app starts.

## Database

The app initializes the SQLite database at startup and creates missing tables through SQLAlchemy metadata. It also seeds:

- `speed-gauntlet`
- `ninja-challenge`
- one active Open Gym session

Alembic is configured through [alembic.ini](alembic.ini), with migrations under [app/db/migrations](app/db/migrations).

Common migration commands:

```powershell
alembic upgrade head
alembic revision --autogenerate -m "describe change"
```

## Tests

Run the test suite with:

```powershell
pytest
```

Optional quality checks:

```powershell
ruff check .
black --check .
mypy app
```

## Release Readiness

See [docs/V1_RELEASE_REVIEW.md](docs/V1_RELEASE_REVIEW.md) for the current code review, security notes, exception-handling work, memory/resource review, and v1.0 task list.

## Project Layout

```text
app/
  api/          API route modules
  db/           SQLAlchemy models, repositories, migrations, and database helpers
  services/     Course, queue, run, and leaderboard service logic
  static/       Browser pages for display, admin, and kiosk views
config/         YAML configuration
data/           Local runtime data, logs, exports, and backups
scripts/        Development helper scripts
tests/          Pytest suite
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
