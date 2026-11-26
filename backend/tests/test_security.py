"""Security regressions run only against temporary files/SQLite and mocked APIs."""
import copy
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("TRACCAR_API_URL", "https://traccar.invalid/api/")
from flask import Flask
from sqlalchemy import text
import requests
from config import db
from routes.auth import auth_bp
from routes.auth import login, logout, check_session
from routes.devices import device_bp, add, device_link, search
from routes.users import user_onboard_bp, user_onboard
from services.login_rate_limit import LoginRateLimiter
import test_search_profile as search_fixtures

HEADERS = {"X-Portal-Request": "1"}


def consume_in_worker(directory):
    return LoginRateLimiter(directory, email_limit=4).consume("peer", "user@example.test")


class StaffGateTests(unittest.TestCase):
    tearDown = search_fixtures.SearchProfileTests.tearDown

    def setUp(self):
        search_fixtures.SearchProfileTests.setUp(self)
        self.app.register_blueprint(user_onboard_bp, url_prefix="/user")
        self.app.register_blueprint(auth_bp, url_prefix="/auth")
        with self.app.app_context():
            db.session.execute(text("ALTER TABLE tc_users ADD COLUMN administrator BOOLEAN DEFAULT 0"))
            db.session.execute(text("UPDATE tc_users SET administrator = 1 WHERE id = 1"))
            db.session.commit()
        self.post_remote = self.enterContext(patch("services.device_link.requests.post"))
        self.delete_remote = self.enterContext(patch("services.user_onboard.requests.delete", return_value=Mock(status_code=204)))
        self.post_remote.return_value = Mock(status_code=200, text="ok")
        self.post_remote.return_value.raise_for_status.return_value = None

    def post(self, url, body, headers=None):
        return self.client.post(url, json=body, headers=HEADERS if headers is None else headers)

    def test_every_privileged_route_rejects_forged_customer_disabled_and_malformed_sessions_before_sql(self):
        attacks = [(401, {}, 401), (200, {"id": 42}, 403), (200, {"id": 1123, "disabled": True}, 403),
                   (200, [], 403), (200, {"id": True}, 403), (200, {"id": "1"}, 403)]
        for code, principal, expected in attacks:
            with self.subTest(principal=principal):
                self.session_response.status_code = code
                self.session_response.json.return_value = principal
                with patch.object(db.session, "execute", side_effect=AssertionError("Unauthorized SQL query")):
                    self.assertEqual(self.client.get("/device/search?term=%").status_code, expected)
                    self.assertEqual(self.post("/device/add", {"name": "attack"}).status_code, expected)
                    self.assertEqual(self.post("/device/link_device", {"email": "ada@example.com", "device_id": 10}).status_code, expected)
                    self.assertEqual(self.post("/user/onboard_user", {"name": "attack", "email": "attack@example.com", "phone": ""}).status_code, expected)
        self.post_remote.assert_not_called()
        self.delete_remote.assert_not_called()

    def test_missing_cookie_and_failed_session_service_do_not_run_handlers(self):
        self.client.delete_cookie("session_token")
        self.assertEqual(self.client.get("/device/search?user_id=42").status_code, 401)
        self.get.assert_not_called()
        self.client.set_cookie("session_token", "forged")
        self.get.side_effect = requests.Timeout("sensitive upstream details")
        response = self.client.get("/device/search?user_id=42")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("sensitive", response.get_data(as_text=True))
        self.post_remote.assert_not_called()

    def test_staff_claim_is_minimal_and_customers_cannot_pass_check_session(self):
        self.session_response.json.return_value = {"id": 1123, "name": "Operator", "administrator": False, "token": "secret", "attributes": {"secret": "private"}}
        response = self.client.get("/auth/check-session")
        self.assertEqual(response.json, {"authenticated": True, "staff": True, "user": {"id": 1123, "name": "Operator"}})
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.session_response.json.return_value = {"id": 42}
        self.assertEqual(self.client.get("/auth/check-session").json, {"authenticated": False})
        self.assertEqual(self.client.get("/auth/check-session").status_code, 401)

    def test_writes_require_json_custom_header_and_object(self):
        payload = {"email": "ada@example.com", "device_id": 10}
        self.assertEqual(self.post("/device/link_device", payload, headers={}).status_code, 403)
        self.assertEqual(self.client.post("/device/link_device", data=payload, headers=HEADERS).status_code, 403)
        self.assertEqual(self.post("/device/link_device", []).status_code, 400)
        self.post_remote.assert_not_called()

    def test_staff_can_link_with_server_key_but_only_valid_customer_and_device(self):
        self.session_response.json.return_value = {"id": 1123, "name": "Staff", "administrator": False}
        with patch("services.device_link.HEADERS_JSON", {"Authorization": "Bearer test-service-key"}):
            result = self.post("/device/link_device", {"email": "ada@example.com", "device_id": 10, "administrator": True, "userId": 1})
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(self.post_remote.call_args.kwargs["json"], {"userId": 42, "deviceId": 10})
        self.assertEqual(self.post_remote.call_args.kwargs["headers"]["Authorization"], "Bearer test-service-key")
        self.post_remote.reset_mock()
        for payload, status in [({"email": "admin@example.com", "device_id": 10}, 403),
                                ({"email": "missing@example.com", "device_id": 10}, 404),
                                ({"email": "ada@example.com", "device_id": 999}, 404),
                                ({"email": "ada@example.com", "device_id": True}, 400),
                                ({"email": "ada@example.com", "device_id": "9" * 5000}, 400),
                                ({"email": "ada@example.com", "device_id": "1 OR 1=1"}, 400)]:
            self.assertEqual(self.post("/device/link_device", payload).status_code, status)
        with self.app.app_context():
            db.session.execute(text("UPDATE tc_users SET administrator=1 WHERE id=42"))
            db.session.commit()
        self.assertEqual(self.post("/device/link_device", {"email": "ada@example.com", "device_id": 10}).status_code, 403)
        self.post_remote.assert_not_called()

    def test_staff_add_route_preserves_valid_handler_contract(self):
        with patch("routes.devices.add._add_single_device", return_value=({"message": "Device added."}, 200)) as add_single:
            response = self.post("/device/add", {"name": "Corolla", "uniqueid": "123456789012345"})
        self.assertEqual(response.status_code, 200)
        add_single.assert_called_once()
        for count in (0, -1, 16, True, "bad"):
            self.assertEqual(self.post("/device/add", {"mode": "bulk", "count": count}).status_code, 400)

    def test_staff_onboarding_uses_constrained_payload_and_cleans_temporary_session(self):
        self.session_response.json.return_value = {"id": 1123, "name": "Staff"}
        def upstream(url, **kwargs):
            result = Mock(status_code=200)
            result.raise_for_status.return_value = None
            result.cookies = {"JSESSIONID": "temporary-customer-session"}
            result.json.return_value = {"id": 123}
            return result
        self.post_remote.side_effect = upstream
        response = self.post("/user/onboard_user", {"name": "New Customer", "email": "new@example.com", "phone": "", "administrator": True})
        self.assertEqual(response.status_code, 201, response.json)
        create = self.post_remote.call_args_list[0]
        self.assertTrue(create.args[0].endswith("users"))
        self.assertFalse(create.kwargs["json"]["administrator"])
        self.assertGreaterEqual(len(create.kwargs["json"]["password"]), 24)
        self.assertNotIn(create.kwargs["json"]["password"], response.get_data(as_text=True))
        self.delete_remote.assert_called_once()
        self.assertEqual(self.delete_remote.call_args.kwargs["cookies"], {"JSESSIONID": "temporary-customer-session"})

    def test_search_wildcards_are_literal_and_broad_results_are_capped(self):
        for term in ("%", "_", "%@%"):
            self.assertEqual(self.client.get("/device/search", query_string={"term": term}).status_code, 404)
        with self.app.app_context():
            db.session.execute(text("UPDATE tc_devices SET name='50%_! unit' WHERE id=10"))
            for device_id in range(100, 170):
                db.session.execute(text("INSERT INTO tc_devices (id, name, uniqueid) VALUES (:id, 'FLEET', :uid)"), {"id": device_id, "uid": str(device_id)})
                db.session.execute(text("INSERT INTO tc_user_device VALUES (42, :id)"), {"id": device_id})
            db.session.commit()
        for term in ("50%", "_!"):
            self.assertEqual(self.client.get("/device/search", query_string={"term": term}).json[0]["device_id"], 10)
        self.assertEqual(len(self.client.get("/device/search?term=FLEET").json), 50)
        profile = self.client.get("/device/search?user_id=42").json
        self.assertEqual(len(profile["devices"]), 72)  # Keep full, explicitly scoped fleets.
        self.assertFalse(profile["truncated"])


class LoginSecurityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, LOGIN_RATE_DATA_DIR=self.directory.name)
        self.app.register_blueprint(auth_bp, url_prefix="/auth")
        self.client = self.app.test_client()
        self.upstream = Mock(status_code=401)
        self.upstream.cookies = {}
        self.upstream.json.return_value = {}
        self.posted = self.enterContext(patch("routes.auth.login.requests.post", return_value=self.upstream))
        self.deleted = self.enterContext(patch("routes.auth.login.requests.delete", return_value=Mock(status_code=204)))

    def attempt(self, email="person@example.com", **kwargs):
        return self.client.post("/auth/login", json={"email": email, "password": "test-password"}, headers=HEADERS, **kwargs)

    def test_generic_failures_cleanup_and_valid_staff_cookie(self):
        invalid = self.attempt()
        self.upstream.status_code = 200
        self.upstream.cookies = {"JSESSIONID": "new-session"}
        for principal in ({"id": 42}, {"id": 1123, "disabled": True}, {"id": True}, []):
            self.upstream.json.return_value = principal
            result = self.attempt()
            self.assertEqual(result.status_code, 401)
            self.assertEqual(result.json, invalid.json)
            self.assertNotIn("Set-Cookie", result.headers)
        self.assertEqual(self.deleted.call_count, 4)
        self.upstream.json.return_value = {"id": 1123, "name": "Operator"}
        result = self.attempt()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json, {"message": "Login successful", "user_name": "Operator"})
        self.assertIn("HttpOnly", result.headers["Set-Cookie"])
        self.assertIn("SameSite=Lax", result.headers["Set-Cookie"])
        self.assertEqual(self.posted.call_args.args[0], "https://traccar.invalid/api/session")
        self.assertEqual(result.headers["Cache-Control"], "no-store")

    def test_attempts_are_limited_across_ip_changes_and_spoofed_headers(self):
        for count in range(10):
            self.assertEqual(self.attempt(email="Person@example.com", environ_overrides={"REMOTE_ADDR": f"192.0.2.{count}"}).status_code, 401)
        result = self.attempt(email=" person@EXAMPLE.com ")
        self.assertEqual(result.status_code, 429)
        self.assertGreater(int(result.headers["Retry-After"]), 0)
        self.assertEqual(self.posted.call_count, 10)
        # Headers do not create new IP budgets; independent emails cannot evade the peer cap.
        with patch("routes.auth.login.login_limiter", return_value=LoginRateLimiter(Path(self.directory.name) / "ip", ip_limit=2)):
            for index in range(2):
                result = self.client.post("/auth/login", json={"email": f"x{index}@example.com", "password": "guess"}, headers={**HEADERS, "X-Forwarded-For": str(index)})
                self.assertEqual(result.status_code, 401)
            self.assertEqual(self.client.post("/auth/login", json={"email": "other@example.com", "password": "guess"}, headers={**HEADERS, "X-Forwarded-For": "new-ip"}).status_code, 429)

    def test_malformed_input_upstream_errors_and_missing_cookie_fail_closed(self):
        for data in ([], None, {}, {"email": [], "password": "x"}, {"email": "a", "password": "x" * 1025}):
            self.assertEqual(self.client.post("/auth/login", json=data, headers=HEADERS, content_type="application/json").status_code, 400)
        self.posted.assert_not_called()
        self.posted.side_effect = requests.Timeout("SECRET")
        result = self.attempt()
        self.assertEqual(result.status_code, 503)
        self.assertNotIn("SECRET", result.get_data(as_text=True))
        self.posted.side_effect = None
        self.upstream.status_code = 200
        self.upstream.json.return_value = {"id": 1}
        self.assertEqual(self.attempt().status_code, 401)

    def test_logout_revokes_actual_upstream_session_and_deletes_cookie(self):
        self.client.set_cookie("session_token", "current-session")
        response = self.client.post("/auth/logout", json={}, headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.deleted.call_args.kwargs["cookies"], {"JSESSIONID": "current-session"})
        self.assertIn("Max-Age=0", response.headers["Set-Cookie"])
        self.client.set_cookie("session_token", "current-session")
        self.deleted.side_effect = requests.Timeout()
        self.assertEqual(self.client.post("/auth/logout", json={}, headers=HEADERS).status_code, 503)


class SharedRateLimitTests(unittest.TestCase):
    def test_shared_workers_cannot_exceed_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            with multiprocessing.get_context("spawn").Pool(3) as pool:
                results = pool.map(consume_in_worker, [directory] * 12)
            self.assertEqual(results.count(0), 4)
            self.assertGreater(LoginRateLimiter(directory, email_limit=4).consume("peer", "user@example.test"), 0)

    def test_expiry_capacity_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            moment = [1000.0]
            limiter = LoginRateLimiter(directory, window=10, email_limit=1, max_keys=8, clock=lambda: moment[0])
            self.assertEqual(limiter.consume("peer", "user@example.test"), 0)
            self.assertEqual(limiter.consume("peer", "user@example.test"), 10)
            # Do not evict live budgets to make room for attacker-controlled keys.
            self.assertGreater(limiter.consume("other", "other@example.test"), 0)
            moment[0] += 11
            self.assertEqual(limiter.consume("peer", "user@example.test"), 0)
            state = (Path(directory) / "ledger.json").read_text()
            self.assertNotIn("user@example.test", state)
