"""
Database engine/session setup.
SQLite by default (zero-config, fine for Phase 1 and early pilots with real
players at AbleGod FC). Point DATABASE_URL at Postgres later without changing
any other code — SQLAlchemy abstracts the difference.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def init_db():
    """Create all tables directly via SQLAlchemy metadata. Fast, zero-config,
    and exactly what you want for local development, running the test
    suite, or a fresh pilot install with no data to protect yet — which is
    why every test script and the quick-start `python main.py` flow uses
    this. It CANNOT safely evolve a schema that already has real data in
    it (it only creates missing tables, never alters existing ones). For
    that, see run_migrations() below.

    After creating the tables, this also stamps the database with
    Alembic's current head revision (a no-op if it's already stamped).
    Without this, a DB built via init_db() has no alembic_version row, so
    the *next* `alembic upgrade head` -- once a second migration exists --
    would try to re-run the baseline migration against tables that already
    exist and crash with "table already exists". Stamping keeps the fast
    create_all() path and Alembic's own bookkeeping in sync."""
    import models  # noqa: F401  (ensures models are registered on Base)
    Base.metadata.create_all(bind=engine)
    _stamp_head_if_needed()


def _stamp_head_if_needed():
    """Mark the DB as being at Alembic's head revision, without running any
    migrations. Safe to call every time init_db() runs (idempotent)."""
    from alembic import command
    from alembic.config import Config

    alembic_ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")
    cfg = Config(alembic_ini_path)
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    cfg.attributes["connection"] = None
    command.stamp(cfg, "head")


def run_migrations():
    """Apply Alembic migrations up to the latest revision. This is the
    production-safe alternative to init_db() once there's real data:
    `alembic upgrade head` (equivalently, this function) applies only the
    incremental changes a migration describes -- e.g. `ADD COLUMN`, not a
    blind create-if-missing -- so existing rows survive a schema change
    instead of a new column silently never appearing on an already-existing
    table. See migrations/ and the README's Database Migrations section."""
    from alembic import command
    from alembic.config import Config

    alembic_ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")
    cfg = Config(alembic_ini_path)
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(cfg, "head")


def seed_academy_curriculum():
    """Idempotently sync Course/Lesson rows from academy_curriculum.py.
    Safe to call every startup: inserts anything new (matched by slug),
    updates title/description/brief/ordering if the curriculum data
    changed, and never touches content_text/quiz_json once generated."""
    import academy_curriculum
    from models import Course, Lesson, CourseCategory

    session = SessionLocal()
    try:
        for course_order, course_data in enumerate(academy_curriculum.COURSES):
            course = session.query(Course).filter_by(slug=course_data["slug"]).first()
            if not course:
                course = Course(slug=course_data["slug"], title=course_data["title"],
                                 description=course_data.get("description"),
                                 category=CourseCategory(course_data["category"]),
                                 order_index=course_order)
                session.add(course)
                session.flush()  # get course.id before adding lessons
            else:
                course.title = course_data["title"]
                course.description = course_data.get("description")
                course.order_index = course_order

            for lesson_order, lesson_data in enumerate(course_data["lessons"]):
                lesson = (
                    session.query(Lesson)
                    .filter_by(course_id=course.id, slug=lesson_data["slug"]).first()
                )
                if not lesson:
                    session.add(Lesson(
                        course_id=course.id, slug=lesson_data["slug"], title=lesson_data["title"],
                        brief=lesson_data["brief"], order_index=lesson_order,
                    ))
                else:
                    lesson.title = lesson_data["title"]
                    lesson.brief = lesson_data["brief"]
                    lesson.order_index = lesson_order
        session.commit()
    finally:
        session.close()


def get_session():
    """Yield a session, always closing it afterwards."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
