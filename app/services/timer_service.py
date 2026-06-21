"""Database-backed timer service."""
from dataclasses import dataclass
from threading import RLock
from time import perf_counter_ns

from sqlalchemy.orm import Session

from app.db.models import Course, CourseRevision, QueueEntry, Run
from app.db.repositories import CourseRepository, QueueRepository, RunRepository, utc_now
from app.db.schemas import (
    TimerArmRequest,
    TimerCourseRead,
    TimerRunnerRead,
    TimerStateRead,
)
from app.services.timer_state import InvalidTimerTransition, TimerState, TimerStateMachine


class TimerServiceError(ValueError):
    code = "INVALID_STATE"


class TimerNotFoundError(TimerServiceError):
    code = "NOT_FOUND"


@dataclass
class ActiveTimerContext:
    session_id: int | None
    athlete_id: int | None
    queue_entry_id: int | None
    course_id: int
    course_revision_id: int | None
    runner_name: str
    age_group: str | None
    course_slug: str
    course_name: str
    course_revision_snapshot: str | None
    mode: str
    source: str
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_ms: int | None = None
    start_monotonic_ns: int | None = None
    finish_monotonic_ns: int | None = None
    start_source: str | None = None
    finish_source: str | None = None
    run_id: int | None = None


class TimerService:
    """Owns the active in-process timer and persists completed runs."""

    def __init__(self):
        self._state_machine = TimerStateMachine()
        self._active: ActiveTimerContext | None = None
        self._lock = RLock()

    @property
    def state(self) -> TimerState:
        return self._state_machine.state

    def get_state(self) -> TimerStateRead:
        with self._lock:
            return self._state_response()

    def arm(self, db: Session, payload: TimerArmRequest) -> TimerStateRead:
        with self._lock:
            if self.state == TimerState.IDLE:
                self._state_machine.transition("arm")
            elif self.state == TimerState.SAVED:
                self._state_machine.transition("next_runner")
            else:
                self._raise_invalid(f"Cannot arm because the timer is {self.state.value}.")

            self._active = self._build_context(db, payload)
            if self._active.queue_entry_id is not None:
                queue_entry = db.get(QueueEntry, self._active.queue_entry_id)
                if queue_entry is not None:
                    QueueRepository(db).mark_active(queue_entry)
            return self._state_response()

    def start(self, source: str = "ADMIN") -> TimerStateRead:
        with self._lock:
            if self._active is None:
                self._raise_invalid("Cannot start because no runner is armed.")
            try:
                self._state_machine.transition("start_command")
            except InvalidTimerTransition as exc:
                raise TimerServiceError(str(exc)) from exc

            self._active.started_at = utc_now()
            self._active.start_monotonic_ns = perf_counter_ns()
            self._active.start_source = source
            return self._state_response()

    def finish(self, db: Session, source: str = "ADMIN") -> TimerStateRead:
        with self._lock:
            self._require_running()
            finish_ns = perf_counter_ns()
            self._state_machine.transition("finish_sensor_triggered")
            run = self._persist_run(db, status="VALID", finish_ns=finish_ns, finish_source=source)
            self._state_machine.transition("save_run")
            self._mark_queue_completed(db)
            self._active.run_id = run.id
            return self._state_response()

    def stop(
        self,
        db: Session,
        status: str,
        source: str = "ADMIN",
        notes: str | None = None,
    ) -> TimerStateRead:
        with self._lock:
            self._require_running()
            finish_ns = perf_counter_ns()
            self._state_machine.transition("manual_stop")
            run = self._persist_run(
                db,
                status=status or TimerState.MANUAL_STOPPED.value,
                finish_ns=finish_ns,
                finish_source=source,
                notes=notes,
            )
            self._mark_queue_completed(db)
            self._active.run_id = run.id
            return self._state_response()

    def dnf(self, db: Session, notes: str | None = None, source: str = "ADMIN") -> TimerStateRead:
        with self._lock:
            self._require_running()
            finish_ns = perf_counter_ns()
            self._state_machine.transition("dnf")
            run = self._persist_run(
                db,
                status=TimerState.DNF.value,
                finish_ns=finish_ns,
                finish_source=source,
                notes=notes,
            )
            self._mark_queue_completed(db)
            self._active.run_id = run.id
            return self._state_response()

    def reset(self, clear_active_runner: bool = True) -> TimerStateRead:
        with self._lock:
            self._state_machine.reset()
            if clear_active_runner:
                self._active = None
            return self._state_response()

    def delete_last_run(self, db: Session, reason: str | None = None) -> TimerStateRead:
        with self._lock:
            run = RunRepository(db).most_recent()
            if run is None:
                raise TimerNotFoundError("No saved run is available to delete.")
            RunRepository(db).soft_delete(run.id, reason=reason)
            if self._active is not None and self._active.run_id == run.id:
                self._active.run_id = None
            if self.state == TimerState.SAVED:
                self._state_machine.transition("reset")
            return self._state_response()

    def reset_for_tests(self) -> None:
        with self._lock:
            self._state_machine = TimerStateMachine()
            self._active = None

    def _build_context(self, db: Session, payload: TimerArmRequest) -> ActiveTimerContext:
        queue_repository = QueueRepository(db)
        queue_entry = (
            queue_repository.get(payload.queue_entry_id)
            if payload.queue_entry_id is not None
            else queue_repository.first_waiting()
        )
        if queue_entry is not None:
            return self._context_from_queue_entry(db, queue_entry)
        if payload.queue_entry_id is not None:
            raise TimerNotFoundError(f"Queue entry {payload.queue_entry_id} was not found.")
        return self._context_from_manual_payload(db, payload)

    def _context_from_queue_entry(self, db: Session, queue_entry: QueueEntry) -> ActiveTimerContext:
        course = self._require_course(db, queue_entry.course_id)
        revision = self._get_revision(db, queue_entry.course_revision_id)
        return ActiveTimerContext(
            session_id=queue_entry.session_id,
            athlete_id=queue_entry.athlete_id,
            queue_entry_id=queue_entry.id,
            course_id=course.id,
            course_revision_id=revision.id if revision is not None else None,
            runner_name=queue_entry.runner_name_snapshot,
            age_group=queue_entry.age_group_snapshot,
            course_slug=course.slug,
            course_name=course.name,
            course_revision_snapshot=revision.revision_name if revision is not None else None,
            mode=queue_entry.mode,
            source=queue_entry.source,
        )

    def _context_from_manual_payload(
        self, db: Session, payload: TimerArmRequest
    ) -> ActiveTimerContext:
        if payload.course_id is None:
            raise TimerNotFoundError("No waiting queue entry is available to arm.")
        course = self._require_course(db, payload.course_id)
        revision = CourseRepository(db).get_open_revision(course.id)
        runner_name = (payload.runner_name or "Anonymous Runner").strip()
        return ActiveTimerContext(
            session_id=None,
            athlete_id=None,
            queue_entry_id=None,
            course_id=course.id,
            course_revision_id=revision.id if revision is not None else None,
            runner_name=runner_name,
            age_group=payload.age_group,
            course_slug=course.slug,
            course_name=course.name,
            course_revision_snapshot=revision.revision_name if revision is not None else None,
            mode=payload.mode,
            source="MANUAL",
        )

    def _persist_run(
        self,
        db: Session,
        *,
        status: str,
        finish_ns: int,
        finish_source: str,
        notes: str | None = None,
    ) -> Run:
        if self._active is None or self._active.start_monotonic_ns is None:
            self._raise_invalid("Cannot save a run before timing has started.")
        elapsed_ms = max(0, (finish_ns - self._active.start_monotonic_ns) // 1_000_000)
        finished_at = utc_now()
        self._active.finished_at = finished_at
        self._active.finish_monotonic_ns = finish_ns
        self._active.finish_source = finish_source
        self._active.elapsed_ms = elapsed_ms

        return RunRepository(db).create(
            session_id=self._active.session_id,
            athlete_id=self._active.athlete_id,
            queue_entry_id=self._active.queue_entry_id,
            course_id=self._active.course_id,
            course_revision_id=self._active.course_revision_id,
            runner_name_snapshot=self._active.runner_name,
            age_group_snapshot=self._active.age_group,
            course_name_snapshot=self._active.course_name,
            course_revision_snapshot=self._active.course_revision_snapshot,
            mode=self._active.mode,
            status=status,
            started_at=self._active.started_at,
            finished_at=finished_at,
            elapsed_ms=elapsed_ms,
            start_monotonic_ns=self._active.start_monotonic_ns,
            finish_monotonic_ns=finish_ns,
            start_source=self._active.start_source,
            finish_source=finish_source,
            source=finish_source,
            false_start_ms=None,
            reaction_ms=None,
            notes=notes,
            deleted_at=None,
            deleted_reason=None,
        )

    def _mark_queue_completed(self, db: Session) -> None:
        if self._active is None or self._active.queue_entry_id is None:
            return
        queue_entry = db.get(QueueEntry, self._active.queue_entry_id)
        if queue_entry is not None:
            QueueRepository(db).mark_completed(queue_entry)

    def _state_response(self) -> TimerStateRead:
        active = self._active
        elapsed_ms = active.elapsed_ms if active is not None else None
        if (
            active is not None
            and self.state == TimerState.RUNNING
            and active.start_monotonic_ns is not None
        ):
            elapsed_ms = max(0, (perf_counter_ns() - active.start_monotonic_ns) // 1_000_000)

        return TimerStateRead(
            state=self.state.value,
            elapsed_ms=elapsed_ms,
            started_at=active.started_at if active is not None else None,
            finished_at=active.finished_at if active is not None else None,
            runner=(
                TimerRunnerRead(
                    id=active.athlete_id,
                    name=active.runner_name,
                    age_group=active.age_group,
                )
                if active is not None
                else None
            ),
            course=(
                TimerCourseRead(
                    id=active.course_id,
                    slug=active.course_slug,
                    name=active.course_name,
                )
                if active is not None
                else None
            ),
            mode=active.mode if active is not None else None,
            run_id=active.run_id if active is not None else None,
        )

    def _require_running(self) -> None:
        if self._active is None:
            self._raise_invalid("Cannot finish because no runner is active.")
        if self.state != TimerState.RUNNING:
            self._raise_invalid(f"Cannot finish because the timer is {self.state.value}.")

    def _require_course(self, db: Session, course_id: int) -> Course:
        course = CourseRepository(db).get_by_id(course_id)
        if course is None:
            raise TimerNotFoundError(f"Course {course_id} was not found.")
        return course

    def _get_revision(self, db: Session, revision_id: int | None) -> CourseRevision | None:
        if revision_id is None:
            return None
        return db.get(CourseRevision, revision_id)

    def _raise_invalid(self, message: str) -> None:
        raise TimerServiceError(message)


timer_service = TimerService()


def get_timer_service() -> TimerService:
    return timer_service


def reset_timer_service_for_tests() -> None:
    timer_service.reset_for_tests()
