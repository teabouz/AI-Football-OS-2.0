"""
Shared pytest fixtures.

Each test gets a fresh, isolated SQLite DB (file-based, not :memory:, so
that separate connections within the same test -- e.g. simulating two
"processes" -- see the same data) built directly from models.py via
create_all(). This deliberately mirrors init_db(), not run_migrations(),
so these tests run fast with no Alembic dependency; migration-chain
correctness itself is covered separately in test_database.py.
"""
import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def db_session():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_url = f"sqlite:///{path}"

    # Import here (not at module load) so each test can control DATABASE_URL
    # before database.py's module-level engine is created for the *app*
    # modules that read config.DATABASE_URL. We build our own throwaway
    # engine/session bound to models.Base metadata instead, which is all
    # these tests need.
    import models
    from database import Base

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        os.remove(path)


@pytest.fixture()
def make_user(db_session):
    """Factory fixture: make_user(telegram_id, role=..., **kwargs) -> User"""
    from models import User, UserRole

    def _make(telegram_id, role=None, registration_complete=True, **kwargs):
        user = User(
            telegram_id=telegram_id,
            username=kwargs.pop("username", f"user{telegram_id}"),
            first_name=kwargs.pop("first_name", f"Test{telegram_id}"),
            role=role,
            registration_complete=registration_complete,
            **kwargs,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make
