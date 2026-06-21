"""SQLAlchemy ORM models matching the MVP persistence schema."""
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class TimestampMixin:
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class Athlete(TimestampMixin, Base):
    __tablename__ = "athletes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String, nullable=False)
    default_age_group: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Course(TimestampMixin, Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    revisions: Mapped[list["CourseRevision"]] = relationship(back_populates="course")


class CourseRevision(TimestampMixin, Base):
    __tablename__ = "course_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    revision_code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    revision_name: Mapped[str] = mapped_column(String, nullable=False)
    revision_start_date: Mapped[str] = mapped_column(String, nullable=False)
    revision_end_date: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)
    obstacle_count: Mapped[int | None] = mapped_column(Integer)
    layout_notes: Mapped[str | None] = mapped_column(Text)
    rules_json: Mapped[str | None] = mapped_column(Text)
    leaderboard_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    course: Mapped[Course] = relationship(back_populates="revisions")


class SessionModel(TimestampMixin, Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    starts_at: Mapped[str | None] = mapped_column(String)
    ends_at: Mapped[str | None] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class QueueEntry(Base):
    __tablename__ = "queue_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str | None] = mapped_column(String, unique=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id"))
    athlete_id: Mapped[int | None] = mapped_column(ForeignKey("athletes.id"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    course_revision_id: Mapped[int | None] = mapped_column(ForeignKey("course_revisions.id"))
    runner_name_snapshot: Mapped[str] = mapped_column(String, nullable=False)
    age_group_snapshot: Mapped[str | None] = mapped_column(String)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_key: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    called_at: Mapped[str | None] = mapped_column(String)
    started_at: Mapped[str | None] = mapped_column(String)
    completed_at: Mapped[str | None] = mapped_column(String)
    cancelled_at: Mapped[str | None] = mapped_column(String)
    skipped_at: Mapped[str | None] = mapped_column(String)
    locked_at: Mapped[str | None] = mapped_column(String)
    locked_by: Mapped[str | None] = mapped_column(String)
    last_error: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class Run(TimestampMixin, Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id"))
    athlete_id: Mapped[int | None] = mapped_column(ForeignKey("athletes.id"))
    queue_entry_id: Mapped[int | None] = mapped_column(ForeignKey("queue_entries.id"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    course_revision_id: Mapped[int | None] = mapped_column(ForeignKey("course_revisions.id"))
    runner_name_snapshot: Mapped[str] = mapped_column(String, nullable=False)
    age_group_snapshot: Mapped[str | None] = mapped_column(String)
    course_name_snapshot: Mapped[str] = mapped_column(String, nullable=False)
    course_revision_snapshot: Mapped[str | None] = mapped_column(String)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[str | None] = mapped_column(String)
    finished_at: Mapped[str | None] = mapped_column(String)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer)
    start_monotonic_ns: Mapped[int | None] = mapped_column(Integer)
    finish_monotonic_ns: Mapped[int | None] = mapped_column(Integer)
    start_source: Mapped[str | None] = mapped_column(String)
    finish_source: Mapped[str | None] = mapped_column(String)
    source: Mapped[str] = mapped_column(String, nullable=False)
    false_start_ms: Mapped[int | None] = mapped_column(Integer)
    reaction_ms: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[str | None] = mapped_column(String)
    deleted_reason: Mapped[str | None] = mapped_column(Text)


class HardwareDevice(TimestampMixin, Base):
    __tablename__ = "hardware_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    device_type: Mapped[str] = mapped_column(String, nullable=False)
    transport: Mapped[str] = mapped_column(String, nullable=False)
    config_json: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[str | None] = mapped_column(String)
    last_sequence_number: Mapped[int | None] = mapped_column(Integer)
    health_status: Mapped[str] = mapped_column(String, nullable=False, default="UNKNOWN")


class HardwareEvent(Base):
    __tablename__ = "hardware_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str | None] = mapped_column(String, unique=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("hardware_devices.id"))
    transport: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    input_key: Mapped[str | None] = mapped_column(String)
    state: Mapped[str | None] = mapped_column(String)
    sequence_number: Mapped[int | None] = mapped_column(Integer)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_json: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[str] = mapped_column(String, nullable=False)
    received_monotonic_ns: Mapped[int | None] = mapped_column(Integer)
    processed_at: Mapped[str | None] = mapped_column(String)
    process_status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING")
    process_error: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"))


class RelayAction(Base):
    __tablename__ = "relay_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("hardware_devices.id"))
    action_key: Mapped[str] = mapped_column(String, nullable=False)
    command: Mapped[str] = mapped_column(String, nullable=False)
    requested_by: Mapped[str] = mapped_column(String, nullable=False)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"))
    status: Mapped[str] = mapped_column(String, nullable=False)
    requested_at: Mapped[str] = mapped_column(String, nullable=False)
    sent_at: Mapped[str | None] = mapped_column(String)
    acknowledged_at: Mapped[str | None] = mapped_column(String)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_response: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class SystemEvent(Base):
    __tablename__ = "system_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str | None] = mapped_column(String, unique=True)
    level: Mapped[str] = mapped_column(String, nullable=False)
    severity_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str | None] = mapped_column(String)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String)
    retention_class: Mapped[str] = mapped_column(String, nullable=False, default="NORMAL")
    acknowledged_at: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str | None] = mapped_column(String)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    pending_value_json: Mapped[str | None] = mapped_column(Text)
    last_good_value_json: Mapped[str | None] = mapped_column(Text)
    default_value_json: Mapped[str | None] = mapped_column(Text)
    validation_status: Mapped[str] = mapped_column(String, nullable=False, default="VALID")
    validation_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    target_type: Mapped[str | None] = mapped_column(String)
    target_id: Mapped[int | None] = mapped_column(Integer)
    request_id: Mapped[str | None] = mapped_column(String)
    payload_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


Index("idx_athletes_normalized_name", Athlete.normalized_name)
Index("idx_athletes_active", Athlete.active)
Index("idx_courses_active", Course.active)
Index(
    "idx_course_revisions_course_dates",
    CourseRevision.course_id,
    CourseRevision.revision_start_date,
    CourseRevision.revision_end_date,
)
Index("idx_course_revisions_active", CourseRevision.course_id, CourseRevision.active)
Index("idx_sessions_active", SessionModel.active)
Index("idx_sessions_status", SessionModel.status)
Index("idx_sessions_starts_at", SessionModel.starts_at)
Index(
    "idx_queue_session_status_position",
    QueueEntry.session_id,
    QueueEntry.status,
    QueueEntry.position,
)
Index("idx_queue_status_sort", QueueEntry.status, QueueEntry.sort_key)
Index("idx_queue_course_revision", QueueEntry.course_revision_id)
Index("idx_queue_created_at", QueueEntry.created_at)
Index("idx_runs_session_created", Run.session_id, Run.created_at)
Index("idx_runs_course_revision_elapsed", Run.course_revision_id, Run.elapsed_ms)
Index("idx_runs_course_elapsed", Run.course_id, Run.elapsed_ms)
Index("idx_runs_status", Run.status)
Index("idx_runs_athlete", Run.athlete_id)
Index("idx_runs_created_at", Run.created_at)
Index("idx_hardware_devices_active", HardwareDevice.active)
Index("idx_hardware_devices_health", HardwareDevice.health_status)
Index("idx_hardware_events_received_at", HardwareEvent.received_at)
Index("idx_hardware_events_process_status", HardwareEvent.process_status)
Index("idx_hardware_events_run", HardwareEvent.run_id)
Index("idx_hardware_events_device_seq", HardwareEvent.device_id, HardwareEvent.sequence_number)
Index("idx_relay_actions_status", RelayAction.status)
Index("idx_relay_actions_run", RelayAction.run_id)
Index("idx_system_events_created_at", SystemEvent.created_at)
Index("idx_system_events_category", SystemEvent.category)
Index("idx_system_events_level", SystemEvent.level)
Index("idx_system_events_ack", SystemEvent.acknowledged_at)
Index("idx_settings_validation_status", Setting.validation_status)
Index("idx_admin_audit_log_created_at", AdminAuditLog.created_at)
Index("idx_admin_audit_log_target", AdminAuditLog.target_type, AdminAuditLog.target_id)
