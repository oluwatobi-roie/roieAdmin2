"""Staff-only finance API. SQL access here is strictly read-only."""
import copy
import os
import uuid
from pathlib import Path

import requests
from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import text

from config import TRACCAR_API_URL, db
from routes.devices.common import admin_user_list, exclude_users_list
from services.finance import (CATEGORIES, FinanceError, Ledger, audit, calculate_tasks,
    check_revision, clean_customer, clean_phone, clean_text, finalize, get_invoice,
    invoice_view, prepare_entries, record_payment, save_draft)

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
        if request.content_length and request.content_length > 100000:
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
        g.finance_actor = {"id": user["id"], "name": user.get("name", "Staff")}
    except (requests.RequestException, ValueError) as exc:
        if isinstance(exc, FinanceError):
            raise
        raise FinanceError("Unable to verify your session with Traccar.", 503) from exc


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
    customer = clean_customer(payload.get("customer"))
    raw = payload["customer"]
    uid = raw.get("traccar_user_id")
    if uid is not None:
        user = user_record(uid)
        uid = user["id"]
        profile_id = f"traccar-{uid}"
    else:
        profile_id = raw.get("profile_id") or f"prospect-{uuid.uuid4().hex}"
        if not isinstance(profile_id, str) or not profile_id.startswith("prospect-"):
            raise FinanceError("Invalid customer profile.")
        if raw.get("profile_id"):
            with ledger().transaction() as data:
                if profile_id not in data["profiles"]:
                    raise FinanceError("Customer profile not found.", 404)
    customer.update(profile_id=profile_id, traccar_user_id=uid)
    return customer


@finance_bp.get("/categories")
def categories():
    return jsonify(CATEGORIES)


@finance_bp.get("/customers")
def customers():
    term = request.args.get("term", "").strip()
    with ledger().transaction() as data:
        profiles = [p for p in data["profiles"].values() if term.lower() in
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
    customer = {"name": user["name"], "email": user["email"], "phone": user["phone"] or "", **profile,
                "profile_id": f"traccar-{user_id}", "traccar_user_id": user_id}
    return jsonify(customer=customer, devices=customer_devices(user_id), traccar_phone=user["phone"] or "")


@finance_bp.post("/customers/<int:user_id>/phone")
def sync_phone(user_id):
    user_record(user_id)
    payload = body()
    phone = clean_phone(payload.get("phone", ""))
    cookies = {"JSESSIONID": request.cookies["session_token"]}
    try:
        response = requests.get(TRACCAR_API_URL + f"users/{user_id}", cookies=cookies, timeout=15)
        response.raise_for_status()
        current = response.json()
        if current.get("id") != user_id:
            raise FinanceError("Traccar returned a different customer.", 502)
        if (current.get("phone") or "") != payload.get("expected_phone", ""):
            raise FinanceError("Traccar phone changed. Reload the customer before updating it.", 409)
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
    return jsonify(customer=customer, entries=entries, total_minor=sum(e["total_minor"] for e in entries))


@finance_bp.post("/calculate")
def calculate():
    results = calculate_tasks(body().get("entries"))
    return jsonify(entries=results, total_minor=sum(e["total_minor"] for e in results))


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
        if customer["traccar_user_id"] is not None:
            user_record(customer["traccar_user_id"])
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
    with ledger().transaction(write=True) as data:
        result = invoice_view(record_payment(get_invoice(data, invoice_id), payload, g.finance_actor))
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
        if not entry or entry["device"]:
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
