"""Course and course revision management API routes."""
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.db.database import get_db
from app.db.repositories import AuditRepository, CourseRepository
from app.db.schemas import (
    CourseCreate,
    CourseRevisionCloseRequest,
    CourseRevisionCreate,
    CourseRevisionUpdate,
    CourseUpdate,
)
from app.services.course_service import (
    close_course_revision,
    course_response,
    course_revision_response,
    create_course,
    create_course_revision,
    disable_course,
    list_course_revisions,
    list_courses,
    update_course,
    update_course_revision,
)
from app.services.event_bus import event_bus

router = APIRouter(prefix="/api/v1", tags=["courses"])


def _ok(data: object) -> dict:
    return {"ok": True, "data": data}


def _error(http_status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"ok": False, "error": {"code": code, "message": message}},
    )


@router.get("/courses")
async def get_courses(db: Session = Depends(get_db)) -> dict:
    return _ok(list_courses(db))


@router.post("/courses")
async def post_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    try:
        course = create_course(db, payload)
        AuditRepository(db).record(
            actor=actor,
            action="CREATE_COURSE",
            target_type="course",
            target_id=course.id,
        )
        db.commit()
        data = course_response(CourseRepository(db), course)
        await event_bus.publish("courses.updated", {"course": data})
        return _ok(data)
    except ValueError as exc:
        db.rollback()
        return _error(status.HTTP_409_CONFLICT, "COURSE_INVALID", str(exc))


@router.patch("/courses/{course_id}")
async def patch_course(
    course_id: int,
    payload: CourseUpdate,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    try:
        course = update_course(db, course_id, payload)
    except ValueError as exc:
        db.rollback()
        return _error(status.HTTP_409_CONFLICT, "COURSE_INVALID", str(exc))
    if course is None:
        db.rollback()
        return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"Course {course_id} was not found.")

    AuditRepository(db).record(
        actor=actor,
        action="UPDATE_COURSE",
        target_type="course",
        target_id=course.id,
    )
    db.commit()
    data = course_response(CourseRepository(db), course)
    await event_bus.publish("courses.updated", {"course": data})
    return _ok(data)


@router.delete("/courses/{course_id}")
async def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    course = disable_course(db, course_id)
    if course is None:
        db.rollback()
        return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"Course {course_id} was not found.")
    AuditRepository(db).record(
        actor=actor,
        action="DISABLE_COURSE",
        target_type="course",
        target_id=course.id,
    )
    db.commit()
    data = course_response(CourseRepository(db), course)
    await event_bus.publish("courses.updated", {"course": data})
    return _ok(data)


@router.get("/courses/{course_id}/revisions")
async def get_course_revisions(course_id: int, db: Session = Depends(get_db)):
    data = list_course_revisions(db, course_id)
    if data is None:
        return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"Course {course_id} was not found.")
    return _ok(data)


@router.post("/courses/{course_id}/revisions")
async def post_course_revision(
    course_id: int,
    payload: CourseRevisionCreate,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    try:
        revision = create_course_revision(db, course_id, payload)
    except ValueError as exc:
        db.rollback()
        return _error(status.HTTP_409_CONFLICT, "REVISION_INVALID", str(exc))
    if revision is None:
        db.rollback()
        return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"Course {course_id} was not found.")

    AuditRepository(db).record(
        actor=actor,
        action="CREATE_COURSE_REVISION",
        target_type="course_revision",
        target_id=revision.id,
    )
    db.commit()
    data = course_revision_response(revision)
    await event_bus.publish("courses.updated", {"revision": data})
    return _ok(data)


@router.patch("/course-revisions/{course_revision_id}")
async def patch_course_revision(
    course_revision_id: int,
    payload: CourseRevisionUpdate,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    try:
        revision = update_course_revision(db, course_revision_id, payload)
    except ValueError as exc:
        db.rollback()
        return _error(status.HTTP_409_CONFLICT, "REVISION_INVALID", str(exc))
    if revision is None:
        db.rollback()
        return _error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            f"Course revision {course_revision_id} was not found.",
        )

    AuditRepository(db).record(
        actor=actor,
        action="UPDATE_COURSE_REVISION",
        target_type="course_revision",
        target_id=revision.id,
    )
    db.commit()
    data = course_revision_response(revision)
    await event_bus.publish("courses.updated", {"revision": data})
    return _ok(data)


@router.post("/course-revisions/{course_revision_id}/close")
async def post_close_course_revision(
    course_revision_id: int,
    payload: CourseRevisionCloseRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    revision = close_course_revision(db, course_revision_id, payload.revision_end_date)
    if revision is None:
        db.rollback()
        return _error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            f"Course revision {course_revision_id} was not found.",
        )

    AuditRepository(db).record(
        actor=actor,
        action="CLOSE_COURSE_REVISION",
        target_type="course_revision",
        target_id=revision.id,
    )
    db.commit()
    data = course_revision_response(revision)
    await event_bus.publish("courses.updated", {"revision": data})
    return _ok(data)
