"""
Run in an isolated subprocess (see test_role_authorization.py), DATABASE_URL
already set before any app module is imported.

Section 10 of the audit: role separation must be enforced server-side, not
just by hiding buttons. Calls the REAL handler functions directly (not
through fake buttons) with a PLAYER's Telegram identity and confirms
coach-only actions are refused and no data is mutated.
"""
import asyncio
import sys

from database import init_db, SessionLocal
from models import User, UserRole, Team

sys.path.insert(0, ".")
from tests.fakes import FakeUpdate, FakeContext  # noqa: E402

init_db()
session = SessionLocal()
try:
    player = User(telegram_id=80001, username="playerA", first_name="Player", role=UserRole.PLAYER, registration_complete=True)
    coach_a = User(telegram_id=80002, username="coachA", first_name="CoachA", role=UserRole.COACH, registration_complete=True)
    coach_b = User(telegram_id=80003, username="coachB", first_name="CoachB", role=UserRole.COACH, registration_complete=True)
    session.add_all([player, coach_a, coach_b])
    session.commit()
finally:
    session.close()

from handlers.team import createteam_command, addplayer_command, get_or_none_team  # noqa: E402

failures = []


def check(condition, msg):
    if not condition:
        failures.append(msg)


async def main():
    # 1. PLAYER tries to create a team -- must be refused server-side.
    update = FakeUpdate(telegram_id=80001, username="playerA")
    ctx = FakeContext(args=["Sneaky", "FC"])
    await createteam_command(update, ctx)
    check(
        any("Coach and Academy" in text for text, _ in update.message.sent),
        "PLAYER was not refused when calling /createteam directly",
    )

    verify_session = SessionLocal()
    try:
        player_team = verify_session.query(Team).filter(
            Team.name.like("%Sneaky%")
        ).first()
        check(player_team is None, "PLAYER's /createteam call created a Team row despite being refused")
    finally:
        verify_session.close()

    # 2. PLAYER tries to add a player to a roster -- must be refused, and
    #    must NOT be able to piggyback onto some other coach's team.
    update2 = FakeUpdate(telegram_id=80001, username="playerA")
    ctx2 = FakeContext(args=["@coachB"])
    await addplayer_command(update2, ctx2)
    check(
        any("Coach and Academy" in text for text, _ in update2.message.sent),
        "PLAYER was not refused when calling /addplayer directly",
    )

    # 3. Legitimate COACH creates their own team -- must succeed.
    update3 = FakeUpdate(telegram_id=80002, username="coachA")
    ctx3 = FakeContext(args=["Real", "FC"])
    await createteam_command(update3, ctx3)
    check(
        any("Team created" in text for text, _ in update3.message.sent),
        "Legitimate COACH was refused when creating their own team",
    )

    # 4. Coach A cannot see/act on Coach B's team through get_or_none_team --
    #    it must always scope by the CALLER's own user id.
    verify_session3 = SessionLocal()
    try:
        coach_a_row = verify_session3.query(User).filter_by(telegram_id=80002).first()
        coach_b_row = verify_session3.query(User).filter_by(telegram_id=80003).first()
        team_for_a = await get_or_none_team(verify_session3, coach_a_row)
        team_for_b = await get_or_none_team(verify_session3, coach_b_row)
        check(team_for_a is not None and team_for_a.name == "Real FC", "Coach A's own team lookup failed")
        check(team_for_b is None, "Coach B incorrectly resolved to a team they don't own (cross-account leak)")
    finally:
        verify_session3.close()


asyncio.run(main())

if failures:
    print("ROLE AUTH PROBE FAILED:")
    for f in failures:
        print(" -", f)
    sys.exit(1)

print("ROLE AUTH PROBE PASSED")
sys.exit(0)
