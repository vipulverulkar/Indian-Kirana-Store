"""Flask app factory: config, JSON provider, blueprint registration."""
import os
import sys
from datetime import date, datetime
from decimal import Decimal

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask.json.provider import DefaultJSONProvider

if getattr(sys, "frozen", False):
    load_dotenv(os.path.join(os.path.dirname(sys.executable), ".env"))
else:
    load_dotenv()

from .auth import auth_bp
from .config import (APP_LICENSE, APP_NAME, DEVELOPER_CONTACT,
                     DEVELOPER_LOCATION, DEVELOPER_NAME, app_version)
from .activity import activity_bp
from .core import core_bp
from .users import users_bp
from .customers import customers_bp
from .db import BASE_DIR, ensure_local_database
from .expenses import expenses_bp
from .orders import orders_bp
from .products import products_bp
from .reports import reports_bp
from .store import store_bp


# ---------- JSON: handle Decimal / datetime from database rows ----------
class KiranaJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


def create_app():
    # Standalone mode: create + seed the SQLite file on first launch.
    ensure_local_database()
    app = Flask(__name__,
                template_folder=os.path.join(BASE_DIR, "templates"),
                static_folder=os.path.join(BASE_DIR, "static"))
    app.secret_key = os.getenv("SECRET_KEY", "kirana-super-secret-key")
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
    )

    app.json = KiranaJSONProvider(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(activity_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(core_bp)
    app.register_blueprint(store_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(reports_bp)

    @app.context_processor
    def inject_app_meta():
        return {
            "app_name": APP_NAME,
            "app_version": app_version(),
            "app_license": APP_LICENSE,
            "app_developer": DEVELOPER_NAME,
            "app_contact": DEVELOPER_CONTACT,
            "app_location": DEVELOPER_LOCATION,
        }

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({"error": "Not found"}), 404
        return render_template('login.html'), 404

    return app
