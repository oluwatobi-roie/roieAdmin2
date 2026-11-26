"""One live staff authorization policy for every portal endpoint."""
import requests
from flask import g, request
from config import TRACCAR_API_URL
from routes.devices.common import admin_user_list


class StaffAuthError(Exception):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


def is_staff(user):
    return (isinstance(user, dict) and type(user.get("id")) is int
            and user["id"] in admin_user_list and not user.get("disabled"))


def verify_staff():
    token = request.cookies.get("session_token")
    if not token or len(token) > 4096:
        raise StaffAuthError("Sign in to access the staff portal.", 401)
    try:
        response = requests.get(TRACCAR_API_URL + "session", cookies={"JSESSIONID": token},
                                timeout=10, allow_redirects=False)
        if response.status_code != 200:
            raise StaffAuthError("Session expired. Sign in again.", 401)
        user = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise StaffAuthError("Unable to verify the staff session.", 503) from exc
    if not is_staff(user):
        raise StaffAuthError("Staff access is required.", 403)
    g.staff_user = {"id": user["id"], "name": user.get("name", "Staff"),
                    "administrator": user.get("administrator") is True}
    return g.staff_user


def require_json_write():
    if request.headers.get("X-Portal-Request") != "1" or not request.is_json:
        raise StaffAuthError("A JSON portal request is required.", 403)
    request.max_content_length = 65536
    if request.content_length and request.content_length > request.max_content_length:
        raise StaffAuthError("Request is too large.", 413)
