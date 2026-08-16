"""
Admin Web Dashboard — Phase 1 deliverable.

A small, dependency-light Flask app that reads the same database as the bot.
Run it alongside the bot (separate process) for a browser-based view of
users, roles, and subscriptions. Later phases (Coach Dashboard, Club
Dashboard, analytics) extend this same app rather than replacing it.

Run:
    python admin_dashboard.py
Then open http://localhost:5000 and log in with ADMIN_DASHBOARD_USERNAME /
ADMIN_DASHBOARD_PASSWORD from your .env.
"""
from functools import wraps
import hmac

from flask import Flask, render_template_string, request, Response
from sqlalchemy import func

import config
from database import SessionLocal, init_db
from models import User, UserRole, SubscriptionTier

app = Flask(__name__)

PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>AI Football OS — Admin</title>
  <style>
    body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; background:#0b1120; color:#e5e7eb; margin:0; padding:2rem; }
    h1 { color:#22c55e; }
    .stats { display:flex; gap:1rem; margin-bottom:2rem; flex-wrap: wrap; }
    .card { background:#111827; border:1px solid #1f2937; border-radius:10px; padding:1rem 1.5rem; min-width:140px; }
    .card .num { font-size:1.8rem; font-weight:700; color:#22c55e; }
    .card .label { font-size:0.85rem; color:#9ca3af; }
    table { width:100%; border-collapse:collapse; background:#111827; border-radius:10px; overflow:hidden; }
    th, td { text-align:left; padding:0.6rem 1rem; border-bottom:1px solid #1f2937; font-size:0.9rem; }
    th { background:#1f2937; color:#9ca3af; text-transform:uppercase; font-size:0.75rem; }
    tr:hover { background:#1a2333; }
    .badge { padding:2px 8px; border-radius:999px; font-size:0.75rem; }
    .badge.premium { background:#14532d; color:#4ade80; }
    .badge.free { background:#374151; color:#d1d5db; }
  </style>
</head>
<body>
  <h1>⚽ AI Football OS — Admin Dashboard</h1>
  <div class="stats">
    <div class="card"><div class="num">{{ total }}</div><div class="label">Total Users</div></div>
    <div class="card"><div class="num">{{ registered }}</div><div class="label">Registered</div></div>
    <div class="card"><div class="num">{{ premium }}</div><div class="label">Premium</div></div>
    <div class="card"><div class="num">{{ players }}</div><div class="label">Players</div></div>
    <div class="card"><div class="num">{{ coaches }}</div><div class="label">Coaches</div></div>
    <div class="card"><div class="num">{{ academies }}</div><div class="label">Academies</div></div>
  </div>
  <table>
    <tr><th>Name</th><th>Role</th><th>Plan</th><th>Telegram ID</th><th>Joined</th></tr>
    {% for u in users %}
    <tr>
      <td>{{ u.display_name() }}</td>
      <td>{{ u.role.value.title() if u.role else '—' }}</td>
      <td><span class="badge {{ 'premium' if u.is_premium() else 'free' }}">{{ 'Premium' if u.is_premium() else 'Free' }}</span></td>
      <td>{{ u.telegram_id }}</td>
      <td>{{ u.created_at.strftime('%d %b %Y') }}</td>
    </tr>
    {% endfor %}
  </table>
</body>
</html>
"""


def check_auth(username, password):
    # Constant-time comparison -- a plain `==` leaks timing information
    # character-by-character, which is a real (if slow) attack against a
    # password sitting behind Basic Auth with no rate limiting.
    return (
        hmac.compare_digest(username, config.ADMIN_DASHBOARD_USERNAME)
        and hmac.compare_digest(password, config.ADMIN_DASHBOARD_PASSWORD)
    )


def authenticate():
    return Response(
        "Login required", 401, {"WWW-Authenticate": 'Basic realm="AI Football OS Admin"'}
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


@app.route("/")
@requires_auth
def dashboard():
    session = SessionLocal()
    try:
        total = session.query(func.count(User.id)).scalar()
        registered = session.query(func.count(User.id)).filter_by(registration_complete=True).scalar()
        premium = session.query(func.count(User.id)).filter_by(subscription_tier=SubscriptionTier.PREMIUM).scalar()

        def role_count(role):
            return session.query(func.count(User.id)).filter_by(role=role).scalar()

        users = session.query(User).order_by(User.created_at.desc()).limit(200).all()

        return render_template_string(
            PAGE,
            total=total,
            registered=registered,
            premium=premium,
            players=role_count(UserRole.PLAYER),
            coaches=role_count(UserRole.COACH),
            academies=role_count(UserRole.ACADEMY),
            users=users,
        )
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
