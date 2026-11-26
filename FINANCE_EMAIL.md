# Invoice numbering and customer email

New invoices start at `ROIE-<year>-019674`, then `019676`, `019678`, increasing by two. Existing invoice and receipt numbers stay unchanged. The existing locked JSON ledger stores the counter; restoring a ledger with a higher issued number continues above that number to avoid duplicates. No SQL schema change is needed.

## Local testing

From the project root with your virtual environment activated:

```powershell
python -m pip install -r backend/requirements.txt
```

Restart the backend and frontend after updating. The backend reads SMTP settings from the process environment (including backend/.env loaded by the existing configuration), with the root `.env` as a fallback for missing SMTP settings only. Database settings are unaffected.

Open a finalized invoice and select **Send to customer**. Check the displayed customer email and PDF filename, then **Confirm send**. To send a receipt, open **Receipt** beside a payment or **Combined receipt**, then use the same send button. Drafts and cancelled invoices cannot be emailed. The customer email comes from the invoice's saved billing contact; it cannot be overridden by a browser request.

The PDF includes grouped vehicles, stored prices, discounts, payment status, bank details, notes and installation sales terms. Individual receipts show the balance as of that payment; combined receipts include all recorded payments. Internal audit records and payment screenshots are excluded.

## Production settings

Keep the six SMTP variables from `.env.example` in `/opt/roieadmin_v2/.env` on the server. The updated Compose file passes them only to the backend container. Your laptop `.env` is not committed or uploaded by the deployment pipeline. Deploy/rebuild through the existing pipeline after adding the server settings; locally, restart the backend after changing its environment.

`SMTP_TLS=true` uses STARTTLS on port 587. Port 465 uses implicit TLS. Certificate validation is enabled. Authenticated SMTP without encryption is refused. For Gmail, use the account's app password where required; never commit credentials. The PDF dependency is installed during the normal backend Docker build.

## Delivery history and retries

Each invoice records who requested a send, recipient, document number, message ID, PDF SHA-256, timestamp and outcome. **Email sent** confirms the message was submitted successfully through SMTP. Repeating the same request key returns the original outcome without sending another email.

A timeout after transmission can leave delivery unconfirmed. Reload the invoice and inspect email history and the sender's mailbox before deliberately resending. Pending requests cannot be resent for two minutes. After that, staff must explicitly confirm another copy; requests are never automatically retried or silently discarded. A normal confirmed resend of a previously sent document also requires clicking Confirm send again.

## Automated verification (no real emails)

```powershell
$env:PYTHONPATH = "$PWD\backend"
python -m unittest discover -s backend/tests -p 'test_*.py'
cd frontend
node --test tests/finance.test.cjs
$env:NEXT_BUILD_DIR = '.next-renewal-check'
npm run build
cd ..
python backend/tests/finance_email_browser_smoke.py
```

The optional browser/PDF check needs Python Playwright, PyMuPDF and Chrome. It uses temporary records, mocked SMTP and local ports 5059/3109. QA artifacts are written to ignored `output/pdf/email-qa/`.

Implementation references: [Python SMTP client](https://docs.python.org/3/library/smtplib.html) and [ReportLab PDF guide](https://www.reportlab.com/docs/reportlab-userguide.pdf).


## Universal PDFs and WhatsApp

**Download PDF** and **Download receipt PDF** use the same backend renderer as email attachments. A document with the same financial contents produces the same PDF bytes. Downloads require a verified staff session; invoices are not published on a public URL. Finalize drafts before downloading or sharing.

**Send to WhatsApp** loads the phone from the customer account matching the invoice email. Nigerian numbers such as `08012345678`, `8012345678`, `2348012345678` and `+2348012345678` normalize to `2348012345678`. Invalid or ambiguous numbers require correcting the customer profile. This does not rewrite the saved phone number.

The panel prepares a message containing the invoice/receipt number, total, balance and GTBank account details. **Open WhatsApp** opens `wa.me` with the customer number and message, and downloads the PDF to attach in the chat. Staff review and send in WhatsApp. A click-to-chat URL cannot carry a binary attachment or force WhatsApp Business to open.

On compatible browsers, **Share PDF with app** opens the device share menu with the PDF and message. Choose WhatsApp Business and the intended customer there; the browser cannot preselect that app or recipient. If sharing is unsupported, use the downloaded PDF and prepared chat. **Copy message** is available if the receiving app omits the text. WhatsApp determines whether the number is registered. No message is sent automatically.

References: [WhatsApp click to chat](https://faq.whatsapp.com/5913398998672934) and [browser file sharing](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/share).


## Staff profile renewal

All authorized portal staff can use the invoice-backed renewal flow. The backend validates their live session, then uses its existing `TRACCAR_ADMIN_KEY` for customer profile reads and the expiry update. Keep this credential in the backend server environment (the existing `backend/.env` is loaded by Compose); it is never exposed to the frontend. The audit identifies the staff member who performed the renewal.

The invoice must be unused, finalized, fully paid and belong to the customer. Every vehicle billed in its Renewal section must be selected, with the same quantity and exact vehicle IDs, and must still belong to the account. Other services do not count. An invoice authorizes one year from the old expiry and can be used once. Disabled profiles remain disabled and administrator profiles are excluded. Existing pending operations use Verify / retry without adding a second year.
