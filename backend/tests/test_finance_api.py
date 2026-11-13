import copy
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

# These tests never contact the configured production database or Traccar server.
os.environ["TRACCAR_API_URL"] = "https://traccar.invalid/api/"
from flask import Flask
from sqlalchemy import text
from config import db
from routes.finance import finance_bp


class FinanceApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, FINANCE_DATA_DIR=self.directory.name,
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SQLALCHEMY_TRACK_MODIFICATIONS=False)
        db.init_app(self.app)
        self.app.register_blueprint(finance_bp, url_prefix="/finance")
        with self.app.app_context():
            for statement in [
                "CREATE TABLE tc_users (id INTEGER, name TEXT, email TEXT, phone TEXT)",
                "CREATE TABLE tc_devices (id INTEGER, name TEXT, uniqueid TEXT, groupid INTEGER)",
                "CREATE TABLE tc_user_device (userid INTEGER, deviceid INTEGER)",
                "CREATE TABLE tc_user_group (userid INTEGER, groupid INTEGER)",
                "INSERT INTO tc_users VALUES (42, 'Ada', 'ada@example.com', ''), (43, 'Ben', 'ben@example.com', '')",
                "INSERT INTO tc_devices VALUES (10, 'Corolla', '12345', NULL), (11, 'Camry', '67890', 8), (12, 'Other', '55555', NULL)",
                "INSERT INTO tc_user_device VALUES (42, 10), (43, 12)",
                "INSERT INTO tc_user_group VALUES (42, 8)",
            ]:
                db.session.execute(text(statement))
            db.session.commit()
        self.client = self.app.test_client()
        self.client.set_cookie("session_token", "verified-session")
        self.headers = {"X-Finance-Request": "1"}
        self.session_response = Mock(status_code=200)
        self.session_response.json.return_value = {"id": 1, "name": "Staff"}
        self.get = self.enterContext(patch("routes.finance.requests.get", return_value=self.session_response))
        self.put = self.enterContext(patch("routes.finance.requests.put"))
        self.payload = {"request_key": "create-1", "customer": {
            "traccar_user_id": 42, "name": "Ada", "email": "ada@example.com", "phone": "+2348012345678",
            "address": {"line1": "1 Main Road", "city": "Ikeja", "state": "Lagos", "country": "Nigeria"}},
            "entries": [{"category": "installation", "total": "140000", "activity": "New Corolla"}], "notes": "", "due_date": ""}

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()

    def post(self, path, payload):
        return self.client.post('/finance/' + path, json=payload, headers=self.headers)

    def create(self):
        response = self.post("invoices", self.payload)
        self.assertEqual(response.status_code, 201, response.json)
        return response.json

    def test_auth_validates_session_and_staff_role(self):
        self.client.delete_cookie("session_token")
        self.assertEqual(self.client.get("/finance/invoices").status_code, 401)
        self.client.set_cookie("session_token", "forged")
        self.session_response.status_code = 401
        self.assertEqual(self.client.get("/finance/invoices").status_code, 401)
        self.session_response.status_code = 200
        self.session_response.json.return_value = {"id": 42}
        self.assertEqual(self.client.get("/finance/invoices").status_code, 403)

    def test_csrf_and_invalid_body(self):
        self.assertEqual(self.client.post("/finance/invoices", json=self.payload).status_code, 403)
        self.assertEqual(self.post("invoices", []).status_code, 400)

    def test_customer_details_and_direct_group_devices(self):
        result = self.client.get("/finance/customers/42")
        self.assertEqual(result.status_code, 200)
        self.assertEqual({d["id"] for d in result.json["devices"]}, {10, 11})
        self.assertEqual(result.json["customer"]["email"], "ada@example.com")
        self.assertEqual(result.headers["Cache-Control"], "no-store")

    def test_preview_and_calculation_do_not_save(self):
        response = self.post("preview", self.payload)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["total_minor"], 14000000)
        result = self.post("calculate", {"entries": [{"category": "renewal", "total": "15000"}]})
        self.assertEqual(result.json["total_minor"], 1500000)
        self.assertEqual(self.client.get("/finance/invoices").json["invoices"], [])

    def test_full_invoice_payment_and_later_device_link(self):
        invoice = self.create()
        self.assertEqual(invoice["entries"][0]["link_status"], "pending_installation")
        issued = self.post(f"invoices/{invoice['id']}/finalize", {"revision": invoice["revision"]}).json
        self.assertEqual(issued["status"], "issued")
        linked_response = self.post(f"invoices/{invoice['id']}/link-device", {
            "revision": issued["revision"], "entry_id": issued["entries"][0]["id"], "device_id": 11})
        self.assertEqual(linked_response.status_code, 200, linked_response.json)
        linked = linked_response.json
        self.assertEqual(linked["total_minor"], invoice["total_minor"])
        paid_response = self.post(f"invoices/{invoice['id']}/payments", {"revision": linked["revision"],
            "request_key": "pay-1", "amount": "140000", "method": "bank_transfer", "paid_on": "2020-01-01", "reference": "BANK-123"})
        self.assertEqual(paid_response.status_code, 200, paid_response.json)
        paid = paid_response.json
        self.assertEqual(paid["payment_status"], "paid")
        self.assertEqual(len(self.client.get("/finance/invoices?user_id=42&device_id=11").json["invoices"]), 1)
        self.assertEqual(self.post(f"invoices/{invoice['id']}/void", {"revision": paid["revision"], "reason": "Cancel"}).status_code, 409)
        self.put.assert_not_called()

    def test_wrong_customer_device_rejected(self):
        self.payload["entries"][0]["device_id"] = 12
        self.assertEqual(self.post("invoices", self.payload).status_code, 400)
        invoice = self.create_after_reset()
        self.assertEqual(self.post(f"invoices/{invoice['id']}/link-device", {
            "revision": invoice["revision"], "entry_id": invoice["entries"][0]["id"], "device_id": 12}).status_code, 400)

    def create_after_reset(self):
        self.payload["entries"][0].pop("device_id", None)
        return self.create()

    def test_finalization_rechecks_device_ownership(self):
        self.payload["entries"][0]["device_id"] = 10
        invoice = self.create()
        with self.app.app_context():
            db.session.execute(text("DELETE FROM tc_user_device WHERE deviceid=10"))
            db.session.commit()
        self.assertEqual(self.post(f"invoices/{invoice['id']}/finalize", {"revision": invoice["revision"]}).status_code, 409)

    def test_prospect_can_link_to_account_without_changing_snapshot(self):
        self.payload["customer"]["traccar_user_id"] = None
        invoice = self.create()
        response = self.post(f"invoices/{invoice['id']}/link-customer", {"revision": invoice["revision"], "user_id": 42})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["customer"]["name"], invoice["customer"]["name"])
        self.assertEqual(response.json["customer"]["traccar_user_id"], 42)

    def test_customer_billing_profile_reused(self):
        self.create()
        customer = self.client.get("/finance/customers/42").json["customer"]
        self.assertEqual(customer["formatted_address"], "1 Main Road\nIkeja, Lagos\nNigeria")
        self.assertEqual(customer["phone"], "+2348012345678")

    def test_phone_sync_changes_only_phone(self):
        original = {"id": 42, "name": "Ada", "email": "ada@example.com", "phone": "", "administrator": False,
                    "attributes": {"custom": "preserve"}, "deviceLimit": 8}
        user_response = Mock(status_code=200)
        user_response.json.return_value = copy.deepcopy(original)
        self.get.side_effect = [self.session_response, user_response]
        response = self.post("customers/42/phone", {"phone": "+234 801 234 5678", "expected_phone": ""})
        self.assertEqual(response.status_code, 200, response.json)
        sent = self.put.call_args.kwargs["json"]
        self.assertEqual(sent, {**original, "phone": "+2348012345678"})

    def test_phone_conflict_does_not_write(self):
        user_response = Mock(status_code=200)
        user_response.json.return_value = {"id": 42, "phone": "08099999999"}
        self.get.side_effect = [self.session_response, user_response]
        response = self.post("customers/42/phone", {"phone": "+2348012345678", "expected_phone": ""})
        self.assertEqual(response.status_code, 409)
        self.put.assert_not_called()

    def test_duplicate_draft_with_changed_amount_rejected(self):
        invoice = self.create()
        self.assertEqual(self.create()["id"], invoice["id"])
        self.payload["entries"][0]["total"] = "100000"
        self.assertEqual(self.post("invoices", self.payload).status_code, 409)

    def test_duplicate_payment_with_changed_amount_rejected(self):
        invoice = self.create()
        invoice = self.post(f"invoices/{invoice['id']}/finalize", {"revision": invoice["revision"]}).json
        payment = {"revision": invoice["revision"], "request_key": "payment-1", "amount": "1000",
                   "method": "cash", "paid_on": "2020-01-01", "reference": "REC-1"}
        endpoint = f"invoices/{invoice['id']}/payments"
        self.assertEqual(self.post(endpoint, payment).status_code, 200)
        self.assertEqual(self.post(endpoint, payment).status_code, 200)
        self.assertEqual(self.post(endpoint, {**payment, "amount": "2000"}).status_code, 409)

    def test_grouped_invoice_lifecycle_preserves_vehicle_mapping(self):
        self.payload["entries"] = [{"category": "renewal", "total": "15000", "device_ids": [10, 11],
                                    "pending_vehicles": [], "quantity": 2, "activity": "Annual renewal"}]
        invoice = self.create()
        self.assertEqual(invoice["total_minor"], 3000000)
        issued = self.post(f"invoices/{invoice['id']}/finalize", {"revision": invoice["revision"]})
        self.assertEqual(issued.status_code, 200)
        self.assertEqual(len(self.client.get("/finance/invoices?user_id=42&device_id=11").json["invoices"]), 1)

    def test_pending_group_links_keep_quantity_and_reject_duplicate_device(self):
        self.payload["entries"] = [{"category": "installation", "total": "140000", "device_ids": [],
                                    "pending_vehicles": ["New Corolla", "New Hilux"], "quantity": 2}]
        invoice = self.create()
        endpoint = f"invoices/{invoice['id']}/link-device"
        linked = self.post(endpoint, {"revision": invoice["revision"], "entry_id": invoice["entries"][0]["id"], "device_id": 10}).json
        duplicate = self.post(endpoint, {"revision": linked["revision"], "entry_id": linked["entries"][1]["id"], "device_id": 10})
        self.assertEqual(duplicate.status_code, 400)
        response = self.post(endpoint, {"revision": linked["revision"], "entry_id": linked["entries"][1]["id"], "device_id": 11})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["entries"]), 2)
        self.assertEqual(response.json["total_minor"], 28000000)


if __name__ == "__main__":
    unittest.main()
