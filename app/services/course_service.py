"""Course persistence services and default course seeding."""
import re

from sqlalchemy.orm import Session

from app.db.models import Course, CourseRevision
from app.db.repositories import CourseRepository
from app.db.schemas import CourseCreate, CourseRevisionCreate, CourseRevisionUpdate, CourseUpdate

DEFAULT_COURSES = (
    {
        "slug": "speed-gauntlet",
        "name": "Speed Gauntlet",
        "description": "Default speed course for open gym and competition timing.",
    },
    {
        "slug": "ninja-challenge",
        "name": "Ninja Challenge",
        "description": "Default all-around ninja course.",
    },
)


def seed_default_courses(db: Session) -> list[Course]:
    """Create default courses and one open revision for each, idempotently."""
    repository = CourseRepository(db)
    courses: list[Course] = []
    for course_seed in DEFAULT_COURSES:
        course = repository.get_by_slug(course_seed["slug"])
        if course is None:
            course = repository.create(**course_seed)

        if repository.get_open_revision(course.id) is None:
            repository.create_open_revision(course)

        courses.append(course)
    return courses


def list_courses(db: Session) -> list[dict]:
    repository = CourseRepository(db)
    return [course_response(repository, course) for course in repository.list_active()]


def create_course(db: Session, payload: CourseCreate) -> Course:
    repository = CourseRepository(db)
    name = payload.name.strip()
    slug = _normalize_slug(payload.slug or name)
    if not name:
        raise ValueError("Course name is required.")
    if repository.get_by_slug(slug) is not None:
        raise ValueError(f"Course slug {slug} already exists.")

    course = repository.create(slug=slug, name=name, description=payload.description)
    repository.create_open_revision(
        course,
        start_date=payload.revision_start_date,
        revision_name=payload.first_revision_name or f"{name} Layout",
        layout_notes=payload.layout_notes,
        obstacle_count=payload.obstacle_count,
    )
    return course


def update_course(db: Session, course_id: int, payload: CourseUpdate) -> Course | None:
    repository = CourseRepository(db)
    course = repository.get_by_id(course_id)
    if course is None:
        return None

    values = payload.model_dump(exclude_unset=True)
    if "name" in values and values["name"] is not None:
        values["name"] = values["name"].strip()
        if not values["name"]:
            raise ValueError("Course name is required.")
    if "slug" in values and values["slug"] is not None:
        values["slug"] = _normalize_slug(values["slug"])
        existing = repository.get_by_slug(values["slug"])
        if existing is not None and existing.id != course.id:
            raise ValueError(f"Course slug {values['slug']} already exists.")

    return repository.update_course(course, **values)


def disable_course(db: Session, course_id: int) -> Course | None:
    repository = CourseRepository(db)
    course = repository.get_by_id(course_id)
    if course is None:
        return None
    return repository.update_course(course, active=False)


def list_course_revisions(db: Session, course_id: int) -> list[dict] | None:
    repository = CourseRepository(db)
    course = repository.get_by_id(course_id)
    if course is None:
        return None
    return [course_revision_response(revision) for revision in repository.list_revisions(course.id)]


def create_course_revision(
    db: Session,
    course_id: int,
    payload: CourseRevisionCreate,
) -> CourseRevision | None:
    repository = CourseRepository(db)
    course = repository.get_by_id(course_id)
    if course is None:
        return None
    revision_name = payload.revision_name.strip()
    if not revision_name:
        raise ValueError("Revision name is required.")
    return repository.create_revision(
        course,
        revision_name=revision_name,
        revision_start_date=payload.revision_start_date,
        revision_end_date=payload.revision_end_date,
        description=payload.description,
        obstacle_count=payload.obstacle_count,
        layout_notes=payload.layout_notes,
        rules_json=payload.rules_json,
        leaderboard_eligible=payload.leaderboard_eligible,
        close_current_revision=payload.close_current_revision,
    )


def update_course_revision(
    db: Session,
    course_revision_id: int,
    payload: CourseRevisionUpdate,
) -> CourseRevision | None:
    repository = CourseRepository(db)
    revision = repository.get_revision(course_revision_id)
    if revision is None:
        return None
    values = payload.model_dump(exclude_unset=True)
    if "revision_name" in values and values["revision_name"] is not None:
        values["revision_name"] = values["revision_name"].strip()
        if not values["revision_name"]:
            raise ValueError("Revision name is required.")
    return repository.update_revision(revision, **values)


def close_course_revision(
    db: Session,
    course_revision_id: int,
    end_date: str | None = None,
) -> CourseRevision | None:
    repository = CourseRepository(db)
    revision = repository.get_revision(course_revision_id)
    if revision is None:
        return None
    return repository.close_revision(revision, end_date=end_date)


def course_response(repository: CourseRepository, course: Course) -> dict:
    open_revision = repository.get_open_revision(course.id)
    revisions = repository.list_revisions(course.id)
    return {
        "id": course.id,
        "slug": course.slug,
        "name": course.name,
        "description": course.description,
        "active": course.active,
        "created_at": course.created_at,
        "updated_at": course.updated_at,
        "open_revision": (
            course_revision_response(open_revision) if open_revision is not None else None
        ),
        "revisions": [course_revision_response(revision) for revision in revisions],
    }


def course_revision_response(revision: CourseRevision) -> dict:
    return {
        "id": revision.id,
        "course_id": revision.course_id,
        "revision_code": revision.revision_code,
        "revision_name": revision.revision_name,
        "revision_start_date": revision.revision_start_date,
        "revision_end_date": revision.revision_end_date,
        "description": revision.description,
        "obstacle_count": revision.obstacle_count,
        "layout_notes": revision.layout_notes,
        "rules_json": revision.rules_json,
        "leaderboard_eligible": revision.leaderboard_eligible,
        "active": revision.active,
        "created_at": revision.created_at,
        "updated_at": revision.updated_at,
    }


def _normalize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("Course slug is required.")
    return slug
