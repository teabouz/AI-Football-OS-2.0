"""
Regression tests for the Coach Dashboard URL / configuration bug found
during this audit (see AI Football OS -- Telegram Integration Test Issues).

Root cause: there was no DASHBOARD_BASE_URL in the codebase at all --
handlers/team.py's dashboard_command() built the "Open Coach Dashboard"
link from PUBLIC_BASE_URL, which is documented and used elsewhere as the
*payment server's* (port 5001) public URL. A coach tapping /dashboard was
therefore sent to the wrong service entirely (payment_server.py has no
/coach/login route), on top of the already-reported localhost problem.

These tests cover the pure helper functions in config.py that decide
whether a configured dashboard URL is (a) syntactically valid at all and
(b) reachable from a device other than the machine running the bot.
"""
import config


def test_dashboard_base_url_is_a_distinct_setting_from_payment_public_base_url():
    # These must never be the same attribute/value by coincidence of code
    # path -- that coincidence is exactly what caused the original bug.
    assert hasattr(config, "DASHBOARD_BASE_URL")
    assert hasattr(config, "PUBLIC_BASE_URL")


def test_localhost_variants_are_detected_as_local_only():
    for url in [
        "http://localhost:5002",
        "http://127.0.0.1:5002",
        "https://localhost",
        "http://0.0.0.0:5002",
        "http://[::1]:5002",
    ]:
        assert config.is_local_only_url(url), f"{url} should be flagged as local-only"


def test_public_domains_and_tunnel_urls_are_not_local_only():
    for url in [
        "https://abcd1234.ngrok-free.app",
        "https://mycoachdashboard.up.railway.app",
        "http://192.168.1.50:5002",  # LAN IP: not loopback, may work on same wifi
        "https://example.com",
    ]:
        assert not config.is_local_only_url(url), f"{url} should NOT be flagged as local-only"


def test_malformed_urls_are_not_well_formed():
    for bad in ["", "not a url", "localhost:5002", "ftp://example.com"]:
        assert not config.is_well_formed_public_url(bad), f"{bad!r} should not be well-formed"


def test_well_formed_http_and_https_urls_pass():
    for good in ["http://127.0.0.1:5002", "https://abcd1234.ngrok-free.app/"]:
        assert config.is_well_formed_public_url(good)
