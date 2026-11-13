# Finance module

Open **Finance → Generate invoice**, or generate one from a customer's search profile.

1. Find an existing Traccar customer, reuse a saved billing profile, or enter a new customer before onboarding.
2. Confirm name, email, phone and billing address. **Update phone in Traccar** explicitly synchronizes the phone; address and other billing edits stay in finance.
3. Add one or more tasks. Select a category to load its default price per vehicle, then adjust that unit price. Select customer vehicles in bulk, or name pending vehicles in a comma-separated list. Quantity is derived from the list, and calculations refresh automatically.
4. Review the invoice and save a draft. Open the saved draft to edit or finalize it. Finalization assigns a unique invoice number and fixes the billing contact snapshot and prices.
5. Print or save a PDF using the browser's print dialog. Reopening the invoice uses the stored snapshot, not current pricing or contact information.
6. Record payments with amount, method, received date and transaction/receipt reference. Partial payments and outstanding balances are supported. Recording does not charge a customer or modify a Traccar subscription.

## Allocation rules

Amounts are stored in **integer kobo**, calculated on the server, with rounding remainders assigned to the final component so totals always match exactly.

| Category | Default per vehicle | Breakdown |
| --- | ---: | --- |
| Renewal | NGN 15,000 | GPRS 80%; server 20% |
| New installation | NGN 140,000 | GPRS max(8.6% of total, NGN 12,000); server max(2.4% of total, NGN 3,000); remaining amount split installation:device = 14:75 |
| Maintenance | NGN 20,000 | Service 60%; logistics 40% |

At NGN 140,000, installation components are NGN 12,040 / 3,360 / 19,600 / 105,000.
At NGN 100,000, they are NGN 12,000 / 3,000 / 13,370.79 / 71,629.21.
Installation totals below NGN 15,000 are rejected. At exactly NGN 15,000, installation and device allocations are zero.

## Customer and vehicle relationships

Each task selects multiple devices belonging directly to the customer or to a group linked to that customer. Internally, each billed vehicle retains its own entry and device reference so existing invoices and vehicle history remain compatible. Device ownership is checked when saving and finalizing, and when linking later.

A task without devices requires a name for each pending vehicle/activity. Separate names with commas or newlines; quote names containing commas. Every name counts as one unit. The backend rejects mismatched quantities and duplicate vehicle assignments for the same category and service period. New installation entries are marked as pending installation. After installation and the normal Traccar device assignment, reload the invoice and use **Link device**. This changes only the finance reference and adds an audit event. It never assigns or edits a Traccar device.

A customer without a Traccar account gets a finance-only prospect profile. After onboarding, use **Link customer after onboarding** on the invoice, then link the device. This preserves the original printed contact details. If a prospect has several invoices, link each applicable invoice explicitly.

Customer search profiles include finance/payment history. Vehicle history filters invoices containing that vehicle; payment totals are **invoice-level**, not an inferred allocation of payments to individual vehicles.

## Persistence and operations

No tables or columns are added to the existing database. The module only reads existing Traccar SQL tables. Its sole Traccar write is the explicit customer-phone PUT, using a freshly retrieved user object and preserving all other fields. It detects a phone change since the customer was loaded; Traccar does not provide an atomic phone-only update, so avoid concurrent edits of the same account while syncing. Failed/uncertain updates ask staff to reload before retrying.

`FINANCE_DATA_DIR` defaults to `backend/data/finance`. In Docker Compose it is `/app/data/finance`, mounted from the persistent **finance_data** named volume. The image creates that directory for runtime UID 10003. Local ledger files are ignored by Git.

The ledger uses a stable file lock across processes, a flushed temporary file, and atomic replacement. It supports the existing two Gunicorn workers on **one host with a local filesystem**. Do not deploy multiple independent backend volumes or put this ledger on an unverified network filesystem. Whole-ledger reads/writes suit an initial small deployment; use a dedicated document store when volume or deployment topology grows.

Back up `ledger.json` regularly to protected storage outside the container host, and test restoration. Copying the committed JSON file on the local filesystem observes an atomic version. Stop backend writes during restore, restore the complete ledger including its sequence, and retain UID 10003 write access in Docker. Never remove the finance volume with `docker compose down -v` unless intentionally discarding finance records. Restart/rebuild alone preserves it. There is no automated backup job in this change.

Staff access is checked against a live Traccar session and the existing `admin_user_list`. Finance responses are not cached. Mutations require JSON and a custom request header, with same-origin enforcement in the Next proxy. Create/payment retries are idempotent; revisions reject stale edits. Corrupt ledgers fail closed rather than being overwritten. Only unpaid invoices can be voided. Payment reversal/refund workflows and automatic tax/payment-provider integrations are not included.

The Next proxy uses `BACKEND_URL` if configured, otherwise the existing `NEXT_PUBLIC_BACKEND_URL`. Existing Traccar/database environment configuration is unchanged. Deploy with the normal backend/frontend rebuild so the new blueprint, route and volume are included.

## Verification

From `backend`, with backend dependencies installed:

```text
python -m unittest discover -s tests -v
```

Tests use temporary JSON files, an in-memory SQLite fixture and mocked Traccar responses. They do not read/write live customer data. Coverage includes rounding/minimums, multi-process persistence, corruption handling, revisions/idempotency, authorization, ownership, billing snapshots, pending installations, payment history and phone-only updates.

From `frontend`:

```text
npx tsc --noEmit
npx eslint src/app/finance/page.tsx "src/app/api/finance/[...path]/route.ts" src/components/FinanceHistory.tsx src/lib/finance.ts
npm run build
```

See the grouped browser-check instructions below for the isolated build, browser/PDF test dependencies and generated samples. Test servers stop on completion.

## Grouped invoice layout

Printed invoices have separate Installations, Renewal and Maintenance sections. Each section contains **Breakdown / Qty / Unit price / Total**, a comma-separated vehicle list with its count, and a subtotal. Identical prices and service periods are grouped together. Different prices or periods use separate rate groups within the category; prices are never averaged. Saved invoices use their stored breakdowns rather than current defaults.

For **68 renewals at NGN 15,000 per vehicle**, GPRS is 68 × NGN 12,000 = NGN 816,000 and server is 68 × NGN 3,000 = NGN 204,000. The vehicle list contains 68 vehicles and the renewal subtotal is NGN 1,020,000. Installation minimums apply to each vehicle. An invoice supports up to 1,000 vehicles/activities.

Browser request keys use native `crypto.randomUUID` where available, with a `crypto.getRandomValues` UUID v4 fallback for HTTP/LAN browser contexts. No insecure random-number fallback is used.

For grouped browser checks, build from `frontend` with `NEXT_BUILD_DIR=.next-finance-qa` (PowerShell: `$env:NEXT_BUILD_DIR = ".next-finance-qa"; npm run build`), then run `python tests/finance_browser_smoke.py` from `backend` with Playwright, PyMuPDF and Chrome installed. This separate build keeps the normal dev server's `.next` output untouched. The test disables `randomUUID`, exercises a 68-vehicle draft/edit/finalize flow, and renders renewal and mixed-task PDFs under ignored `MyComputer/finance-qa`. Frontend regression tests run with `node --test tests/finance.test.cjs` from `frontend`.
