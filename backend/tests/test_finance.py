import copy
import multiprocessing
import random
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from services.finance import (FinanceError, Ledger, breakdown, clean_customer,
    finalize, invoice_view, prepare_entries, record_payment, save_draft)


ACTOR = {"id": 1, "name": "Finance staff"}
CUSTOMER = {"profile_id": "traccar-42", "traccar_user_id": 42,
    "name": "Ada Customer", "email": "ada@example.com", "phone": "+2348012345678",
    "address": {"line1": "  10   Main Road ", "line2": "", "city": " Ikeja ",
                "state": " Lagos ", "postal_code": "", "country": "Nigeria"}}


def increment_ledger(directory, count):
    for _ in range(count):
        with Ledger(directory).transaction(write=True) as data:
            data["sequence"] += 1


class PricingTests(unittest.TestCase):
    def test_defaults(self):
        expected = {"renewal": ("15000", [1200000, 300000]),
                    "maintenance": ("20000", [1200000, 800000]),
                    "installation": ("140000", [1204000, 336000, 1960000, 10500000])}
        for category, (total, amounts) in expected.items():
            self.assertEqual([p["amount_minor"] for p in breakdown(category, total)["breakdown"]], amounts)

    def test_installation_floor_and_negotiation(self):
        self.assertEqual([p["amount_minor"] for p in breakdown("installation", "15000")["breakdown"]],
                         [1200000, 300000, 0, 0])
        parts = breakdown("installation", "100000")["breakdown"]
        self.assertEqual([p["amount_minor"] for p in parts], [1200000, 300000, 1337079, 7162921])
        with self.assertRaises(FinanceError):
            breakdown("installation", "14999.99")

    def test_random_amounts_sum_exactly(self):
        rng = random.Random(123)
        for category in ("renewal", "installation", "maintenance"):
            for _ in range(400):
                cents = rng.randint(1500000 if category == "installation" else 1, 100000000000)
                result = breakdown(category, str(Decimal(cents) / 100))
                self.assertEqual(sum(p["amount_minor"] for p in result["breakdown"]), cents)
                self.assertTrue(all(p["amount_minor"] >= 0 for p in result["breakdown"]))
                if category == "installation":
                    self.assertGreaterEqual(result["breakdown"][0]["amount_minor"], 1200000)
                    self.assertGreaterEqual(result["breakdown"][1]["amount_minor"], 300000)

    def test_invalid_amounts(self):
        for value in (0, -1, "NaN", "Infinity", "1.005", "bad", None, True, "1000000000.01"):
            with self.subTest(value=value), self.assertRaises(FinanceError):
                breakdown("renewal", value)

    def test_contact_normalization(self):
        result = clean_customer(CUSTOMER)
        self.assertEqual(result["formatted_address"], "10 Main Road\nIkeja, Lagos\nNigeria")
        self.assertEqual(result["phone"], "+2348012345678")
        for key, value in [("phone", "***"), ("email", "bad"), ("address", {})]:
            with self.subTest(key=key), self.assertRaises(FinanceError):
                clean_customer({**CUSTOMER, key: value})

    def test_device_ownership_and_pending_activity(self):
        raw = {"category": "installation", "total": "140000", "activity": "New Corolla"}
        entry = prepare_entries([raw], [])[0]
        self.assertEqual(entry["link_status"], "pending_installation")
        with self.assertRaises(FinanceError):
            prepare_entries([{**raw, "device_id": 99}], [{"id": 22, "name": "Owned"}])
        with self.assertRaises(FinanceError):
            prepare_entries([{**raw, "activity": ""}], [])


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.ledger = Ledger(self.directory.name)
        self.customer = {**clean_customer(CUSTOMER), "profile_id": "traccar-42", "traccar_user_id": 42}
        self.payload = {"request_key": "draft-request-1", "notes": "Thanks", "due_date": "2027-01-01"}

    def create(self, data):
        return save_draft(data, self.payload, self.customer,
            prepare_entries([{"category": "renewal", "total": "15000", "activity": "Annual subscription"}], []), ACTOR)

    def test_draft_issue_payment_retry_and_snapshot(self):
        with self.ledger.transaction(write=True) as data:
            invoice = self.create(data)
            duplicate = self.create(data)
            self.assertEqual(invoice["id"], duplicate["id"])
            self.assertEqual(len(data["invoices"]), 1)
            self.customer["name"] = "Changed contact"
            self.assertEqual(invoice["customer"]["name"], "Ada Customer")
            finalize(data, invoice, {"revision": 1}, ACTOR)
            finalize(data, invoice, {"revision": 1}, ACTOR)
            self.assertEqual(data["sequence"], 1)
            payment = {"revision": invoice["revision"], "request_key": "pay-1", "amount": "5000",
                       "method": "bank_transfer", "paid_on": "2020-01-01", "reference": "BANK-001"}
            record_payment(invoice, payment, ACTOR)
            record_payment(invoice, payment, ACTOR)
            self.assertEqual(len(invoice["payments"]), 1)
            self.assertEqual(invoice_view(invoice)["balance_minor"], 1000000)
            self.assertEqual(invoice_view(invoice)["payment_status"], "partial")
            record_payment(invoice, {**payment, "revision": invoice["revision"], "request_key": "pay-2", "amount": "10000"}, ACTOR)
            self.assertEqual(invoice_view(invoice)["payment_status"], "paid")
        with self.ledger.transaction() as data:
            self.assertEqual(len(next(iter(data["invoices"].values()))["payments"]), 2)

    def test_stale_revision_overpayment_and_issued_edit(self):
        with self.ledger.transaction(write=True) as data:
            invoice = self.create(data)
            with self.assertRaises(FinanceError):
                finalize(data, invoice, {"revision": 0}, ACTOR)
            finalize(data, invoice, {"revision": 1}, ACTOR)
            with self.assertRaises(FinanceError):
                save_draft(data, {**self.payload, "revision": invoice["revision"]}, self.customer, [], ACTOR, invoice["id"])
            with self.assertRaises(FinanceError):
                record_payment(invoice, {"revision": invoice["revision"], "request_key": "pay-1", "amount": "15000.01"}, ACTOR)

    def test_failed_transaction_does_not_persist(self):
        with self.assertRaises(RuntimeError):
            with self.ledger.transaction(write=True) as data:
                self.create(data)
                raise RuntimeError("Simulated failure")
        with self.ledger.transaction() as data:
            self.assertEqual(data["invoices"], {})

    def test_corruption_is_not_overwritten(self):
        path = Path(self.directory.name) / "ledger.json"
        path.write_text("not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            with self.ledger.transaction(write=True):
                pass
        self.assertEqual(path.read_text(encoding="utf-8"), "not json")

    def test_multiple_processes_cannot_lose_writes(self):
        workers = [multiprocessing.Process(target=increment_ledger, args=(self.directory.name, 15)) for _ in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(25)
            self.assertEqual(worker.exitcode, 0)
        with self.ledger.transaction() as data:
            self.assertEqual(data["sequence"], 60)


if __name__ == "__main__":
    unittest.main()
