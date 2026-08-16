"""
Run in an isolated subprocess (see test_dashboard_login_flow.py) with
DATABASE_URL already pointed at a throwaway file, BEFORE any app module is
imported -- database.py/config.py bind their engine at import time.

Exercises the real Flask /coach/login route (coach_dashboard.py) via
Flask's test client, covering the magic-link token lifecycle end to end:
  - valid, unused, unexpired token -> logs in, single-use afterwards
  - reusing the same (now-used) token -> rejected
  - expired token -> rejected
  - garbage/nonexistent token -> rejected
  - missing token -> rejected
  - open-redirect guard on `next`
  - team-ownership isolation: coach A's session only ever sees coach A's
    team, never coach B's, even if coach B's team_id/membership ids are
    guessed
"""
import sys
from datetime import datetime, timedelta, timezone

from database import init_db, SessionLocal
from models import User, UserRole, Team, DashboardToken

init_db()

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


session = SessionLocal()
coach_a = User(telegram_id=80001, username="coach_a", first_name="Alice",
               role=UserRole.COACH, registration_complete=True)
coach_b = User(telegram_id=80002, username="coach_b", first_name="Bob",
               role=UserRole.COACH, registration_complete=True)
session.add_all([coach_a, coach_b])
session.commit()

team_a = Team(owner_user_id=coach_a.id, name="Alice FC")
team_b = Team(owner_user_id=coach_b.id, name="Bob United")
session.add_all([team_a, team_b])
session.commit()

now = datetime.now(timezone.utc).replace(tzinfo=None)
valid_token = DashboardToken(user_id=coach_a.id, token="valid-token-aaa", expires_at=now + timedelta(minutes=15))
expired_token = DashboardToken(user_id=coach_a.id, token="expired-token-bbb", expires_at=now - timedelta(minutes=1))
used_token = DashboardToken(user_id=coach_a.id, token="used-token-ccc", expires_at=now + timedelta(minutes=15), used=True)
session.add_all([valid_token, expired_token, used_token])
session.commit()

coach_a_id, coach_b_id = coach_a.id, coach_b.id
session.close()

import coach_dashboard  # noqa: E402  (must import after DATABASE_URL is set)

coach_dashboard.app.config["TESTING"] = True
client = coach_dashboard.app.test_client()

# --- valid token logs in ---
resp = client.get("/coach/login?token=valid-token-aaa", follow_redirects=False)
check(resp.status_code == 302, f"valid token should redirect (302), got {resp.status_code}")
check(resp.headers.get("Location", "").endswith("/coach/"),
      f"valid token should redirect to /coach/ by default, got {resp.headers.get('Location')}")

home_resp = client.get("/coach/")
check(home_resp.status_code == 200, "logged-in coach should be able to load /coach/")
check(b"Alice FC" in home_resp.data, "coach A's dashboard should show coach A's own team name")
client.get("/coach/logout")

# --- reusing the same token a second time must fail (single-use) ---
resp = client.get("/coach/login?token=valid-token-aaa")
check(resp.status_code == 401, f"reused token should be rejected (401), got {resp.status_code}")
check(b"invalid or has expired" in resp.data, "reused-token error message missing/changed")

# --- expired token rejected ---
resp = client.get("/coach/login?token=expired-token-bbb")
check(resp.status_code == 401, f"expired token should be rejected (401), got {resp.status_code}")

# --- already-used token rejected ---
resp = client.get("/coach/login?token=used-token-ccc")
check(resp.status_code == 401, f"already-used token should be rejected (401), got {resp.status_code}")

# --- garbage/nonexistent token rejected ---
resp = client.get("/coach/login?token=this-token-does-not-exist")
check(resp.status_code == 401, f"nonexistent token should be rejected (401), got {resp.status_code}")

# --- missing token entirely rejected ---
resp = client.get("/coach/login")
check(resp.status_code == 401, f"missing token should be rejected (401), got {resp.status_code}")

# --- unauthenticated access to a protected route redirects to login ---
anon_client = coach_dashboard.app.test_client()
resp = anon_client.get("/coach/", follow_redirects=False)
check(resp.status_code == 302 and "/coach/login" in resp.headers.get("Location", ""),
      f"unauthenticated /coach/ should redirect to login, got {resp.status_code} {resp.headers.get('Location')}")
resp = anon_client.get("/coach/roster", follow_redirects=False)
check(resp.status_code == 302 and "/coach/login" in resp.headers.get("Location", ""),
      f"unauthenticated /coach/roster should redirect to login, got {resp.status_code}")

# --- open-redirect guard: a crafted `next` outside /coach/ is ignored ---
session = SessionLocal()
redirect_token = DashboardToken(user_id=coach_a_id, token="redirect-token-ddd", expires_at=now + timedelta(minutes=15))
session.add(redirect_token)
session.commit()
session.close()
evil_client = coach_dashboard.app.test_client()
resp = evil_client.get("/coach/login?token=redirect-token-ddd&next=https://evil.example/steal")
check(resp.status_code == 302, "valid token with crafted next= should still redirect")
check(resp.headers.get("Location", "").startswith("/coach/"),
      f"open-redirect guard failed -- redirected to {resp.headers.get('Location')}")
check("evil.example" not in resp.headers.get("Location", ""), "open-redirect guard failed")

# --- team ownership isolation: coach B never sees coach A's team ---
session = SessionLocal()
token_b = DashboardToken(user_id=coach_b_id, token="valid-token-for-b", expires_at=now + timedelta(minutes=15))
session.add(token_b)
session.commit()
session.close()

client_b = coach_dashboard.app.test_client()
client_b.get("/coach/login?token=valid-token-for-b")
home_b = client_b.get("/coach/")
check(b"Bob United" in home_b.data, "coach B's dashboard should show coach B's own team name")
check(b"Alice FC" not in home_b.data, "coach B's dashboard leaked coach A's team name -- IDOR")

if failures:
    print("DASHBOARD LOGIN PROBE FAILED:")
    for f in failures:
        print(" -", f)
    sys.exit(1)

print("DASHBOARD LOGIN PROBE PASSED")
sys.exit(0)
