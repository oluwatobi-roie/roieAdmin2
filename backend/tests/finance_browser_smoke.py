"""Optional end-to-end test: installed Playwright + Chrome, built Next app required.

Runs only temporary finance data and mocked Traccar on loopback ports 5057/3107.
Run from backend: python tests/finance_browser_smoke.py
"""
import os
import subprocess
import sys
import threading
from pathlib import Path
from urllib.request import urlopen
from time import monotonic, sleep

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from test_finance_api import FinanceApiTests
from config import db
from sqlalchemy import text
import pymupdf as fitz


def main():
    fixture = FinanceApiTests()
    fixture.setUp()
    with fixture.app.app_context():
        for number in range(1, 67):
            db.session.execute(text("INSERT INTO tc_devices VALUES (:id, :name, :imei, NULL)"),
                               {"id": 100 + number, "name": f"FLEET-{number:03}", "imei": f"900000{number:06}"})
            db.session.execute(text("INSERT INTO tc_user_device VALUES (42, :id)"), {"id": 100 + number})
        db.session.commit()
    fixture.app.register_blueprint(__import__("routes.finance", fromlist=["finance_bp"]).finance_bp,
                                  url_prefix="/backend/finance", name="finance_browser")
    server = make_server("127.0.0.1", 5057, fixture.app, threaded=True)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    project = Path(__file__).resolve().parents[2]
    output = project / "MyComputer" / "finance-qa"
    output.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "BACKEND_URL": "http://127.0.0.1:5057", "NEXT_TELEMETRY_DISABLED": "1", "NEXT_BUILD_DIR": ".next-finance-qa"}
    log = (output / "next.log").open("w", encoding="utf-8")
    process = subprocess.Popen(["node", "node_modules/next/dist/bin/next", "start", "-p", "3107", "--hostname", "127.0.0.1"],
        cwd=project / "frontend", env=environment, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        deadline = monotonic() + 45
        while monotonic() < deadline:
            try:
                with urlopen("http://127.0.0.1:3107/finance", timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:
                sleep(0.3)
        else:
            raise RuntimeError("Next test server did not start")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            context.add_init_script("Object.defineProperty(globalThis.crypto, 'randomUUID', { value: undefined, configurable: true })")
            context.add_cookies([{"name": "session_token", "value": "test-session", "url": "http://127.0.0.1:3107"}])
            context.route("**/api/auth/check-session", lambda route: route.fulfill(json={"authenticated": True}))
            page = context.new_page()
            page_errors = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto("http://127.0.0.1:3107/finance")
            expect(page.get_by_text("No invoices found. Generate an invoice to get started.")).to_be_visible()
            page.get_by_role("button", name="Generate invoice", exact=True).click()
            page.get_by_label("Find a customer by name, email or phone").fill("ada")
            page.get_by_role("button", name="Find customer", exact=True).click()
            page.get_by_role("button", name="Ada · ada@example.com").click()
            expect(page.get_by_label("Customer name *")).to_have_value("Ada")
            page.get_by_label("Phone number *").fill("+2348012345678")
            page.get_by_label("Street address *").fill("10 Main Road")
            page.get_by_label("City *", exact=True).fill("Ikeja")
            page.get_by_label("State / region *").fill("Lagos")
            page.get_by_label("Invoice category").select_option("installation")
            expect(page.get_by_label("Negotiated price per vehicle (NGN)")).to_have_value("140000.00")
            page.get_by_label("Negotiated price per vehicle (NGN)").fill("100000")
            page.get_by_label("Vehicles / activities without devices (comma-separated)").fill("New Toyota Corolla")
            expect(page.get_by_text("₦13,370.79", exact=True).first).to_be_visible()
            page.get_by_label("Customer notes / payment instructions").fill("Installation by appointment.")
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=str(output / "desktop-form.png"), full_page=True, animations="disabled")
            page.get_by_role("button", name="Review invoice", exact=True).click()
            expect(page.get_by_role("heading", name="DRAFT INVOICE")).to_be_visible()
            page.get_by_role("button", name="Confirm details & save draft").click()
            expect(page.get_by_role("button", name="Finalize invoice", exact=True)).to_be_visible()
            page.get_by_role("button", name="Finalize invoice", exact=True).click()
            expect(page.get_by_role("heading", name="ROIE-", exact=False)).to_be_visible()
            page.get_by_label("Amount received (NGN)").fill("50000")
            page.get_by_label("Transaction / receipt reference").fill("QA-TRANSFER-1")
            page.get_by_role("button", name="Record payment", exact=True).click()
            expect(page.get_by_text("Payment recorded.", exact=True)).to_be_visible()
            page.get_by_label("New installation · New Toyota Corolla").select_option("10")
            page.get_by_role("button", name="Link device", exact=True).click()
            expect(page.locator(".invoice-vehicle-name").filter(has_text="Corolla")).to_be_visible()
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=str(output / "desktop-invoice.png"), full_page=True, animations="disabled")
            page.emulate_media(media="print")
            expect(page.get_by_role("button", name="Generate invoice", exact=True)).not_to_be_visible()
            expect(page.locator("header").first).not_to_be_visible()
            page.screenshot(path=str(output / "print-invoice.png"), full_page=True, animations="disabled")
            page.emulate_media(media="screen")
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(output / "mobile-invoice.png"), full_page=True, animations="disabled")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile invoice overflows"
            page.get_by_role("button", name="All invoices", exact=True).click()
            expect(page.get_by_role("cell", name="partial", exact=True)).to_be_visible()
            page.get_by_role("button", name="Open", exact=True).click()
            expect(page.get_by_text("QA-TRANSFER-1", exact=False)).to_be_visible()
            # Large fleet: one renewal task, two fee rows, and exactly 68 names.
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.get_by_role("button", name="Generate invoice", exact=True).click()
            page.get_by_label("Find a customer by name, email or phone").fill("ada")
            page.get_by_role("button", name="Find customer", exact=True).click()
            page.get_by_role("button", name="Ada · ada@example.com").click()
            page.get_by_role("button", name="Select all matching (68)", exact=True).click()
            expect(page.get_by_label("Quantity (from vehicle list)")).to_have_value("68")
            page.get_by_role("button", name="Review invoice", exact=True).click()
            expect(page.locator(".invoice-paper .invoice-breakdown tbody tr")).to_have_count(2)
            expect(page.locator(".invoice-paper .invoice-vehicle-name")).to_have_count(68)
            expect(page.locator(".invoice-task-subtotal")).to_contain_text("1,020,000.00")
            page.get_by_role("button", name="Confirm details & save draft").click()
            page.get_by_role("button", name="Edit draft", exact=True).click()
            expect(page.get_by_label("Quantity (from vehicle list)")).to_have_value("68")
            expect(page.get_by_label("Invoice category")).to_have_count(1)
            page.get_by_role("button", name="Review invoice", exact=True).click()
            page.get_by_role("button", name="Confirm details & save draft").click()
            page.get_by_role("button", name="Finalize invoice", exact=True).click()
            expect(page.get_by_role("button", name="Finalize invoice", exact=True)).not_to_be_visible()
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=str(output / "68-vehicle-renewal.png"), full_page=True, animations="disabled")
            page.emulate_media(media="print")
            pdf_path = output / "68-vehicle-renewal.pdf"
            page.pdf(path=str(pdf_path), format="A4", print_background=True, prefer_css_page_size=True)
            with fitz.open(pdf_path) as document:
                assert len(document) <= 2, f"68-vehicle invoice unexpectedly spans {len(document)} pages"
                printed = "\n".join(pdf_page.get_text() for pdf_page in document)
                for number in range(1, 67):
                    assert f"FLEET-{number:03}" in printed
                assert "1,020,000.00" in printed
                for index, pdf_page in enumerate(document):
                    pdf_page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(str(output / f"68-vehicle-renewal-page-{index + 1}.png"))
                print(f"PASS: 68-vehicle renewal PDF uses {len(document)} page(s)")
            page.emulate_media(media="screen")
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(output / "68-vehicle-mobile.png"), full_page=True, animations="disabled")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Grouped mobile invoice overflows"
            # A second task must keep its own quantity, pricing and vehicle list.
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.get_by_role("button", name="Generate invoice", exact=True).click()
            page.get_by_label("Find a customer by name, email or phone").fill("ada")
            page.get_by_role("button", name="Find customer", exact=True).click()
            page.get_by_role("button", name="Ada · ada@example.com").click()
            page.get_by_role("button", name="Select all matching (68)", exact=True).click()
            page.get_by_role("button", name="Add task", exact=True).click()
            page.get_by_label("Invoice category").nth(1).select_option("installation")
            page.get_by_label("Vehicles / activities without devices (comma-separated)").nth(1).fill("New Corolla, New Hilux")
            expect(page.get_by_label("Quantity (from vehicle list)").nth(1)).to_have_value("2")
            page.get_by_role("button", name="Review invoice", exact=True).click()
            expect(page.locator(".invoice-paper .invoice-task")).to_have_count(2)
            expect(page.locator(".invoice-paper .invoice-breakdown tbody tr")).to_have_count(6)
            expect(page.locator(".invoice-paper .invoice-vehicle-name")).to_have_count(70)
            page.get_by_role("button", name="Confirm details & save draft").click()
            page.get_by_role("button", name="Finalize invoice", exact=True).click()
            expect(page.get_by_role("button", name="Finalize invoice", exact=True)).not_to_be_visible()
            page.emulate_media(media="print")
            mixed_path = output / "mixed-tasks-invoice.pdf"
            page.pdf(path=str(mixed_path), format="A4", print_background=True, prefer_css_page_size=True)
            with fitz.open(mixed_path) as document:
                assert len(document) == 1, f"Mixed invoice unexpectedly spans {len(document)} pages"
                for stale in output.glob("mixed-tasks-page-*.png"):
                    stale.unlink()
                printed = "\n".join(pdf_page.get_text() for pdf_page in document)
                assert "1,300,000.00" in printed
                assert "Installations subtotal" in printed and "Renewal subtotal" in printed
                for index, pdf_page in enumerate(document):
                    pdf_page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(str(output / f"mixed-tasks-page-{index + 1}.png"))
                print(f"PASS: mixed installation/renewal PDF uses {len(document)} page(s)")
            assert not page_errors, page_errors
            print("PASS: browser customer lookup, pricing, preview, save, issue, payment, device link, reload, mobile, grouped fleet printing and UUID fallback")
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=15)
        log.close()
        server.shutdown()
        server.server_close()
        fixture.tearDown()
        fixture.doCleanups()


if __name__ == "__main__":
    main()
