import pytest


@pytest.mark.asyncio
async def test_coach_cannot_remove_another_coachs_roster_member(
    db_session, make_user, monkeypatch
):
    from models import (
        Team,
        TeamMembership,
        UserRole,
    )
    from handlers import team as team_handler

    owner_a = make_user(telegram_id=10001, role=UserRole.COACH)
    owner_b = make_user(telegram_id=10002, role=UserRole.COACH)
    player = make_user(telegram_id=10003, role=UserRole.PLAYER)

    team_a = Team(owner_user_id=owner_a.id, name="Team A")
    team_b = Team(owner_user_id=owner_b.id, name="Team B")

    db_session.add_all([team_a, team_b])
    db_session.commit()

    membership = TeamMembership(
        team_id=team_a.id,
        player_user_id=player.id,
    )
    db_session.add(membership)
    db_session.commit()
    db_session.refresh(membership)

    class FakeCallbackQuery:
        data = f"roster:remove:{membership.id}"

        async def answer(self, *args, **kwargs):
            pass

        async def edit_message_text(self, *args, **kwargs):
            pass

    class FakeTelegramUser:
        id = 10002  # Coach B attempting to attack Team A

    class FakeUpdate:
        callback_query = FakeCallbackQuery()
        effective_user = FakeTelegramUser()

    from sqlalchemy.orm import sessionmaker

    HandlerSession = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(team_handler, "SessionLocal", HandlerSession)

    await team_handler.remove_player(FakeUpdate(), None)

    db_session.refresh(membership)

    assert membership.active is True


@pytest.mark.asyncio
async def test_coach_cannot_toggle_another_coachs_attendance(
    db_session, make_user, monkeypatch
):
    from datetime import date

    from models import (
        Team,
        TeamMembership,
        TrainingSession,
        AttendanceRecord,
        UserRole,
    )
    from handlers import attendance as attendance_handler

    owner_a = make_user(telegram_id=11001, role=UserRole.COACH)
    owner_b = make_user(telegram_id=11002, role=UserRole.COACH)
    player = make_user(telegram_id=11003, role=UserRole.PLAYER)

    team_a = Team(owner_user_id=owner_a.id, name="Team A")

    db_session.add(team_a)
    db_session.commit()

    membership = TeamMembership(
        team_id=team_a.id,
        player_user_id=player.id,
    )
    db_session.add(membership)
    db_session.commit()

    training = TrainingSession(
        team_id=team_a.id,
        session_date=date.today(),
    )
    db_session.add(training)
    db_session.commit()

    record = AttendanceRecord(
        session_id=training.id,
        membership_id=membership.id,
        present=False,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)

    class FakeCallbackQuery:
        data = f"att:toggle:{record.id}"

        async def answer(self, *args, **kwargs):
            pass

        async def edit_message_text(self, *args, **kwargs):
            pass

    class FakeTelegramUser:
        id = 11002  # Coach B attacking Team A

    class FakeUpdate:
        callback_query = FakeCallbackQuery()
        effective_user = FakeTelegramUser()

    from sqlalchemy.orm import sessionmaker

    HandlerSession = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(attendance_handler, "SessionLocal", HandlerSession)

    await attendance_handler.toggle_attendance(FakeUpdate(), None)

    db_session.refresh(record)

    assert record.present is False
