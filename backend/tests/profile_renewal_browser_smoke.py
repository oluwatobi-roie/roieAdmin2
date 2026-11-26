"""Paid renewal UI against temporary SQLite/JSON and a mocked account API.
Run after building frontend with NEXT_BUILD_DIR=.next-finance-qa.
"""
import logging
import re
from urllib.parse import parse_qs, urlparse
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
from config import db
from sqlalchemy import text


def main():
    fixture = ProfileRenewalTests()
    fixture.setUp()
    from routes.auth import auth_bp, check_session
    fixture.app.register_blueprint(auth_bp, url_prefix="/backend/auth")
    fixture.session_response.json.return_value = {"id": 1123, "name": "Renewal Staff", "administrator": False}
    with fixture.app.app_context():
        db.session.execute(text("INSERT INTO tc_devices (id, name, uniqueid) VALUES (13, 'Offline vehicle', '11111'), (14, 'Failed vehicle', '22222')"))
        db.session.execute(text("INSERT INTO tc_user_device VALUES (42, 13), (42, 14)"))
        db.session.commit()
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
            context.route('**/api/auth/check-session', lambda route: route.fulfill(json={'authenticated': True, 'staff': True}))
            devices = [{
                'device_id': '10', 'device_name': 'LAGOS-DELIVERY-FLEET-' + 'X' * 65,
                'imei': '123456789012345', 'model': 'GPS_D_V4', 'phone': '+2348012345678',
                'position_address': 'Loading bay 12, a long industrial estate address, Ikeja, Lagos. Landmark-' + 'A' * 70,
                'online_status': {'status': 'Likely Online, but not updating frequently', 'recommendation': 'Check device communication and monitor the next position update.'},
                'user_profiles': [{'id': '42', 'name': 'Ada Customer With A Long Business Name',
                    'email': 'customer.' + 'x' * 65 + '@example.com', 'status': 'Expired', 'expiry': '2020-02-29T12:34:56Z'}],
            }, {'device_id': '11', 'device_name': 'Camry', 'imei': '67890', 'model': '', 'phone': '',
                'online_status': {'status': 'NOC Passed Online'}, 'user_profiles': []},
                {'device_id': '13', 'device_name': 'Offline vehicle', 'imei': '11111', 'model': 'GPS_D_V4', 'online_status': {'status': 'Device is Offline'}},
                {'device_id': '14', 'device_name': 'Failed vehicle', 'imei': '22222', 'model': 'GPS_D_V4', 'online_status': {'status': 'NOC Failed Online'}}]

            def search_response(route):
                term = parse_qs(urlparse(route.request.url).query).get('term', [''])[0]
                if term == 'device-only':
                    route.fulfill(json=devices)
                else:
                    route.fulfill(json={'user': {
                        'id': '42', 'name': 'Ada', 'email': 'ada@example.com', 'phone': '1234',
                        'expiry': fixture.account['expirationTime'], 'status': 'Expired'},
                        'devices': [] if term == 'empty-fleet' else devices})
            context.route('**/api/search?*', search_response)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda message: errors.append(message.text) if 'same key' in message.text else None)
            page.goto('http://127.0.0.1:3108/search')
            page.get_by_role('button', name='Open search', exact=True).click()
            expect(page.locator('#workspace-search')).to_be_visible()
            assert page.locator('#workspace-search').bounding_box()['width'] <= 448, 'Desktop search should remain compact'
            page.get_by_placeholder('e.g. GGE 173 XN or user@email.com').fill('Ada')
            page.get_by_role('button', name='Search', exact=True).click()
            expect(page.get_by_placeholder('e.g. GGE 173 XN or user@email.com')).to_have_count(0)
            expect(page.get_by_role('heading', name='Customer workspace', exact=True)).to_be_visible()
            actions = page.get_by_role('group', name='Profile actions')
            expect(actions.get_by_role('button')).to_have_count(3)
            expect(page.get_by_text('4 Assets', exact=True)).to_be_visible()
            counts = page.get_by_label('Fleet status')
            for label in ['NOC passed', 'NOC failed', 'Offline', 'Infrequent updates']:
                metric = counts.locator('div').filter(has=page.get_by_text(label, exact=True))
                expect(metric.locator('dd')).to_have_text('1')
            for label in ['Extend Profile Expiry', 'Finance History', 'View Devices']:
                expect(actions.get_by_role('button', name=label)).to_have_attribute('aria-expanded', 'false')
            page.screenshot(path=str(output / 'profile-desktop.png'), full_page=True)
            actions.get_by_role('button', name='Finance History').click()
            finance = page.get_by_role('region', name='Finance records')
            expect(finance.get_by_role('link', name='Generate invoice')).to_be_visible()
            expect(finance.get_by_role('link', name=re.compile(paid['number']))).to_be_visible()
            actions.get_by_role('button', name='View Devices').click()
            expect(finance).not_to_be_visible()
            device_panel = page.get_by_role('region', name='Devices', exact=True)
            expect(device_panel.get_by_role('article')).to_have_count(4)
            expect(device_panel.get_by_text('NOC Passed Online', exact=True)).to_have_class(re.compile('text-green-800'))
            expect(device_panel.get_by_text('NOC Failed Online', exact=True)).to_have_class(re.compile('text-red-800'))
            expect(device_panel.get_by_text('Device is Offline', exact=True)).to_have_class(re.compile('bg-slate-700'))
            device_panel.locator('summary').first.click()
            expect(device_panel.get_by_text('customer.' + 'x' * 65 + '@example.com')).to_be_visible()
            for width in [320, 390, 768, 1440]:
                page.set_viewport_size({'width': width, 'height': 1000})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Profile overflow at {width}'
                boxes = [button.bounding_box() for button in actions.get_by_role('button').all()]
                assert max(box['y'] for box in boxes) - min(box['y'] for box in boxes) < 2, 'Profile buttons must stay in one horizontal row'
                for card in device_panel.get_by_role('article').all():
                    assert card.evaluate('(element) => element.scrollWidth <= element.clientWidth + 1'), f'Device overflow at {width}'
                if width in [390, 1440]:
                    page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
                    page.screenshot(path=str(output / f'devices-{width}.png'), full_page=True, animations='disabled')
            page.set_viewport_size({'width': 390, 'height': 844})
            device_panel.get_by_role('button', name='Assign to a User').first.click()
            dialog = page.get_by_role('dialog', name='Assign device')
            expect(dialog.get_by_label('User email')).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Assign dialog overflow'
            dialog.get_by_role('button', name='Cancel').click()
            actions.get_by_role('button', name='View Devices').click()
            expect(device_panel).not_to_be_visible()
            actions.get_by_role('button', name='Finance History').click()
            page.wait_for_function("document.querySelector('[aria-label=\"Profile actions\"]').getBoundingClientRect().top < 200")
            assert page.get_by_role('region', name='Finance records').bounding_box()['y'] < 500, 'Opened panel should be in the mobile viewport'
            actions.get_by_role('button', name='Finance History').click()
            page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
            page.screenshot(path=str(output / 'profile-mobile.png'), full_page=True, animations='disabled')
            page.set_viewport_size({'width': 1440, 'height': 1000})
            page.get_by_role('button', name='Extend Profile Expiry').click()
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
            expect(confirm).to_be_disabled()
            panel.get_by_role('checkbox', name='Camry').check()
            expect(confirm).to_be_enabled()
            actions.get_by_role('button', name='Finance History').click()
            expect(panel).not_to_be_visible()
            actions.get_by_role('button', name='Extend Profile Expiry').click()
            expect(select).to_have_value(paid['id'])
            expect(panel.get_by_role('checkbox', name='Corolla')).to_be_checked()
            page.screenshot(path=str(output / 'renewal-desktop.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            actions.get_by_role('button', name='Finance History').click()
            actions.get_by_role('button', name='Extend Profile Expiry').click()
            expect(confirm).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
            page.wait_for_function("document.querySelector('[aria-label=\"Profile actions\"]').getBoundingClientRect().top < 200")
            page.screenshot(path=str(output / 'renewal-mobile-viewport.png'), animations='disabled')
            page.screenshot(path=str(output / 'renewal-mobile.png'), full_page=True, animations='disabled')
            confirm.click()
            expect(panel.get_by_text('Profile extended to', exact=False)).to_be_visible()
            expect(panel.get_by_text('Renewal vehicles (2): Corolla (12345), Camry (67890)', exact=True)).to_be_visible()
            expect(panel.get_by_role('link', name=paid['number'], exact=True)).to_be_visible()
            expect(panel.get_by_text('No unused, fully paid Renewal invoice', exact=False)).to_be_visible()
            assert fixture.account['expirationTime'] == '2021-02-28T12:34:56.000Z'
            fixture.put.assert_called_once()
            assert fixture.put.call_args.kwargs['headers']['Authorization'] == 'Bearer test-renewal-service-token'
            assert 'cookies' not in fixture.put.call_args.kwargs
            panel.get_by_role('link', name=paid['number'], exact=True).click()
            expect(page.get_by_text('Profile expiry extension', exact=True)).to_be_visible()
            expect(page.get_by_text('Renewal vehicles (2): Corolla (12345), Camry (67890)', exact=True)).to_be_visible()
            expect(page.get_by_text('Applied', exact=True)).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Invoice mobile overflow'
            invoice_actions = page.get_by_role('navigation', name='Invoice actions')
            for width in [320, 390]:
                page.set_viewport_size({'width': width, 'height': 844})
                buttons = invoice_actions.locator('a, button')
                expect(buttons).to_have_count(4)
                boxes = [button.bounding_box() for button in buttons.all()]
                assert max(box['y'] for box in boxes) - min(box['y'] for box in boxes) < 2, 'Invoice actions must fit one row'
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Invoice actions overflow'
            page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
            page.screenshot(path=str(output / 'invoice-actions-mobile.png'), animations='disabled')
            page.screenshot(path=str(output / 'renewal-invoice-audit.png'), full_page=True)
            page.emulate_media(media='print')
            expect(page.get_by_text('Profile expiry extension', exact=True)).not_to_be_visible()
            page.emulate_media(media='screen')
            profile_link = page.get_by_role('link', name='View client profile', exact=True)
            expect(profile_link).to_have_attribute('href', '/search?user_id=42')
            with page.expect_request('**/api/search?user_id=42'):
                profile_link.click()
            expect(page.get_by_role('heading', name='Ada', exact=True)).to_be_visible()
            expect(page.get_by_role('button', name='Extend Profile Expiry')).to_be_visible()
            assert '/search?user_id=42' in page.url
            # A dropped request leaves an actionable pending record. Retry must
            # use its original target, then disappear once reconciled.
            another = fixture.issued(key='retry')
            import requests
            fixture.put.side_effect = requests.Timeout()
            page.goto('http://127.0.0.1:3108/search')
            page.get_by_role('button', name='Open search', exact=True).click()
            page.get_by_placeholder('e.g. GGE 173 XN or user@email.com').fill('Ada')
            page.get_by_role('button', name='Search', exact=True).click()
            page.get_by_role('button', name='Extend Profile Expiry').click()
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
            page.get_by_role('button', name='Open search', exact=True).click()
            page.get_by_placeholder('e.g. GGE 173 XN or user@email.com').fill('device-only')
            page.get_by_role('button', name='Search', exact=True).click()
            expect(page.get_by_role('group', name='Profile actions')).to_have_count(0)
            expect(page.get_by_role('region', name='Devices', exact=True)).to_be_visible()
            page.get_by_role('button', name='Open search', exact=True).click()
            page.get_by_placeholder('e.g. GGE 173 XN or user@email.com').fill('empty-fleet')
            page.get_by_role('button', name='Search', exact=True).click()
            expect(page.get_by_role('button', name='View Devices')).to_have_attribute('aria-expanded', 'false')
            page.get_by_role('button', name='View Devices').click()
            expect(page.get_by_text('No devices found for this account.')).to_be_visible()
            page.emulate_media(reduced_motion='reduce')
            page.get_by_role('button', name='Finance History').click()
            assert page.locator('#profile-panel-finance').evaluate('(element) => getComputedStyle(element).animationName') == 'none'
            page.emulate_media(reduced_motion='no-preference')
            # The same card/button system must remain usable on every screen.
            for route_path in ['/', '/add-device', '/onboard_user', '/finance', '/login']:
                page.goto('http://127.0.0.1:3108' + route_path)
                expect(page.locator('h1').first).to_be_visible()
                for width in [320, 390, 1024, 1440]:
                    page.set_viewport_size({'width': width, 'height': 900})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'{route_path} overflow at {width}'
                if route_path == '/onboard_user':
                    expect(page.get_by_role('link', name='Back to finance', exact=True)).to_have_count(0)
                if route_path != '/login':
                    nav = page.get_by_role('navigation', name='Main navigation')
                    expect(nav).to_be_visible()
                    box = nav.bounding_box()
                    assert box['x'] >= 1440 - 113 and box['width'] <= 113, 'Desktop navigation must be on the right'
            page.goto('http://127.0.0.1:3108/finance?new=1')
            page.get_by_role('link', name='Onboard a customer first', exact=True).click()
            expect(page.get_by_role('link', name='Back to finance', exact=True)).to_be_visible()
            page.set_viewport_size({'width': 390, 'height': 844})
            page.screenshot(path=str(output / 'onboard-mobile.png'), full_page=True, animations='disabled')
            page.goto('http://127.0.0.1:3108/add-device')
            page.get_by_role('radio', name='Bulk', exact=True).click()
            expect(page.get_by_role('radio', name='Bulk', exact=True)).to_have_attribute('data-state', 'on')
            page.screenshot(path=str(output / 'add-device-mobile.png'), full_page=True, animations='disabled')
            page.get_by_role('navigation', name='Main navigation').get_by_role('link', name='Onboard Users', exact=True).click()
            expect(page.get_by_role('heading', name='Onboard New User')).to_be_visible()
            expect(page.get_by_role('link', name='Back to finance', exact=True)).to_have_count(0)
            page.goto('http://127.0.0.1:3108/')
            expect(page.get_by_role('heading', name='Your workspace')).to_be_visible()
            for width, height in [(320, 568), (390, 844), (768, 1024), (844, 390)]:
                page.set_viewport_size({'width': width, 'height': height})
                assert page.evaluate('document.documentElement.scrollHeight <= innerHeight + 1'), f'Home must fit one screen at {width}x{height}'
                nav = page.get_by_role('navigation', name='Main navigation')
                box = nav.bounding_box()
                assert abs(box['y'] + box['height'] - height) < 2, 'Mobile navigation must stay at the bottom'
                last_card = page.get_by_role('region', name='Quick actions').get_by_role('link').last.bounding_box()
                assert last_card['y'] + last_card['height'] <= box['y'], 'Bottom navigation overlaps home cards'
                if width == 390:
                    page.screenshot(path=str(output / 'home-mobile.png'), animations='disabled')
            page.set_viewport_size({'width': 1440, 'height': 1000})
            page.screenshot(path=str(output / 'home-desktop.png'), animations='disabled')
            assert not errors, errors
            browser.close()
            print('Browser checks passed: paid-only selection, required vehicles, old-expiry warning, responsive profile actions, long device details at 320/390/768/1440px, preserved renewal selections, profile/invoice audit, safe pending retry; no browser errors.')
    finally:
        process.terminate()
        process.wait(timeout=15)
        log.close()
        server.shutdown()
        fixture.tearDown()
        fixture.doCleanups()


if __name__ == '__main__':
    main()
