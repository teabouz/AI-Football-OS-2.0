"""
Run in an isolated subprocess (see test_dashboard_command.py) with
DATABASE_URL already pointed at a throwaway file, BEFORE any app module is
imported -- database.py/config.py bind their engine at import time.

Exercises the real /dashboard code path (handlers/team.py:dashboard_command)
via a fake Telegram Update/Context, the same way a coach would trigger it:
  1. Register a coach, create a team.
  2. Call dashboard_command with DASHBOARD_BASE_URL left at its local-only
     default -- assert the link points at port 5002 (the dashboard) and
     NOT port 5001 (the payment server, the original bug), and that NO
     inline keyboard button is attached (local URLs are sent as plain text
     with a warning instead, since Telegram can't open them anyway).
  3. Point DASHBOARD_BASE_URL at a public tunnel URL -- assert a real
     inline "Open Coach Dashboard" button is attached with the correct URL.
  4. Assert a DashboardToken row was actually created in the DB.
"""
import asyncio
import sys

from database import init_db, SessionLocal
from models import User, UserRole, DashboardToken

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from fakes import FakeUpdate, FakeContext  # noqa: E402

init_db()

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


async def main():
    import config
    from handlers import team

    session = SessionLocal()
    coach = User(telegram_id=70001, username="coach70001", first_name="Coach",
                 role=UserRole.COACH, registration_complete=True)
    session.add(coach)
    session.commit()
    coach_id = coach.id
    session.close()

    update = FakeUpdate(70001, username="coach70001")
    context = FakeContext(args=["AbleGod", "FC"])
    await team.createteam_command(update, context)

    # --- Case 1: local-only DASHBOARD_BASE_URL (the default) ---
    config.DASHBOARD_BASE_URL = "http://127.0.0.1:5002"
    update2 = FakeUpdate(70001, username="coach70001")
    context2 = FakeContext()
    await team.dashboard_command(update2, context2)
    check(len(update2.message.sent) == 1, "dashboard_command (local) sent no message")
    text, kwargs = update2.message.sent[0]

    check(":5002" in text, f"expected port 5002 (coach dashboard) in link, got: {text}")
    check(":5001" not in text, f"link incorrectly points at port 5001 (payment server): {text}")
    check("/coach/login?token=" in text, f"link missing /coach/login?token=: {text}")
    check(kwargs.get("reply_markup") is None,
          "a local-only URL should NOT be sent as a clickable inline button "
          "(Telegram can't open it from a phone, and some Bot API deployments "
          "reject unreachable URLs in buttons outright)")

    # --- Case 2: public DASHBOARD_BASE_URL (a tunnel/domain) ---
    config.DASHBOARD_BASE_URL = "https://abcd1234.ngrok-free.app"
    update3 = FakeUpdate(70001, username="coach70001")
    context3 = FakeContext()
    await team.dashboard_command(update3, context3)
    text3, kwargs3 = update3.message.sent[0]
    markup = kwargs3.get("reply_markup")
    check(markup is not None, "a public URL should be sent with a clickable inline button")
    if markup is not None:
        button = markup.inline_keyboard[0][0]
        check(button.url.startswith("https://abcd1234.ngrok-free.app/coach/login?token="),
              f"button URL wrong: {button.url}")

    # --- DB side effect: real single-use tokens were actually created ---
    session = SessionLocal()
    token_count = session.query(DashboardToken).filter_by(user_id=coach_id).count()
    session.close()
    check(token_count == 2, f"expected 2 DashboardToken rows (one per /dashboard call), got {token_count}")


asyncio.run(main())

if failures:
    print("DASHBOARD COMMAND PROBE FAILED:")
    for f in failures:
        print(" -", f)
    sys.exit(1)

print("DASHBOARD COMMAND PROBE PASSED")
sys.exit(0)
