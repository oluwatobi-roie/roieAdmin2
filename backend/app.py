from flask import Flask, send_from_directory
from flask_cors import CORS
from config import init_db
from routes.devices import device_bp
from routes.devices import add
from routes.devices import search
from routes.devices import device_link
from routes.users import user_onboard_bp
from routes.users import user_onboard
from routes.auth import auth_bp
from routes.auth import login
from routes.auth import logout
from routes.auth import check_session




# Initialize Flask application and register blueprints
def create_app():
    app = Flask(__name__)
    CORS(app, supports_credentials=True, origins=["https://admin.roie.com.ng"])
    
    app.config.update(
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True
)

    init_db(app)


    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/backend/auth')  # Registering the login blueprint
    app.register_blueprint(device_bp, url_prefix='/backend/device') # Registering the device blueprint
    app.register_blueprint(user_onboard_bp, url_prefix='/backend/user') # Registering the user onboarding blueprint
    return app


    # ------------------------
    # Serve Frontend
    # ------------------------
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_nextjs(path):
        file_path = os.path.join(app.static_folder, path)
        if path != "" and os.path.exists(file_path):
            return send_from_directory(app.static_folder, path)
        return send_from_directory(app.static_folder, 'index.html')

    return app

app = create_app()


# Main entry point for the application
# This will create the Flask app and run it
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
