"""Staff-only finance API. SQL access here is strictly read-only."""
import copy
import hashlib
import io
import re
from datetime import datetime, timezone
from email.utils import make_msgid
import os
import uuid
from pathlib import Path

import requests
from flask import Blueprint, current_app, g, jsonify, request, send_file
from sqlalchemy import text

from config import TRACCAR_API_URL, TRACCAR_API_KEY, db
from routes.devices.common import admin_user_list, exclude_users_list
from services.finance import (CATEGORIES, FinanceError, Ledger, audit, calculate_tasks,
    check_revision, clean_customer, clean_phone, clean_text, finalize, get_invoice,
    invoice_view, invoice_totals, now, prepare_entries, record_payment, receipt_view, save_draft)
from services.profile_renewal import account_lock, canonical_expiry, eligible_devices, next_expiry
from services.payment_proof import prepare_proof, save_proof
from services.finance_pdf import document_pdf
from services.finance_mail import mailbox, smtp_settings, send_document

finance_bp = Blueprint("finance", __name__)


def ledger():
    return Ledger(current_app.config.get("FINANCE_DATA_DIR") or os.getenv(
        "FINANCE_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data" / "finance")))


@finance_bp.before_request
def require_staff():
    if request.method == "OPTIONS":
        return None
    if request.method != "GET":
        # A custom header and JSON content type prevent cross-origin form submissions.
        # CORS only allows the configured admin origin; Next also checks same-origin.
        if request.headers.get("X-Finance-Request") != "1" or not request.is_json:
            raise FinanceError("A JSON finance request is required.", 403)
        request.max_content_length = 7 * 1024 * 1024 if request.path.endswith("/payments") else 250000
        if request.content_length and request.content_length > request.max_content_length:
            raise FinanceError("Request is too large.", 413)
    token = request.cookies.get("session_token")
    if not token:
        raise FinanceError("Sign in to access finance.", 401)
    try:
        response = requests.get(TRACCAR_API_URL + "session",
            cookies={"JSESSIONID": token}, timeout=15)
        if response.status_code != 200:
            raise FinanceError("Session expired. Sign in again.", 401)
        user = response.json()
        if user.get("id") not in admin_user_list or user.get("disabled"):
            raise FinanceError("Staff access is required.", 403)
        g.finance_can_cancel = user.get("id") == 1 and user.get("administrator") is True
        g.finance_actor = {"id": user["id"], "name": user.get("name", "Staff")}
    except (requests.RequestException, ValueError) as exc:
        if isinstance(exc, FinanceError):
            raise
        raise FinanceError("Unable to verify your session with RoieTrackers.", 503) from exc


@finance_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@finance_bp.errorhandler(FinanceError)
def finance_error(exc):
    return jsonify(error=str(exc)), exc.status


def body():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise FinanceError("A JSON object is required.")
    return value


def user_record(user_id):
    if isinstance(user_id, bool) or not str(user_id).isdigit():
        raise FinanceError("Invalid customer account ID.")
    row = db.session.execute(text("SELECT id, name, email, phone FROM tc_users WHERE id = :id"),
                             {"id": int(user_id)}).mappings().first()
    if not row or row["id"] in exclude_users_list:
        raise FinanceError("Customer account not found.", 404)
    return dict(row)


def customer_devices(user_id):
    if user_id is None:
        return []
    rows = db.session.execute(text("""
        SELECT DISTINCT d.id, d.name, d.uniqueid AS imei FROM tc_devices d
        WHERE EXISTS (SELECT 1 FROM tc_user_device ud WHERE ud.deviceid = d.id AND ud.userid = :uid)
           OR EXISTS (SELECT 1 FROM tc_user_group ug WHERE ug.groupid = d.groupid AND ug.userid = :uid)
        ORDER BY d.name
    """), {"uid": user_id}).mappings().all()
    return [dict(row) for row in rows]


def customer_from_body(payload):
    raw = payload.get("customer")
    if not isinstance(raw, dict) or raw.get("traccar_user_id") is None:
        raise FinanceError("Onboard the customer first, then select their RoieTrackers account.")
    user = user_record(raw["traccar_user_id"])
    if raw.get("name") != user["name"] or raw.get("email") != user["email"]:
        raise FinanceError("Customer name and email must match their RoieTrackers account. Reload the customer.")
    customer = clean_customer({**raw, "name": user["name"], "email": user["email"]})
    customer.update(profile_id=f"traccar-{user['id']}", traccar_user_id=user["id"])
    return customer


@finance_bp.get("/permissions")
def permissions():
    return jsonify(can_cancel=g.finance_can_cancel)


@finance_bp.post("/validate-customer")
def validate_customer():
    return jsonify(customer=customer_from_body(body()))


@finance_bp.get("/categories")
def categories():
    return jsonify(CATEGORIES)


@finance_bp.get("/customers")
def customers():
    term = request.args.get("term", "").strip()
    with ledger().transaction() as data:
        profiles = [p for p in data["profiles"].values() if p.get("traccar_user_id") and term.lower() in
                    f"{p['name']} {p['email']} {p['phone']}".lower()]
    matches = []
    if term:
        rows = db.session.execute(text("""
            SELECT id, name, email, phone FROM tc_users
            WHERE name LIKE :term OR email LIKE :term OR phone LIKE :term
            ORDER BY name LIMIT 50
        """), {"term": f"%{term[:250]}%"}).mappings().all()
        matches = [dict(row) for row in rows if row["id"] not in exclude_users_list]
    return jsonify(accounts=matches, profiles=profiles[:50])


@finance_bp.get("/customers/<int:user_id>")
def customer_detail(user_id):
    user = user_record(user_id)
    with ledger().transaction() as data:
        profile = copy.deepcopy(data["profiles"].get(f"traccar-{user_id}", {}))
    # Billing contact details may differ; use the saved billing profile on regeneration.
    customer = {**profile, "name": user["name"], "email": user["email"], "phone": user["phone"] or profile.get("phone", ""),
                "profile_id": f"traccar-{user_id}", "traccar_user_id": user_id}
    devices = customer_devices(user_id)
    return jsonify(customer=customer, devices=devices, account_phone=user["phone"] or "", vehicle_count=len(devices))


@finance_bp.post("/customers/<int:user_id>/phone")
def sync_phone(user_id):
    user_record(user_id)
    payload = body()
    phone = clean_phone(payload.get("phone", ""))
    cookies = {"JSESSIONID": request.cookies["session_token"]}
    with account_lock(ledger().directory, user_id):
        try:
            response = requests.get(TRACCAR_API_URL + f"users/{user_id}", cookies=cookies, timeout=15)
            response.raise_for_status()
            current = response.json()
            if current.get("id") != user_id:
                raise FinanceError("RoieTrackers returned a different customer.", 502)
            if (current.get("phone") or "") != payload.get("expected_phone", ""):
                raise FinanceError("RoieTrackers phone changed. Reload the customer before updating it.", 409)
            # Traccar PUT expects the user object: preserve everything and change only phone.
            current["phone"] = phone
            response = requests.put(TRACCAR_API_URL + f"users/{user_id}", cookies=cookies,
                                    json=current, timeout=15)
            response.raise_for_status()
        except (requests.RequestException, ValueError) as exc:
            if isinstance(exc, FinanceError):
                raise
            raise FinanceError("Phone update could not be confirmed. Reload the customer before retrying.", 502) from exc
        return jsonify(phone=phone)


@finance_bp.post("/preview")
def preview():
    payload = body()
    customer = customer_from_body(payload)
    entries = prepare_entries(payload.get("entries"), customer_devices(customer["traccar_user_id"]))
    return jsonify(customer=customer, entries=entries, **invoice_totals(entries, payload.get("discount")))


@finance_bp.post("/calculate")
def calculate():
    payload = body()
    results = calculate_tasks(payload.get("entries"))
    return jsonify(entries=results, **invoice_totals(results, payload.get("discount")))


@finance_bp.get("/invoices")
def invoices():
    profile_id = request.args.get("profile_id")
    user_id = request.args.get("user_id")
    device_id = request.args.get("device_id")
    with ledger().transaction() as data:
        values = [invoice_view(i) for i in data["invoices"].values()
            if (not profile_id or i["customer"]["profile_id"] == profile_id)
            and (not user_id or str(i["customer"]["traccar_user_id"]) == user_id)
            and (not device_id or any(str((e["device"] or {}).get("id")) == device_id for e in i["entries"]))]
    return jsonify(invoices=sorted(values, key=lambda i: i["created_at"], reverse=True))


@finance_bp.get("/invoices/<invoice_id>")
def invoice_detail(invoice_id):
    with ledger().transaction() as data:
        return jsonify(invoice_view(get_invoice(data, invoice_id)))


@finance_bp.post("/invoices")
@finance_bp.put("/invoices/<invoice_id>")
def draft(invoice_id=None):
    payload = body()
    customer = customer_from_body(payload)
    entries = prepare_entries(payload.get("entries"), customer_devices(customer["traccar_user_id"]))
    with ledger().transaction(write=True) as data:
        invoice = save_draft(data, payload, customer, entries, g.finance_actor, invoice_id)
        result = invoice_view(invoice)
    return jsonify(result), 200 if invoice_id else 201


@finance_bp.post("/invoices/<invoice_id>/finalize")
def issue(invoice_id):
    payload = body()
    # Revalidate device ownership at finalization, not just when a draft was saved.
    with ledger().transaction() as data:
        snapshot = copy.deepcopy(get_invoice(data, invoice_id))
    customer = snapshot["customer"]
    if snapshot["status"] == "draft":
        if customer["traccar_user_id"] is None:
            raise FinanceError("Select an onboarded customer before finalizing this draft.", 409)
        current = user_record(customer["traccar_user_id"])
        if customer["name"] != current["name"] or customer["email"] != current["email"]:
            raise FinanceError("Customer identity changed. Reload the customer and review the draft.", 409)
        if any(not entry["device"] and entry["category"] not in ("installation", "special") for entry in snapshot["entries"]):
            raise FinanceError("Select vehicles for every renewal and maintenance task before finalizing.", 409)
        valid = {d["id"] for d in customer_devices(customer["traccar_user_id"])}
        if any(e["device"] and e["device"]["id"] not in valid for e in snapshot["entries"]):
            raise FinanceError("A selected device is no longer on this account. Edit the draft.", 409)
    with ledger().transaction(write=True) as data:
        invoice = get_invoice(data, invoice_id)
        result = invoice_view(finalize(data, invoice, payload, g.finance_actor))
    return jsonify(result)


@finance_bp.post("/invoices/<invoice_id>/payments")
def payment(invoice_id):
    payload = body()
    proof, content = prepare_proof(payload.get("proof"))
    store = ledger()
    with store.transaction(write=True) as data:
        result = invoice_view(record_payment(get_invoice(data, invoice_id), {**payload, "proof": proof}, g.finance_actor))
        save_proof(store.directory, proof, content)
    return jsonify(result)


@finance_bp.post("/invoices/<invoice_id>/link-device")
def link_device(invoice_id):
    payload = body()
    with ledger().transaction() as data:
        snapshot = copy.deepcopy(get_invoice(data, invoice_id))
    devices = customer_devices(snapshot["customer"]["traccar_user_id"])
    selected = next((d for d in devices if str(d["id"]) == str(payload.get("device_id"))), None)
    if not selected:
        raise FinanceError("Select a device belonging to this customer.")
    with ledger().transaction(write=True) as data:
        invoice = get_invoice(data, invoice_id)
        check_revision(invoice, payload)
        if invoice["status"] == "void":
            raise FinanceError("A void invoice cannot be linked.", 409)
        entry = next((e for e in invoice["entries"] if e["id"] == payload.get("entry_id")), None)
        if not entry or entry["device"] or entry["category"] != "installation":
            raise FinanceError("Select an entry that is awaiting a device.")
        if any(other["id"] != entry["id"] and other["device"] and
               other["device"]["id"] == selected["id"] and other["category"] == entry["category"] and
               other["activity"].casefold() == entry["activity"].casefold() for other in invoice["entries"]):
            raise FinanceError("This vehicle is already linked to the same task and service period.")
        entry.update(device=selected, link_status="linked")
        audit(invoice, "device_linked", g.finance_actor, entry_id=entry["id"], device_id=selected["id"])
        result = invoice_view(invoice)
    return jsonify(result)


@finance_bp.post("/invoices/<invoice_id>/link-customer")
def link_customer(invoice_id):
    payload = body()
    user = user_record(payload.get("user_id"))
    with ledger().transaction(write=True) as data:
        invoice = get_invoice(data, invoice_id)
        check_revision(invoice, payload)
        if invoice["status"] == "void" or invoice["customer"]["traccar_user_id"] is not None:
            raise FinanceError("Only an unlinked customer invoice can be linked.", 409)
        previous = invoice["customer"]["profile_id"]
        # Preserve the printed contact snapshot; add only the account relationship.
        invoice["customer"].update(traccar_user_id=user["id"], profile_id=f"traccar-{user['id']}")
        data["profiles"].setdefault(invoice["customer"]["profile_id"], copy.deepcopy(invoice["customer"]))
        audit(invoice, "customer_linked", g.finance_actor, previous_profile_id=previous, user_id=user["id"])
        result = invoice_view(invoice)
    return jsonify(result)


@finance_bp.post("/invoices/<invoice_id>/void")
def void(invoice_id):
    if not g.finance_can_cancel:
        raise FinanceError("Only account 1 with the administrator role can cancel invoices.", 403)
    payload = body()
    reason = clean_text(payload.get("reason", ""), "Void reason", 500)
    with ledger().transaction(write=True) as data:
        invoice = get_invoice(data, invoice_id)
        check_revision(invoice, payload)
        if invoice["payments"] or invoice["status"] == "void":
            raise FinanceError("Only unpaid, non-void invoices can be voided.", 409)
        invoice["status"] = "void"
        audit(invoice, "voided", g.finance_actor, reason=reason)
        result = invoice_view(invoice)
    return jsonify(result)


@finance_bp.get("/invoices/<invoice_id>/payments/<payment_id>/proof")
def payment_proof(invoice_id, payment_id):
    store = ledger()
    with store.transaction() as data:
        invoice = get_invoice(data, invoice_id)
        payment = next((p for p in invoice["payments"] if p["id"] == payment_id), None)
        if not payment or not payment.get("proof"):
            raise FinanceError("Payment screenshot not found.", 404)
        digest = payment["proof"]["sha256"]
    import re
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise FinanceError("Payment screenshot not found.", 404)
    path = store.directory / "payment-proofs" / f"{digest}.png"
    if not path.is_file():
        raise FinanceError("Payment screenshot is unavailable.", 404)
    response = send_file(path, mimetype="image/png", download_name="payment-screenshot.png")
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@finance_bp.get("/invoices/<invoice_id>/receipts")
def receipts(invoice_id):
    with ledger().transaction() as data:
        return jsonify(receipt_view(get_invoice(data, invoice_id), request.args.get("payment_id")))


@finance_bp.get("/customers/<int:user_id>/summary")
def customer_summary(user_id):
    user_record(user_id)
    with ledger().transaction() as data:
        values = [invoice_view(i) for i in data["invoices"].values()
                  if i["customer"].get("traccar_user_id") == user_id and i["status"] == "issued"]
    paid = sum(i["paid_minor"] for i in values)
    balance = sum(i["balance_minor"] for i in values)
    status = "no_invoices" if not values else "paid" if balance == 0 else "partial" if paid else "unpaid"
    return jsonify(vehicle_count=len(customer_devices(user_id)), finance_status=status,
                   paid_minor=paid, balance_minor=balance,
                   unpaid_invoice_count=sum(i["balance_minor"] > 0 for i in values))


# Expiry is an account property. Vehicles below are immutable invoice/audit links;
# this action never changes device records or writes to SQL directly.
def renewal_credentials():
    # The live staff session is still required by require_staff. The server
    # credential is scoped here to the invoice-backed customer expiry workflow.
    if TRACCAR_API_KEY:
        return {"headers": {"Authorization": f"Bearer {TRACCAR_API_KEY}", "Content-Type": "application/json"}}
    return {"cookies": {"JSESSIONID": request.cookies.get("session_token")}}


def renewal_account(user_id):
    try:
        response = requests.get(TRACCAR_API_URL + f"users/{user_id}",
            **renewal_credentials(), timeout=8)
        if response.status_code != 200:
            raise FinanceError("Could not load this profile from RoieTrackers. Ask the administrator to check the backend TRACCAR_ADMIN_KEY and its account permissions.", 503)
        account = response.json()
        if not isinstance(account, dict) or account.get("id") != user_id:
            raise FinanceError("RoieTrackers returned an unexpected profile.", 503)
        if account.get("administrator") is True:
            raise FinanceError("Administrator profiles cannot be extended through customer finance.", 403)
        return account
    except (requests.RequestException, ValueError) as exc:
        if isinstance(exc, FinanceError):
            raise
        raise FinanceError("Could not verify the live profile. Please retry.", 503) from exc


@finance_bp.get("/customers/<int:user_id>/renewal-options")
def renewal_options(user_id):
    user_record(user_id)
    account = renewal_account(user_id)
    devices = customer_devices(user_id)
    invoices, history = [], []
    with ledger().transaction() as data:
        for invoice in data["invoices"].values():
            if invoice["customer"].get("traccar_user_id") != user_id:
                continue
            operation = invoice.get("renewal_extension")
            if operation:
                history.append(copy.deepcopy(operation))
                continue
            available = eligible_devices(invoice, user_id, devices)
            if available:
                invoices.append({"id": invoice["id"], "number": invoice["number"],
                    "revision": invoice["revision"], "devices": available})
    reason = None
    try:
        proposed = next_expiry(account.get("expirationTime"))
    except FinanceError as exc:
        proposed, reason = None, str(exc)
    return jsonify(expiration_time=account.get("expirationTime"), proposed_expiration_time=proposed,
        disabled=bool(account.get("disabled")), unavailable_reason=reason,
        invoices=invoices, history=sorted(history, key=lambda item: item["requested_at"], reverse=True))


@finance_bp.post("/customers/<int:user_id>/extend-expiry")
def extend_profile_expiry(user_id):
    user_record(user_id)
    payload = body()
    invoice_id = clean_text(payload.get("invoice_id", ""), "Invoice ID")
    request_key = clean_text(payload.get("request_key", ""), "Request key")
    selected = payload.get("device_ids")
    if (not isinstance(selected, list) or not selected or len(selected) > 1000
            or any(type(value) is not int or value <= 0 for value in selected)
            or len(set(selected)) != len(selected)):
        raise FinanceError("Select distinct vehicles from the paid invoice's Renewal section.")
    selected = sorted(selected)
    expected = canonical_expiry(payload.get("expected_expiration_time"))
    store = ledger()
    with account_lock(store.directory, user_id):
        with store.transaction() as data:
            invoice = get_invoice(data, invoice_id)
            if invoice["customer"].get("traccar_user_id") != user_id:
                raise FinanceError("The invoice belongs to a different customer.", 409)
            operation = copy.deepcopy(invoice.get("renewal_extension"))
            if operation:
                if (operation["request_key"] != request_key or operation["device_ids"] != selected
                        or operation["previous_expiration_time"] != expected):
                    raise FinanceError("This invoice already has a profile extension. Reload its renewal history.", 409)
                if operation["state"] == "applied":
                    return jsonify(extension=operation)
            for other in data["invoices"].values():
                prior = other.get("renewal_extension")
                if prior and prior["request_key"] == request_key and other["id"] != invoice_id:
                    raise FinanceError("This request key has already been used for another invoice.", 409)
                if (other["id"] != invoice_id and prior and prior["user_id"] == user_id
                        and prior["state"] == "pending"):
                    raise FinanceError("Resolve the pending profile extension before using another invoice.", 409)
        account = renewal_account(user_id)
        current_expiry = canonical_expiry(account.get("expirationTime"))
        if operation is None:
            if current_expiry != expected:
                raise FinanceError("The profile expiry changed. Reload before extending it.", 409)
            with store.transaction(write=True) as data:
                invoice = get_invoice(data, invoice_id)
                check_revision(invoice, payload)
                available = {device["id"]: device for device in eligible_devices(invoice, user_id, customer_devices(user_id))}
                if set(selected) != set(available):
                    raise FinanceError("Use an unused, fully paid Renewal invoice and select exactly all vehicles billed for renewal. Every renewal vehicle must still belong to this customer.", 409)
                operation = {"id": str(uuid.uuid4()), "request_key": request_key, "state": "pending",
                    "invoice_id": invoice_id, "invoice_number": invoice["number"], "user_id": user_id,
                    "renewal_quantity": len(selected), "device_ids": selected, "devices": [available[key] for key in selected],
                    "previous_expiration_time": expected, "expiration_time": next_expiry(expected),
                    "requested_at": now(), "actor": copy.deepcopy(g.finance_actor)}
                invoice["renewal_extension"] = operation
                audit(invoice, "profile_extension_requested", g.finance_actor, extension_id=operation["id"],
                    device_ids=selected, previous_expiration_time=expected, expiration_time=operation["expiration_time"])
            # The intent, immutable target date and vehicle snapshots are durable
            # before any remote write. Retries always use this same target date.
        target = operation["expiration_time"]
        if current_expiry not in (expected, target):
            raise FinanceError("The live expiry differs from both recorded dates. No change was made. Ask an administrator to reconcile this pending extension.", 409)
        if current_expiry != target:
            with store.transaction() as data:
                invoice = get_invoice(data, invoice_id)
                available = {device["id"] for device in eligible_devices(invoice, user_id, customer_devices(user_id))}
                if set(selected) != set(available):
                    raise FinanceError("Invoice payment or vehicle ownership changed. This pending extension requires reconciliation.", 409)
            updated = copy.deepcopy(account)
            updated["expirationTime"] = target
            try:
                response = requests.put(TRACCAR_API_URL + f"users/{user_id}", json=updated,
                    **renewal_credentials(), timeout=8)
                if response.status_code not in (200, 204):
                    return jsonify(extension=operation, error="RoieTrackers did not accept the update. Ask the administrator to check the backend TRACCAR_ADMIN_KEY, then use Verify / retry on this pending extension."), 202
            except requests.RequestException:
                # The server might have committed despite a timeout. Read back
                # before deciding; never calculate another year on a retry.
                pass
        try:
            confirmed = renewal_account(user_id)
            if canonical_expiry(confirmed.get("expirationTime")) != target:
                raise FinanceError("Expiry not confirmed.", 503)
        except FinanceError:
            return jsonify(extension=operation, error="The extension is not confirmed yet. Use Verify / retry in renewal history; do not create another extension."), 202
        with store.transaction(write=True) as data:
            invoice = get_invoice(data, invoice_id)
            operation = invoice["renewal_extension"]
            operation.update(state="applied", applied_at=now(), verified_by=copy.deepcopy(g.finance_actor),
                disabled=bool(confirmed.get("disabled")))
            audit(invoice, "profile_extended", g.finance_actor, extension_id=operation["id"],
                device_ids=selected, previous_expiration_time=expected, expiration_time=target)
            result = copy.deepcopy(operation)
        return jsonify(extension=result)


@finance_bp.post("/invoices/<invoice_id>/email")
def email_document(invoice_id):
    payload = body()
    key = clean_text(payload.get("request_key", ""), "Request key", 100)
    if not key:
        raise FinanceError("A request key is required.")
    kind, payment_id = payload.get("kind"), payload.get("payment_id")
    if kind not in ("invoice", "receipt") or (payment_id is not None and (not isinstance(payment_id, str) or not payment_id)):
        raise FinanceError("Choose an invoice or receipt to send.")
    if kind == "invoice" and payment_id is not None:
        raise FinanceError("A payment can only be selected for a receipt.")
    store = ledger()
    with store.transaction() as data:
        snapshot = copy.deepcopy(get_invoice(data, invoice_id))
        prior = next((item for item in snapshot.get("email_deliveries", []) if item["request_key"] == key), None)
        if prior:
            if prior["kind"] != kind or prior.get("payment_id") != payment_id:
                raise FinanceError("This email request was already used for a different document.", 409)
            return jsonify(delivery=prior, invoice=invoice_view(snapshot))
        check_revision(snapshot, payload)
        if snapshot["status"] != "issued":
            raise FinanceError("Only finalized, active invoices and their receipts can be emailed.", 409)
    recipient = mailbox(snapshot["customer"]["email"])
    settings = smtp_settings()
    attachment, number = document_pdf(snapshot, kind, payment_id)
    label = "Invoice" if kind == "invoice" else "Payment receipt" if payment_id else "Combined payment receipt"
    operation = {"id": uuid.uuid4().hex, "request_key": key, "kind": kind, "payment_id": payment_id,
        "recipient": recipient, "customer_name": snapshot["customer"]["name"], "label": label,
        "document_number": number, "filename": re.sub(r"[^A-Za-z0-9_.-]", "_", number) + ".pdf",
        "message_id": make_msgid(domain=settings["envelope"].split("@")[-1]),
        "document_sha256": hashlib.sha256(attachment).hexdigest(), "invoice_revision": snapshot["revision"],
        "state": "pending", "requested_at": now(), "actor": copy.deepcopy(g.finance_actor),
        "message": "Sending is pending or its outcome is unconfirmed. Reload to check before sending again."}
    with store.transaction(write=True) as data:
        invoice = get_invoice(data, invoice_id)
        prior = next((item for item in invoice.get("email_deliveries", []) if item["request_key"] == key), None)
        if prior:
            if prior["kind"] != kind or prior.get("payment_id") != payment_id:
                raise FinanceError("This email request was already used for a different document.", 409)
            return jsonify(delivery=prior, invoice=invoice_view(invoice))
        check_revision(invoice, payload)
        attempts = [item for item in invoice.get("email_deliveries", []) if item["kind"] == kind and item.get("payment_id") == payment_id]
        if attempts and attempts[-1]["state"] in ("pending", "unknown"):
            latest = attempts[-1]
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(latest["requested_at"])).total_seconds()
            if latest["state"] == "pending" and age < 120:
                raise FinanceError("An email request is still pending. Wait two minutes and reload before trying again.", 409)
            if payload.get("confirm_resend") is not True:
                raise FinanceError("The previous email outcome is unconfirmed. Check the sender's mailbox and confirm before resending.", 409)
        invoice.setdefault("email_deliveries", []).append(operation)
        audit(invoice, "email_requested", g.finance_actor, delivery_id=operation["id"], recipient=recipient, document_number=number)
    # Commit the intent before contacting SMTP. No network call holds the ledger lock.
    state, message = send_document(settings, operation, attachment)
    with store.transaction(write=True) as data:
        invoice = get_invoice(data, invoice_id)
        delivery = next(item for item in invoice["email_deliveries"] if item["id"] == operation["id"])
        delivery.update(state=state, message=message, completed_at=now())
        audit(invoice, "email_" + state, g.finance_actor, delivery_id=operation["id"], recipient=recipient, document_number=number)
        result = invoice_view(invoice)
    return jsonify(delivery=delivery, invoice=result)


@finance_bp.get("/invoices/<invoice_id>/pdf")
def download_document(invoice_id):
    kind, payment_id = request.args.get("kind", "invoice"), request.args.get("payment_id")
    if kind not in ("invoice", "receipt") or (kind == "invoice" and payment_id is not None) or payment_id == "":
        raise FinanceError("Choose an invoice or receipt to download.")
    with ledger().transaction() as data:
        snapshot = copy.deepcopy(get_invoice(data, invoice_id))
    if snapshot["status"] != "issued":
        raise FinanceError("Only finalized, active invoices and receipts can be downloaded.", 409)
    revision = request.args.get("revision")
    if revision is not None:
        if not revision.isdigit():
            raise FinanceError("Invalid document revision.")
        check_revision(snapshot, {"revision": int(revision)})
    content, number = document_pdf(snapshot, kind, payment_id)
    filename = re.sub(r"[^A-Za-z0-9_.-]", "_", number) + ".pdf"
    response = send_file(io.BytesIO(content), mimetype="application/pdf", as_attachment=True,
                         download_name=filename, max_age=0)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
