"""Course persistence services and default course seeding."""
from sqlalchemy.orm import Session

from app.db.models import Course
from app.db.repositories import CourseRepository

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

