from flask import Blueprint
auth_bp = Blueprint("auth_bp", __name__)

@auth_bp.after_request
def private_auth_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response
