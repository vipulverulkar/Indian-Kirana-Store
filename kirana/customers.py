"""Customers, Udhaar ledger and repayments (Jama)."""
from decimal import Decimal

from flask import Blueprint, jsonify, request, session

from .auth import login_required
from .constants import (
    DEFAULT_REPAYMENT_REMARK,
    MAX_LEN_PHONE_MAX,
    MAX_LEN_PHONE_MIN,
    ROLE_ADMIN,
    TXN_CREDIT,
)
from .db import UNIQUE_ERRORS, db_cursor
from .settings import get_decimal_setting
from .utils import fmt_money, get_pagination, page_meta, to_decimal

customers_bp = Blueprint("customers", __name__)


@customers_bp.route('/api/customers', methods=['GET', 'POST'])
@login_required
def manage_customers():
    if request.method == 'GET':
        search = (request.args.get('search') or '').strip()
        page, per_page = get_pagination()
        try:
            with db_cursor() as cur:
                if search:
                    where = "WHERE name ILIKE %s OR phone ILIKE %s"
                    params: list = [f"%{search}%", f"%{search}%"]
                else:
                    where = ""
                    params = []
                cur.execute(f"SELECT COUNT(*) AS total FROM customers {where}", tuple(params))
                meta = page_meta(cur.fetchone()['total'], page, per_page)
                order = "ORDER BY name ASC" if search else "ORDER BY current_balance DESC"
                cur.execute(f"SELECT * FROM customers {where} {order} LIMIT %s OFFSET %s",
                            tuple(params) + (per_page, meta["offset"]))
                return jsonify({"customers": cur.fetchall(), **meta})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip().replace(' ', '')
    if not name or not phone:
        return jsonify({"error": "Name and phone are required"}), 400
    if len(phone) < MAX_LEN_PHONE_MIN or len(phone) > MAX_LEN_PHONE_MAX:
        return jsonify({"error": f"Phone must be {MAX_LEN_PHONE_MIN}–{MAX_LEN_PHONE_MAX} characters"}), 400
    try:
        default_limit = get_decimal_setting("default_credit_limit")
        credit_limit = to_decimal(data.get('credit_limit', default_limit), 'credit_limit')
        if credit_limit < 0:
            raise ValueError("credit_limit cannot be negative")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO customers (name, phone, credit_limit) VALUES (%s, %s, %s) RETURNING customer_id",
                (name, phone, credit_limit))
            cid = cur.fetchone()['customer_id']
        return jsonify({"status": "success", "customer_id": cid}), 201
    except UNIQUE_ERRORS:
        return jsonify({"error": "Phone number already registered"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@customers_bp.route('/api/customers/<int:cid>', methods=['PUT', 'DELETE'])
@login_required
def customer_detail(cid):
    """Edit name/phone (any staff) or credit limit (admin only); delete (admin only).
    Delete is blocked while dues are outstanding or orders reference the customer."""
    if request.method == 'PUT':
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        phone = (data.get('phone') or '').strip().replace(' ', '')
        if not name or not phone:
            return jsonify({"error": "Name and phone are required"}), 400
        if len(phone) < MAX_LEN_PHONE_MIN or len(phone) > MAX_LEN_PHONE_MAX:
            return jsonify({"error": f"Phone must be {MAX_LEN_PHONE_MIN}–{MAX_LEN_PHONE_MAX} characters"}), 400
        try:
            with db_cursor(commit=True) as cur:
                cur.execute("SELECT * FROM customers WHERE customer_id=%s", (cid,))
                row = cur.fetchone()
                if not row:
                    return jsonify({"error": "Customer not found"}), 404
                limit = Decimal(str(row['credit_limit']))
                if data.get('credit_limit') not in (None, ''):
                    if session.get('role') != ROLE_ADMIN:
                        return jsonify({"error": "Only admin can change credit limit"}), 403
                    try:
                        limit = to_decimal(data.get('credit_limit'), 'credit_limit')
                    except ValueError as e:
                        return jsonify({"error": str(e)}), 400
                    if limit < 0:
                        return jsonify({"error": "credit_limit cannot be negative"}), 400
                    if limit < Decimal(str(row['current_balance'])):
                        return jsonify({"error": f"Limit cannot be below outstanding dues ({fmt_money(row['current_balance'])})"}), 400
                cur.execute("UPDATE customers SET name=%s, phone=%s, credit_limit=%s WHERE customer_id=%s",
                            (name, phone, limit, cid))
                cur.execute("SELECT * FROM customers WHERE customer_id=%s", (cid,))
                updated = cur.fetchone()
            return jsonify({"status": "success", "customer": updated})
        except UNIQUE_ERRORS:
            return jsonify({"error": "Phone number already registered"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    # DELETE - admin only
    if session.get('role') != ROLE_ADMIN:
        return jsonify({"error": "Admin access required"}), 403
    try:
        with db_cursor(commit=True) as cur:
            cur.execute("SELECT * FROM customers WHERE customer_id=%s", (cid,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Customer not found"}), 404
            if Decimal(str(row['current_balance'])) != 0:
                return jsonify({"error": f"Cannot delete: {fmt_money(row['current_balance'])} dues outstanding. Settle first."}), 400
            cur.execute("SELECT COUNT(*) AS n FROM orders WHERE customer_id=%s", (cid,))
            if cur.fetchone()['n'] > 0:
                return jsonify({"error": "Cannot delete: customer has order history. Keep the record."}), 400
            cur.execute("DELETE FROM udhaar_ledger WHERE customer_id=%s", (cid,))
            cur.execute("DELETE FROM customers WHERE customer_id=%s", (cid,))
        from .activity import log_activity
        log_activity("customer.delete", entity="customer", entity_id=cid,
                     detail=row['name'])
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@customers_bp.route('/api/customers/<phone>', methods=['GET'])
@login_required
def get_customer(phone):
    try:
        with db_cursor() as cur:
            cur.execute("SELECT * FROM customers WHERE phone = %s", (phone,))
            customer = cur.fetchone()
        if customer:
            return jsonify(customer)
        return jsonify({"error": "Customer not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@customers_bp.route('/api/customers/<int:cid>/ledger', methods=['GET'])
@login_required
def customer_ledger(cid):
    try:
        with db_cursor() as cur:
            cur.execute("SELECT * FROM customers WHERE customer_id=%s", (cid,))
            customer = cur.fetchone()
            if not customer:
                return jsonify({"error": "Customer not found"}), 404
            page, per_page = get_pagination()
            cur.execute("SELECT COUNT(*) AS total FROM udhaar_ledger WHERE customer_id=%s", (cid,))
            meta = page_meta(cur.fetchone()['total'], page, per_page)
            cur.execute(
                "SELECT * FROM udhaar_ledger WHERE customer_id=%s ORDER BY transaction_date DESC LIMIT %s OFFSET %s",
                (cid, per_page, meta["offset"]))
            ledger = cur.fetchall()
        return jsonify({"customer": customer, "ledger": ledger, **meta})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@customers_bp.route('/api/repayment', methods=['POST'])
@login_required
def repayment():
    data = request.get_json(silent=True) or {}
    try:
        customer_id = data.get('customer_id')
        if customer_id is not None:
            customer_id = int(customer_id)
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Invalid customer_id"}), 400
    if not customer_id:
        return jsonify({"status": "error", "message": "customer_id required"}), 400
    try:
        amount = to_decimal(data.get('amount'), 'amount')
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    if amount <= 0:
        return jsonify({"status": "error", "message": "Amount must be positive"}), 400

    try:
        with db_cursor(commit=True) as cur:
            cur.execute("SELECT current_balance FROM customers WHERE customer_id = %s FOR UPDATE", (customer_id,))
            customer = cur.fetchone()
            if not customer:
                raise Exception("Customer not found")
            if amount > customer['current_balance']:
                raise Exception(f"Amount exceeds dues (₹{customer['current_balance']})")
            cur.execute(
                "INSERT INTO udhaar_ledger (customer_id, amount, transaction_type, remarks) VALUES (%s, %s, %s, %s)",
                (customer_id, amount, TXN_CREDIT, data.get('remarks') or DEFAULT_REPAYMENT_REMARK)
            )
            cur.execute("UPDATE customers SET current_balance = current_balance - %s WHERE customer_id = %s",
                        (amount, customer_id))
        from .activity import log_activity
        log_activity("udhaar.repayment", entity="customer", entity_id=customer_id,
                     detail=f"Rs.{amount}")
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
