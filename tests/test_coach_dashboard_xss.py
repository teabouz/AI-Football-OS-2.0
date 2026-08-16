"""
Regression test for the stored-XSS vulnerability found during this audit
(Section 30 of the audit prompt: injection / data privacy).

Root cause: coach_dashboard.py renders `body` via Jinja's `{{ body|safe }}`,
and `body` was built from raw f-strings embedding DB fields -- including
Telegram `first_name`, which is fully attacker-controlled. Fixed by
escaping every user-authored / AI-generated field with markupsafe.escape
before interpolation.

Run in a subprocess because database.py/config.py bind DATABASE_URL and
coach_dashboard.py binds a module-level Flask app + SessionLocal at import
time -- this has to happen against a throwaway DB, isolated from every
other test module in this suite.
"""
import os
import subprocess
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_xss_probe.py")


def test_coach_dashboard_escapes_attacker_controlled_fields():
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
            "Stored XSS regression detected:\n" + result.stdout + "\n" + result.stderr
        )
        assert "XSS PROBE PASSED" in result.stdout
    finally:
        if os.path.exists(path):
            os.remove(path)
