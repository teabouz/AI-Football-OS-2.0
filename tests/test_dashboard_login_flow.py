"""
Covers the DashboardToken magic-link authentication flow end to end
against the real /coach/login Flask route: valid, expired, single-use,
invalid, and missing tokens; unauthenticated access; the open-redirect
guard on `next`; and per-coach team-ownership isolation.

Run in a subprocess for the same reason as test_coach_dashboard_xss.py:
database.py/config.py bind DATABASE_URL at import time, and coach_dashboard
binds a module-level Flask app + SessionLocal at import time too.
"""
import os
import subprocess
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_dashboard_login_probe.py")


def test_dashboard_login_token_lifecycle_and_team_isolation():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{path}"
    env["TELEGRAM_BOT_TOKEN"] = "test_token"
    env["FLASK_SECRET_KEY"] = "test-secret-not-for-production"
    env["PYTHONPATH"] = PROJECT_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    try:
        result = subprocess.run(
            [sys.executable, PROBE_SCRIPT],
            cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            "Dashboard login flow regression detected:\n" + result.stdout + "\n" + result.stderr
        )
        assert "DASHBOARD LOGIN PROBE PASSED" in result.stdout
    finally:
        if os.path.exists(path):
            os.remove(path)
