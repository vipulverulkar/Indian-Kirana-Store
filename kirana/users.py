"""User management (admin only): list/create/edit/delete login accounts."""
from flask import Blueprint, jsonify, request, session
from werkzeug.security import generate_password_hash

from .auth import admin_required, login_required
from .constants import (
    MAX_LEN_FULL_NAME,
    MAX_LEN_USERNAME,
    MIN_PASSWORD_LEN,
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLES,
)
from .db import UNIQUE_ERRORS, db_cursor

users_bp = Blueprint("users", __name__)


def _validate_payload(data, is_create):
    username = (data.get('username') or '').strip()
    if not username:
        raise ValueError("Username is required")
    if len(username) > MAX_LEN_USERNAME:
        raise ValueError(f"Username too long (max {MAX_LEN_USERNAME})")
    full_name = (data.get('full_name') or '').strip() or None
    if full_name and len(full_name) > MAX_LEN_FULL_NAME:
        raise ValueError(f"Full name too long (max {MAX_LEN_FULL_NAME})")
    role = (data.get('role') or '').strip() or ROLE_STAFF
    if role not in ROLES:
        raise ValueError("Role must be admin or staff")
    password = data.get('password') or ''
    if is_create and not password:
        raise ValueError("Password is required")
    if password and len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LEN} characters")
    return username, full_name, role, password


def _admin_count(cur, exclude_uid=None):
    if exclude_uid:
        cur.execute("SELECT COUNT(*) AS n FROM app_users WHERE role=%s AND user_id <> %s", (ROLE_ADMIN, exclude_uid))
    else:
        cur.execute("SELECT COUNT(*) AS n FROM app_users WHERE role=%s", (ROLE_ADMIN,))
    return cur.fetchone()['n']


@users_bp.route('/api/users', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_users():
    if request.method == 'GET':
        try:
            with db_cursor() as cur:
                cur.execute("SELECT user_id, username, role, full_name, created_at FROM app_users ORDER BY username ASC")
                return jsonify({"users": cur.fetchall()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    data = request.get_json(silent=True) or {}
    try:
        username, full_name, role, password = _validate_payload(data, is_create=True)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO app_users (username, password_hash, role, full_name) VALUES (%s, %s, %s, %s) RETURNING user_id",
                (username, generate_password_hash(password), role, full_name))
            uid = cur.fetchone()['user_id']
    except UNIQUE_ERRORS:
        return jsonify({"error": "Username already taken"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    from .activity import log_activity
    log_activity("user.create", entity="user", entity_id=uid, detail=f"{username} ({role})")
    return jsonify({"status": "success", "user_id": uid}), 201


@users_bp.route('/api/users/<int:uid>', methods=['PUT', 'DELETE'])
@login_required
@admin_required
def user_detail(uid):
    if request.method == 'PUT':
        data = request.get_json(silent=True) or {}
        try:
            username, full_name, role, password = _validate_payload(data, is_create=False)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        if uid == session.get('user_id') and role != ROLE_ADMIN:
            return jsonify({"error": "You cannot demote your own account"}), 400
        try:
            with db_cursor(commit=True) as cur:
                cur.execute("SELECT * FROM app_users WHERE user_id=%s", (uid,))
                row = cur.fetchone()
                if not row:
                    return jsonify({"error": "User not found"}), 404
                if row['role'] == ROLE_ADMIN and role != ROLE_ADMIN and _admin_count(cur, exclude_uid=uid) < 1:
                    return jsonify({"error": "Cannot demote the last admin"}), 400
                if password:
                    cur.execute("UPDATE app_users SET username=%s, full_name=%s, role=%s, password_hash=%s WHERE user_id=%s",
                                (username, full_name, role, generate_password_hash(password), uid))
                else:
                    cur.execute("UPDATE app_users SET username=%s, full_name=%s, role=%s WHERE user_id=%s",
                                (username, full_name, role, uid))
        except UNIQUE_ERRORS:
            return jsonify({"error": "Username already taken"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 400
        from .activity import log_activity
        log_activity("user.update", entity="user", entity_id=uid,
                     detail=f"{username} ({role})" + (" + password reset" if password else ""))
        return jsonify({"status": "success"})
    # DELETE
    if uid == session.get('user_id'):
        return jsonify({"error": "You cannot delete your own account"}), 400
    try:
        with db_cursor(commit=True) as cur:
            cur.execute("SELECT * FROM app_users WHERE user_id=%s", (uid,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "User not found"}), 404
            if row['role'] == ROLE_ADMIN and _admin_count(cur, exclude_uid=uid) < 1:
                return jsonify({"error": "Cannot delete the last admin"}), 400
            cur.execute("DELETE FROM app_users WHERE user_id=%s", (uid,))
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    from .activity import log_activity
    log_activity("user.delete", entity="user", entity_id=uid, detail=row['username'])
    return jsonify({"status": "success"})
