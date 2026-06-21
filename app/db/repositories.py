"""Repository helpers for database-backed timer workflows."""
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AdminAuditLog,
    Course,
    CourseRevision,
    QueueEntry,
    Run,
    SessionModel,
    Setting,
    SystemEvent,
)


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp suitable for SQLite text storage."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_utc_date() -> str:
    return datetime.now(UTC).date().isoformat()


def normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


class CourseRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_slug(self, slug: str) -> Course | None:
        return self.db.scalar(select(Course).where(Course.slug == slug))

    def get_by_id(self, course_id: int) -> Course | None:
        return self.db.get(Course, course_id)

    def get_revision(self, course_revision_id: int) -> CourseRevision | None:
        return self.db.get(CourseRevision, course_revision_id)

    def list_active(self) -> list[Course]:
        statement = select(Course).where(Course.active.is_(True)).order_by(Course.name)
        return list(self.db.scalars(statement))

    def list_revisions(self, course_id: int) -> list[CourseRevision]:
        statement = (
            select(CourseRevision)
            .where(CourseRevision.course_id == course_id)
            .order_by(CourseRevision.revision_start_date.desc(), CourseRevision.id.desc())
        )
        return list(self.db.scalars(statement))

    def create(self, slug: str, name: str, description: str | None = None) -> Course:
        now = utc_now()
        course = Course(
            slug=slug,
            name=name,
            description=description,
            active=True,
            created_at=now,
            updated_at=now,
        )
        self.db.add(course)
        self.db.flush()
        return course

    def update_course(self, course: Course, **values: Any) -> Course:
        for key, value in values.items():
            setattr(course, key, value)
        course.updated_at = utc_now()
        self.db.flush()
        return course

    def get_open_revision(self, course_id: int) -> CourseRevision | None:
        statement = select(CourseRevision).where(
            CourseRevision.course_id == course_id,
            CourseRevision.active.is_(True),
            CourseRevision.revision_end_date.is_(None),
        )
        return self.db.scalar(statement)

    def create_open_revision(
        self,
        course: Course,
        start_date: str | None = None,
        description: str | None = None,
        revision_name: str | None = None,
        obstacle_count: int | None = None,
        layout_notes: str | None = None,
        rules_json: str | None = None,
        leaderboard_eligible: bool = True,
    ) -> CourseRevision:
        existing = self.get_open_revision(course.id)
        if existing is not None:
            raise ValueError(f"Course {course.slug} already has an open revision")

        revision_start = start_date or today_utc_date()
        revision_code = f"{course.slug}-{revision_start}-to-open"
        now = utc_now()
        revision = CourseRevision(
            course_id=course.id,
            revision_code=self._unique_revision_code(revision_code),
            revision_name=revision_name or f"{course.name} Open Layout",
            revision_start_date=revision_start,
            revision_end_date=None,
            description=description,
            obstacle_count=obstacle_count,
            layout_notes=layout_notes,
            rules_json=rules_json,
            leaderboard_eligible=leaderboard_eligible,
            active=True,
            created_at=now,
            updated_at=now,
        )
        self.db.add(revision)
        self.db.flush()
        return revision

    def create_revision(
        self,
        course: Course,
        *,
        revision_name: str,
        revision_start_date: str | None = None,
        revision_end_date: str | None = None,
        description: str | None = None,
        obstacle_count: int | None = None,
        layout_notes: str | None = None,
        rules_json: str | None = None,
        leaderboard_eligible: bool = True,
        close_current_revision: bool = True,
    ) -> CourseRevision:
        revision_start = revision_start_date or today_utc_date()
        if close_current_revision:
            current = self.get_open_revision(course.id)
            if current is not None:
                self.close_revision(current, end_date=revision_start)

        if revision_end_date is None and self.get_open_revision(course.id) is not None:
            raise ValueError(f"Course {course.slug} already has an open revision")

        end_code = revision_end_date or "open"
        now = utc_now()
        revision = CourseRevision(
            course_id=course.id,
            revision_code=self._unique_revision_code(
                f"{course.slug}-{revision_start}-to-{end_code}"
            ),
            revision_name=revision_name,
            revision_start_date=revision_start,
            revision_end_date=revision_end_date,
            description=description,
            obstacle_count=obstacle_count,
            layout_notes=layout_notes,
            rules_json=rules_json,
            leaderboard_eligible=leaderboard_eligible,
            active=True,
            created_at=now,
            updated_at=now,
        )
        self.db.add(revision)
        self.db.flush()
        return revision

    def update_revision(self, revision: CourseRevision, **values: Any) -> CourseRevision:
        for key, value in values.items():
            setattr(revision, key, value)
        revision.updated_at = utc_now()
        self.db.flush()
        return revision

    def close_revision(
        self,
        revision: CourseRevision,
        *,
        end_date: str | None = None,
    ) -> CourseRevision:
        revision.revision_end_date = end_date or today_utc_date()
        revision.active = False
        revision.updated_at = utc_now()
        self.db.flush()
        return revision

    def _unique_revision_code(self, base_code: str) -> str:
        code = base_code
        suffix = 2
        while self.db.scalar(select(CourseRevision.id).where(CourseRevision.revision_code == code)):
            code = f"{base_code}-{suffix}"
            suffix += 1
        return code


class SessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_active(self) -> SessionModel | None:
        return self.db.scalar(
            select(SessionModel).where(
                SessionModel.active.is_(True),
                SessionModel.status == "ACTIVE",
            )
        )

    def create_active_open_gym(self, name: str = "Today's Open Gym") -> SessionModel:
        now = utc_now()
        session = SessionModel(
            name=name,
            mode="OPEN_GYM",
            status="ACTIVE",
            starts_at=now,
            ends_at=None,
            active=True,
            notes=None,
            created_at=now,
            updated_at=now,
        )
        self.db.add(session)
        self.db.flush()
        return session


class QueueRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_request_id(self, request_id: str) -> QueueEntry | None:
        return self.db.scalar(select(QueueEntry).where(QueueEntry.request_id == request_id))

    def get(self, queue_entry_id: int) -> QueueEntry | None:
        return self.db.get(QueueEntry, queue_entry_id)

    def next_position(self, session_id: int | None) -> int:
        statement = select(func.coalesce(func.max(QueueEntry.position), 0)).where(
            QueueEntry.session_id == session_id,
            QueueEntry.status.in_(["WAITING", "CALLED", "ACTIVE"]),
        )
        return int(self.db.scalar(statement) or 0) + 1

    def create_waiting(
        self,
        *,
        runner_name: str,
        course_id: int,
        mode: str,
        source: str,
        request_id: str | None = None,
        session_id: int | None = None,
        course_revision_id: int | None = None,
        age_group: str | None = None,
        athlete_id: int | None = None,
    ) -> QueueEntry:
        if request_id:
            existing = self.get_by_request_id(request_id)
            if existing is not None:
                return existing

        position = self.next_position(session_id)
        now = utc_now()
        entry = QueueEntry(
            request_id=request_id,
            session_id=session_id,
            athlete_id=athlete_id,
            course_id=course_id,
            course_revision_id=course_revision_id,
            runner_name_snapshot=runner_name.strip(),
            age_group_snapshot=age_group,
            mode=mode,
            status="WAITING",
            position=position,
            sort_key=position * 1000,
            version=1,
            source=source,
            priority=0,
            attempt_count=0,
            created_at=now,
            called_at=None,
            started_at=None,
            completed_at=None,
            cancelled_at=None,
            skipped_at=None,
            locked_at=None,
            locked_by=None,
            last_error=None,
            notes=None,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def list_active_queue(
        self,
        session_id: int | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[QueueEntry]:
        statement: Select[tuple[QueueEntry]] = select(QueueEntry).where(
            QueueEntry.status.in_(["WAITING", "CALLED", "ACTIVE"])
        )
        if session_id is not None:
            statement = statement.where(QueueEntry.session_id == session_id)
        if status is not None:
            statement = statement.where(QueueEntry.status == status)
        statement = statement.order_by(QueueEntry.sort_key, QueueEntry.created_at).limit(limit)
        return list(self.db.scalars(statement))

    def first_waiting(self) -> QueueEntry | None:
        statement = (
            select(QueueEntry)
            .where(QueueEntry.status == "WAITING")
            .order_by(QueueEntry.sort_key, QueueEntry.created_at)
            .limit(1)
        )
        return self.db.scalar(statement)

    def mark_active(self, entry: QueueEntry) -> QueueEntry:
        now = utc_now()
        entry.status = "ACTIVE"
        entry.started_at = now
        entry.version += 1
        self.db.flush()
        return entry

    def mark_completed(self, entry: QueueEntry) -> QueueEntry:
        now = utc_now()
        entry.status = "COMPLETED"
        entry.completed_at = now
        entry.version += 1
        self.db.flush()
        return entry

    def cancel(self, queue_entry_id: int) -> QueueEntry | None:
        entry = self.get(queue_entry_id)
        if entry is None:
            return None
        now = utc_now()
        entry.status = "CANCELLED"
        entry.cancelled_at = now
        entry.version += 1
        self.db.flush()
        return entry

    def update(
        self,
        entry: QueueEntry,
        *,
        expected_version: int,
        position: int | None = None,
        status: str | None = None,
    ) -> QueueEntry:
        if entry.version != expected_version:
            raise ValueError("Queue entry version is stale")

        now = utc_now()
        if position is not None:
            entry.position = position
            entry.sort_key = position * 1000
        if status is not None:
            entry.status = status
            if status == "CANCELLED":
                entry.cancelled_at = now
            elif status == "SKIPPED":
                entry.skipped_at = now
            elif status == "COMPLETED":
                entry.completed_at = now
            elif status == "ACTIVE":
                entry.started_at = now
        entry.version += 1
        self.db.flush()
        return entry

    def recover_active(self, policy: str) -> list[QueueEntry]:
        active_entries = list(
            self.db.scalars(select(QueueEntry).where(QueueEntry.status == "ACTIVE"))
        )
        if policy == "LEAVE_UNCHANGED":
            return active_entries

        for entry in active_entries:
            if policy == "RETURN_ACTIVE_TO_WAITING":
                entry.status = "WAITING"
                entry.started_at = None
                entry.locked_at = None
                entry.locked_by = None
            elif policy == "MARK_ACTIVE_ERROR":
                entry.status = "ERROR"
                entry.last_error = "Recovered active queue entry after restart"
            else:
                raise ValueError(f"Unknown recovery policy: {policy}")
            entry.version += 1
            entry.completed_at = None
            entry.cancelled_at = None
            entry.skipped_at = None
        self.db.flush()
        return active_entries


class RunRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **values: Any) -> Run:
        now = utc_now()
        run = Run(created_at=now, updated_at=now, **values)
        self.db.add(run)
        self.db.flush()
        return run

    def get(self, run_id: int) -> Run | None:
        return self.db.get(Run, run_id)

    def recent(
        self,
        *,
        limit: int = 10,
        session_id: int | None = None,
        course_id: int | None = None,
        course_revision_id: int | None = None,
        mode: str | None = None,
        status: str | None = None,
    ) -> list[Run]:
        statement = select(Run).where(Run.deleted_at.is_(None))
        if session_id is not None:
            statement = statement.where(Run.session_id == session_id)
        if course_id is not None:
            statement = statement.where(Run.course_id == course_id)
        if course_revision_id is not None:
            statement = statement.where(Run.course_revision_id == course_revision_id)
        if mode is not None:
            statement = statement.where(Run.mode == mode)
        if status is not None:
            statement = statement.where(Run.status == status)
        statement = statement.order_by(Run.created_at.desc()).limit(limit)
        return list(self.db.scalars(statement))

    def most_recent(self) -> Run | None:
        return self.db.scalar(
            select(Run)
            .where(Run.deleted_at.is_(None))
            .order_by(Run.created_at.desc())
            .limit(1)
        )

    def update(self, run: Run, **values: Any) -> Run:
        for key, value in values.items():
            setattr(run, key, value)
        run.updated_at = utc_now()
        self.db.flush()
        return run

    def soft_delete(self, run_id: int, reason: str | None = None) -> Run | None:
        run = self.db.get(Run, run_id)
        if run is None:
            return None
        now = utc_now()
        run.deleted_at = now
        run.deleted_reason = reason
        run.status = "DELETED"
        run.updated_at = now
        self.db.flush()
        return run


class SettingsRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, key: str) -> Setting | None:
        return self.db.get(Setting, key)

    def list_all(self) -> list[Setting]:
        return list(self.db.scalars(select(Setting).order_by(Setting.key)))

    def upsert_default(
        self,
        key: str,
        value_json: str,
        value_type: str | None = None,
        updated_by: str = "SYSTEM",
    ) -> Setting:
        existing = self.get(key)
        if existing is not None:
            return existing
        now = utc_now()
        setting = Setting(
            key=key,
            value_json=value_json,
            value_type=value_type,
            schema_version=1,
            version=1,
            pending_value_json=None,
            last_good_value_json=None,
            default_value_json=value_json,
            validation_status="VALID",
            validation_error=None,
            updated_at=now,
            updated_by=updated_by,
        )
        self.db.add(setting)
        self.db.flush()
        return setting

    def update_value(
        self,
        setting: Setting,
        *,
        value_json: str,
        value_type: str | None,
        updated_by: str,
    ) -> Setting:
        setting.last_good_value_json = setting.value_json
        setting.value_json = value_json
        setting.value_type = value_type
        setting.pending_value_json = None
        setting.validation_status = "VALID"
        setting.validation_error = None
        setting.version += 1
        setting.updated_at = utc_now()
        setting.updated_by = updated_by
        self.db.flush()
        return setting

    def store_invalid_pending(
        self,
        setting: Setting,
        *,
        pending_value_json: str,
        validation_error: str,
        updated_by: str,
    ) -> Setting:
        setting.pending_value_json = pending_value_json
        setting.validation_status = "INVALID"
        setting.validation_error = validation_error
        setting.updated_at = utc_now()
        setting.updated_by = updated_by
        self.db.flush()
        return setting

    def rollback(self, setting: Setting, *, updated_by: str) -> Setting:
        fallback = setting.last_good_value_json or setting.default_value_json
        if fallback is None:
            raise ValueError(f"Setting {setting.key} has no rollback value.")
        setting.value_json = fallback
        setting.pending_value_json = None
        setting.validation_status = "VALID"
        setting.validation_error = None
        setting.version += 1
        setting.updated_at = utc_now()
        setting.updated_by = updated_by
        self.db.flush()
        return setting


class SystemEventRepository:
    def __init__(self, db: Session):
        self.db = db

    def record(
        self,
        *,
        level: str,
        category: str,
        message: str,
        source: str | None = None,
        payload_json: str | None = None,
        request_id: str | None = None,
        retention_class: str = "NORMAL",
    ) -> SystemEvent:
        severity_rank = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}.get(
            level.upper(),
            20,
        )
        event = SystemEvent(
            event_id=None,
            level=level.upper(),
            severity_rank=severity_rank,
            category=category.upper(),
            source=source,
            message=message,
            payload_json=payload_json,
            request_id=request_id,
            retention_class=retention_class,
            acknowledged_at=None,
            created_at=utc_now(),
        )
        self.db.add(event)
        self.db.flush()
        return event

    def recent(
        self,
        *,
        limit: int = 100,
        category: str | None = None,
        level: str | None = None,
    ) -> list[SystemEvent]:
        statement = select(SystemEvent)
        if category is not None:
            statement = statement.where(SystemEvent.category == category.upper())
        if level is not None:
            statement = statement.where(SystemEvent.level == level.upper())
        statement = statement.order_by(SystemEvent.created_at.desc(), SystemEvent.id.desc()).limit(
            limit
        )
        return list(self.db.scalars(statement))


class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def record(
        self,
        *,
        actor: str,
        action: str,
        target_type: str | None = None,
        target_id: int | None = None,
        request_id: str | None = None,
        payload_json: str | None = None,
    ) -> AdminAuditLog:
        audit = AdminAuditLog(
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            request_id=request_id,
            payload_json=payload_json,
            created_at=utc_now(),
        )
        self.db.add(audit)
        self.db.flush()
        return audit
