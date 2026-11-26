from flask import Blueprint
device_bp = Blueprint('device_bp', __name__)

@device_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response
