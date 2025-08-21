from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os

load_dotenv()

db = SQLAlchemy()

TRACCAR_API_URL  = os.getenv("TRACCAR_API_URL").rstrip("/") + "/"
TRACCAR_API_KEY  = os.getenv("TRACCAR_ADMIN_KEY")          # Bearer token
HEADERS_JSON     = {
    "Authorization": f"Bearer {TRACCAR_API_KEY}",
    "Content-Type":  "application/json"
}
HEADERS_FORM     = {
    "Authorization": f"Bearer {TRACCAR_API_KEY}",
    "Content-Type":  "application/x-www-form-urlencoded"
}

def init_db(app: Flask):
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return db
    