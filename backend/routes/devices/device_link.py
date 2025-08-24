# routes/device_link.py
from .common import request, jsonify
from services.device_link import link_device_to_user, UserNotFound, DeviceNotFound, AlreadyLinked
from routes.devices import device_bp
from services.login_required import login_required


# Full route => /api/device/link_device
@device_bp.route("/link_device", methods=["POST"])
@login_required
def api_link_device():
    data = request.get_json() or {}
    email      = data.get("email")
    device_id  = data.get("device_id")

    if not email or not device_id:
        return jsonify({"error": "email and device_id required"}), 400

    try:
        result = link_device_to_user(email, int(device_id))
        return jsonify({"message": "Device linked", **result}), 200

    except UserNotFound as e:
        return jsonify({"error": str(e)}), 404
    except DeviceNotFound as e:
        return jsonify({"error": str(e)}), 404
    except AlreadyLinked as e:
        return jsonify({"error": str(e)}), 409
    except ValueError as e:  # multiple users or bad int conversion
        return jsonify({"error": str(e)}), 409
    except Exception as e:
        return jsonify({"error": f"Unexpected: {str(e)}"}), 500
