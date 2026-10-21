"""Dashboard shell + health check."""
import os

from flask import Blueprint, jsonify, redirect, render_template, session, url_for

from .config import app_version
from .db import db_cursor, db_mode, db_target_info
from .settings import get_all_settings
from .store import uploaded_logo_url

core_bp = Blueprint("core", __name__)


@core_bp.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    s = get_all_settings()
    return render_template('index.html',
                           store_name=s.get("store_name", "KiranaPro"),
                           store_location=s.get("store_location", "Default Location"),
                           store_address=s.get("store_address", ""),
                           store_phone=s.get("store_phone", ""),
                           store_logo=os.getenv("STORE_LOGO", "") or uploaded_logo_url())


@core_bp.route('/api/health', methods=['GET'])
def health():
    try:
        with db_cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            cur.fetchone()
        return jsonify({"status": "ok", "db": "up", "db_mode": db_mode(),
                        "version": app_version(), "target": db_target_info()})
    except Exception as e:
        return jsonify({"status": "degraded", "db": "down", "error": str(e)}), 500
