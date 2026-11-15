"""No real SMTP, customer accounts or production ledger are used in these tests."""
import copy
import json
import os
import smtplib
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_finance_api as fixtures
from services.finance import Ledger, finalize
from services.finance_mail import mailbox, send_document, smtp_settings
from services.finance_pdf import document_pdf, groups, SALES_TERMS

SETTINGS = dict(host="smtp.example.test", port=587, user="staff", password="test-only",
                sender="RoieTrackers <staff@example.test>", envelope="staff@example.test", tls=True)


class EmailApiTests(unittest.TestCase):
    setUp = fixtures.FinanceApiTests.setUp
    tearDown = fixtures.FinanceApiTests.tearDown
    post = fixtures.FinanceApiTests.post
    create = fixtures.FinanceApiTests.create

    def issued(self):
        draft = self.create()
        response = self.post(f"invoices/{draft['id']}/finalize", {"revision": draft["revision"]})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def send(self, invoice, **extra):
        return self.post(f"invoices/{invoice['id']}/email", {"revision": invoice["revision"],
            "request_key": "mail-1", "kind": "invoice", **extra})

    def paid(self, invoice, amount, key):
        response = self.post(f"invoices/{invoice['id']}/payments", {"revision": invoice["revision"],
            "request_key": key, "amount": amount, "method": "bank_transfer", "paid_on": "2020-01-01",
            "reference": key, "proof": fixtures.screenshot()})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    @patch("routes.finance.smtp_settings", return_value=SETTINGS)
    @patch("routes.finance.send_document", return_value=("sent", "Email sent."))
    def test_invoice_pdf_recipient_audit_and_retry(self, transport, settings):
        invoice = self.issued()
        response = self.send(invoice, recipient="attacker@example.test")
        self.assertEqual(response.status_code, 200, response.json)
        delivery = response.json["delivery"]
        self.assertEqual(delivery["recipient"], "ada@example.com")
        self.assertEqual(delivery["state"], "sent")
        self.assertTrue(transport.call_args.args[2].startswith(b"%PDF"))
        self.assertEqual(transport.call_args.args[1]["document_number"], invoice["number"])
        self.assertEqual(self.send(invoice).json["delivery"]["id"], delivery["id"])
        transport.assert_called_once()
        self.assertEqual(self.send(invoice, kind="receipt").status_code, 409)
        self.assertEqual(response.json["invoice"]["events"][-1]["action"], "email_sent")

    @patch("routes.finance.smtp_settings", return_value=SETTINGS)
    @patch("routes.finance.send_document", return_value=("sent", "Email sent."))
    def test_individual_and_combined_receipts(self, transport, settings):
        invoice = self.paid(self.issued(), "40000", "payment-1")
        invoice = self.paid(invoice, "100000", "payment-2")
        single = self.send(invoice, kind="receipt", payment_id=invoice["payments"][0]["id"])
        self.assertEqual(single.status_code, 200, single.json)
        self.assertTrue(single.json["delivery"]["document_number"].endswith("-R001"))
        combined = self.send(single.json["invoice"], kind="receipt", request_key="mail-2")
        self.assertEqual(combined.status_code, 200, combined.json)
        self.assertTrue(combined.json["delivery"]["document_number"].endswith("-ALL-002"))
        self.assertEqual(transport.call_count, 2)

    @patch("routes.finance.smtp_settings", return_value=SETTINGS)
    @patch("routes.finance.send_document")
    def test_validation_never_sends(self, transport, settings):
        draft = self.create()
        self.assertEqual(self.send(draft).status_code, 409)
        invoice = self.post(f"invoices/{draft['id']}/finalize", {"revision": draft["revision"]}).json
        self.assertEqual(self.send(invoice, revision=0).status_code, 409)
        self.assertEqual(self.send(invoice, kind="receipt").status_code, 409)
        self.assertEqual(self.send(invoice, kind="invoice", payment_id="bad").status_code, 400)
        self.assertEqual(self.send(invoice, kind="bad").status_code, 400)
        paid = self.paid(invoice, "1000", "p1")
        self.assertEqual(self.send(paid, kind="receipt", payment_id="missing").status_code, 404)
        with Ledger(self.directory.name).transaction(write=True) as data:
            data["invoices"][invoice["id"]]["status"] = "void"
        self.assertEqual(self.send(paid).status_code, 409)
        self.client.delete_cookie("session_token")
        self.assertEqual(self.send(paid).status_code, 401)
        transport.assert_not_called()

    @patch("routes.finance.smtp_settings", return_value=SETTINGS)
    @patch("routes.finance.send_document", return_value=("unknown", "Check mailbox before resending."))
    def test_unknown_outcome_requires_explicit_resend(self, transport, settings):
        invoice = self.issued()
        result = self.send(invoice).json
        current = result["invoice"]
        self.assertEqual(self.send(invoice).json["delivery"]["state"], "unknown")
        self.assertEqual(self.send(current, request_key="second").status_code, 409)
        self.assertEqual(self.send(current, request_key="second", confirm_resend=True).status_code, 200)
        self.assertEqual(transport.call_count, 2)

    @patch("routes.finance.smtp_settings", return_value=SETTINGS)
    @patch("routes.finance.send_document")
    def test_intent_is_durable_and_duplicate_during_send_is_not_sent(self, transport, settings):
        invoice = self.issued()
        def during_send(*args):
            duplicate = self.send(invoice)
            self.assertEqual(duplicate.json["delivery"]["state"], "pending")
            current = duplicate.json["invoice"]
            self.assertEqual(self.send(current, request_key="second", confirm_resend=True).status_code, 409)
            return "sent", "Email sent."
        transport.side_effect = during_send
        self.assertEqual(self.send(invoice).status_code, 200)
        transport.assert_called_once()

    def test_numbering_starts_at_019674_and_skips_two_without_changing_history(self):
        first = self.issued()
        self.assertTrue(first["number"].endswith("-019674"))
        self.payload["request_key"] = "draft-two"
        second = self.issued()
        self.assertTrue(second["number"].endswith("-019676"))
        with Ledger(self.directory.name).transaction(write=True) as data:
            old = copy.deepcopy(first)
            old["number"] = "ROIE-2025-000001"
            old["id"] = "legacy"
            data["invoices"]["legacy"] = old
            data["sequence"] = 1  # Simulate a stale counter on an imported ledger.
            before = copy.deepcopy(old)
        self.payload["request_key"] = "draft-three"
        third = self.issued()
        self.assertTrue(third["number"].endswith("-019678"))
        with Ledger(self.directory.name).transaction() as data:
            self.assertEqual(data["invoices"]["legacy"], before)
            self.assertEqual(data["invoices"][first["id"]]["number"], first["number"])
        again = self.post(f"invoices/{first['id']}/finalize", {"revision": first["revision"]}).json
        self.assertEqual(again["number"], first["number"])

    def test_grouped_large_pdf_and_receipt_generation(self):
        invoice = self.issued()
        renewal = copy.deepcopy(invoice["entries"][0])
        renewal.update(category="renewal", total_minor=1500000, activity="Annual renewal", task_notes="Fleet renewal",
            breakdown=[{"label": "GPRS fee", "amount_minor": 1200000}, {"label": "Server fee", "amount_minor": 300000}])
        invoice["entries"] = [dict(renewal, id=str(i), device={"id": i, "name": f"Vehicle {i:03}", "imei": str(i)}) for i in range(1, 69)]
        invoice.update(total_minor=102000000, subtotal_minor=102000000, discount_minor=0)
        self.assertEqual(len(groups(invoice["entries"])), 1)
        pdf, number = document_pdf(invoice)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 10000)
        # Long customer-entered text must wrap, be escaped, and paginate.
        invoice["entries"][0].update(category="special", breakdown=[{"label": "<b>Custom & equipment</b>", "description": "Description " * 180, "amount_minor": 1500000}])
        pdf, number = document_pdf(invoice)
        self.assertTrue(pdf.startswith(b"%PDF"))


class TransportTests(unittest.TestCase):
    def operation(self):
        return {"recipient": "ada@example.com", "label": "Invoice", "document_number": "ROIE-2026-019674",
                "message_id": "<test@example.test>", "customer_name": "Ada", "filename": "invoice.pdf"}

    @patch("services.finance_mail.smtplib.SMTP")
    def test_tls_auth_single_recipient_pdf(self, smtp):
        connection = smtp.return_value
        connection.send_message.return_value = {}
        state, message = send_document(SETTINGS, self.operation(), b"%PDF-test")
        self.assertEqual(state, "sent")
        connection.starttls.assert_called_once()
        connection.login.assert_called_once_with("staff", "test-only")
        connection.close.assert_called_once()
        call = connection.send_message.call_args
        self.assertEqual(call.kwargs["to_addrs"], ["ada@example.com"])
        mail = call.args[0]
        self.assertEqual(mail["To"], "ada@example.com")
        attachments = list(mail.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_content_type(), "application/pdf")
        self.assertEqual(attachments[0].get_payload(decode=True), b"%PDF-test")

    @patch("services.finance_mail.smtplib.SMTP")
    def test_failures_are_sanitized_and_disconnect_after_data_is_uncertain(self, smtp):
        connection = smtp.return_value
        connection.login.side_effect = smtplib.SMTPAuthenticationError(535, b"SECRET")
        state, message = send_document(SETTINGS, self.operation(), b"%PDF")
        self.assertEqual(state, "failed")
        self.assertNotIn("SECRET", message)
        connection.send_message.assert_not_called()
        connection.login.side_effect = None
        connection.send_message.side_effect = TimeoutError("SECRET")
        self.assertEqual(send_document(SETTINGS, self.operation(), b"%PDF")[0], "unknown")
        connection.send_message.side_effect = smtplib.SMTPDataError(550, b"SECRET")
        self.assertEqual(send_document(SETTINGS, self.operation(), b"%PDF")[0], "failed")

    @patch("services.finance_mail.smtplib.SMTP_SSL")
    def test_implicit_tls(self, smtp):
        smtp.return_value.send_message.return_value = {}
        self.assertEqual(send_document({**SETTINGS, "port": 465}, self.operation(), b"%PDF")[0], "sent")
        smtp.return_value.starttls.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch("services.finance_mail.dotenv_values")
    def test_root_smtp_fallback_environment_precedence_and_validation(self, dotenv):
        dotenv.return_value = {"SMTP_HOST": "smtp.example.test", "SMTP_FROM": "Roie <staff@example.test>",
            "SMTP_USER": "user", "SMTP_PASSWORD": "test-only", "SMTP_TLS": "true", "DATABASE_URL": "never-loaded"}
        self.assertEqual(smtp_settings()["port"], 587)
        self.assertNotIn("DATABASE_URL", os.environ)
        with patch.dict(os.environ, {"SMTP_HOST": "override.test"}):
            self.assertEqual(smtp_settings()["host"], "override.test")
        for value in ("bad", "person@example.com\nBcc: x@example.test", "a@example.test,b@example.test"):
            with self.assertRaises(ValueError):
                mailbox(value)
        with patch.dict(os.environ, {"SMTP_TLS": "false"}):
            with self.assertRaises(ValueError):
                smtp_settings()

    def test_pdf_sales_terms_match_browser_document(self):
        import re
        source = (Path(__file__).resolve().parents[2] / "frontend/src/lib/invoice-content.ts").read_text(encoding="utf-8")
        expected = re.findall(r"^  '(.*)',?$", source.split("export const salesTerms = [")[1], re.M)
        self.assertEqual(SALES_TERMS, expected)
        self.assertEqual(len(SALES_TERMS), 14)
