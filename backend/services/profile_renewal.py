"""Paid renewal eligibility, calendar dates and a per-account operation lock."""
from contextlib import contextmanager
from datetime import datetime, timezone
import os

from services.finance import FinanceError, invoice_view


def expiry_date(value):
    if not isinstance(value, str) or not value.strip():
        raise FinanceError("This profile has no expiry date. An unlimited profile cannot be extended.", 409)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise FinanceError("The profile expiry date is invalid. Correct it before renewing.", 409) from exc


def canonical_expiry(value):
    return expiry_date(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def next_expiry(value):
    previous = expiry_date(value)
    try:
        renewed = previous.replace(year=previous.year + 1)
    except ValueError:
        if previous.month != 2 or previous.day != 29:
            raise FinanceError("The profile expiry cannot be extended further.", 409)
        renewed = previous.replace(year=previous.year + 1, day=28)
    return renewed.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def eligible_devices(invoice, user_id, owned_devices):
    view = invoice_view(invoice)
    if (invoice["customer"].get("traccar_user_id") != user_id or invoice["status"] != "issued"
            or view["payment_status"] != "paid" or view["paid_minor"] <= 0):
        return []
    owned = {device["id"] for device in owned_devices}
    devices = {}
    renewals = [entry for entry in invoice["entries"] if entry["category"] == "renewal"]
    for entry in renewals:
        device = entry.get("device")
        # Each invoice entry bills one vehicle. Do not silently shrink a paid
        # quantity when a vehicle is missing, unlinked, or billed twice.
        if (entry["total_minor"] <= 0 or not device or device["id"] not in owned
                or device["id"] in devices):
            return []
        devices[device["id"]] = {**device, "entry_ids": [entry["id"]]}
    return list(devices.values())


@contextmanager
def account_lock(directory, user_id):
    # Separate from the ledger lock: unrelated finance operations remain available
    # during remote I/O. Nonblocking OS locks also serialize multiple workers.
    directory = directory / "renewal-locks"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"{user_id}.lock").open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            acquire = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        try:
            acquire()
        except OSError as exc:
            raise FinanceError("An account update is already running for this profile. Reload shortly.", 409) from exc
        try:
            yield
        finally:
            release()
