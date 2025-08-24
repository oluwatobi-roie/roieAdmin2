import os
import requests
from routes.auth import auth_bp
from flask import Flask, request, jsonify, make_response
from dotenv import load_dotenv
from routes.devices.common import admin_user_list

load_dotenv()

TRACCAR_API_URL = os.getenv("TRACCAR_API_URL")

# Full api path: /api/auth/login
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    # Authenticate with Traccar API
    try:

            # Send credentials to Traccar as form-data
        response = requests.post(
            f"{TRACCAR_API_URL}/session",
            data={"email": email, "password": password}
        )

        if response.status_code == 200:
            print ("Login successful, setting cookie")
            user_data = response.json()

            if user_data.get("id") not in admin_user_list:
                return jsonify({"error": "Unauthorized - not an admin user"}), 401
            # ✅ Traccar returned valid session
            resp = make_response(jsonify({"message": "Login successful",
                                          "user_name": user_data.get("name")}))
            
            # Store Traccar session cookie in our own HttpOnly cookie
            resp.set_cookie(
                "session_token",
                response.cookies.get("JSESSIONID"),  # Traccar session ID
                httponly=True,
                secure=True,
                samesite="Strict"
            )
            return resp
        else:
            return jsonify({"error": "Invalid credentials"}), 401

    except Exception as e:
        return jsonify({"error": str(e)}), 500


