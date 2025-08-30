from functools import wraps
from flask import request, jsonify

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        session_token = request.cookies.get("session_token")
        if not session_token:
            return jsonify({"error": "Unauthorized"}), 401
        # Optional: validate session with Traccar API here
        return f(*args, **kwargs)
    return decorated
