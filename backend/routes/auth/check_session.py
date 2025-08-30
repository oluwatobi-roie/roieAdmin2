from flask import Blueprint, request, jsonify
from routes.auth import auth_bp
from config import TRACCAR_API_URL
import requests
import os

# Full route: /api/auth/check-session
@auth_bp.route('/check-session', methods=['GET'])
def check_session():
    # Get our stored cookie
    session_token = request.cookies.get("session_token")

    if not session_token:
        return jsonify({"authenticated": False}), 401

    # Forward it to Traccar as JSESSIONID
    traccar_resp = requests.get(
        TRACCAR_API_URL + "session",
        cookies={"JSESSIONID": session_token}
    )

    if traccar_resp.status_code == 200:
        return jsonify({"authenticated": True, "user": traccar_resp.json()})
    return jsonify({"authenticated": False}), 401
