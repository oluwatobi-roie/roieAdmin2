import base64
import copy
from pathlib import Path
from unittest.mock import patch
from services.finance import FinanceError, Ledger, invoice_totals, prepare_entries
import unittest
import test_finance_api as fixtures
screenshot = fixtures.screenshot


class RevisedFinanceTests(unittest.TestCase):
    setUp = fixtures.FinanceApiTests.setUp
    tearDown = fixtures.FinanceApiTests.tearDown
    post = fixtures.FinanceApiTests.post
    create = fixtures.FinanceApiTests.create
    def issued(self):
        invoice = self.create()
        result = self.post(f"invoices/{invoice['id']}/finalize", {"revision": invoice["revision"]})
        self.assertEqual(result.status_code, 200, result.json)
        return result.json

    def pay(self, invoice, amount, key='payment-one', proof=None):
        return self.post(f"invoices/{invoice['id']}/payments", {
            "revision": invoice["revision"], "amount": amount, "method": "bank_transfer",
            "reference": key, "request_key": key, "paid_on": "2020-01-01", "proof": proof or screenshot()})

    def test_identity_is_authoritative_and_billing_address_reused(self):
        for key, value in (("name", "Different"), ("email", "other@example.com")):
            payload = copy.deepcopy(self.payload)
            payload['customer'][key] = value
            self.assertEqual(self.post('preview', payload).status_code, 400)
            self.assertEqual(self.post('invoices', payload).status_code, 400)
        invoice = self.create()
        from config import db
        from sqlalchemy import text
        with self.app.app_context():
            db.session.execute(text("UPDATE tc_users SET name='Ada Updated' WHERE id=42"))
            db.session.commit()
        loaded = self.client.get('/finance/customers/42').json['customer']
        self.assertEqual(loaded['name'], 'Ada Updated')
        self.assertEqual(loaded['address'], invoice['customer']['address'])
        self.assertEqual(self.post(f"invoices/{invoice['id']}/finalize", {'revision': invoice['revision']}).status_code, 409)

    def test_only_owner_with_live_admin_role_can_cancel(self):
        invoice = self.create()
        endpoint = f"invoices/{invoice['id']}/void"
        for user in ({'id': 1}, {'id': 1, 'administrator': False}, {'id': 1123, 'administrator': True}, {'id': 1, 'administrator': 'true'}):
            self.session_response.json.return_value = user
            self.assertFalse(self.client.get('/finance/permissions').json['can_cancel'])
            self.assertEqual(self.post(endpoint, {'revision': invoice['revision'], 'reason': 'Cancelled'}).status_code, 403)
        self.session_response.json.return_value = {'id': 1, 'administrator': True}
        self.assertTrue(self.client.get('/finance/permissions').json['can_cancel'])
        result = self.post(endpoint, {'revision': invoice['revision'], 'reason': 'Duplicate order'})
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json['status'], 'void')

    def test_renewal_and_maintenance_require_devices(self):
        for category in ('renewal', 'maintenance'):
            for task in ({'activity': 'Service'}, {'device_ids': [], 'pending_count': 2}, {'device_ids': [], 'pending_vehicles': ['Car']}):
                self.payload['entries'] = [{'category': category, 'total': '15000', **task}]
                self.assertEqual(self.post('invoices', self.payload).status_code, 400)

    def test_installation_count_mixed_selection_notes_and_special_service(self):
        self.payload['entries'] = [
            {'category': 'installation', 'total': '100000', 'device_ids': [10], 'pending_count': 2, 'quantity': 3, 'task_notes': 'Install at customer site'},
            {'category': 'special', 'total': '12500.25', 'item': 'Diagnostic visit', 'description': 'Inspect wiring and report faults', 'quantity': 1}]
        invoice = self.issued()
        self.assertEqual(len(invoice['entries']), 4)
        self.assertEqual(invoice['total_minor'], 31250025)
        self.assertEqual(invoice['entries'][0]['task_notes'], 'Install at customer site')
        special = invoice['entries'][-1]
        self.assertEqual(special['breakdown'][0]['description'], 'Inspect wiring and report faults')
        self.assertEqual(special['link_status'], 'activity_only')
        self.assertEqual(self.post(f"invoices/{invoice['id']}/link-device", {'revision': invoice['revision'], 'entry_id': special['id'], 'device_id': 11}).status_code, 400)
        for changes in ({'description': ''}, {'item': ''}, {'quantity': 2}, {'device_ids': [10]}):
            self.assertEqual(self.post('preview', {**self.payload, 'entries': [{**self.payload['entries'][-1], **changes}]}).status_code, 400)

    def test_discounts_apply_once_and_payment_uses_net_total(self):
        self.payload['entries'] = [{'category': 'renewal', 'total': '15000', 'device_ids': [10, 11]}]
        self.payload['discount'] = {'type': 'percent', 'value': '10'}
        invoice = self.issued()
        self.assertEqual(invoice['subtotal_minor'], 3000000)
        self.assertEqual(invoice['discount_minor'], 300000)
        self.assertEqual(invoice['total_minor'], 2700000)
        self.assertEqual(self.pay(invoice, '27000.01').status_code, 400)
        paid = self.pay(invoice, '27000')
        self.assertEqual(paid.status_code, 200, paid.json)
        self.assertEqual(paid.json['payment_status'], 'paid')
        self.assertEqual(paid.json['balance_minor'], 0)
        self.assertEqual(self.client.put(f"/finance/invoices/{invoice['id']}", json={**self.payload, 'revision': paid.json['revision']}, headers=self.headers).status_code, 409)

    def test_discount_validation_and_rounding(self):
        rows = [{'total_minor': 10001}]
        self.assertEqual(invoice_totals(rows, {'type': 'percent', 'value': '12.5'})['discount_minor'], 1250)
        self.assertEqual(invoice_totals(rows, {'type': 'amount', 'value': '10.50'})['total_minor'], 8951)
        for discount in ({'type': 'percent', 'value': '100.01'}, {'type': 'amount', 'value': '100.02'}, {'type': 'amount', 'value': '-1'}, {'type': 'amount', 'value': 'NaN'}, {'type': 'amount', 'value': '.001'}, {'type': 'invalid', 'value': '1'}):
            with self.subTest(discount=discount), self.assertRaises(FinanceError):
                invoice_totals(rows, discount)

    def test_proof_required_validated_private_and_durable(self):
        invoice = self.issued()
        for proof in ({}, {'name': 'x', 'data_url': 'data:image/png;base64,' + base64.b64encode(b'<script>bad</script>').decode()}, {'name': 'x', 'data_url': 'data:image/svg+xml;base64,AAAA'}, {'name': 'x', 'data_url': 'x' * (6 * 1024 * 1024 + 1)}):
            response = self.post(f"invoices/{invoice['id']}/payments", {'proof': proof})
            self.assertEqual(response.status_code, 400, response.json)
        paid = self.pay(invoice, '1000').json
        self.assertEqual(len(paid['payments']), 1)
        proof = paid['payments'][0]['proof']
        self.assertTrue((Path(self.directory.name) / 'payment-proofs' / (proof['sha256'] + '.png')).is_file())
        endpoint = f"/finance/invoices/{invoice['id']}/payments/{paid['payments'][0]['id']}/proof"
        response = self.client.get(endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/png')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertTrue(response.data.startswith(b'\x89PNG'))
        response.close()
        self.assertEqual(self.pay(invoice, '1000').status_code, 200)
        self.assertEqual(self.pay(invoice, '1000', proof=screenshot('blue')).status_code, 409)
        self.client.delete_cookie('session_token')
        self.assertEqual(self.client.get(endpoint).status_code, 401)

    def test_failed_proof_storage_does_not_record_payment(self):
        invoice = self.issued()
        with patch('routes.finance.save_proof', side_effect=OSError('simulated disk full')):
            with self.assertRaises(OSError):
                self.pay(invoice, '1000')
        current = self.client.get(f"/finance/invoices/{invoice['id']}").json
        self.assertEqual(current['payments'], [])
        self.assertEqual(current['revision'], invoice['revision'])

    def test_receipts_preserve_historical_balance_and_combined_total(self):
        invoice = self.issued()
        endpoint = f"/finance/invoices/{invoice['id']}/receipts"
        self.assertEqual(self.client.get(endpoint).status_code, 409)
        first = self.pay(invoice, '40000').json
        first_id = first['payments'][0]['id']
        original = self.client.get(endpoint + '?payment_id=' + first_id).json
        second = self.pay(first, '100000', 'payment-two').json
        self.assertEqual(second['payment_status'], 'paid')
        historical = self.client.get(endpoint + '?payment_id=' + first_id).json
        self.assertEqual(historical, original)
        self.assertEqual(historical['balance_minor'], 10000000)
        self.assertEqual(historical['received_minor'], 4000000)
        combined = self.client.get(endpoint).json
        self.assertEqual(combined['received_minor'], 14000000)
        self.assertEqual(combined['balance_minor'], 0)
        self.assertEqual(len(combined['payments']), 2)
        self.assertNotIn('proof', combined['payments'][0])
        self.assertNotIn('recorded_by', combined['payments'][0])
        self.assertEqual(self.client.get(endpoint + '?payment_id=unknown').status_code, 404)

    def test_customer_summary_counts_devices_once_and_excludes_drafts_voids(self):
        endpoint = '/finance/customers/42/summary'
        original = self.client.get(endpoint).json
        self.assertEqual(original['vehicle_count'], 2)
        self.assertEqual(original['unpaid_invoice_count'], 0)
        self.assertEqual(original['finance_status'], 'no_invoices')
        invoice = self.issued()
        self.assertEqual(self.client.get(endpoint).json['finance_status'], 'unpaid')
        self.assertEqual(self.client.get(endpoint).json['unpaid_invoice_count'], 1)
        paid = self.pay(invoice, '1000').json
        self.assertEqual(self.client.get(endpoint).json['finance_status'], 'partial')
        self.assertEqual(self.client.get(endpoint).json['unpaid_invoice_count'], 1)
        self.pay(paid, '139000', 'payment-two')
        self.assertEqual(self.client.get(endpoint).json['finance_status'], 'paid')
        self.payload['request_key'] = 'other-draft'
        draft = self.create()
        self.post(f"invoices/{draft['id']}/void", {'revision': draft['revision'], 'reason': 'Cancelled'})
        self.assertEqual(self.client.get(endpoint).json['balance_minor'], 0)
        self.assertEqual(self.client.get(endpoint).json['unpaid_invoice_count'], 0)
        for index in range(2):
            self.payload['request_key'] = f'unpaid-{index}'
            self.issued()
        self.assertEqual(self.client.get(endpoint).json['unpaid_invoice_count'], 2)

