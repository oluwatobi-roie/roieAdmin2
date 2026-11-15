"""Isolated account-renewal tests; all remote calls are mocked."""
import copy
import unittest
from unittest.mock import Mock, patch

import requests
from sqlalchemy import text
import test_finance_api as fixtures
from test_finance_api import screenshot
from config import db
from routes.finance import ledger
from services.finance import FinanceError
from services.profile_renewal import account_lock, next_expiry


class ProfileRenewalTests(unittest.TestCase):
    tearDown = fixtures.FinanceApiTests.tearDown
    post = fixtures.FinanceApiTests.post
    create = fixtures.FinanceApiTests.create

    def setUp(self):
        fixtures.FinanceApiTests.setUp(self)
        self.account = {"id": 42, "name": "Ada", "email": "ada@example.com",
            "expirationTime": "2020-02-29T12:34:56.000+00:00", "disabled": False,
            "administrator": False, "attributes": {"keep": "unchanged"}, "phone": "1234"}
        self.get.side_effect = self.remote_get
        self.put.side_effect = self.remote_put

    def remote_get(self, url, **kwargs):
        if url.endswith("session"):
            return self.session_response
        self.assertTrue(url.endswith("users/42"), url)
        response = Mock(status_code=200)
        response.json.return_value = copy.deepcopy(self.account)
        return response

    def remote_put(self, url, **kwargs):
        self.assertTrue(url.endswith("users/42"))
        self.account = copy.deepcopy(kwargs["json"])
        return Mock(status_code=200)

    def issued(self, category="renewal", pay="30000", key="create-1"):
        self.payload["request_key"] = key
        self.payload["entries"] = [{"category": category, "total": "15000", "device_ids": [10, 11]}]
        invoice = self.create()
        response = self.post(f"invoices/{invoice['id']}/finalize", {"revision": invoice["revision"]})
        self.assertEqual(response.status_code, 200, response.json)
        invoice = response.json
        if pay:
            response = self.post(f"invoices/{invoice['id']}/payments", {"revision": invoice["revision"],
                "request_key": "payment-" + key, "amount": pay, "method": "bank_transfer",
                "paid_on": "2020-01-01", "reference": "TEST-BANK", "proof": screenshot()})
            self.assertEqual(response.status_code, 200, response.json)
            invoice = response.json
        return invoice

    def options(self):
        return self.client.get("/finance/customers/42/renewal-options")

    def extension_body(self, invoice):
        return {"invoice_id": invoice["id"], "request_key": "extend-" + invoice["id"],
            "revision": invoice["revision"], "device_ids": [10, 11],
            "expected_expiration_time": self.account["expirationTime"]}

    def extend(self, payload):
        return self.post("customers/42/extend-expiry", payload)

    def test_calendar_year_always_starts_at_old_expiry(self):
        self.assertEqual(next_expiry("2020-02-29T12:34:56Z"), "2021-02-28T12:34:56.000Z")
        self.assertEqual(next_expiry("2090-12-01T15:00:00+01:00"), "2091-12-01T14:00:00.000Z")
        for invalid in [None, "", "nonsense", "2020-01-01", "9999-01-01T00:00:00Z"]:
            with self.subTest(invalid=invalid), self.assertRaises(FinanceError):
                next_expiry(invalid)

    def test_extension_preserves_account_and_cross_audit(self):
        invoice = self.issued()
        before = copy.deepcopy(self.account)
        result = self.options()
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(len(result.json["invoices"]), 1)
        payload = self.extension_body(invoice)
        response = self.extend(payload)
        self.assertEqual(response.status_code, 200, response.json)
        operation = response.json["extension"]
        self.assertEqual(operation["expiration_time"], "2021-02-28T12:34:56.000Z")
        self.assertEqual(operation["state"], "applied")
        self.assertEqual(operation["actor"]["id"], 1)
        self.assertEqual(operation["device_ids"], [10, 11])
        self.assertEqual(operation["devices"][0]["entry_ids"], [invoice["entries"][0]["id"]])
        before["expirationTime"] = operation["expiration_time"]
        self.assertEqual(self.account, before)
        stored = self.client.get(f"/finance/invoices/{invoice['id']}").json
        self.assertEqual(stored["renewal_extension"], operation)
        self.assertEqual(stored["events"][-1]["action"], "profile_extended")
        self.assertEqual(self.options().json["invoices"], [])
        self.assertEqual(self.options().json["history"][0], operation)
        self.assertEqual(self.extend(payload).json["extension"], operation)
        self.put.assert_called_once()
        self.assertEqual(self.extend({**payload, "request_key": "repeat"}).status_code, 409)

    def test_fully_paid_invoice_required(self):
        for pay in [None, "15000"]:
            with self.subTest(pay=pay):
                invoice = self.issued(pay=pay, key=str(pay))
                self.assertEqual(self.extend(self.extension_body(invoice)).status_code, 409)
        self.assertEqual(self.options().json["invoices"], [])
        self.put.assert_not_called()

    def test_draft_void_and_free_invoices_rejected(self):
        invoice = self.issued()
        for changes in [{"status": "draft"}, {"status": "void"}, {"total_minor": 0, "payments": []}]:
            with self.subTest(changes=changes):
                with self.app.app_context(), ledger().transaction(write=True) as data:
                    data["invoices"][invoice["id"]] = {**invoice, **changes}
                self.assertEqual(self.extend(self.extension_body(invoice)).status_code, 409)
        self.put.assert_not_called()

    def test_maintenance_payment_does_not_qualify(self):
        invoice = self.issued(category="maintenance")
        self.assertEqual(self.options().json["invoices"], [])
        self.assertEqual(self.extend(self.extension_body(invoice)).status_code, 409)
        self.put.assert_not_called()

    def test_other_customer_invoice_rejected(self):
        invoice = self.issued()
        with self.app.app_context(), ledger().transaction(write=True) as data:
            data["invoices"][invoice["id"]]["customer"]["traccar_user_id"] = 43
        self.assertEqual(self.extend(self.extension_body(invoice)).status_code, 409)
        self.put.assert_not_called()

    def test_selection_must_be_distinct_renewal_vehicles_owned_now(self):
        invoice = self.issued()
        payload = self.extension_body(invoice)
        for ids in [[], [10, 10], [True], ["10"], [12], [999], None]:
            with self.subTest(ids=ids):
                self.assertIn(self.extend({**payload, "device_ids": ids}).status_code, [400, 409])
        with self.app.app_context():
            db.session.execute(text("DELETE FROM tc_user_device WHERE deviceid = 10"))
            db.session.commit()
        self.assertEqual([d["id"] for d in self.options().json["invoices"][0]["devices"]], [11])
        self.assertEqual(self.extend(payload).status_code, 409)
        self.put.assert_not_called()

    def test_mixed_invoice_excludes_installation_devices(self):
        invoice = self.issued()
        with self.app.app_context(), ledger().transaction(write=True) as data:
            data["invoices"][invoice["id"]]["entries"][1]["category"] = "installation"
        self.assertEqual([d["id"] for d in self.options().json["invoices"][0]["devices"]], [10])
        payload = self.extension_body(invoice)
        self.assertEqual(self.extend(payload).status_code, 409)
        self.assertEqual(self.extend({**payload, "device_ids": [10]}).status_code, 200)

    def test_expiry_and_invoice_revision_are_checked(self):
        invoice = self.issued()
        payload = self.extension_body(invoice)
        self.assertEqual(self.extend({**payload, "revision": 0}).status_code, 409)
        self.account["expirationTime"] = "2021-02-28T00:00:00Z"
        self.assertEqual(self.extend(payload).status_code, 409)
        self.put.assert_not_called()

    def test_unlimited_account_not_shortened_and_disabled_not_reenabled(self):
        invoice = self.issued()
        self.account["expirationTime"] = None
        self.assertIsNone(self.options().json["proposed_expiration_time"])
        self.assertEqual(self.extend(self.extension_body(invoice)).status_code, 409)
        self.put.assert_not_called()
        self.account.update(expirationTime="2090-01-01T00:00:00Z", disabled=True)
        response = self.extend(self.extension_body(invoice))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.account["disabled"])
        self.assertTrue(response.json["extension"]["disabled"])
        self.assertTrue(self.account["expirationTime"].startswith("2091"))

    def test_timeout_after_remote_commit_reconciles_without_another_put(self):
        invoice = self.issued()
        payload = self.extension_body(invoice)
        def committed(url, **kwargs):
            self.remote_put(url, **kwargs)
            raise requests.Timeout()
        self.put.side_effect = committed
        response = self.extend(payload)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.extend(payload).status_code, 200)
        self.put.assert_called_once()

    def test_pending_retry_uses_original_target_and_blocks_other_invoices(self):
        invoice = self.issued()
        second = self.issued(key="second")
        payload = self.extension_body(invoice)
        self.put.side_effect = requests.Timeout()
        response = self.extend(payload)
        self.assertEqual(response.status_code, 202, response.json)
        self.assertEqual(response.json["extension"]["state"], "pending")
        self.assertEqual(self.extend(self.extension_body(second)).status_code, 409)
        self.assertEqual(self.extend({**payload, "device_ids": [10]}).status_code, 409)
        self.put.side_effect = self.remote_put
        self.assertEqual(self.extend(payload).status_code, 200)
        self.assertEqual(self.account["expirationTime"], "2021-02-28T12:34:56.000Z")
        self.assertEqual(self.extend(payload).status_code, 200)
        self.assertEqual(self.put.call_count, 2)

    def test_uncertain_readback_and_external_changes_fail_closed(self):
        invoice = self.issued()
        payload = self.extension_body(invoice)
        def committed(url, **kwargs):
            self.remote_put(url, **kwargs)
            def unavailable(url, **kwargs):
                if url.endswith("session"):
                    return self.session_response
                raise requests.Timeout()
            self.get.side_effect = unavailable
            return Mock(status_code=200)
        self.put.side_effect = committed
        self.assertEqual(self.extend(payload).status_code, 202)
        self.get.side_effect = self.remote_get
        self.account["expirationTime"] = "2030-01-01T00:00:00Z"
        self.assertEqual(self.extend(payload).status_code, 409)
        self.put.assert_called_once()
        self.account["expirationTime"] = "2021-02-28T12:34:56.000Z"
        self.assertEqual(self.extend(payload).status_code, 200)
        self.put.assert_called_once()

    def test_intent_is_saved_before_put_and_storage_failure_prevents_write(self):
        invoice = self.issued()
        payload = self.extension_body(invoice)
        with patch("services.finance.os.replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.extend(payload)
        self.put.assert_not_called()
        def verify_intent(url, **kwargs):
            with self.app.app_context(), ledger().transaction() as data:
                self.assertEqual(data["invoices"][invoice["id"]]["renewal_extension"]["state"], "pending")
            return self.remote_put(url, **kwargs)
        self.put.side_effect = verify_intent
        self.assertEqual(self.extend(payload).status_code, 200)

    def test_ledger_failure_after_remote_commit_is_recoverable(self):
        invoice = self.issued()
        payload = self.extension_body(invoice)
        import os
        original = os.replace
        count = 0
        def replace(source, destination):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("disk failed after account update")
            return original(source, destination)
        with patch("services.finance.os.replace", side_effect=replace):
            with self.assertRaises(OSError):
                self.extend(payload)
        self.assertEqual(self.options().json["history"][0]["state"], "pending")
        self.assertEqual(self.extend(payload).status_code, 200)
        self.put.assert_called_once()

    def test_remote_rejection_and_wrong_account_never_claim_success(self):
        invoice = self.issued()
        payload = self.extension_body(invoice)
        self.account["id"] = 43
        self.assertEqual(self.extend(payload).status_code, 503)
        self.put.assert_not_called()
        self.account["id"] = 42
        self.put.side_effect = None
        self.put.return_value = Mock(status_code=403)
        self.assertEqual(self.extend(payload).status_code, 202)
        self.assertEqual(self.options().json["history"][0]["state"], "pending")

    def test_unauthorized_and_cross_origin_requests_cannot_extend(self):
        invoice = self.issued()
        payload = self.extension_body(invoice)
        self.assertEqual(self.client.post("/finance/customers/42/extend-expiry", json=payload).status_code, 403)
        self.session_response.json.return_value = {"id": 42}
        self.assertEqual(self.extend(payload).status_code, 403)
        self.assertEqual(self.options().status_code, 403)
        self.client.delete_cookie("session_token")
        self.assertEqual(self.extend(payload).status_code, 401)
        self.put.assert_not_called()

    def test_account_lock_prevents_parallel_extensions(self):
        invoice = self.issued()
        with self.app.app_context():
            directory = ledger().directory
        with account_lock(directory, 42):
            self.assertEqual(self.extend(self.extension_body(invoice)).status_code, 409)
        self.put.assert_not_called()

    def test_phone_updates_share_the_account_lock(self):
        with self.app.app_context():
            directory = ledger().directory
        with account_lock(directory, 42):
            response = self.post("customers/42/phone", {"phone": "+2348012345678", "expected_phone": "1234"})
            self.assertEqual(response.status_code, 409)
        self.put.assert_not_called()


if __name__ == "__main__":
    unittest.main()
