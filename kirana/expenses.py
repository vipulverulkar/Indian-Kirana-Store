"""Daily expense tracking."""
from datetime import datetime

from flask import Blueprint, jsonify, request, session

from .auth import admin_required, login_required
from .constants import MAX_LEN_EXPENSE_CATEGORY, MAX_LEN_EXPENSE_TITLE
from .db import db_cursor
from .settings import SETTING_DEFAULTS, get_setting
from .utils import get_pagination, page_meta, parse_date_yyyy_mm_dd, to_decimal

expenses_bp = Blueprint("expenses", __name__)


@expenses_bp.route('/api/expenses', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_expenses():
    if request.method == 'GET':
        month = request.args.get('month')  # YYYY-MM
        if month:
            try:
                datetime.strptime(month, "%Y-%m")
            except (ValueError, TypeError):
                return jsonify({"error": "Invalid month, use YYYY-MM"}), 400
        page, per_page = get_pagination()
        try:
            with db_cursor() as cur:
                if month:
                    where = "WHERE to_char(expense_date,'YYYY-MM')=%s"
                    params: tuple = (month,)
                else:
                    where = ""
                    params = ()
                cur.execute(f"SELECT COUNT(*) AS total FROM expenses {where}", params)
                meta = page_meta(cur.fetchone()['total'], page, per_page)
                cur.execute(f"SELECT * FROM expenses {where} ORDER BY expense_date DESC LIMIT %s OFFSET %s",
                            params + (per_page, meta["offset"]))
                rows = cur.fetchall()
                cur.execute("SELECT COALESCE(SUM(amount),0) AS total FROM expenses WHERE expense_date::date = CURRENT_DATE")
                today_total = cur.fetchone()['total']
            return jsonify({"expenses": rows, "today_total": today_total, **meta})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({"error": "Title required"}), 400
    if len(title) > MAX_LEN_EXPENSE_TITLE:
        return jsonify({"error": f"Title too long (max {MAX_LEN_EXPENSE_TITLE})"}), 400
    try:
        amount = to_decimal(data.get('amount'), 'amount')
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    expense_date = data.get('expense_date')
    if expense_date not in (None, ''):
        if parse_date_yyyy_mm_dd(expense_date) is None:
            return jsonify({"error": "Invalid expense_date, use YYYY-MM-DD"}), 400
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO expenses (title, amount, category, notes, user_id, expense_date) VALUES (%s,%s,%s,%s,%s,COALESCE(%s::date, CURRENT_DATE)) RETURNING expense_id",
                (title, amount, (data.get('category') or get_setting("default_expense_category") or SETTING_DEFAULTS["default_expense_category"])[:MAX_LEN_EXPENSE_CATEGORY], data.get('notes'),
                 session['user_id'], expense_date or None))
            eid = cur.fetchone()['expense_id']
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"status": "success", "expense_id": eid}), 201


@expenses_bp.route('/api/expenses/<int:eid>', methods=['DELETE'])
@login_required
@admin_required
def delete_expense(eid):
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM expenses WHERE expense_id=%s", (eid,))
        if cur.rowcount == 0:
            return jsonify({"error": "Not found"}), 404
    from .activity import log_activity
    log_activity("expense.delete", entity="expense", entity_id=eid)
    return jsonify({"status": "success"})
