import os
from pathlib import Path
import requests
from flask import current_app, request, jsonify, make_response
from routes.auth import auth_bp
from config import TRACCAR_API_URL
from services.staff_auth import StaffAuthError, is_staff, require_json_write
from services.login_rate_limit import LoginRateLimiter


def invalidate_session(response):
    token = response.cookies.get("JSESSIONID")
    if token:
        try:
            requests.delete(TRACCAR_API_URL + "session", cookies={"JSESSIONID": token}, timeout=5, allow_redirects=False)
        except requests.RequestException:
            current_app.logger.warning("Could not close a rejected upstream login session")


def login_limiter():
    directory = current_app.config.get("LOGIN_RATE_DATA_DIR")
    if not directory:
        finance_dir = current_app.config.get("FINANCE_DATA_DIR") or os.getenv("FINANCE_DATA_DIR") or str(Path(__file__).resolve().parents[2] / "data/finance")
        directory = Path(finance_dir) / "security/login-limits"
    return LoginRateLimiter(directory)


@auth_bp.post("/login")
def login():
    try:
        require_json_write()
    except StaffAuthError as exc:
        return jsonify(error=str(exc)), exc.status
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Email and password are required"), 400
    email, password = data.get("email"), data.get("password")
    if (not isinstance(email, str) or not isinstance(password, str) or not email.strip() or not password
            or len(email) > 254 or len(password) > 1024):
        return jsonify(error="Email and password are required"), 400
    try:
        retry_after = login_limiter().consume(request.remote_addr or "unknown", email)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        return jsonify(error="Sign-in is temporarily unavailable."), 503
    if retry_after:
        response = jsonify(error="Too many login attempts. Please try again later.")
        response.headers["Retry-After"] = str(retry_after)
        return response, 429
    try:
        upstream = requests.post(TRACCAR_API_URL + "session", data={"email": email.strip(), "password": password},
                                 timeout=10, allow_redirects=False)
        valid = False
        user = None
        if upstream.status_code == 200:
            try:
                user = upstream.json()
                valid = is_staff(user) and bool(upstream.cookies.get("JSESSIONID"))
            except ValueError:
                pass
        if not valid:
            invalidate_session(upstream)
            return jsonify(error="Invalid credentials"), 401
        response = make_response(jsonify(message="Login successful", user_name=user.get("name")))
        response.set_cookie("session_token", upstream.cookies.get("JSESSIONID"), httponly=True,
                            secure=os.getenv("FLASK_ENV") != "development", samesite="Lax", path="/")
        return response
    except requests.RequestException:
        return jsonify(error="Sign-in is temporarily unavailable."), 503
