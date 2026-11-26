from functools import wraps
from flask import request, jsonify
from services.staff_auth import StaffAuthError, require_json_write, verify_staff


def login_required(handler):
    @wraps(handler)
    def decorated(*args, **kwargs):
        try:
            verify_staff()
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                require_json_write()
                if not isinstance(request.get_json(silent=True), dict):
                    return jsonify(error="A JSON object is required."), 400
        except StaffAuthError as exc:
            return jsonify(error=str(exc)), exc.status
        response = handler(*args, **kwargs)
        return response
    return decorated
