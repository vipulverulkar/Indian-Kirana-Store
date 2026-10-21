"""Login / session / role guards + auth routes."""
from functools import wraps

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from .constants import ROLE_ADMIN
from .db import db_cursor

auth_bp = Blueprint("auth", __name__)


# --- Auth Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # API callers get JSON, page loads get redirect
            if request.path.startswith('/api/'):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for('auth.login'))
        if session.get('role') != ROLE_ADMIN:
            return jsonify({"error": "Administrator privileges required"}), 403
        return f(*args, **kwargs)
    return decorated_function


# --- Routes ---
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json(silent=True)
        if data is None:
            data = request.form
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''

        if not username or not password:
            return jsonify({"error": "Username and password required"}), 400

        try:
            with db_cursor() as cur:
                cur.execute("SELECT * FROM app_users WHERE username = %s", (username,))
                user = cur.fetchone()
        except Exception as e:
            return jsonify({"error": f"Database error: {e}"}), 500

        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['role'] = user['role']
            return jsonify({"status": "success", "role": user['role']})

        return jsonify({"error": "Invalid credentials"}), 401
    # already logged in? go to dashboard
    if 'user_id' in session:
        return redirect(url_for('core.index'))
    return render_template('login.html')


@auth_bp.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"status": "success"})


@auth_bp.route('/api/me', methods=['GET'])
@login_required
def get_me():
    try:
        with db_cursor() as cur:
            cur.execute("SELECT username, role, full_name FROM app_users WHERE user_id = %s", (session['user_id'],))
            user = cur.fetchone()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    if not user:
        session.clear()
        return jsonify({"error": "User not found"}), 404
    return jsonify(user)
