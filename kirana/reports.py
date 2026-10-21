"""Financial reports: Z-report (day/month/year), dashboard stats, dues aging."""
from datetime import date, datetime

from flask import Blueprint, jsonify, request, session

from .auth import admin_required, login_required
from .constants import MAX_REPORT_YEAR, MIN_REPORT_YEAR, ROLE_ADMIN
from .db import db_cursor
from .utils import get_pagination, page_meta, parse_date_yyyy_mm_dd

reports_bp = Blueprint("reports", __name__)


@reports_bp.route('/api/reports/z-report', methods=['GET'])
@login_required
@admin_required
def get_z_report():
    """Financial report for a day, month, or year.
    Query: ?period=day&date=YYYY-MM-DD (default today)
            ?period=month&month=YYYY-MM
            ?period=year&year=YYYY
    Returns summary + payment breakdown + per-hour/day/month series.
    Profit & expense figures are admin-only (stripped for staff)."""
    import calendar
    period = (request.args.get('period') or 'day').strip().lower()
    if period not in ('day', 'month', 'year'):
        return jsonify({"error": "Invalid period, use day/month/year"}), 400
    day = request.args.get('date')
    month = request.args.get('month')
    year = request.args.get('year')

    if period == 'day':
        label_date = parse_date_yyyy_mm_dd(day) if day else date.today()
        if label_date is None:
            return jsonify({"error": "Invalid date, use YYYY-MM-DD"}), 400
        iso = label_date.isoformat()
        date_filter, exp_filter, params = "order_date::date = %s::date", "expense_date = %s::date", (iso,)
        label = label_date.strftime('%d %b %Y')
        series_keys = [(h, f"{h:02d}:00") for h in range(24)]
    elif period == 'month':
        if not month:
            today = date.today()
            month = f"{today.year}-{today.month:02d}"
        try:
            m_date = datetime.strptime(month, "%Y-%m").date()
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid month, use YYYY-MM"}), 400
        date_filter, exp_filter = "to_char(order_date,'YYYY-MM') = %s", "to_char(expense_date,'YYYY-MM') = %s"
        params = (month,)
        label = m_date.strftime('%B %Y')
        ndays = calendar.monthrange(m_date.year, m_date.month)[1]
        series_keys = [(d, f"{m_date.year}-{m_date.month:02d}-{d:02d}") for d in range(1, ndays + 1)]
    else:
        if not year:
            year = str(date.today().year)
        if not (year.isdigit() and MIN_REPORT_YEAR <= int(year) <= MAX_REPORT_YEAR):
            return jsonify({"error": f"Invalid year, use YYYY ({MIN_REPORT_YEAR}-{MAX_REPORT_YEAR})"}), 400
        date_filter, exp_filter = "EXTRACT(YEAR FROM order_date)::int = %s::int", "EXTRACT(YEAR FROM expense_date)::int = %s::int"
        params = (year,)
        label = year
        month_names = [datetime(2000, m, 1).strftime('%b') for m in range(1, 13)]
        series_keys = [(m, month_names[m - 1]) for m in range(1, 13)]

    is_admin = session.get('role') == ROLE_ADMIN
    try:
        with db_cursor() as cur:
            cur.execute(f"""
                SELECT COALESCE(SUM(final_invoice_amount),0) as total_revenue,
                       COALESCE(SUM(total_cgst),0) as total_cgst,
                       COALESCE(SUM(total_sgst),0) as total_sgst,
                       COALESCE(SUM(total_profit),0) as total_profit,
                       COALESCE(SUM(discount_amount),0) as total_discount,
                       COUNT(order_id) as order_count
                FROM orders WHERE {date_filter}""", params)
            summary = cur.fetchone()
            cur.execute(f"""
                SELECT payment_mode, COUNT(*) as count, SUM(final_invoice_amount) as amount
                FROM orders WHERE {date_filter} GROUP BY payment_mode""", params)
            breakdown = cur.fetchall()
            # --- series (zero-filled) ---
            if period == 'day':
                cur.execute(f"""
                    SELECT EXTRACT(HOUR FROM order_date)::int AS k,
                           COALESCE(SUM(final_invoice_amount),0) AS revenue,
                           COUNT(*) AS orders, COALESCE(SUM(total_profit),0) AS profit
                    FROM orders WHERE {date_filter} GROUP BY k""", params)
            elif period == 'month':
                cur.execute(f"""
                    SELECT EXTRACT(DAY FROM order_date)::int AS k,
                           COALESCE(SUM(final_invoice_amount),0) AS revenue,
                           COUNT(*) AS orders, COALESCE(SUM(total_profit),0) AS profit
                    FROM orders WHERE {date_filter} GROUP BY k""", params)
            else:
                cur.execute(f"""
                    SELECT EXTRACT(MONTH FROM order_date)::int AS k,
                           COALESCE(SUM(final_invoice_amount),0) AS revenue,
                           COUNT(*) AS orders, COALESCE(SUM(total_profit),0) AS profit
                    FROM orders WHERE {date_filter} GROUP BY k""", params)
            by_key = {int(r['k']): r for r in cur.fetchall()}
            series = [{"key": k, "label": lbl,
                       "revenue": float(by_key.get(k, {}).get('revenue') or 0),
                       "orders": int(by_key.get(k, {}).get('orders') or 0),
                       **({"profit": float(by_key.get(k, {}).get('profit') or 0)} if is_admin else {})}
                      for k, lbl in series_keys]
            if is_admin:
                cur.execute(f"SELECT COALESCE(SUM(amount),0) AS total FROM expenses WHERE {exp_filter}", params)
                expenses_total = cur.fetchone()['total']
                summary['expenses_total'] = expenses_total
                try:
                    summary['net_profit'] = float(summary['total_profit'] or 0) - float(expenses_total or 0)
                except Exception:
                    summary['net_profit'] = summary['total_profit']
            else:
                # Staff-safe: hide profit & expense figures
                summary.pop('total_profit', None)
                summary.pop('expenses_total', None)
                summary.pop('net_profit', None)
        return jsonify({"summary": summary, "breakdown": breakdown, "series": series,
                        "period": period, "label": label, "role": session.get('role')})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@reports_bp.route('/api/dashboard/stats', methods=['GET'])
@login_required
@admin_required
def dashboard_stats():
    try:
        with db_cursor() as cur:
            cur.execute("""
                SELECT order_date::date AS day, SUM(final_invoice_amount) AS revenue, COUNT(*) AS orders,
                       SUM(total_profit) AS profit
                FROM orders WHERE order_date >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY day ORDER BY day ASC""")
            weekly = cur.fetchall()
            cur.execute("""
                SELECT p.name, SUM(oi.quantity) AS qty, SUM(oi.line_total) AS revenue
                FROM order_items oi JOIN products p ON p.product_id=oi.product_id
                JOIN orders o ON o.order_id=oi.order_id
                WHERE o.order_date >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY p.name ORDER BY qty DESC LIMIT 5""")
            top_products = cur.fetchall()
            cur.execute("SELECT COUNT(*) AS n FROM products WHERE stock_quantity <= min_threshold")
            low_count = cur.fetchone()['n']
            cur.execute("SELECT COALESCE(SUM(current_balance),0) AS total FROM customers")
            udhaar_total = cur.fetchone()['total']
            cur.execute("SELECT COALESCE(SUM(stock_quantity * cost_price),0) AS v FROM products")
            stock_value = cur.fetchone()['v']
            cur.execute("SELECT COALESCE(SUM(amount),0) AS t FROM expenses WHERE expense_date::date = CURRENT_DATE")
            today_expenses = cur.fetchone()['t']
            cur.execute("SELECT COALESCE(SUM(final_invoice_amount),0) AS r, COALESCE(SUM(total_profit),0) AS p, COUNT(*) AS c FROM orders WHERE order_date::date = CURRENT_DATE")
            today = cur.fetchone()
        is_admin = session.get('role') == ROLE_ADMIN
        if not is_admin:
            # Staff-safe: hide profit & expense/cost figures (mirrors z-report)
            for w in weekly:
                w.pop('profit', None)
            return jsonify({"weekly": weekly, "top_products": top_products,
                            "low_stock_count": low_count, "udhaar_total": udhaar_total,
                            "today_revenue": today['r'], "today_orders": today['c']})
        return jsonify({"weekly": weekly, "top_products": top_products,
                        "low_stock_count": low_count, "udhaar_total": udhaar_total,
                        "stock_value": stock_value, "today_expenses": today_expenses,
                        "today_revenue": today['r'], "today_profit": today['p'], "today_orders": today['c']})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@reports_bp.route('/api/reports/dues', methods=['GET'])
@login_required
@admin_required
def dues_report():
    page, per_page = get_pagination()
    try:
        with db_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM customers WHERE current_balance > 0")
            meta = page_meta(cur.fetchone()['total'], page, per_page)
            cur.execute("""SELECT customer_id, name, phone, current_balance, credit_limit, loyalty_points,
                                  CASE WHEN credit_limit > 0 THEN ROUND(current_balance/credit_limit*100) ELSE 0 END AS used_pct
                           FROM customers WHERE current_balance > 0 ORDER BY current_balance DESC
                           LIMIT %s OFFSET %s""", (per_page, meta["offset"]))
            return jsonify({"dues": cur.fetchall(), **meta})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
