from flask import Blueprint
user_onboard_bp = Blueprint("user_onboard", __name__)

@user_onboard_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response
