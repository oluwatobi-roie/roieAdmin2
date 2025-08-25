from flask import Blueprint, request, jsonify
from routes.auth import auth_bp
from config import TRACCAR_API_URL
import requests
import os


@auth_bp.route('/check-session', methods=['GET'])
def check_session():
    # Forward cookie to Traccar to validate session
    cookies = request.cookies
    traccar_resp = requests.get(
        TRACCAR_API_URL + "session",
        cookies=cookies
    )
    if traccar_resp.status_code == 200:
        return jsonify({"authenticated": True, "user": traccar_resp.json()})
    return jsonify({"authenticated": False}), 401