"""
Section 6/7 of the audit: database integrity + Alembic migration chain.
"""
import os
import subprocess
import sys
import tempfile

import pytest
from sqlalchemy.exc import IntegrityError

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Model-level integrity (fast, no subprocess)
# ---------------------------------------------------------------------------

def test_duplicate_telegram_id_rejected(db_session, make_user):
    """Users.telegram_id must be unique -- two rows for the same Telegram
    account would let one person "be" two users in the system."""
    make_user(telegram_id=1001)
    from models import User
    db_session.add(User(telegram_id=1001, username="dupe"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_duplicate_payment_reference_rejected(db_session, make_user):
    from models import Payment, PaymentStatus
    user = make_user(telegram_id=2001)
    db_session.add(Payment(user_id=user.id, reference="ref-abc", amount_kobo=500000, status=PaymentStatus.PENDING))
    db_session.commit()
    db_session.add(Payment(user_id=user.id, reference="ref-abc", amount_kobo=500000, status=PaymentStatus.PENDING))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_duplicate_dashboard_token_rejected(db_session, make_user):
    from models import DashboardToken
    from datetime import datetime, timedelta
    user = make_user(telegram_id=2002)
    exp = datetime.utcnow() + timedelta(minutes=15)
    db_session.add(DashboardToken(user_id=user.id, token="tok-1", expires_at=exp))
    db_session.commit()
    db_session.add(DashboardToken(user_id=user.id, token="tok-1", expires_at=exp))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_team_owner_is_one_to_one(db_session, make_user):
    """Team.owner_user_id is unique=True -- one coach/academy owns exactly
    one team. A second team for the same owner must fail at the DB level,
    not just be caught in application code."""
    from models import Team, UserRole
    coach = make_user(telegram_id=3001, role=UserRole.COACH)
    db_session.add(Team(owner_user_id=coach.id, name="Team A"))
    db_session.commit()
    db_session.add(Team(owner_user_id=coach.id, name="Team B"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_cascade_delete_user_removes_dependents(db_session, make_user):
    """Deleting a User should cascade to owned rows (goals, payments, etc.)
    rather than leaving orphaned foreign keys."""
    from models import Goal, GoalTimeframe
    user = make_user(telegram_id=4001)
    db_session.add(Goal(user_id=user.id, title="Improve first touch", timeframe=GoalTimeframe.WEEKLY))
    db_session.commit()
    assert db_session.query(Goal).filter_by(user_id=user.id).count() == 1

    db_session.delete(user)
    db_session.commit()
    assert db_session.query(Goal).filter_by(user_id=user.id).count() == 0


def test_duplicate_team_membership_rejected(db_session, make_user):
    """A registered player can occupy only one roster slot per team.

    The DB constraint protects against concurrent requests bypassing the
    application-level duplicate check. Nullable player_user_id still allows
    multiple guest roster entries.
    """
    from models import Team, TeamMembership, UserRole
    coach = make_user(telegram_id=5001, role=UserRole.COACH)
    player = make_user(telegram_id=5002, role=UserRole.PLAYER)
    team = Team(owner_user_id=coach.id, name="Team C")
    db_session.add(team)
    db_session.commit()

    db_session.add(TeamMembership(team_id=team.id, player_user_id=player.id))
    db_session.commit()
    db_session.add(TeamMembership(team_id=team.id, player_user_id=player.id))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_guest_memberships_can_share_name(db_session, make_user):
    """Guest entries are intentionally not subject to the registered-player
    uniqueness constraint because guest_name is nullable and multiple teams
    may legitimately have players with the same name.
    """
    from models import Team, TeamMembership, UserRole
    coach = make_user(telegram_id=5003, role=UserRole.COACH)
    team = Team(owner_user_id=coach.id, name="Team D")
    db_session.add(team)
    db_session.commit()
    db_session.add_all([
        TeamMembership(team_id=team.id, guest_name="John Doe"),
        TeamMembership(team_id=team.id, guest_name="John Doe"),
    ])
    db_session.commit()
    assert db_session.query(TeamMembership).filter_by(team_id=team.id, guest_name="John Doe").count() == 2


# ---------------------------------------------------------------------------
# Alembic migration chain (subprocess, exercises the real CLI path)
# ---------------------------------------------------------------------------

def _run_alembic(*args, db_path):
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["TELEGRAM_BOT_TOKEN"] = "test_token"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )


def test_alembic_upgrade_head_succeeds_on_fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # alembic/sqlite will create it
    try:
        result = _run_alembic("upgrade", "head", db_path=path)
        assert result.returncode == 0, result.stderr
        assert os.path.exists(path)
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_alembic_downgrade_then_upgrade_round_trips():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        r1 = _run_alembic("upgrade", "head", db_path=path)
        assert r1.returncode == 0, r1.stderr
        r2 = _run_alembic("downgrade", "base", db_path=path)
        assert r2.returncode == 0, r2.stderr
        r3 = _run_alembic("upgrade", "head", db_path=path)
        assert r3.returncode == 0, r3.stderr
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_alembic_check_reports_no_model_drift():
    """Fails if models.py has been changed without a matching migration."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        _run_alembic("upgrade", "head", db_path=path)
        result = _run_alembic("check", db_path=path)
        assert result.returncode == 0, (
            "alembic detected schema drift between models.py and the migration chain:\n"
            + result.stdout + result.stderr
        )
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_init_db_stamps_alembic_head_so_future_upgrades_dont_crash():
    """Regression test for the bug found during this audit: init_db()
    (used by the quick-start `python main.py` path) previously left the DB
    unstamped, so the *next* `alembic upgrade head` -- once a second
    migration exists -- would crash with 'table already exists'. This
    reproduces that exact scenario against the CURRENT single migration by
    checking the stamp directly rather than requiring a second migration
    to exist."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{path}"
        env["TELEGRAM_BOT_TOKEN"] = "test_token"
        code = (
            "from database import init_db; init_db()"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr

        import sqlite3
        conn = sqlite3.connect(path)
        rows = conn.execute("select version_num from alembic_version").fetchall()
        conn.close()
        assert len(rows) == 1, "init_db() must stamp exactly one alembic_version row"

        # And now the real regression check: alembic upgrade head must be a
        # harmless no-op against a DB that init_db() created, not a crash.
        result2 = _run_alembic("upgrade", "head", db_path=path)
        assert result2.returncode == 0, result2.stderr
    finally:
        if os.path.exists(path):
            os.remove(path)
