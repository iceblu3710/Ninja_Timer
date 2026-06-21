"""Operational helpers for backups, exports, logs, and recovery."""

from __future__ import annotations

import json
import sqlite3
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import Settings, get_settings
from app.db.database import SessionLocal
from app.db.repositories import AuditRepository, QueueRepository, SystemEventRepository

BACKUP_PREFIX = "dynasty_ninja_timer"
LOG_DIR = Path("data/logs")


def create_database_backup(settings: Settings | None = None) -> dict[str, object]:
    active_settings = settings or get_settings()
    source_path = sqlite_database_path(active_settings.database_url)
    if source_path is None:
        raise ValueError("Database backup is only supported for SQLite databases.")
    if not source_path.exists():
        raise FileNotFoundError(f"Database file does not exist: {source_path}")

    backup_dir = Path("data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    target_path = backup_dir / f"{BACKUP_PREFIX}_{timestamp}.sqlite"

    with sqlite3.connect(source_path) as source:
        with sqlite3.connect(target_path) as target:
            source.backup(target)

    pruned = prune_old_backups(active_settings.backup_retention_days)
    return {
        "filename": target_path.name,
        "path": str(target_path),
        "size_bytes": target_path.stat().st_size,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "pruned": pruned,
    }


def list_database_backups() -> list[dict[str, object]]:
    backup_dir = Path("data/backups")
    if not backup_dir.exists():
        return []
    backups = []
    for path in sorted(backup_dir.glob(f"{BACKUP_PREFIX}_*.sqlite"), reverse=True):
        stat = path.stat()
        backups.append(
            {
                "filename": path.name,
                "path": str(path),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        )
    return backups


def tail_log_file(filename: str, *, lines: int = 200) -> dict[str, object]:
    safe_name, log_path = _log_file_path(filename)
    if not log_path.exists():
        raise FileNotFoundError(f"Log file does not exist: {safe_name}")
    tail: deque[str] = deque(maxlen=lines)
    with log_path.open("r", encoding="utf-8", errors="replace") as file:
        for line in file:
            tail.append(line)
    return {
        "filename": safe_name,
        "lines": list(tail),
    }


def prune_old_backups(retention_days: int) -> list[str]:
    backup_dir = Path("data/backups")
    if not backup_dir.exists():
        return []
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    pruned: list[str] = []
    for path in backup_dir.glob(f"{BACKUP_PREFIX}_*.sqlite"):
        modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        if modified < cutoff:
            path.unlink()
            pruned.append(path.name)
    return pruned


def sqlite_database_path(database_url: str) -> Path | None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite") or url.database in (None, ":memory:"):
        return None
    return Path(url.database)


def _log_file_path(filename: str) -> tuple[str, Path]:
    requested = Path(filename)
    if (
        not filename
        or requested.is_absolute()
        or requested.name != filename
        or filename in {".", ".."}
    ):
        raise ValueError("Log filename is invalid.")
    log_dir = LOG_DIR.resolve()
    log_path = (LOG_DIR / requested.name).resolve()
    try:
        log_path.relative_to(log_dir)
    except ValueError as exc:
        raise ValueError("Log filename is outside the log directory.") from exc
    return requested.name, log_path


def recover_after_restart() -> dict[str, object]:
    with SessionLocal() as db:
        entries = QueueRepository(db).recover_active("RETURN_ACTIVE_TO_WAITING")
        if entries:
            SystemEventRepository(db).record(
                level="WARNING",
                category="SERVER",
                source="startup",
                message="Recovered active queue entries after restart.",
                payload_json=json.dumps({"queue_entry_ids": [entry.id for entry in entries]}),
            )
            AuditRepository(db).record(
                actor="SYSTEM",
                action="RECOVER_AFTER_RESTART",
                target_type="queue",
            )
        db.commit()
        return {"recovered_queue_entries": len(entries)}
