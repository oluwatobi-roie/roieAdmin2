"""Real frontend/API with temporary data and mocked SMTP; never sends customer email."""
import copy
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from time import monotonic, sleep
from urllib.request import urlopen
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from test_finance_email import EmailApiTests, SETTINGS
from routes.finance import finance_bp
from services.finance_pdf import document_pdf


def main():
    fixture = EmailApiTests()
    fixture.setUp()
    fixture.enterContext(patch("routes.finance.smtp_settings", return_value=SETTINGS))
    transport = fixture.enterContext(patch("routes.finance.send_document", return_value=("sent", "Email sent.")))
    fixture.app.register_blueprint(finance_bp, url_prefix="/backend/finance", name="email_browser")
    invoice = fixture.issued()
    invoice = fixture.paid(invoice, "40000", "part-one")
    invoice = fixture.paid(invoice, "100000", "part-two")
    project = Path(__file__).resolve().parents[2]
    output = project / "output/pdf/email-qa"
    output.mkdir(parents=True, exist_ok=True)
    samples = [("installation", invoice, "invoice", None),
        ("single-receipt", invoice, "receipt", invoice["payments"][0]["id"]),
        ("combined-receipt", invoice, "receipt", None)]
    renewal = copy.deepcopy(invoice)
    entry = copy.deepcopy(invoice["entries"][0])
    entry.update(category="renewal", total_minor=1500000, activity="Annual renewal", task_notes="Coverage for the full fleet.",
        breakdown=[{"label": "GPRS fee", "amount_minor": 1200000}, {"label": "Server fee", "amount_minor": 300000}])
    renewal["entries"] = [dict(entry, id=str(i), device={"id": i, "name": f"Fleet Vehicle {i:03}", "imei": str(i)}) for i in range(1, 69)]
    renewal.update(payments=[], subtotal_minor=102000000, total_minor=91800000, discount_minor=10200000, discount={"type": "percent", "value": "10"})
    samples.append(("renewal-68-vehicles", renewal, "invoice", None))
    fixture.payload.update(request_key="mixed-sample", discount={"type": "amount", "value": "5000"}, notes="Thank you, Ada & team.\nPlease retain this invoice.")
    fixture.payload["entries"].extend([
        {"category": "renewal", "total": "15000", "activity": "2027 coverage", "device_id": 10, "task_notes": "Annual subscription"},
        {"category": "maintenance", "total": "20000", "activity": "Inspection", "device_id": 11},
        {"category": "special", "total": "5000", "item": "Custom <service>", "description": "Diagnostic report & assistance"}])
    mixed = fixture.issued()
    samples.append(("mixed-services", mixed, "invoice", None))
    for name, data, kind, payment_id in samples:
        pdf, number = document_pdf(data, kind, payment_id)
        (output / (name + ".pdf")).write_bytes(pdf)
        with pymupdf.open(stream=pdf, filetype="pdf") as parsed:
            text = "\n".join(page.get_text() for page in parsed)
            assert "RoieTrackers" in text and number in text
            assert "traccar" not in text.lower() and "Payment records are shown" not in text
            if name == "renewal-68-vehicles":
                assert "Fleet Vehicle 001" in text and "Fleet Vehicle 068" in text
                assert "Vehicles for renewal (68)" in text
                assert "NGN 918,000.00" in text and "Discount (10%)" in text
                assert "Sales Terms" not in text
            elif name == "installation":
                assert "Sales Terms" in text and "0421439134" in text and "PAID IN FULL" in text
                assert text.index("GPS_D_V4") < text.index("GPRS_GSM") < text.index("GPS_Server_Maintenance")
            elif name == "single-receipt":
                assert "NGN 40,000.00" in text and "NGN 100,000.00" in text and "PARTIALLY PAID" in text
            elif name == "combined-receipt":
                assert "NGN 140,000.00" in text and "PAID IN FULL" in text
            elif name == "mixed-services":
                for value in ("NGN 175,000.00", "Custom <service>", "Diagnostic report & assistance", "Annual subscription", "Thank you, Ada & team.", "Sales Terms", "Maintenance", "Renewal"):
                    assert value in text, value
            for index, page in enumerate(parsed):
                page.get_pixmap(matrix=pymupdf.Matrix(1.25, 1.25)).save(output / f"{name}-{index+1}.png")
                for block in page.get_text("dict")["blocks"]:
                    if "lines" in block:
                        assert block["bbox"][0] >= 25 and block["bbox"][2] <= page.rect.width-25, (name, block["bbox"])
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    server = make_server("127.0.0.1", 5059, fixture.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    process = subprocess.Popen(["node", "node_modules/next/dist/bin/next", "start", "-p", "3109", "--hostname", "127.0.0.1"],
        cwd=project / "frontend", env={**os.environ, "BACKEND_URL": "http://127.0.0.1:5059",
            "NEXT_BUILD_DIR": os.environ.get("NEXT_BUILD_DIR", ".next-renewal-check"), "NEXT_TELEMETRY_DISABLED": "1"},
        stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        deadline = monotonic() + 45
        while monotonic() < deadline:
            try:
                with urlopen("http://127.0.0.1:3109/finance", timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:
                sleep(.3)
        else:
            log.seek(0)
            raise RuntimeError(log.read())
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(viewport={"width": 390, "height": 844})
            context.add_cookies([{"name": "session_token", "value": "test-session", "url": "http://127.0.0.1:3109"}])
            context.route("**/api/auth/check-session", lambda route: route.fulfill(json={"authenticated": True}))
            context.add_init_script("""
                window.sharedDocuments = [];
                Object.defineProperty(navigator, 'canShare', { configurable: true, value: data => !!data.files?.length });
                Object.defineProperty(navigator, 'share', { configurable: true, value: async data => {
                    window.sharedDocuments.push({ text: data.text, name: data.files[0].name,
                        type: data.files[0].type, bytes: Array.from(new Uint8Array(await data.files[0].arrayBuffer())) });
                }});
            """)
            context.route('https://wa.me/**', lambda route: route.fulfill(body='WhatsApp handoff intercepted by test.'))
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto("http://127.0.0.1:3109/finance?invoice=" + invoice["id"])
            send = page.get_by_role("region", name="Email customer document")
            send.get_by_role("button", name="Send to customer", exact=True).click()
            expect(send.get_by_text("ada@example.com", exact=True)).to_be_visible()
            for width in [320, 390, 768, 1440]:
                page.set_viewport_size({"width": width, "height": 900})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
                buttons = page.get_by_role("navigation", name="Invoice actions").get_by_role("button").all()
                boxes = [button.bounding_box() for button in buttons]
                assert max(box["y"] for box in boxes) - min(box["y"] for box in boxes) < 2
                if width in (390, 1440):
                    page.screenshot(path=str(output / f"send-invoice-{width}.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            send.get_by_role("button", name="Confirm send", exact=True).click()
            expect(send.get_by_role("status")).to_contain_text("Email sent.")
            assert transport.call_count == 1
            with page.expect_download() as download_info:
                page.get_by_role("button", name="Download PDF", exact=True).click()
            downloaded = download_info.value
            assert downloaded.suggested_filename == invoice["number"] + ".pdf"
            assert Path(downloaded.path()).read_bytes() == transport.call_args.args[2]
            whatsapp = page.get_by_role("region", name="WhatsApp customer document")
            whatsapp.get_by_role("button", name="Send to WhatsApp", exact=True).click()
            expect(whatsapp.get_by_text("+2348012345678", exact=True)).to_be_visible()
            message = whatsapp.get_by_role("textbox", name="WhatsApp message").input_value()
            assert "NGN 140,000.00" in message and "0421439134" in message and "GTBank" in message
            assert whatsapp.get_by_role("link", name="Open WhatsApp").get_attribute("href").startswith("https://wa.me/2348012345678?text=")
            for width in [320, 390, 1440]:
                page.set_viewport_size({"width": width, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
            page.set_viewport_size({"width": 390, "height": 844})
            whatsapp.screenshot(path=str(output / "whatsapp-mobile.png"))
            whatsapp.get_by_role("button", name="Share PDF with app").click()
            expect(whatsapp.get_by_role("status")).to_contain_text("Complete sending in WhatsApp")
            shared = page.evaluate("window.sharedDocuments[0]")
            assert shared["text"] == message and shared["type"] == "application/pdf"
            assert bytes(shared["bytes"]) == transport.call_args.args[2]
            with page.expect_popup() as popup_info, page.expect_download() as whatsapp_download:
                whatsapp.get_by_role("link", name="Open WhatsApp").click()
            popup_info.value.close()
            assert Path(whatsapp_download.value.path()).read_bytes() == transport.call_args.args[2]
            page.get_by_role("button", name="Receipt", exact=True).first.click()
            send = page.get_by_role("region", name="Email customer document")
            send.get_by_role("button", name="Send to customer", exact=True).click()
            expect(send.get_by_text("PDF attachment:", exact=False)).to_contain_text("-R001.pdf")
            send.get_by_role("button", name="Confirm send", exact=True).click()
            expect(send.get_by_role("status")).to_contain_text("Email sent.")
            assert transport.call_count == 2
            with page.expect_download() as receipt_download:
                page.get_by_role("button", name="Download receipt PDF", exact=True).click()
            assert Path(receipt_download.value.path()).read_bytes() == transport.call_args.args[2]
            page.get_by_role("button", name="Back to invoice", exact=True).click()
            page.get_by_role("button", name="Combined receipt", exact=True).click()
            send.get_by_role("button", name="Send to customer", exact=True).click()
            expect(send.get_by_text("PDF attachment:", exact=False)).to_contain_text("-ALL-002.pdf")
            send.get_by_role("button", name="Confirm send", exact=True).click()
            expect(send.get_by_role("status")).to_contain_text("Email sent.")
            assert transport.call_count == 3
            with page.expect_download() as combined_download:
                page.get_by_role("button", name="Download receipt PDF", exact=True).click()
            assert Path(combined_download.value.path()).read_bytes() == transport.call_args.args[2]
            # A browser without native file sharing must still offer download + chat.
            page.evaluate("Object.defineProperty(navigator, 'canShare', {configurable: true, value: undefined})")
            whatsapp.get_by_role("button", name="Send to WhatsApp", exact=True).click()
            expect(whatsapp.get_by_role("link", name="Open WhatsApp")).to_be_visible()
            expect(whatsapp.get_by_role("button", name="Share PDF with app")).to_have_count(0)
            expect(whatsapp.get_by_role("button", name="Download PDF", exact=True)).to_be_visible()
            page.screenshot(path=str(output / "combined-receipt-mobile.png"), full_page=True)
            assert not errors, errors
            browser.close()
            print("Email browser/PDF checks passed: invoice, single/combined receipts, 320/390/768/1440px layout, 68 vehicles, matching PDF downloads, WhatsApp message/phone, native file sharing and fallback; no real emails or WhatsApp messages.")
    finally:
        process.terminate()
        process.wait(timeout=15)
        server.shutdown()
        log.close()
        fixture.tearDown()
        fixture.doCleanups()


if __name__ == "__main__":
    main()
