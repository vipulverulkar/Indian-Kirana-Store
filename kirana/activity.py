"""Staff activity log: who changed what, when.

Best-effort audit trail for admin-visible actions (settings, products,
categories, customers, expenses, logo). Logging never breaks the primary
action — failures are swallowed.
"""
from flask import Blueprint, jsonify, request, session

from .auth import admin_required, login_required
from .constants import (
    MAX_LEN_ACTIVITY_ACTION,
    MAX_LEN_ACTIVITY_DETAIL,
    MAX_LEN_ACTIVITY_ENTITY,
    MAX_LEN_ACTIVITY_ENTITY_ID,
)
from .db import active_backend, db_cursor
from .utils import get_pagination, page_meta

activity_bp = Blueprint("activity", __name__)

ACTIVITY_DDL = """
CREATE TABLE IF NOT EXISTS activity_log (
    log_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES app_users(user_id),
    username VARCHAR(50),
    role VARCHAR(20),
    action VARCHAR(100) NOT NULL,
    entity VARCHAR(100),
    entity_id VARCHAR(100),
    detail TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_activity_date ON activity_log(created_at DESC);
"""

ACTIVITY_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS activity_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES app_users(user_id),
    username TEXT,
    role TEXT,
    action TEXT NOT NULL,
    entity TEXT,
    entity_id TEXT,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_activity_date ON activity_log(created_at DESC);
"""


def ensure_activity_table():
    ddl = ACTIVITY_DDL_SQLITE if active_backend() == "sqlite" else ACTIVITY_DDL
    with db_cursor(commit=True) as cur:
        cur.execute(ddl)


def log_activity(action, entity=None, entity_id=None, detail=None):
    """Record one audit row. Never raises."""
    try:
        ensure_activity_table()
        with db_cursor(commit=True) as cur:
            cur.execute(
                """INSERT INTO activity_log (user_id, username, role, action, entity, entity_id, detail)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (session.get('user_id'), session.get('username'),
                 session.get('role'), action[:MAX_LEN_ACTIVITY_ACTION],
                 (entity or '')[:MAX_LEN_ACTIVITY_ENTITY] if entity else None,
                 str(entity_id)[:MAX_LEN_ACTIVITY_ENTITY_ID] if entity_id is not None else None,
                 (detail or '')[:MAX_LEN_ACTIVITY_DETAIL] if detail else None),
            )
    except Exception:
        pass


@activity_bp.route('/api/activity', methods=['GET'])
@login_required
@admin_required
def list_activity():
    action = (request.args.get('action') or '').strip()
    search = (request.args.get('search') or '').strip()
    page, per_page = get_pagination()
    try:
        ensure_activity_table()
        where = "WHERE 1=1"
        params: list = []
        if action:
            where += " AND action = %s"
            params.append(action)
        if search:
            where += " AND (username ILIKE %s OR detail ILIKE %s OR entity ILIKE %s)"
            params += [f"%{search}%"] * 3
        with db_cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS total FROM activity_log {where}", tuple(params))
            meta = page_meta(cur.fetchone()['total'], page, per_page)
            cur.execute(
                f"""SELECT * FROM activity_log {where}
                    ORDER BY created_at DESC LIMIT %s OFFSET %s""",
                tuple(params) + (per_page, meta["offset"]))
            rows = cur.fetchall()
            cur.execute("SELECT DISTINCT action FROM activity_log ORDER BY action")
            actions = [r['action'] for r in cur.fetchall()]
        return jsonify({"activity": rows, "actions": actions, **meta})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
