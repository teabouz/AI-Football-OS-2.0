"""
Section 10 of the audit: role/authorization enforcement, exercised against
the real handler functions (see tests/_role_auth_probe.py for the scenario).
Subprocess-isolated for the same reason as the XSS regression test --
DATABASE_URL must be set before database.py/config.py are imported.
"""
import os
import subprocess
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_role_auth_probe.py")


def test_player_cannot_access_coach_only_commands():
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
            "Role authorization regression detected:\n" + result.stdout + "\n" + result.stderr
        )
        assert "ROLE AUTH PROBE PASSED" in result.stdout
    finally:
        if os.path.exists(path):
            os.remove(path)
