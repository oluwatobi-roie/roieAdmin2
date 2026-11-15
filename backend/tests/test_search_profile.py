"""Account-ID profile links use the same search profile and ownership queries."""
import unittest
from sqlalchemy import text
import test_finance_api as fixtures
from config import db
from routes.devices import device_bp
from routes.devices import search  # register the existing authenticated route


class SearchProfileTests(unittest.TestCase):
    tearDown = fixtures.FinanceApiTests.tearDown

    def setUp(self):
        fixtures.FinanceApiTests.setUp(self)
        self.app.register_blueprint(device_bp, url_prefix="/device")
        with self.app.app_context():
            for statement in [
                "ALTER TABLE tc_users ADD COLUMN expirationtime DATETIME",
                "ALTER TABLE tc_users ADD COLUMN disabled INTEGER DEFAULT 0",
                "ALTER TABLE tc_devices ADD COLUMN phone TEXT",
                "ALTER TABLE tc_devices ADD COLUMN status TEXT",
                "ALTER TABLE tc_devices ADD COLUMN model TEXT",
                "ALTER TABLE tc_devices ADD COLUMN positionid INTEGER",
                "CREATE TABLE tc_positions (id INTEGER, fixtime DATETIME, devicetime DATETIME, address TEXT)",
                "CREATE TABLE tc_groups (id INTEGER, name TEXT)",
                "INSERT INTO tc_groups VALUES (8, 'Fleet')",
                "INSERT INTO tc_users (id, name, email, phone) VALUES (1, 'Admin', 'admin@example.com', ''), (44, 'No assets', 'empty@example.com', '')",
                "INSERT INTO tc_devices (id, name, uniqueid) VALUES (42, 'Device ID collision', '99999')",
            ]:
                db.session.execute(text(statement))
            db.session.commit()

    def test_exact_customer_id_returns_profile_and_direct_group_devices(self):
        response = self.client.get('/device/search?user_id=42')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['user']['id'], 42)
        self.assertEqual(response.json['user']['name'], 'Ada')
        self.assertEqual({device['device_id'] for device in response.json['devices']}, {10, 11})

    def test_id_link_survives_email_changes_and_ignores_stale_search_term(self):
        with self.app.app_context():
            db.session.execute(text("UPDATE tc_users SET email='changed+alias@example.com' WHERE id=42"))
            db.session.commit()
        response = self.client.get('/device/search?user_id=42&term=old@example.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['user']['id'], 42)
        email_response = self.client.get('/device/search', query_string={'term': 'changed+alias@example.com'})
        self.assertEqual(email_response.json['user']['id'], 42)

    def test_account_without_devices_still_opens(self):
        response = self.client.get('/device/search?user_id=44')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['user']['id'], 44)
        self.assertEqual(response.json['devices'], [])

    def test_invalid_missing_and_excluded_accounts(self):
        for value in ['', 'abc', '0', '-1', '42 OR 1=1', '999999999999999999999']:
            with self.subTest(value=value):
                self.assertEqual(self.client.get('/device/search', query_string={'user_id': value}).status_code, 400)
        self.assertEqual(self.client.get('/device/search?user_id=999').status_code, 404)
        self.assertEqual(self.client.get('/device/search?user_id=1').status_code, 403)

    def test_profile_link_requires_sign_in(self):
        self.client.delete_cookie('session_token')
        self.assertEqual(self.client.get('/device/search?user_id=42').status_code, 401)

    def test_normal_device_search_still_works(self):
        response = self.client.get('/device/search?term=12345')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json[0]['device_id'], 10)
