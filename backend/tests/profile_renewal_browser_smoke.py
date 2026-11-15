"""Paid renewal UI against temporary SQLite/JSON and a mocked account API.
Run after building frontend with NEXT_BUILD_DIR=.next-finance-qa.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from test_profile_renewal import ProfileRenewalTests
from routes.finance import finance_bp


def main():
    fixture = ProfileRenewalTests()
    fixture.setUp()
    fixture.app.register_blueprint(finance_bp, url_prefix='/backend/finance', name='renewal_browser')
    paid = fixture.issued()
    unpaid = fixture.issued(pay=None, key='unpaid')
    partial = fixture.issued(pay='15000', key='partial')
    maintenance = fixture.issued(category='maintenance', key='maintenance')
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    server = make_server('127.0.0.1', 5058, fixture.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    project = Path(__file__).resolve().parents[2]
    output = project / 'output' / 'renewal-qa'
    output.mkdir(parents=True, exist_ok=True)
    log = tempfile.TemporaryFile(mode='w+', encoding='utf-8')
    process = subprocess.Popen(['node', 'node_modules/next/dist/bin/next', 'start', '-p', '3108', '--hostname', '127.0.0.1'],
        cwd=project / 'frontend', env={**os.environ, 'BACKEND_URL': 'http://127.0.0.1:5058',
        'NEXT_BUILD_DIR': os.environ.get('NEXT_BUILD_DIR', '.next-finance-qa'), 'NEXT_TELEMETRY_DISABLED': '1'}, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        deadline = monotonic() + 45
        while monotonic() < deadline:
            try:
                with urlopen('http://127.0.0.1:3108/search', timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:
                sleep(.3)
        else:
            log.seek(0)
            raise RuntimeError('Frontend did not start: ' + log.read())
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            context.add_init_script("Object.defineProperty(globalThis.crypto, 'randomUUID', {value: undefined, configurable: true})")
            context.add_cookies([{'name': 'session_token', 'value': 'test-session', 'url': 'http://127.0.0.1:3108'}])
            context.route('**/api/auth/check-session', lambda route: route.fulfill(json={'authenticated': True}))
            context.route('**/api/search?*', lambda route: route.fulfill(json={'user': {
                'id': '42', 'name': 'Ada', 'email': 'ada@example.com', 'phone': '1234',
                'expiry': fixture.account['expirationTime'], 'status': 'Expired'}, 'devices': []}))
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto('http://127.0.0.1:3108/search')
            page.get_by_placeholder('e.g. GGE 173 XN or user@email.com').fill('Ada')
            page.get_by_role('button', name='Search', exact=True).click()
            page.get_by_role('button', name='Extend profile expiry').click()
            panel = page.get_by_role('region', name='Profile renewal')
            select = panel.get_by_label('Paid renewal invoice')
            expect(select.locator('option')).to_have_count(2)
            expect(select).not_to_contain_text(unpaid['number'])
            expect(select).not_to_contain_text(partial['number'])
            expect(select).not_to_contain_text(maintenance['number'])
            select.select_option(paid['id'])
            confirm = panel.get_by_role('button', name='Confirm one-year extension')
            expect(confirm).to_be_disabled()
            expect(panel.get_by_text('The profile will still be expired', exact=False)).to_be_visible()
            panel.get_by_role('checkbox', name='Corolla').check()
            expect(confirm).to_be_enabled()
            page.screenshot(path=str(output / 'renewal-desktop.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            expect(confirm).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
            page.screenshot(path=str(output / 'renewal-mobile.png'), full_page=True)
            confirm.click()
            expect(panel.get_by_text('Profile extended to', exact=False)).to_be_visible()
            expect(panel.get_by_text('Renewal vehicles (1): Corolla (12345)', exact=True)).to_be_visible()
            expect(panel.get_by_role('link', name=paid['number'], exact=True)).to_be_visible()
            expect(panel.get_by_text('No unused, fully paid Renewal invoice', exact=False)).to_be_visible()
            assert fixture.account['expirationTime'] == '2021-02-28T12:34:56.000Z'
            fixture.put.assert_called_once()
            panel.get_by_role('link', name=paid['number'], exact=True).click()
            expect(page.get_by_text('Profile expiry extension', exact=True)).to_be_visible()
            expect(page.get_by_text('Renewal vehicles (1): Corolla (12345)', exact=True)).to_be_visible()
            expect(page.get_by_text('Applied', exact=True)).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Invoice mobile overflow'
            page.screenshot(path=str(output / 'renewal-invoice-audit.png'), full_page=True)
            page.emulate_media(media='print')
            expect(page.get_by_text('Profile expiry extension', exact=True)).not_to_be_visible()
            page.emulate_media(media='screen')
            # A dropped request leaves an actionable pending record. Retry must
            # use its original target, then disappear once reconciled.
            another = fixture.issued(key='retry')
            import requests
            fixture.put.side_effect = requests.Timeout()
            page.goto('http://127.0.0.1:3108/search')
            page.get_by_placeholder('e.g. GGE 173 XN or user@email.com').fill('Ada')
            page.get_by_role('button', name='Search', exact=True).click()
            page.get_by_role('button', name='Extend profile expiry').click()
            panel = page.get_by_role('region', name='Profile renewal')
            panel.get_by_label('Paid renewal invoice').select_option(another['id'])
            panel.get_by_role('button', name='Select all renewal vehicles').click()
            panel.get_by_role('button', name='Confirm one-year extension').click()
            retry = panel.get_by_role('button', name='Verify / retry extension')
            expect(retry).to_be_visible()
            expect(panel.get_by_label('Paid renewal invoice')).to_have_count(0)
            fixture.put.side_effect = fixture.remote_put
            retry.click()
            expect(panel.get_by_text('Profile extended to', exact=False)).to_be_visible()
            expect(retry).to_have_count(0)
            assert fixture.account['expirationTime'] == '2022-02-28T12:34:56.000Z'
            assert fixture.put.call_count == 3
            assert not errors, errors
            browser.close()
            print('Browser checks passed: paid-only selection, required vehicles, old-expiry warning, mobile layout, profile/invoice audit, safe pending retry; no browser errors.')
    finally:
        process.terminate()
        process.wait(timeout=15)
        log.close()
        server.shutdown()
        fixture.tearDown()
        fixture.doCleanups()


if __name__ == '__main__':
    main()
