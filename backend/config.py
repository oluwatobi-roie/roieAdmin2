from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os
from pathlib import Path

# Resolve files explicitly so starting from the repo root or backend folder
# loads the same service credential. Shell/container variables still win.
load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

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
    