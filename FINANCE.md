# Finance module

## Staff workflow

Open **Finance → Generate invoice**, or use **Generate invoice** on a customer profile.

1. **Customer:** Find an existing RoieTrackers account. Name and email are read-only and validated against the account on the server. Phone is loaded when available. The last saved billing address is reused. New customers must use the existing onboarding page; its success link returns to finance with that customer selected.
2. **Task:** Choose Renewal, New installation, Maintenance, or Special Service. Standard categories load their default negotiated price per vehicle. Renewal and maintenance require actual account vehicles. For installation, enter a count of vehicles awaiting installation, select already installed vehicles, or combine both. Special Service takes one item, its description, and amount. Each task can include explanatory notes.
3. **Task list:** Edit, remove or add another task. Quantity comes from the selected vehicles and pending installation count.
4. **Terms:** Set a due date, invoice notes, and an optional percentage or fixed NGN discount. Discount is deducted once from the subtotal, after the item allocations.
5. **Review:** Confirm the calculated invoice and save a draft. Edit it if needed, then finalize. Finalization assigns a unique invoice number and locks the billing snapshot and amounts.

Use **Update phone in RoieTrackers** to explicitly synchronize a changed/missing phone. Saving an invoice alone stores the billing contact; it does not update the account. Addresses remain in finance. The existing onboarding flow creates customer accounts; finance itself cannot create them.

## Invoice and receipt layout

Invoices group identical prices, service periods and task explanations. Each section shows **Item / Qty / Price / Amount**, a comma-separated vehicle list and a subtotal. Long vehicle lists stay inside the invoice; the mobile invoice list has separate customer and service columns.

Installation items print in this order:

1. **GPS_D_V4** — Intelligent GPS Tracker Device for Automobile
2. **GPRS_GSM** — GSM Access Fee for 12 months per module (MTN)
3. **GPS_Server_Maintenance** — Global Server App License Fee for 1 year per module
4. **Installation** — Logistics, Installation

Renewals show the GPRS and server items. Maintenance shows service and logistics. Special Service prints the entered item and description. Historical invoices retain their stored amounts; display codes do not recalculate prices.

All invoices include **GTBank / 0421439134 / Roie Technologies Ltd**. The supplied 14 sales terms and a signature/date area appear only when at least one installation is present. Payment status appears as an angled stamp beside Bill to: unpaid red, partial yellow, fully paid green. Draft and cancelled documents retain explicit labels.

Use **Print / save PDF** for the customer document. Staff controls, activity history and payment screenshots are excluded from printing.

## Payments and cancellation

Every new payment requires amount, method, date, reference, and a PNG, JPEG or WebP screenshot (up to 4 MB and 20 megapixels). The server decodes and normalizes the image to PNG before saving it privately. Screenshots are accessible only through the authenticated staff API.

Each payment has a stable receipt number. **Receipt** generates the individual payment receipt with the balance as of that recorded payment. Later payments do not change that historical balance. **Combined receipt** includes all payments currently recorded on the invoice. Neither receipt exposes staff identity or screenshot contents.

Cancellation requires **account ID 1 AND a live administrator role**. Other staff cannot cancel through either the UI or API. Paid/partially paid invoices cannot be cancelled through this workflow. Cancellation preserves the record and its reason in the audit history. Refunds/reversals are not implemented.

Customer profiles show the distinct number of associated vehicles, whole-account finance status and outstanding balance, plus linked invoice/payment history. Vehicle history filters whole invoices containing that vehicle; payments are recorded per invoice rather than allocated artificially across vehicles.

## Allocation rules

All money is calculated server-side and stored in integer kobo. Rounding remainders keep component totals exact.

| Category | Default per vehicle | Allocation |
| --- | ---: | --- |
| Renewal | NGN 15,000 | GPRS 80%; server 20% |
| New installation | NGN 140,000 | GPRS max(8.6%, NGN 12,000); server max(2.4%, NGN 3,000); remainder split installation:device = 14:75 |
| Maintenance | NGN 20,000 | Service 60%; logistics 40% |
| Special Service | Enter amount | One custom item at the entered amount |

At NGN 100,000 per installation, allocations are GPRS 12,000, server 3,000, installation 13,370.79 and device 71,629.21. Installation prices below NGN 15,000 are rejected. Minimums apply per vehicle before any invoice-level discount.

For 68 renewals at NGN 15,000, GPRS is 68 × NGN 12,000 = NGN 816,000 and server is 68 × NGN 3,000 = NGN 204,000. The vehicle list contains 68 vehicles and the section subtotal is NGN 1,020,000. There is a limit of 1,000 entries per invoice.

Device ownership is checked when saving, finalizing and linking after installation. Use the normal account/device workflow to install and associate a vehicle, then reload the invoice and choose **Link device**. This only changes the finance relationship, never the account's actual device assignment.

## Storage and deployment

No SQL tables or columns are added. Finance reads the existing customer/device tables and stores its own records in a locked, atomic JSON ledger. Its sole account write is the explicit phone PUT, based on a freshly retrieved user object while preserving other fields. A changed phone since loading is detected; the account API does not support atomic phone-only updates, so avoid simultaneous edits of that account while syncing.

`FINANCE_DATA_DIR` contains:

- `ledger.json`: customers, invoices, payments, sequence and audit history.
- `ledger.lock`: stable lock for coordinating workers.
- `payment-proofs/`: normalized, content-addressed payment screenshots.

Docker uses `/app/data/finance` in the persistent **finance_data** volume, writable by runtime UID 10003. Rebuild both backend and frontend to deploy code changes; the backend requirements now include Pillow for screenshot validation. Do not remove the finance volume during deployment.

Back up the **whole finance directory**, including payment proofs, to protected storage. For a live backup, copy the committed ledger first and then its referenced proofs; proof files are immutable and written before the ledger commit. For restore, stop backend writes and restore the full snapshot, including the invoice sequence and proofs, with the correct ownership. No automated backup job is supplied.

The local JSON store supports multiple workers on one host and one local filesystem. It is not intended for multiple independent backend volumes or unverified network filesystems. All staff requests validate a live session and the existing staff allowlist. Mutations require JSON plus a custom header, and the Next proxy checks same-origin requests. Revisions reject stale edits; creation/payment retries are idempotent; corrupt ledgers fail closed.

The Next finance proxy uses `BACKEND_URL`, falling back to `NEXT_PUBLIC_BACKEND_URL`. For laptop testing, keep the SSH tunnel open and use `python run_local.py` from `backend`. The launcher preserves DB credentials but routes the connection through `127.0.0.1:13306` and selects a local finance directory. See `MyComputer/notes.md` for exact PowerShell steps. Customer/device reads still use the live account database; explicit account actions still affect that account.

## Verification

From `backend` with its dependencies installed:

```text
python -m unittest discover -s tests -p "test_*.py"
```

Tests use temporary JSON, in-memory SQLite and mocked remote responses. They cover calculations, quantity/ownership, persistence, permissions, identity, discounts, private screenshots, receipts and account summaries without contacting production.

From `frontend`:

```text
npx tsc --noEmit
node --test tests/finance.test.cjs
```

Build separately for browser checks (PowerShell):

```powershell
$env:NEXT_BUILD_DIR = '.next-finance-qa'
npm run build
```

Then from `backend`, with Playwright, PyMuPDF and Chrome installed:

```text
python tests/finance_browser_smoke.py
```

The browser test uses loopback ports 5057/3107, temporary records, mocked sessions and the isolated build. It verifies the guided flow, mobile layout, 68-vehicle invoices, proof uploads and receipts, including PDF text checks and rendered page images. PDFs are under ignored `output/pdf`; QA screenshots are under ignored `MyComputer/finance-qa`. Test servers stop on completion. The browser test deliberately disables `crypto.randomUUID` to exercise the secure `crypto.getRandomValues` fallback used on HTTP/LAN contexts.
