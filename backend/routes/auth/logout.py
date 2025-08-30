from routes.auth import auth_bp
from flask import jsonify, make_response

# Full api path: /api/auth/logout
@auth_bp.route("/logout", methods=["POST"])
def logout():
    resp = make_response(jsonify({"message": "Logged out"}))
    resp.delete_cookie("session_token")
    return resp
