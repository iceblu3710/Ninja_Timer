"""Pydantic DTOs for persistence-layer records."""
from pydantic import BaseModel, ConfigDict, model_validator


class OrmSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CourseRead(OrmSchema):
    id: int
    slug: str
    name: str
    description: str | None = None
    active: bool
    created_at: str
    updated_at: str


class CourseRevisionRead(OrmSchema):
    id: int
    course_id: int
    revision_code: str
    revision_name: str
    revision_start_date: str
    revision_end_date: str | None = None
    leaderboard_eligible: bool
    active: bool
    created_at: str
    updated_at: str


class CourseCreate(BaseModel):
    slug: str | None = None
    name: str
    description: str | None = None
    first_revision_name: str | None = None
    revision_start_date: str | None = None
    layout_notes: str | None = None
    obstacle_count: int | None = None


class CourseUpdate(BaseModel):
    slug: str | None = None
    name: str | None = None
    description: str | None = None
    active: bool | None = None


class CourseRevisionCreate(BaseModel):
    revision_name: str
    revision_start_date: str | None = None
    revision_end_date: str | None = None
    description: str | None = None
    obstacle_count: int | None = None
    layout_notes: str | None = None
    rules_json: str | None = None
    leaderboard_eligible: bool = True
    close_current_revision: bool = True


class CourseRevisionUpdate(BaseModel):
    revision_name: str | None = None
    revision_start_date: str | None = None
    revision_end_date: str | None = None
    description: str | None = None
    obstacle_count: int | None = None
    layout_notes: str | None = None
    rules_json: str | None = None
    leaderboard_eligible: bool | None = None
    active: bool | None = None


class CourseRevisionCloseRequest(BaseModel):
    revision_end_date: str | None = None


class SessionRead(OrmSchema):
    id: int
    name: str
    mode: str
    status: str
    starts_at: str | None = None
    ends_at: str | None = None
    active: bool
    created_at: str
    updated_at: str


class QueueEntryCreate(BaseModel):
    request_id: str | None = None
    runner_name: str | None = None
    name: str | None = None
    age_group: str | None = None
    course_slug: str | None = None
    course_id: int | None = None
    course_revision_id: int | None = None
    mode: str = "OPEN_GYM"
    source: str = "KIOSK"
    session_id: int | None = None

    @model_validator(mode="after")
    def validate_required_identity(self) -> "QueueEntryCreate":
        if not (self.runner_name or self.name):
            raise ValueError("runner_name or name is required")
        if self.course_id is None and self.course_slug is None:
            raise ValueError("course_id or course_slug is required")
        return self

    @property
    def display_name(self) -> str:
        return (self.runner_name or self.name or "").strip()


class QueueEntryRead(OrmSchema):
    id: int
    request_id: str | None = None
    session_id: int | None = None
    course_id: int
    course_revision_id: int | None = None
    runner_name_snapshot: str
    age_group_snapshot: str | None = None
    mode: str
    status: str
    position: int
    sort_key: int
    version: int
    source: str
    created_at: str


class QueueEntryUpdate(BaseModel):
    request_id: str | None = None
    version: int
    position: int | None = None
    status: str | None = None


class QueueRecoverRequest(BaseModel):
    policy: str = "RETURN_ACTIVE_TO_WAITING"


class RunRead(OrmSchema):
    id: int
    session_id: int | None = None
    athlete_id: int | None = None
    queue_entry_id: int | None = None
    course_id: int
    course_revision_id: int | None = None
    runner_name_snapshot: str
    age_group_snapshot: str | None = None
    course_name_snapshot: str
    course_revision_snapshot: str | None = None
    mode: str
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_ms: int | None = None
    source: str
    created_at: str
    updated_at: str
    deleted_at: str | None = None


class RunUpdate(BaseModel):
    runner_name: str | None = None
    age_group: str | None = None
    status: str | None = None
    notes: str | None = None


class RunDeleteRequest(BaseModel):
    reason: str | None = None


class TimerRunnerRead(BaseModel):
    id: int | None = None
    name: str
    age_group: str | None = None


class TimerCourseRead(BaseModel):
    id: int
    slug: str
    name: str


class TimerStateRead(BaseModel):
    state: str
    elapsed_ms: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    runner: TimerRunnerRead | None = None
    course: TimerCourseRead | None = None
    mode: str | None = None
    run_id: int | None = None


class TimerArmRequest(BaseModel):
    queue_entry_id: int | None = None
    course_id: int | None = None
    mode: str = "OPEN_GYM"
    runner_name: str | None = None
    age_group: str | None = None


class TimerSourceRequest(BaseModel):
    source: str = "ADMIN"


class TimerStopRequest(BaseModel):
    status: str = "MANUAL_STOPPED"
    source: str = "ADMIN"
    notes: str | None = None


class TimerResetRequest(BaseModel):
    clear_active_runner: bool = True


class TimerDnfRequest(BaseModel):
    notes: str | None = None
    source: str = "ADMIN"


class TimerDeleteLastRunRequest(BaseModel):
    reason: str | None = None


class AdminLoginRequest(BaseModel):
    pin: str


class SettingChange(BaseModel):
    value: object
    version: int | None = None


class SettingsPatchRequest(BaseModel):
    request_id: str | None = None
    changes: dict[str, SettingChange]
    apply_immediately: bool = True


class SettingsValidateRequest(BaseModel):
    changes: dict[str, SettingChange]


class SettingRollbackRequest(BaseModel):
    request_id: str | None = None
    reason: str | None = None


class BackupCreateRequest(BaseModel):
    request_id: str | None = None
    reason: str | None = None
