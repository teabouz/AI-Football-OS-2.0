"""
Regression test for the Coach Dashboard root-cause bug found during this
audit: /dashboard built its link from PUBLIC_BASE_URL (the payment
server's port-5001 URL) instead of a dedicated dashboard URL, sending
coaches to a service with no /coach/login route at all. Also covers the
local-only-URL handling added as part of the fix.

Run in a subprocess for the same reason as test_coach_dashboard_xss.py:
database.py/config.py bind DATABASE_URL at import time.
"""
import os
import subprocess
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_dashboard_command_probe.py")


def test_dashboard_command_uses_dashboard_base_url_not_payment_url():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{path}"
    env["TELEGRAM_BOT_TOKEN"] = "test_token"
    env["PYTHONPATH"] = PROJECT_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    try:
        result = subprocess.run(
            [sys.executable, PROBE_SCRIPT],
            cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            "Dashboard command regression detected:\n" + result.stdout + "\n" + result.stderr
        )
        assert "DASHBOARD COMMAND PROBE PASSED" in result.stdout
    finally:
        if os.path.exists(path):
            os.remove(path)
