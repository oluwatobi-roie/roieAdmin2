
# backend/routes/user_onboard.py
from flask import Blueprint, request, jsonify
from services.user_onboard import onboard_user
from routes.users import user_onboard_bp

# Full api path: /api/user/onboard_user
@user_onboard_bp.route("/onboard_user", methods=["POST"])
def api_onboard_user():
    result = onboard_user(request.get_json())

    # normalise (dict, status)
    if isinstance(result, tuple):
        data, status = result
    else:                     # just dict returned
        data, status = result, 201

    return jsonify(data), status
