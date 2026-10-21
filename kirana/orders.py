"""Orders, checkout (billing) and returns."""
from decimal import Decimal, ROUND_HALF_UP

from flask import Blueprint, jsonify, request, session

from .auth import login_required
from .db import db_cursor
from .settings import PAYMENT_MODES, SETTING_DEFAULTS, get_decimal_setting, get_int_setting
from .utils import get_pagination, page_meta, to_decimal

orders_bp = Blueprint("orders", __name__)


@orders_bp.route('/api/orders', methods=['GET'])
@login_required
def get_orders():
    try:
        limit = max(1, min(int(request.args.get('limit', 100)), 500))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid limit"}), 400
    page, per_page = get_pagination()
    per_page = min(per_page, limit)
    try:
        with db_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM orders")
            meta = page_meta(cur.fetchone()['total'], page, per_page)
            cur.execute("""
                SELECT o.*, c.name AS customer_name, c.phone AS customer_phone
                FROM orders o LEFT JOIN customers c ON c.customer_id = o.customer_id
                ORDER BY order_date DESC LIMIT %s OFFSET %s""", (per_page, meta["offset"]))
            orders = cur.fetchall()
        return jsonify({"orders": orders, **meta})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@orders_bp.route('/api/orders/<int:oid>', methods=['GET'])
@login_required
def get_order_detail(oid):
    try:
        with db_cursor() as cur:
            cur.execute("""
                SELECT o.*, c.name AS customer_name, c.phone AS customer_phone, u.full_name AS billed_by
                FROM orders o LEFT JOIN customers c ON c.customer_id=o.customer_id
                LEFT JOIN app_users u ON u.user_id=o.user_id WHERE o.order_id=%s""", (oid,))
            order = cur.fetchone()
            if not order:
                return jsonify({"error": "Order not found"}), 404
            cur.execute("""
                SELECT oi.*, p.name AS product_name FROM order_items oi
                JOIN products p ON p.product_id=oi.product_id WHERE oi.order_id=%s""", (oid,))
            items = cur.fetchall()
            cur.execute("""SELECT r.*, p.name AS product_name FROM returns r
                           JOIN products p ON p.product_id=r.product_id WHERE r.order_id=%s ORDER BY r.created_at DESC""", (oid,))
            returns = cur.fetchall()
        order['items'] = items
        order['returns'] = returns
        return jsonify(order)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@orders_bp.route('/api/checkout', methods=['POST'])
@login_required
def checkout():
    data = request.get_json(silent=True) or {}
    customer_id = data.get('customer_id')
    items = data.get('items')
    payment_mode = data.get('payment_mode', 'Cash')
    discount_pct = data.get('discount_pct', 0) or 0
    try:
        redeem_points = int(float(data.get('redeem_points') or 0))
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Invalid redeem_points"}), 400

    if not isinstance(items, list) or not items:
        return jsonify({"status": "error", "message": "No items in cart"}), 400
    if payment_mode not in PAYMENT_MODES:
        return jsonify({"status": "error", "message": f"Invalid payment mode (use {', '.join(PAYMENT_MODES)})"}), 400
    if customer_id is not None:
        try:
            customer_id = int(customer_id)
        except (ValueError, TypeError):
            return jsonify({"status": "error", "message": "Invalid customer_id"}), 400
    try:
        discount_pct = to_decimal(discount_pct, 'discount_pct')
        max_discount_pct = get_decimal_setting("max_discount_pct")
        if discount_pct < 0 or discount_pct > max_discount_pct:
            raise ValueError(f"Discount must be 0–{max_discount_pct}%")
        if redeem_points < 0:
            raise ValueError("Redeem points cannot be negative")
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    if redeem_points > 0 and not customer_id:
        return jsonify({"status": "error", "message": "Select a customer to redeem loyalty points"}), 400

    try:
        with db_cursor(commit=True) as cur:
            total_amount = Decimal('0.00')
            total_cgst = Decimal('0.00')
            total_sgst = Decimal('0.00')
            total_profit = Decimal('0.00')
            order_items_processed = []

            for item in items:
                try:
                    pid = int(item['product_id'])
                    qty = to_decimal(item.get('quantity', 0), 'quantity')
                except (ValueError, KeyError, TypeError):
                    raise Exception("Each item needs a valid product_id and quantity")
                if qty <= 0:
                    raise Exception("Quantity must be positive")

                cur.execute("SELECT * FROM products WHERE product_id = %s FOR UPDATE", (pid,))
                product = cur.fetchone()

                if not product:
                    raise Exception(f"Product {pid} not found")
                if product['stock_quantity'] < qty:
                    raise Exception(f"Insufficient stock for {product['name']} (have {product['stock_quantity']})")

                unit_price = Decimal(str(product['unit_price']))
                cost_price = Decimal(str(product['cost_price']))
                gst_slab = Decimal(str(product['gst_slab']))

                subtotal = (unit_price * qty).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                cost_total = (cost_price * qty).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                gst_total = (subtotal * (gst_slab / 100)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                cgst = (gst_total / 2).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                sgst = gst_total - cgst
                line_total = subtotal + gst_total

                total_amount += subtotal
                total_cgst += cgst
                total_sgst += sgst
                total_profit += (subtotal - cost_total)

                order_items_processed.append({
                    'product_id': pid, 'quantity': qty, 'unit_price': unit_price, 'cost_price': cost_price,
                    'gst_slab': gst_slab, 'subtotal': subtotal, 'cgst_amount': cgst,
                    'sgst_amount': sgst, 'line_total': line_total
                })

            final_invoice_amount = total_amount + total_cgst + total_sgst

            # --- Discount (on subtotal+tax) ---
            discount_amount = (final_invoice_amount * (discount_pct / 100)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            final_invoice_amount -= discount_amount

            # --- Loyalty redemption: 1 point = ₹1, capped at redeem_cap% of bill ---
            loyalty_redeemed_value = Decimal('0.00')
            loyalty_points_used = 0
            customer_row = None
            redeem_cap_pct = get_decimal_setting("loyalty_redeem_cap_pct")
            earn_per_rs = get_int_setting("loyalty_earn_per_rs") or int(SETTING_DEFAULTS["loyalty_earn_per_rs"])
            if redeem_cap_pct < 0:
                redeem_cap_pct = Decimal('0')
            if redeem_cap_pct > 100:
                redeem_cap_pct = Decimal('100')
            if customer_id:
                cur.execute("SELECT * FROM customers WHERE customer_id = %s FOR UPDATE", (customer_id,))
                customer_row = cur.fetchone()
                if not customer_row:
                    raise Exception("Customer not found")
                if redeem_points > 0:
                    if redeem_points > (customer_row['loyalty_points'] or 0):
                        raise Exception(f"Only {customer_row['loyalty_points']} loyalty points available")
                    max_redeem = int((final_invoice_amount * (redeem_cap_pct / 100)).to_integral_value(rounding=ROUND_HALF_UP))
                    if redeem_points > max_redeem:
                        raise Exception(f"Max {max_redeem} points redeemable on this bill ({redeem_cap_pct}%)")
                    loyalty_points_used = redeem_points
                    loyalty_redeemed_value = Decimal(loyalty_points_used)
                    final_invoice_amount -= loyalty_redeemed_value
                    if final_invoice_amount < 0:
                        final_invoice_amount = Decimal('0.00')

            if payment_mode == 'Udhaar':
                if not customer_id:
                    raise Exception("Customer selection required for Udhaar")
                credit_limit = Decimal(str(customer_row['credit_limit']))
                balance = Decimal(str(customer_row['current_balance']))
                if balance + final_invoice_amount > credit_limit:
                    raise Exception("Credit limit exceeded for this customer")

            cur.execute(
                """INSERT INTO orders (customer_id, user_id, total_amount, total_cgst, total_sgst, total_profit, payment_mode, payment_status, final_invoice_amount, discount_amount, loyalty_redeemed)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING order_id""",
                (customer_id, session['user_id'], total_amount, total_cgst, total_sgst, total_profit,
                 payment_mode, 'Paid' if payment_mode != 'Udhaar' else 'Pending', final_invoice_amount,
                 discount_amount, loyalty_points_used)
            )
            order_id = cur.fetchone()['order_id']

            for item in order_items_processed:
                cur.execute(
                    """INSERT INTO order_items (order_id, product_id, quantity, unit_price, cost_price, gst_slab, subtotal, cgst_amount, sgst_amount, line_total)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (order_id, item['product_id'], item['quantity'], item['unit_price'], item['cost_price'],
                     item['gst_slab'], item['subtotal'], item['cgst_amount'], item['sgst_amount'], item['line_total'])
                )
                cur.execute("UPDATE products SET stock_quantity = stock_quantity - %s WHERE product_id = %s",
                            (item['quantity'], item['product_id']))

            if payment_mode == 'Udhaar':
                cur.execute(
                    "INSERT INTO udhaar_ledger (customer_id, order_id, amount, transaction_type, remarks) VALUES (%s, %s, %s, %s, %s)",
                    (customer_id, order_id, final_invoice_amount, 'Debit', 'Purchase on credit')
                )
                cur.execute("UPDATE customers SET current_balance = current_balance + %s WHERE customer_id = %s",
                            (final_invoice_amount, customer_id))

            if customer_id:
                points = int(final_invoice_amount // earn_per_rs) if earn_per_rs > 0 else 0
                cur.execute("UPDATE customers SET loyalty_points = loyalty_points - %s + %s, lifetime_spend = lifetime_spend + %s WHERE customer_id = %s",
                            (loyalty_points_used, points, final_invoice_amount, customer_id))

        return jsonify({"status": "success", "order_id": order_id, "final_amount": float(final_invoice_amount),
                        "discount": float(discount_amount), "redeemed": loyalty_points_used})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@orders_bp.route('/api/orders/<int:oid>/return', methods=['POST'])
@login_required
def return_order_items(oid):
    """Partial/full return. Body: {items: [{product_id, quantity}], reason}. Restocks + adjusts Udhaar dues."""
    data = request.get_json(silent=True) or {}
    items = data.get('items') or []
    reason = (data.get('reason') or 'Customer return')[:500]
    if not isinstance(items, list) or not items:
        return jsonify({"status": "error", "message": "No return items"}), 400
    try:
        with db_cursor(commit=True) as cur:
            cur.execute("SELECT * FROM orders WHERE order_id=%s FOR UPDATE", (oid,))
            order = cur.fetchone()
            if not order:
                return jsonify({"status": "error", "message": "Order not found"}), 404
            if (order.get('order_status') or 'Completed') == 'Returned':
                return jsonify({"status": "error", "message": "Order already fully returned"}), 400
            # Prorate refunds when the original bill had discounts / loyalty redemption
            gross = (Decimal(str(order.get('total_amount') or 0)) + Decimal(str(order.get('total_cgst') or 0))
                     + Decimal(str(order.get('total_sgst') or 0)))
            paid = Decimal(str(order.get('final_invoice_amount') or 0))
            refund_factor = (paid / gross) if gross > 0 else Decimal('1')
            if refund_factor > 1:
                refund_factor = Decimal('1')
            total_refund = Decimal('0.00')
            for it in items:
                try:
                    pid = int(it['product_id'])
                except (ValueError, TypeError, KeyError):
                    raise Exception("Each return item needs a valid product_id")
                qty = to_decimal(it.get('quantity', 0), 'quantity')
                if qty <= 0:
                    raise Exception("Return quantity must be positive")
                cur.execute("SELECT * FROM order_items WHERE order_id=%s AND product_id=%s", (oid, pid))
                oi = cur.fetchone()
                if not oi:
                    raise Exception(f"Product {pid} not in this order")
                cur.execute("SELECT COALESCE(SUM(quantity),0) AS q FROM returns WHERE order_id=%s AND product_id=%s", (oid, pid))
                already = Decimal(str(cur.fetchone()['q']))
                if already + qty > Decimal(str(oi['quantity'])):
                    raise Exception(f"Cannot return more than purchased ({oi['quantity']})")
                unit_refund = (Decimal(str(oi['line_total'])) / Decimal(str(oi['quantity'])))
                refund = (unit_refund * qty * refund_factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                total_refund += refund
                cur.execute(
                    "INSERT INTO returns (order_id, product_id, quantity, refund_amount, reason, user_id) VALUES (%s,%s,%s,%s,%s,%s)",
                    (oid, pid, qty, refund, reason, session['user_id']))
                cur.execute("UPDATE products SET stock_quantity = stock_quantity + %s WHERE product_id=%s", (qty, pid))
            # Adjust Udhaar dues if original was on credit
            if order.get('payment_mode') == 'Udhaar' and order.get('customer_id'):
                cur.execute("UPDATE customers SET current_balance = GREATEST(0, current_balance - %s) WHERE customer_id=%s",
                            (total_refund, order['customer_id']))
                cur.execute(
                    "INSERT INTO udhaar_ledger (customer_id, order_id, amount, transaction_type, remarks) VALUES (%s,%s,%s,'Credit',%s)",
                    (order['customer_id'], oid, total_refund, f'Return: {reason}'))
            # Mark fully returned?
            cur.execute("SELECT COALESCE(SUM(oi.quantity),0) AS bought FROM order_items oi WHERE oi.order_id=%s", (oid,))
            bought = Decimal(str(cur.fetchone()['bought']))
            cur.execute("SELECT COALESCE(SUM(quantity),0) AS ret FROM returns WHERE order_id=%s", (oid,))
            ret = Decimal(str(cur.fetchone()['ret']))
            if ret >= bought:
                cur.execute("UPDATE orders SET order_status='Returned', payment_status='Refunded' WHERE order_id=%s", (oid,))
            else:
                cur.execute("UPDATE orders SET order_status='Partially Returned' WHERE order_id=%s", (oid,))
        from .activity import log_activity
        log_activity("order.return", entity="order", entity_id=oid,
                     detail=f"Rs.{total_refund} ({reason})")
        return jsonify({"status": "success", "refund_amount": float(total_refund)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@orders_bp.route('/api/returns', methods=['GET'])
@login_required
def list_returns():
    page, per_page = get_pagination()
    try:
        with db_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM returns")
            meta = page_meta(cur.fetchone()['total'], page, per_page)
            cur.execute("""SELECT r.*, p.name AS product_name, o.final_invoice_amount
                           FROM returns r JOIN products p ON p.product_id=r.product_id
                           JOIN orders o ON o.order_id=r.order_id
                           ORDER BY r.created_at DESC LIMIT %s OFFSET %s""",
                        (per_page, meta["offset"]))
            return jsonify({"returns": cur.fetchall(), **meta})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
