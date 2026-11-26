
# backend/routes/user_onboard.py
from flask import Blueprint, request, jsonify, current_app, g
from services.user_onboard import onboard_user
from routes.users import user_onboard_bp
from services.login_required import login_required

# Full api path: /api/user/onboard_user
@user_onboard_bp.route("/onboard_user", methods=["POST"])
@login_required
def api_onboard_user():
    result = onboard_user(request.get_json())

    # normalise (dict, status)
    if isinstance(result, tuple):
        data, status = result
    else:                     # just dict returned
        data, status = result, 201

    if status == 201:
        current_app.logger.info("Staff %s onboarded customer %s", g.staff_user["id"], data.get("user_id"))
    return jsonify(data), status
