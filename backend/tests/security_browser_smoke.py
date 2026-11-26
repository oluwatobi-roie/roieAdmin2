"""Actual Next proxy/middleware and Flask routes, with fake upstream auth and temporary SQL.
No production API calls, account changes, emails or WhatsApp messages.
"""
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from time import monotonic, sleep
from urllib.request import urlopen
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from test_security import StaffGateTests
from routes.auth import auth_bp
from routes.devices import device_bp
from routes.users import user_onboard_bp
from routes.finance import finance_bp


def main():
    fixture = StaffGateTests()
    fixture.setUp()
    fixture.enterContext(patch.dict(os.environ, {"FLASK_ENV": "development"}))
    for bp, prefix, name in [(auth_bp, "auth", "security_auth"), (device_bp, "device", "security_devices"),
                             (user_onboard_bp, "user", "security_users"), (finance_bp, "finance", "security_finance")]:
        fixture.app.register_blueprint(bp, url_prefix="/backend/" + prefix, name=name)
    sessions = {"customer": {"id": 42, "name": "Customer"}, "disabled": {"id": 1123, "disabled": True}}
    revoked = []
    def get_session(url, **kwargs):
        assert url.endswith("session"), url
        principal = sessions.get(kwargs.get("cookies", {}).get("JSESSIONID"))
        result = Mock(status_code=200 if principal else 401)
        result.json.return_value = principal or {}
        return result
    def post_session(url, **kwargs):
        assert url.endswith("session"), url
        fields = kwargs.get("data", {})
        staff = fields.get("email") == "staff@example.test" and fields.get("password") == "correct-password"
        customer = fields.get("email") == "customer@example.test" and fields.get("password") == "correct-password"
        result = Mock(status_code=200 if staff or customer else 401)
        token = "staff-session" if staff else "customer-login"
        principal = {"id": 1123 if staff else 42, "name": "Staff" if staff else "Customer"}
        result.cookies = {"JSESSIONID": token} if staff or customer else {}
        result.json.return_value = principal if staff or customer else {}
        if staff or customer:
            sessions[token] = principal
        return result
    def delete_session(url, **kwargs):
        assert url.endswith("session"), url
        token = kwargs.get("cookies", {}).get("JSESSIONID")
        revoked.append(token)
        sessions.pop(token, None)
        return Mock(status_code=204)
    fixture.get.side_effect = get_session
    fixture.post_remote.side_effect = post_session
    fixture.delete_remote.side_effect = delete_session
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    server = make_server("127.0.0.1", 5062, fixture.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    project = Path(__file__).resolve().parents[2]
    log = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    process = subprocess.Popen(["node", "node_modules/next/dist/bin/next", "start", "-p", "3110", "--hostname", "127.0.0.1"],
        cwd=project / "frontend", env={**os.environ, "BACKEND_URL": "http://127.0.0.1:5062",
        "NEXT_BUILD_DIR": os.environ.get("NEXT_BUILD_DIR", ".next-renewal-check"), "NEXT_TELEMETRY_DISABLED": "1"},
        stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    base = "http://127.0.0.1:3110"
    try:
        deadline = monotonic() + 45
        while monotonic() < deadline:
            try:
                with urlopen(base + "/login", timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:
                sleep(.3)
        else:
            log.seek(0)
            raise RuntimeError(log.read())
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context()
            for cookie in (None, "forged", "customer", "disabled"):
                context.clear_cookies()
                if cookie:
                    context.add_cookies([{"name": "session_token", "value": cookie, "url": base}])
                for path in ("/", "/search", "/finance", "/add-device", "/onboard_user"):
                    response = context.request.get(base + path, max_redirects=0)
                    assert response.status == 307, (cookie, path, response.status)
                    assert response.headers["location"].endswith("/login")
                response = context.request.get(base + "/api/search?user_id=42")
                assert response.status in (401, 403), (cookie, response.status)
            context.clear_cookies()
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base + "/login")
            cross = context.request.post(base + "/api/auth/login", data={"email": "staff@example.test", "password": "correct-password"}, headers={"origin": "https://evil.test", "x-forwarded-host": "evil.test"})
            assert cross.status == 403
            # Login messages must not reveal that a customer's password was valid.
            for email, password in [("customer@example.test", "correct-password"), ("wrong@example.test", "wrong")]:
                result = page.evaluate("""async body => { const r = await fetch('/api/auth/login', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); return {status:r.status, data:await r.json()}; }""", {"email": email, "password": password})
                assert result == {"status": 401, "data": {"error": "Invalid credentials"}}, result
            assert "customer-login" in revoked
            page.get_by_placeholder("Enter your email").fill("staff@example.test")
            page.get_by_placeholder("Enter your password").fill("correct-password")
            page.get_by_role("button", name="Login", exact=True).click()
            expect(page.get_by_role("heading", name="Your workspace")).to_be_visible()
            cookie = next(item for item in context.cookies() if item["name"] == "session_token")
            assert cookie["httpOnly"] and cookie["sameSite"] == "Lax"
            search = context.request.get(base + "/api/search?user_id=42")
            assert search.status == 200 and search.json()["user"]["id"] == 42
            page.get_by_role("button", name="Logout", exact=True).click()
            expect(page).to_have_url(base + "/login")
            assert "staff-session" in revoked
            assert not any(item["name"] == "session_token" for item in context.cookies())
            assert context.request.get(base + "/search", max_redirects=0).status == 307
            # Rate limits survive separate requests/proxy workers; forwarded IPs do not evade them.
            statuses = []
            for index in range(11):
                response = context.request.post(base + "/api/auth/login", data={"email": "guess@example.test", "password": "wrong"}, headers={"origin": base, "x-forwarded-for": f"192.0.2.{index}"})
                statuses.append(response.status)
            assert statuses[:10] == [401] * 10 and statuses[-1] == 429, statuses
            assert int(response.headers["retry-after"]) > 0
            assert not errors, errors
            browser.close()
        print("Security browser checks passed: all console pages gated, forged/customer/disabled sessions blocked, valid staff login/search/logout, generic failures, same-origin guard and proxy rate limiting.")
    except Exception:
        log.flush()
        log.seek(0)
        print(log.read()[-8000:])
        raise
    finally:
        process.terminate()
        process.wait(timeout=15)
        server.shutdown()
        log.close()
        fixture.tearDown()
        fixture.doCleanups()


if __name__ == "__main__":
    main()
