# services/device_link.py
from routes.devices.common import db, requests, text
from config import TRACCAR_API_URL, HEADERS_JSON
from routes.devices.common import exclude_users_list


class UserNotFound(Exception):    pass
class DeviceNotFound(Exception):  pass
class AlreadyLinked(Exception):   pass
class ProtectedUser(Exception):   pass


# # ────────────────────────── helpers ────────────────────────── #
# Find user ID by email, check if device exists in database
def _find_user_id_by_email(email: str) -> int:
    """
    Return user ID by email from the tc_users table.
    Case‑insensitive exact match.
    """
    sql = text("""
        SELECT id FROM tc_users
        WHERE LOWER(email) = LOWER(:email)
    """)
    rows = db.session.execute(sql, {"email": email}).fetchall()

    if not rows:
        raise UserNotFound("Email not found")

    if len(rows) > 1:
        raise ValueError("Multiple users with that email")

    return rows[0].id


# check if the device exit
def _device_exists(device_id: int) -> None:
    """
    Verify the device exists in tc_devices using direct DB access.
    Raises DeviceNotFound if no row is returned.
    """
    sql = text("SELECT 1 FROM tc_devices WHERE id = :did LIMIT 1")
    row = db.session.execute(sql, {"did": device_id}).fetchone()
    if row is None:
        raise DeviceNotFound("Device not found")



def link_device_to_user(email: str, device_id: int) -> dict:
    # Attempt to create permission
    user_id = _find_user_id_by_email(email)
    if user_id in exclude_users_list:
        raise ProtectedUser("Select a customer account, not an administrator account.")
    administrator = db.session.execute(text("SELECT administrator FROM tc_users WHERE id = :uid"), {"uid": user_id}).scalar()
    if administrator:
        raise ProtectedUser("Select a customer account, not an administrator account.")
    _device_exists(device_id)
    perm_payload = {"userId": user_id, "deviceId": device_id}
    resp = requests.post(TRACCAR_API_URL + "permissions", json=perm_payload, headers=HEADERS_JSON, timeout=15, allow_redirects=False)

    if resp.status_code == 400 and "duplicate" in resp.text.lower():
        raise AlreadyLinked("Device already linked to this user")
    resp.raise_for_status()

    return {"user_id": user_id, "device_id": device_id}
