from flask import jsonify
from routes.auth import auth_bp
from services.staff_auth import StaffAuthError, verify_staff


@auth_bp.get("/check-session")
def check_session():
    try:
        user = verify_staff()
    except StaffAuthError as exc:
        return jsonify(authenticated=False), 503 if exc.status == 503 else 401
    return jsonify(authenticated=True, staff=True, user={"id": user["id"], "name": user["name"]})
