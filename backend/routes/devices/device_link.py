# routes/device_link.py
from .common import request, jsonify
from flask import current_app, g
from services.device_link import link_device_to_user, UserNotFound, DeviceNotFound, AlreadyLinked, ProtectedUser
from routes.devices import device_bp
from services.login_required import login_required


# Full route => /api/device/link_device
@device_bp.route("/link_device", methods=["POST"])
@login_required
def api_link_device():
    data = request.get_json() or {}
    email      = data.get("email")
    device_id  = data.get("device_id")

    if (not isinstance(email, str) or not email.strip() or len(email) > 254
            or type(device_id) not in (int, str) or not str(device_id).isascii()
            or len(str(device_id)) > 19 or not str(device_id).isdigit() or not 0 < int(device_id) <= 9223372036854775807):
        return jsonify({"error": "email and device_id required"}), 400

    try:
        result = link_device_to_user(email.strip(), int(device_id))
        current_app.logger.info("Staff %s linked device %s to customer %s", g.staff_user["id"], result["device_id"], result["user_id"])
        return jsonify({"message": "Device linked", **result}), 200

    except ProtectedUser as e:
        return jsonify(error=str(e)), 403
    except UserNotFound as e:
        return jsonify({"error": str(e)}), 404
    except DeviceNotFound as e:
        return jsonify({"error": str(e)}), 404
    except AlreadyLinked as e:
        return jsonify({"error": str(e)}), 409
    except ValueError as e:  # multiple users or bad int conversion
        return jsonify({"error": str(e)}), 409
    except Exception as e:
        return jsonify({"error": "Could not link the device. Check the account and retry."}), 502
