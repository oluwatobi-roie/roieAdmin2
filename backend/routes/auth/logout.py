import os
import requests
from flask import jsonify, make_response, request
from routes.auth import auth_bp
from config import TRACCAR_API_URL
from services.staff_auth import StaffAuthError, require_json_write


@auth_bp.post("/logout")
def logout():
    try:
        require_json_write()
    except StaffAuthError as exc:
        return jsonify(error=str(exc)), exc.status
    token = request.cookies.get("session_token")
    if token:
        try:
            upstream = requests.delete(TRACCAR_API_URL + "session", cookies={"JSESSIONID": token}, timeout=10, allow_redirects=False)
            if upstream.status_code not in (200, 204, 401, 404):
                return jsonify(error="Could not finish signing out. Please retry."), 503
        except requests.RequestException:
            return jsonify(error="Could not finish signing out. Please retry."), 503
    response = make_response(jsonify(message="Logged out"))
    response.delete_cookie("session_token", path="/", samesite="Lax", secure=os.getenv("FLASK_ENV") != "development", httponly=True)
    return response
