from flask import Flask
from flask_cors import CORS
from config import init_db
from routes.devices import device_bp
from routes.devices import add
from routes.devices import search
from routes.devices import device_link
from routes.users import user_onboard_bp
from routes.users import user_onboard




# Initialize Flask application and register blueprints
def create_app():
    app = Flask(__name__)
    CORS(app)
    init_db(app)

    # Register blueprints
    app.register_blueprint(device_bp, url_prefix='/api/device') # Registering the device blueprint
    app.register_blueprint(user_onboard_bp, url_prefix='/api/user') # Registering the user onboarding blueprint
    return app



# Main entry point for the application
# This will create the Flask app and run it
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)