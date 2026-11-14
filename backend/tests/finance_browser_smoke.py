"""Browser/PDF integration against temporary SQLite/JSON and mocked remote sessions.
Build frontend with NEXT_BUILD_DIR=.next-finance-qa first. Requires Chrome,
Playwright and PyMuPDF. Never uses the production database or writes live accounts.
"""
import base64
import logging
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from time import monotonic, sleep
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from test_finance_api import FinanceApiTests, screenshot
from config import db
from sqlalchemy import text
import pymupdf as fitz


def main():
    fixture = FinanceApiTests()
    fixture.setUp()
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    with fixture.app.app_context():
        for number in range(1, 67):
            db.session.execute(text('INSERT INTO tc_devices VALUES (:id, :name, :imei, NULL)'), {'id': 100 + number, 'name': f'FLEET-{number:03}', 'imei': f'900000{number:06}'})
            db.session.execute(text('INSERT INTO tc_user_device VALUES (42, :id)'), {'id': 100 + number})
        db.session.commit()
    fixture.app.register_blueprint(__import__('routes.finance', fromlist=['finance_bp']).finance_bp, url_prefix='/backend/finance', name='finance_browser')
    server = make_server('127.0.0.1', 5057, fixture.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    project = Path(__file__).resolve().parents[2]
    output = project / 'MyComputer' / 'finance-qa'
    output.mkdir(parents=True, exist_ok=True)
    pdf_output = project / 'output' / 'pdf'
    pdf_output.mkdir(parents=True, exist_ok=True)
    proof = output / 'test-payment.png'
    proof.write_bytes(base64.b64decode(screenshot()['data_url'].split(',')[1]))
    log = (output / 'next.log').open('w', encoding='utf-8')
    process = subprocess.Popen(['node', 'node_modules/next/dist/bin/next', 'start', '-p', '3107', '--hostname', '127.0.0.1'], cwd=project / 'frontend', env={**os.environ, 'BACKEND_URL': 'http://127.0.0.1:5057', 'NEXT_BUILD_DIR': '.next-finance-qa', 'NEXT_TELEMETRY_DISABLED': '1'}, stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        deadline = monotonic() + 45
        while monotonic() < deadline:
            try:
                with urlopen('http://127.0.0.1:3107/finance', timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:
                sleep(.3)
        else:
            raise RuntimeError('Test frontend did not start')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            context.add_init_script("Object.defineProperty(globalThis.crypto, 'randomUUID', {value: undefined, configurable: true})")
            context.add_cookies([{'name': 'session_token', 'value': 'test-session', 'url': 'http://127.0.0.1:3107'}])
            context.route('**/api/auth/check-session', lambda route: route.fulfill(json={'authenticated': True}))
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))

            def click(name):
                page.get_by_role('button', name=name, exact=True).click()

            def print_pdf(name, required, forbidden=()):
                page.emulate_media(media='print')
                path = pdf_output / (name + '.pdf')
                page.pdf(path=str(path), format='A4', print_background=True, prefer_css_page_size=True)
                with fitz.open(path) as document:
                    text_content = '\n'.join(p.get_text() for p in document)
                    for value in required:
                        assert ' '.join(value.split()) in ' '.join(text_content.split()), (name, value, text_content)
                    for value in ['Traccar', 'Payment records are shown separately', 'Record payment', *forbidden]:
                        assert value not in text_content, (name, value)
                    for number, pdf_page in enumerate(document):
                        assert pdf_page.get_text().strip(), 'Blank PDF page'
                        pdf_page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4)).save(str(output / f'{name}-page-{number+1}.png'))
                    print(f'{name}: {len(document)} PDF pages verified', flush=True)
                page.emulate_media(media='screen')

            page.goto('http://127.0.0.1:3107/finance')
            expect(page.get_by_text('No invoices found. Generate an invoice to get started.')).to_be_visible()
            click('Generate invoice')
            expect(page.get_by_role('link', name='Onboard a customer first')).to_have_attribute('href', '/onboard_user?returnTo=finance')
            page.get_by_label('Find a customer by name, email or phone').fill('ada')
            click('Find customer')
            page.get_by_role('button', name=re.compile('Ada.*ada@example.com')).click()
            expect(page.get_by_label('Customer name', exact=True)).to_have_value('Ada')
            expect(page.get_by_label('Customer name', exact=True)).to_have_attribute('readonly', '')
            expect(page.get_by_label('Email', exact=True)).to_have_attribute('readonly', '')
            page.get_by_label('Phone number', exact=True).fill('+2348012345678')
            page.get_by_label('Street address', exact=True).fill('10 Main Road')
            page.get_by_label('City', exact=True).fill('Ikeja')
            page.get_by_label('State / region', exact=True).fill('Lagos')
            click('Next: task')
            expect(page.get_by_role('button', name='Save task & continue')).to_be_disabled()
            page.get_by_label('Task category').select_option('installation')
            expect(page.get_by_label('Negotiated price per vehicle (NGN)')).to_have_value('140000.00')
            page.get_by_label('Negotiated price per vehicle (NGN)').fill('100000')
            page.get_by_label('Number of vehicles awaiting installation').fill('2')
            page.get_by_label('Task notes (optional)').fill('Installation by appointment at customer premises.')
            click('Save task & continue')
            click('Add another task')
            click('Select all matching (68)')
            page.get_by_label('Task notes (optional)').fill('Annual subscription for the selected fleet.')
            click('Save task & continue')
            click('Add another task')
            page.get_by_label('Task category').select_option('maintenance')
            expect(page.get_by_role('button', name='Save task & continue')).to_be_disabled()
            page.get_by_role('checkbox', name='Corolla IMEI 12345', exact=True).check()
            click('Save task & continue')
            click('Add another task')
            page.get_by_label('Task category').select_option('special')
            page.get_by_label('Item', exact=True).fill('Fleet diagnostic report')
            page.get_by_label('Description', exact=True).fill('Inspect wiring and provide a fleet health report.')
            page.get_by_label('Amount (NGN)', exact=True).fill('25000')
            click('Save task & continue')
            click('Next: due date & discount')
            page.get_by_label('Invoice due date').fill('2027-01-31')
            page.get_by_label('Discount type').select_option('percent')
            page.get_by_label('Discount (%)', exact=True).fill('10')
            page.get_by_label('Invoice notes (optional)').fill('Please include your invoice number as the transfer reference.')
            click('Next: review')
            expect(page.locator('.invoice-paper')).to_contain_text('GPS_D_V4')
            expect(page.locator('.invoice-paper')).to_contain_text('1,138,500.00')
            expect(page.locator('.invoice-vehicles').filter(has_text='Vehicles for renewal (68)')).to_contain_text('FLEET-066')
            click('Confirm details & save draft')
            click('Edit draft')
            expect(page.get_by_label('Street address', exact=True)).to_have_value('10 Main Road')
            click('Next: task list')
            expect(page.get_by_role('button', name='Edit task', exact=True)).to_have_count(4)
            page.get_by_role('button', name='Edit task', exact=True).nth(3).click()
            expect(page.get_by_label('Item', exact=True)).to_have_value('Fleet diagnostic report')
            click('Save task & continue')
            click('Next: due date & discount')
            expect(page.get_by_label('Discount (%)', exact=True)).to_have_value('10')
            click('Next: review')
            click('Confirm details & save draft')
            click('Finalize invoice')
            expect(page.locator('.invoice-paper')).to_contain_text('ROIE-')
            expect(page.locator('.stamp-unpaid')).to_be_visible()
            print_pdf('mixed-unpaid', ['GPS_D_V4', 'GPRS_GSM', 'GPS_Server_Maintenance', 'Installation', 'Sales Terms', '0421439134', 'Fleet diagnostic report', '1,138,500.00'])
            page.get_by_label('Amount received (NGN)').fill('50000')
            page.get_by_label('Transaction / receipt reference').fill('QA-BANK-001')
            expect(page.get_by_role('button', name='Record payment', exact=True)).to_be_disabled()
            page.get_by_label('Payment screenshot (required)').set_input_files(str(proof))
            click('Record payment')
            expect(page.locator('.stamp-partial')).to_be_visible()
            print_pdf('mixed-partial', ['PARTIALLY PAID', '50,000.00', '1,088,500.00'])
            evidence_url = page.get_by_role('link', name='View screenshot').get_attribute('href')
            evidence = context.request.get('http://127.0.0.1:3107' + evidence_url)
            assert evidence.status == 200 and evidence.headers['content-type'].startswith('image/png')
            click('Receipt')
            expect(page.locator('.receipt-paper')).to_contain_text('QA-BANK-001')
            print_pdf('payment-receipt', ['Payment receipt', '50,000.00', '1,088,500.00'], ['QA-BANK-002'])
            click('Back to invoice')
            page.get_by_label('Amount received (NGN)').fill('1088500')
            page.get_by_label('Transaction / receipt reference').fill('QA-BANK-002')
            page.get_by_label('Payment screenshot (required)').set_input_files(str(proof))
            click('Record payment')
            expect(page.locator('.stamp-paid')).to_be_visible()
            print_pdf('mixed-paid', ['PAID IN FULL', '1,138,500.00'])
            page.get_by_role('button', name='Receipt', exact=True).first.click()
            expect(page.locator('.receipt-paper')).to_contain_text('1,088,500.00')
            click('Back to invoice')
            click('Combined receipt')
            expect(page.locator('.receipt-paper')).to_contain_text('Combined payment receipt')
            print_pdf('combined-receipt', ['Combined payment receipt', 'QA-BANK-001', 'QA-BANK-002', '1,138,500.00', 'PAID IN FULL'])
            click('Back to invoice')
            page.get_by_label('Installation 1 - vehicle 1', exact=True).select_option('10')
            page.get_by_role('button', name='Link device', exact=True).first.click()
            expect(page.locator('.invoice-vehicles').filter(has_text='Vehicles for installations')).to_contain_text('Corolla')
            page.set_viewport_size({'width': 390, 'height': 844})
            page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
            page.screenshot(path=str(output / 'mobile-invoice.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile invoice overflow'
            click('All invoices')
            expect(page.locator('.invoice-list-row')).to_have_count(1)
            expect(page.locator('.invoice-list-row')).not_to_contain_text('FLEET-066')
            expect(page.locator('.invoice-list-row')).to_contain_text('Special Service')
            page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
            page.screenshot(path=str(output / 'mobile-list.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile list overflow'
            click('Generate invoice')
            page.get_by_label('Find a customer by name, email or phone').fill('ada')
            click('Find customer')
            page.get_by_role('button', name=re.compile('Ada.*ada@example.com')).click()
            expect(page.get_by_label('Street address', exact=True)).to_have_value('10 Main Road')
            click('Next: task')
            page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
            page.screenshot(path=str(output / 'mobile-task.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile task overflow'
            fixture.payload['request_key'] = 'renewal-68'
            fixture.payload['entries'] = [{'category': 'renewal', 'total': '15000', 'device_ids': [10, 11, *range(101, 167)], 'quantity': 68}]
            invoice = fixture.create()
            invoice = fixture.post(f"invoices/{invoice['id']}/finalize", {'revision': invoice['revision']}).json
            page.goto(f"http://127.0.0.1:3107/finance?invoice={invoice['id']}")
            expect(page.locator('.invoice-vehicles')).to_contain_text('Vehicles for renewal (68)')
            print_pdf('renewal-68', ['1,020,000.00', '816,000.00', '204,000.00', 'FLEET-066', '0421439134'], ['Sales Terms', 'GPS_D_V4'])
            with fitz.open(pdf_output / 'renewal-68.pdf') as document:
                assert len(document) == 1, '68-vehicle renewal should fit one A4 page'
            fixture.session_response.json.return_value = {'id': 1, 'name': 'Owner', 'administrator': False}
            page.reload()
            expect(page.locator('.invoice-paper')).to_be_visible()
            expect(page.get_by_text('Cancel invoice', exact=True)).to_have_count(0)
            context.route('**/api/search?*', lambda route: route.fulfill(json={'user': {'id': '42', 'name': 'Ada', 'email': 'ada@example.com', 'phone': '+2348012345678', 'status': 'Active', 'expiry': '2027-01-01'}, 'devices': []}))
            page.goto('http://127.0.0.1:3107/search')
            page.get_by_placeholder('e.g. GGE 173 XN or user@email.com').fill('ada')
            click('Search')
            expect(page.get_by_text('Vehicles on account', exact=True)).to_be_visible()
            expect(page.get_by_text('68', exact=True)).to_be_visible()
            expect(page.get_by_text('Partially paid', exact=True)).to_be_visible()
            page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
            page.screenshot(path=str(output / 'mobile-profile.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile profile overflow'
            context.route('**/api/user/onboarduser', lambda route: route.fulfill(json={'success': True}))
            page.goto('http://127.0.0.1:3107/onboard_user?returnTo=finance')
            page.get_by_placeholder('Full Name').fill('Ada')
            page.get_by_placeholder('Email Address').fill('ada@example.com')
            page.get_by_placeholder('Phone Number').fill('+2348012345678')
            click('Onboard User')
            page.get_by_role('link', name='Create invoice for this customer').click()
            expect(page.get_by_label('Customer name', exact=True)).to_have_value('Ada')
            expect(page.get_by_label('Street address', exact=True)).to_have_value('1 Main Road')
            page.goto('http://127.0.0.1:3107/')
            page.set_viewport_size({'width': 1440, 'height': 1000})
            expect(page.get_by_role('heading', name='Device Manager Dashboard')).to_be_visible()
            page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
            page.screenshot(path=str(output / 'desktop-dashboard.png'), full_page=True)
            assert not errors, errors
            fixture.put.assert_not_called()
            browser.close()
            print('PASS: guided workflow, 68 vehicles, notes, discounts, custom service, draft edit, payment proof, receipts, device linking, saved address, live permission, mobile and PDFs', flush=True)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        log.close()
        server.shutdown()
        fixture.tearDown()
        fixture.doCleanups()


if __name__ == '__main__':
    main()
