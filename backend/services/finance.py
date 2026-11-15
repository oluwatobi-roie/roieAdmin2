"""Finance calculations and a locked, atomic JSON ledger (no SQL writes)."""

import copy
import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


CATEGORIES = {
    "renewal": {"label": "Renewal", "default_total": "15000.00"},
    "installation": {"label": "New installation", "default_total": "140000.00"},
    "maintenance": {"label": "Maintenance", "default_total": "20000.00"},
    "special": {"label": "Special Service", "default_total": "0.00"},
}
_thread_lock = threading.RLock()


class FinanceError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat()


def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount <= 0 or amount > Decimal("1000000000"):
            raise FinanceError("Amount must be greater than zero and at most NGN 1 billion.")
        if amount != amount.quantize(Decimal("0.01")):
            raise FinanceError("Amounts must have at most two decimal places.")
        return int(amount * 100)
    except (InvalidOperation, TypeError, ValueError) as exc:
        if isinstance(exc, FinanceError):
            raise
        raise FinanceError("Enter a valid amount.") from exc


def portion(total, numerator, denominator=100):
    return int((Decimal(total) * Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP))


def breakdown(category, total, item="", description=""):
    if not isinstance(category, str) or category not in CATEGORIES:
        raise FinanceError("Choose a valid invoice category.")
    amount = money(total)
    if category == "special":
        item = clean_text(item, "Special Service item", 200)
        description = clean_text(description, "Special Service description", 2000)
        return {"category": category, "total_minor": amount, "breakdown": [
            {"label": item, "description": description, "amount_minor": amount}]}
    if category == "renewal":
        gprs = portion(amount, 80)
        parts = [("GPRS fee", gprs), ("Server fee", amount - gprs)]
    elif category == "maintenance":
        service = portion(amount, 60)
        parts = [("Service fee", service), ("Logistics", amount - service)]
    else:
        if amount < 1500000:
            raise FinanceError("New installation must be at least NGN 15,000 to cover GPRS and server fees.")
        gprs = max(1200000, portion(amount, 86, 1000))
        server = max(300000, portion(amount, 24, 1000))
        remainder = amount - gprs - server
        installation = portion(remainder, 14, 89)
        parts = [("GPRS fee", gprs), ("Server fee", server),
                 ("Installation", installation), ("Device", remainder - installation)]
    return {"category": category, "total_minor": amount,
            "breakdown": [{"label": label, "amount_minor": value} for label, value in parts]}


def clean_text(value, label, limit=250, required=True):
    if not isinstance(value, str):
        raise FinanceError(f"{label} must be text.")
    value = " ".join(value.split())
    if (required and not value) or len(value) > limit:
        raise FinanceError(f"{label} is required and must be at most {limit} characters." if required
                           else f"{label} must be at most {limit} characters.")
    return value


def clean_phone(value):
    phone = re.sub(r"[\s().-]", "", clean_text(value, "Phone", 40))
    if not re.fullmatch(r"\+?[0-9]{7,15}", phone):
        raise FinanceError("Enter a phone number containing 7 to 15 digits, optionally starting with +.")
    return phone


def clean_customer(data):
    if not isinstance(data, dict):
        raise FinanceError("Customer details are required.")
    email = clean_text(data.get("email", ""), "Email")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise FinanceError("Enter a valid customer email.")
    phone = clean_phone(data.get("phone", ""))
    address = data.get("address")
    if not isinstance(address, dict):
        raise FinanceError("A billing address is required.")
    address = {key: clean_text(address.get(key, ""), label, 200, required)
               for key, label, required in [("line1", "Street address", True),
                   ("line2", "Address line 2", False), ("city", "City", True),
                   ("state", "State / region", True), ("postal_code", "Postal code", False),
                   ("country", "Country", True)]}
    formatted = "\n".join(filter(None, [address["line1"], address["line2"],
        ", ".join(filter(None, [address["city"], address["state"], address["postal_code"]])), address["country"]]))
    return {"name": clean_text(data.get("name", ""), "Name"), "email": email,
            "phone": phone, "address": address, "formatted_address": formatted}


class Ledger:
    """One host, multiple workers. Lock a stable sidecar, never the replaced file.

    Corrupt/unreadable existing ledgers fail closed; they are never reset.
    All values are stored in integer kobo. A write replaces the complete ledger.
    """
    def __init__(self, directory):
        self.directory = Path(directory)

    @contextmanager
    def transaction(self, write=False):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / "ledger.json"
        with _thread_lock, open(self.directory / "ledger.lock", "a+b") as lock:
            if os.name == "nt":
                import msvcrt
                lock.seek(0, os.SEEK_END)
                if lock.tell() == 0:
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                if path.exists():
                    with path.open(encoding="utf-8") as stream:
                        data = json.load(stream)
                    if (data.get("version") != 1 or not isinstance(data.get("invoices"), dict)
                            or not isinstance(data.get("profiles"), dict)
                            or not isinstance(data.get("sequence"), int)):
                        raise RuntimeError("Unsupported or invalid finance ledger.")
                else:
                    data = {"version": 1, "sequence": 0, "profiles": {}, "invoices": {}}
                yield data
                if write:
                    fd, temporary = tempfile.mkstemp(dir=self.directory, prefix="ledger-", suffix=".tmp")
                    try:
                        with os.fdopen(fd, "w", encoding="utf-8") as stream:
                            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
                            stream.flush()
                            os.fsync(stream.fileno())
                        os.replace(temporary, path)
                        if os.name != "nt":
                            directory_fd = os.open(self.directory, os.O_RDONLY)
                            try:
                                os.fsync(directory_fd)
                            finally:
                                os.close(directory_fd)
                    finally:
                        if os.path.exists(temporary):
                            os.unlink(temporary)
            finally:
                if os.name == "nt":
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def get_invoice(data, invoice_id):
    invoice = data["invoices"].get(invoice_id)
    if not invoice:
        raise FinanceError("Invoice not found.", 404)
    return invoice


def audit(invoice, action, actor, **details):
    invoice["events"].append({"at": now(), "action": action, "actor": actor, **details})
    invoice["updated_at"] = now()
    invoice["revision"] += 1


def check_revision(invoice, body):
    if body.get("revision") != invoice["revision"]:
        raise FinanceError("This invoice changed. Reload it before trying again.", 409)


def invoice_view(invoice):
    result = copy.deepcopy(invoice)
    result.setdefault("subtotal_minor", sum(e["total_minor"] for e in invoice["entries"]))
    result.setdefault("discount_minor", 0)
    result.setdefault("discount", {"type": "none", "value": "0"})
    result["paid_minor"] = sum(p["amount_minor"] for p in invoice["payments"])
    result["balance_minor"] = invoice["total_minor"] - result["paid_minor"]
    result["payment_status"] = ("paid" if result["balance_minor"] == 0 else
                                "partial" if result["paid_minor"] else "unpaid")
    return result


def invoice_totals(entries, raw_discount=None):
    subtotal = sum(entry["total_minor"] for entry in entries)
    raw = raw_discount if raw_discount is not None else {"type": "none", "value": "0"}
    if not isinstance(raw, dict) or raw.get("type") not in ("none", "percent", "amount"):
        raise FinanceError("Choose no discount, a percentage, or an amount.")
    kind = raw["type"]
    try:
        value = Decimal(str(raw.get("value", "0")))
        if not value.is_finite() or value < 0 or value > Decimal("1000000000") or value != value.quantize(Decimal("0.01")):
            raise ValueError()
    except (ValueError, InvalidOperation):
        raise FinanceError("Discount must be a non-negative number with at most two decimal places.")
    if kind == "percent" and value > 100:
        raise FinanceError("Percentage discount cannot exceed 100%.")
    if kind == "none":
        value = Decimal(0)
    discount = portion(subtotal, value) if kind == "percent" else int(value * 100)
    if discount > subtotal:
        raise FinanceError("Discount cannot exceed the invoice subtotal.")
    return {"subtotal_minor": subtotal, "discount_minor": discount,
            "discount": {"type": kind, "value": format(value, "f")}, "total_minor": subtotal - discount}


def task_vehicles(raw, allow_empty=False):
    """Validate a grouped task. Quantity always comes from its vehicle list."""
    if raw.get("category") == "special":
        if raw.get("device_ids") or raw.get("pending_vehicles") or raw.get("pending_count") or raw.get("quantity", 1) != 1:
            raise FinanceError("Special Service is one item with a description and amount.")
        return [], [clean_text(raw.get("item", ""), "Special Service item", 200)]
    ids = raw.get("device_ids", [])
    pending = raw.get("pending_vehicles", [])
    count = raw.get("pending_count", 0)
    if type(count) is not int or not 0 <= count <= 1000:
        raise FinanceError("Installation vehicle count must be a whole number from 0 to 1,000.")
    if raw.get("category") != "installation" and (count or pending):
        raise FinanceError("Renewal and maintenance require selecting account vehicles.")
    if not isinstance(ids, list) or not isinstance(pending, list):
        raise FinanceError("Vehicle selections must be lists.")
    if any(isinstance(i, bool) or not str(i).isdigit() or int(i) < 1 for i in ids):
        raise FinanceError("Invalid vehicle selection.")
    ids = [int(i) for i in ids]
    pending = [clean_text(name, "Pending vehicle / activity", 200) for name in pending]
    if len(set(ids)) != len(ids) or len({name.casefold() for name in pending}) != len(pending):
        raise FinanceError("Each vehicle must appear only once in a task.")
    pending += [f"Installation {raw.get('task_index', 0) + 1} - vehicle {index + 1}" for index in range(count)]
    quantity = len(ids) + len(pending)
    if quantity > 1000 or (not allow_empty and quantity == 0):
        raise FinanceError("Select or name between 1 and 1,000 vehicles / activities per task.")
    if "quantity" in raw and (type(raw["quantity"]) is not int or raw["quantity"] != quantity):
        raise FinanceError("Task quantity must match its vehicle list.")
    return ids, pending


def calculate_tasks(raw_entries):
    if not isinstance(raw_entries, list) or not 1 <= len(raw_entries) <= 1000:
        raise FinanceError("Add between 1 and 1,000 invoice entries.")
    results = []
    quantity_sum = 0
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise FinanceError("Invalid invoice task.")
        unit = breakdown(raw.get("category"), raw.get("total"), raw.get("item", ""), raw.get("description", ""))
        grouped = "device_ids" in raw or "pending_vehicles" in raw or "pending_count" in raw
        if grouped:
            ids, pending = task_vehicles(raw, allow_empty=True)
            quantity = len(ids) + len(pending)
        else:
            quantity = 1
        quantity_sum += quantity
        results.append({**unit, "quantity": quantity, "unit_total_minor": unit["total_minor"],
            "total_minor": unit["total_minor"] * quantity,
            "breakdown": [{**part, "unit_amount_minor": part["amount_minor"],
                           "amount_minor": part["amount_minor"] * quantity} for part in unit["breakdown"]]})
    if quantity_sum > 1000:
        raise FinanceError("An invoice can contain at most 1,000 vehicles / activities.")
    if sum(e["total_minor"] for e in results) > 100000000000:
        raise FinanceError("Invoice total cannot exceed NGN 1 billion.")
    return results


def prepare_entries(raw_entries, devices):
    calculate_tasks(raw_entries)
    expanded = []
    for task_index, raw in enumerate(raw_entries):
        raw = {**raw, "task_index": task_index}
        if raw.get("category") == "special":
            task_vehicles(raw)
            expanded.append({**raw, "device_id": None, "vehicle_label": raw.get("item", "")})
        elif "device_ids" in raw or "pending_vehicles" in raw or "pending_count" in raw:
            ids, pending = task_vehicles(raw)
            expanded.extend({**raw, "device_id": device_id} for device_id in ids)
            expanded.extend({**raw, "device_id": None, "vehicle_label": label} for label in pending)
        else:
            expanded.append(raw)
    entries = []
    device_map = {str(device["id"]): device for device in devices}
    seen = set()
    for raw in expanded:
        entry = breakdown(raw.get("category"), raw.get("total"), raw.get("item", ""), raw.get("description", ""))
        device_id = raw.get("device_id")
        device = device_map.get(str(device_id)) if device_id not in (None, "") else None
        if device_id not in (None, "") and device is None:
            raise FinanceError("Selected device does not belong to this customer.")
        activity = clean_text(raw.get("activity", ""), "Activity / service period", 500, False)
        label = clean_text(raw.get("vehicle_label", ""), "Vehicle / activity name", 200, False)
        if not device and entry["category"] not in ("installation", "special"):
            raise FinanceError("Renewal and maintenance require selecting account vehicles.")
        task_notes = clean_text(raw.get("task_notes", ""), "Task notes", 2000, False)
        if not device and not (label or activity):
            raise FinanceError("Describe the vehicle or activity when no device is selected.")
        identity = (entry["category"], activity.casefold(),
                    f"device:{device['id']}" if device else f"pending:{raw.get('task_index', 0)}:{(label or activity).casefold()}")
        if identity in seen:
            raise FinanceError("A vehicle is repeated for the same task and service period.")
        seen.add(identity)
        entry.update({"id": uuid.uuid4().hex, "device": copy.deepcopy(device),
                      "vehicle_label": label, "activity": activity, "task_notes": task_notes,
                      "link_status": "linked" if device else
                      "pending_installation" if entry["category"] == "installation" else "activity_only"})
        entries.append(entry)
    return entries


def save_draft(data, body, customer, entries, actor, invoice_id=None):
    request_key = clean_text(body.get("request_key", ""), "Request key", 100)
    fingerprint = hashlib.sha256(json.dumps({key: body.get(key) for key in
        ("customer", "entries", "notes", "due_date", "discount")}, sort_keys=True).encode()).hexdigest()
    if not invoice_id:
        existing = next((i for i in data["invoices"].values() if i["request_key"] == request_key), None)
        if existing:
            if existing.get("request_fingerprint") != fingerprint:
                raise FinanceError("This request already saved a different draft. Open it from All invoices.", 409)
            return existing
    due_date = body.get("due_date", "")
    if not isinstance(due_date, str):
        raise FinanceError("Use a valid due date (YYYY-MM-DD).")
    if due_date:
        try:
            date.fromisoformat(due_date)
        except (TypeError, ValueError) as exc:
            raise FinanceError("Use a valid due date (YYYY-MM-DD).") from exc
    notes = clean_text(body.get("notes", ""), "Notes", 2000, False)
    if invoice_id:
        invoice = get_invoice(data, invoice_id)
        check_revision(invoice, body)
        if invoice["status"] != "draft":
            raise FinanceError("Only draft invoices can be edited.", 409)
    else:
        invoice = {"id": uuid.uuid4().hex, "request_key": request_key, "number": None,
                   "request_fingerprint": fingerprint,
                   "created_at": now(), "status": "draft", "currency": "NGN", "revision": 0,
                   "payments": [], "events": []}
    invoice.update({"customer": copy.deepcopy(customer), "entries": entries,
                    **invoice_totals(entries, body.get("discount")), "due_date": due_date,
                    "notes": notes})
    audit(invoice, "draft_saved", actor)
    data["invoices"][invoice["id"]] = invoice
    data["profiles"][customer["profile_id"]] = copy.deepcopy(customer)
    return invoice


def finalize(data, invoice, body, actor):
    if invoice["status"] == "issued":
        return invoice  # Retrying finalization cannot assign a second number.
    check_revision(invoice, body)
    if invoice["status"] != "draft":
        raise FinanceError("Only drafts can be finalized.", 409)
    data["sequence"] += 1
    invoice.update(status="issued", number=f"ROIE-{datetime.now(timezone.utc).year}-{data['sequence']:06d}",
                   issued_at=now())
    audit(invoice, "issued", actor)
    return invoice


def record_payment(invoice, body, actor):
    key = clean_text(body.get("request_key", ""), "Request key", 100)
    proof = body.get("proof")
    if not isinstance(proof, dict) or not re.fullmatch(r"[a-f0-9]{64}", str(proof.get("sha256", ""))):
        raise FinanceError("Attach a payment screenshot before recording payment.")
    previous = next((p for p in invoice["payments"] if p["request_key"] == key), None)
    if previous:
        if (previous["amount_minor"] != money(body.get("amount")) or
                previous["method"] != body.get("method") or previous["paid_on"] != body.get("paid_on") or
                previous["reference"] != clean_text(body.get("reference", ""), "Payment reference", 250) or
                previous.get("proof", {}).get("sha256") != proof["sha256"]):
            raise FinanceError("This request already recorded a different payment. Reload the invoice.", 409)
        return invoice
    check_revision(invoice, body)
    if invoice["status"] != "issued":
        raise FinanceError("Payments can only be recorded against issued invoices.", 409)
    amount = money(body.get("amount"))
    if amount > invoice_view(invoice)["balance_minor"]:
        raise FinanceError("Payment exceeds the outstanding balance.")
    method = body.get("method")
    if method not in ("bank_transfer", "cash", "pos", "other"):
        raise FinanceError("Choose a payment method.")
    try:
        paid_on = date.fromisoformat(body.get("paid_on", ""))
    except (TypeError, ValueError) as exc:
        raise FinanceError("Enter the payment date.") from exc
    if paid_on > datetime.now(timezone.utc).date():
        raise FinanceError("Payment date cannot be in the future.")
    invoice["payments"].append({"id": uuid.uuid4().hex, "request_key": key,
        "amount_minor": amount, "method": method, "paid_on": paid_on.isoformat(),
        "reference": clean_text(body.get("reference", ""), "Payment reference", 250),
        "recorded_at": now(), "recorded_by": actor, "proof": proof,
        "receipt_number": f"{invoice['number']}-R{len(invoice['payments']) + 1:03d}"})
    audit(invoice, "payment_recorded", actor, amount_minor=amount)
    return invoice


def receipt_view(invoice, payment_id=None):
    payments = invoice["payments"]
    if not payments:
        raise FinanceError("No payments have been recorded for this invoice.", 409)
    if payment_id:
        index = next((index for index, payment in enumerate(payments) if payment["id"] == payment_id), None)
        if index is None:
            raise FinanceError("Payment not found.", 404)
        selected = [payments[index]]
        cumulative = payments[:index + 1]
        number = selected[0].get("receipt_number", f"{invoice['number']}-R{index + 1:03d}")
    else:
        selected = cumulative = payments
        number = f"{invoice['number']}-ALL-{len(payments):03d}"
    return {"number": number, "invoice_number": invoice["number"], "invoice_id": invoice["id"],
        "customer": copy.deepcopy(invoice["customer"]), "currency": "NGN",
        "as_of": selected[-1]["recorded_at"], "kind": "payment" if payment_id else "combined",
        "payments": [{key: payment.get(key) for key in ("id", "receipt_number", "amount_minor", "method", "paid_on", "reference")} for payment in selected],
        "invoice_total_minor": invoice["total_minor"],
        "received_minor": sum(payment["amount_minor"] for payment in selected),
        "cumulative_paid_minor": sum(payment["amount_minor"] for payment in cumulative),
        "balance_minor": invoice["total_minor"] - sum(payment["amount_minor"] for payment in cumulative)}
