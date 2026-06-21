"""Shared API response serializers."""

from sqlalchemy.orm import Session

from app.db.models import Course, CourseRevision, QueueEntry, Run


def queue_entry_response(db: Session, entry: QueueEntry) -> dict:
    course = db.get(Course, entry.course_id)
    revision = (
        db.get(CourseRevision, entry.course_revision_id)
        if entry.course_revision_id is not None
        else None
    )
    return {
        "id": entry.id,
        "request_id": entry.request_id,
        "session_id": entry.session_id,
        "athlete_id": entry.athlete_id,
        "position": entry.position,
        "sort_key": entry.sort_key,
        "version": entry.version,
        "runner_name": entry.runner_name_snapshot,
        "age_group": entry.age_group_snapshot,
        "course": (
            {"id": course.id, "slug": course.slug, "name": course.name}
            if course is not None
            else None
        ),
        "course_revision": (
            {
                "id": revision.id,
                "revision_code": revision.revision_code,
                "revision_start_date": revision.revision_start_date,
                "revision_end_date": revision.revision_end_date,
            }
            if revision is not None
            else None
        ),
        "mode": entry.mode,
        "status": entry.status,
        "source": entry.source,
        "created_at": entry.created_at,
    }


def run_response(run: Run) -> dict:
    return {
        "id": run.id,
        "session_id": run.session_id,
        "athlete_id": run.athlete_id,
        "queue_entry_id": run.queue_entry_id,
        "course_id": run.course_id,
        "course_revision_id": run.course_revision_id,
        "runner_name": run.runner_name_snapshot,
        "age_group": run.age_group_snapshot,
        "course_name": run.course_name_snapshot,
        "course_revision": run.course_revision_snapshot,
        "mode": run.mode,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "elapsed_ms": run.elapsed_ms,
        "source": run.source,
        "notes": run.notes,
        "obstacle_status_json": run.obstacle_status_json,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "deleted_at": run.deleted_at,
        "deleted_reason": run.deleted_reason,
    }
