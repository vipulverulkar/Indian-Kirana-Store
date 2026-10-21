"""Products, categories, inventory and product CSV import/export."""
import csv
import io

from flask import Blueprint, Response, jsonify, request, session

from .auth import admin_required, login_required
from .constants import (
    BARCODE_MAX_RETRIES,
    BARCODE_PREFIX,
    MAX_GST_SLAB,
    MAX_IMPORT_BYTES,
    MAX_IMPORT_ROWS,
    MAX_LEN_BILL_NO,
    MAX_LEN_CATEGORY,
    MAX_LEN_VENDOR,
    MIN_GST_SLAB,
    ROLE_ADMIN,
)
from .db import FK_ERRORS, UNIQUE_ERRORS, db_cursor
from .settings import SETTING_DEFAULTS, get_decimal_setting, get_setting
from .utils import ensure_category, get_pagination, page_meta, to_decimal

products_bp = Blueprint("products", __name__)

PRODUCT_FIELDS = ('name', 'unit', 'stock_quantity', 'cost_price', 'unit_price', 'gst_slab')


def _strip_cost_for_staff(rows):
    """Staff (billing terminal) must never see margins: drop cost_price."""
    if session.get('role') == ROLE_ADMIN:
        return rows
    if isinstance(rows, dict):
        rows.pop('cost_price', None)
        return rows
    for r in (rows or []):
        if isinstance(r, dict):
            r.pop('cost_price', None)
    return rows


def auto_barcode(cur):
    """Generate a random, non-sequential barcode: KP + 8 random digits.

    Deliberately not derived from the product id, so codes reveal nothing
    about catalog size/order. The 6-digit legacy scheme (KP000028) can never
    collide with this 8-digit one; the DB check covers manual codes too."""
    import random
    max_value = 10 ** BARCODE_DIGIT_COUNT - 1
    fmt = f"{{:0{BARCODE_DIGIT_COUNT}d}}"
    for _ in range(BARCODE_MAX_RETRIES):
        code = f"{BARCODE_PREFIX}{fmt.format(random.randint(0, max_value))}"
        cur.execute("SELECT 1 FROM products WHERE barcode=%s", (code,))
        if not cur.fetchone():
            return code
    raise ValueError("Could not generate a unique barcode, set one manually")


def validate_product_payload(data):
    """Returns cleaned dict or raises ValueError."""
    cleaned = {}
    name = str(data.get('name') or '').strip()
    if not name:
        raise ValueError("Product name is required")
    cleaned['name'] = name
    # Handle 'unit' separately (required + validation) — not in the generic loop below.
    unit = str(data.get('unit') or '').strip()
    if not unit:
        raise ValueError("Unit is required (e.g. kg, packet, L, piece)")
    cleaned['unit'] = unit
    for f in ('barcode', 'distributor_name', 'category'):
        if f in data:
            v = data.get(f)
            cleaned[f] = (str(v).strip() or None) if v is not None else None
    for num_field in ('stock_quantity', 'cost_price', 'unit_price', 'gst_slab', 'min_threshold'):
        if num_field in data and data.get(num_field) not in (None, ''):
            cleaned[num_field] = to_decimal(data[num_field], num_field)
    for f in PRODUCT_FIELDS:
        if f not in cleaned:
            raise ValueError(f"Missing required field: {f}")
    cleaned.setdefault('min_threshold', get_decimal_setting("default_min_threshold"))
    if 'gst_slab' in cleaned and (cleaned['gst_slab'] < MIN_GST_SLAB or cleaned['gst_slab'] > MAX_GST_SLAB):
        raise ValueError(f"GST slab must be between {MIN_GST_SLAB} and {MAX_GST_SLAB}")
    for f in ('stock_quantity', 'cost_price', 'unit_price'):
        if f in cleaned and cleaned[f] < 0:
            raise ValueError(f"{f} cannot be negative")
    if 'min_threshold' in cleaned and cleaned['min_threshold'] < 0:
        raise ValueError("min_threshold cannot be negative")
    if cleaned.get('category') and len(cleaned['category']) > MAX_LEN_CATEGORY:
        raise ValueError(f"Category too long (max {MAX_LEN_CATEGORY})")
    return cleaned


@products_bp.route('/api/products', methods=['GET', 'POST'])
@login_required
def manage_products():
    if request.method == 'GET':
        search = (request.args.get('search') or '').strip()
        category = (request.args.get('category') or '').strip()
        low_only = request.args.get('low_stock') == '1'
        page, per_page = get_pagination()
        try:
            with db_cursor() as cur:
                where = "WHERE 1=1"
                params: list = []
                if search:
                    where += " AND (name ILIKE %s OR barcode ILIKE %s)"
                    params += [f"%{search}%", f"%{search}%"]
                if category:
                    where += " AND category = %s"
                    params.append(category)
                if low_only:
                    where += " AND stock_quantity <= min_threshold"
                cur.execute(f"SELECT COUNT(*) AS total FROM products {where}", tuple(params))
                meta = page_meta(cur.fetchone()['total'], page, per_page)
                cur.execute(f"SELECT * FROM products {where} ORDER BY name ASC LIMIT %s OFFSET %s",
                            tuple(params) + (per_page, meta["offset"]))
                products = cur.fetchall()
            return jsonify({"products": _strip_cost_for_staff(products), **meta})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # POST - admin only
    if session.get('role') != ROLE_ADMIN:
        return jsonify({"error": "Admin access required"}), 403
    data = request.get_json(silent=True) or {}
    try:
        data = dict(data)
        # Apply store defaults for fields the UI may omit.
        data.setdefault('unit', get_setting("default_unit", SETTING_DEFAULTS["default_unit"]))
        data.setdefault('gst_slab', get_setting("default_gst_slab", SETTING_DEFAULTS["default_gst_slab"]))
        data.setdefault('min_threshold', get_setting("default_min_threshold", SETTING_DEFAULTS["default_min_threshold"]))
        cleaned = validate_product_payload(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    try:
        with db_cursor(commit=True) as cur:
            if cleaned.get('category'):
                cleaned['category'] = ensure_category(cur, cleaned['category'])
            cur.execute(
                """INSERT INTO products (name, barcode, unit, stock_quantity, cost_price, unit_price, gst_slab, min_threshold, distributor_name, category)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING product_id""",
                (cleaned['name'], cleaned.get('barcode'), cleaned['unit'], cleaned['stock_quantity'],
                 cleaned['cost_price'], cleaned['unit_price'], cleaned['gst_slab'],
                 cleaned.get('min_threshold', get_decimal_setting("default_min_threshold")), cleaned.get('distributor_name'), cleaned.get('category'))
            )
            new_id = cur.fetchone()['product_id']
            if not cleaned.get('barcode'):
                code = auto_barcode(cur)
                cur.execute("UPDATE products SET barcode=%s WHERE product_id=%s", (code, new_id))
                cleaned['barcode'] = code
        from .activity import log_activity
        log_activity("product.create", entity="product", entity_id=new_id,
                     detail=cleaned.get('name', ''))
        return jsonify({"status": "success", "product_id": new_id, "barcode": cleaned.get('barcode')}), 201
    except UNIQUE_ERRORS:
        return jsonify({"error": "Barcode already exists"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@products_bp.route('/api/products/<int:pid>', methods=['PUT', 'DELETE'])
@login_required
def product_detail(pid):
    if session.get('role') != ROLE_ADMIN:
        return jsonify({"error": "Admin access required"}), 403
    try:
        if request.method == 'PUT':
            data = request.get_json(silent=True) or {}
            try:
                cleaned = validate_product_payload(data)
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
            with db_cursor(commit=True) as cur:
                cur.execute("SELECT product_id FROM products WHERE product_id=%s", (pid,))
                if not cur.fetchone():
                    return jsonify({"error": "Product not found"}), 404
                if cleaned.get('category'):
                    cleaned['category'] = ensure_category(cur, cleaned['category'])
                cur.execute(
                    """UPDATE products SET name=%s, barcode=%s, unit=%s, stock_quantity=%s, cost_price=%s,
                       unit_price=%s, gst_slab=%s, min_threshold=%s, distributor_name=%s, category=%s
                       WHERE product_id=%s""",
                    (cleaned['name'], cleaned.get('barcode'), cleaned['unit'], cleaned['stock_quantity'],
                     cleaned['cost_price'], cleaned['unit_price'], cleaned['gst_slab'],
                     cleaned.get('min_threshold', get_decimal_setting("default_min_threshold")), cleaned.get('distributor_name'),
                      cleaned.get('category'), pid)
                )
            from .activity import log_activity
            log_activity("product.update", entity="product", entity_id=pid,
                         detail=cleaned.get('name', ''))
            return jsonify({"status": "success"})

        if request.method == 'DELETE':
            with db_cursor(commit=True) as cur:
                cur.execute("SELECT product_id FROM products WHERE product_id = %s", (pid,))
                if not cur.fetchone():
                    return jsonify({"error": "Product not found"}), 404
                cur.execute("SELECT COUNT(*) AS n FROM order_items WHERE product_id = %s", (pid,))
                if cur.fetchone()['n'] > 0:
                    return jsonify({"error": "Cannot delete: product has order history. Keep the record."}), 400
                cur.execute("SELECT COUNT(*) AS n FROM returns WHERE product_id = %s", (pid,))
                if cur.fetchone()['n'] > 0:
                    return jsonify({"error": "Cannot delete: product has return history. Keep the record."}), 400
                cur.execute("DELETE FROM products WHERE product_id = %s", (pid,))
            from .activity import log_activity
            log_activity("product.delete", entity="product", entity_id=pid)
            return jsonify({"status": "success"})
    except UNIQUE_ERRORS:
        return jsonify({"error": "Barcode already exists"}), 400
    except FK_ERRORS:
        return jsonify({"error": "Cannot delete: product is referenced by orders or returns. Keep the record."}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@products_bp.route('/api/products/<int:pid>/stock', methods=['POST'])
@login_required
def stock_in(pid):
    """Add stock (purchase / correction). Body: {quantity, cost_price?, vendor?, bill_no?}
    Every stock-in is logged in the procurement history (purchases) with the
    effective cost, so the same product bought at different rates stays traceable."""
    if session.get('role') != ROLE_ADMIN:
        return jsonify({"error": "Admin access required"}), 403
    data = request.get_json(silent=True) or {}
    try:
        qty = to_decimal(data.get('quantity'), 'quantity')
        if qty <= 0:
            raise ValueError("Quantity must be positive")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    vendor = (data.get('vendor') or '').strip() or None
    if vendor and len(vendor) > MAX_LEN_VENDOR:
        return jsonify({"error": f"Vendor too long (max {MAX_LEN_VENDOR})"}), 400
    bill_no = (data.get('bill_no') or '').strip() or None
    if bill_no and len(bill_no) > MAX_LEN_BILL_NO:
        return jsonify({"error": f"Bill no too long (max {MAX_LEN_BILL_NO})"}), 400
    try:
        with db_cursor(commit=True) as cur:
            cur.execute("SELECT cost_price FROM products WHERE product_id=%s FOR UPDATE", (pid,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Product not found"}), 404
            effective_cost = row['cost_price']
            if data.get('cost_price') not in (None, ''):
                cp = to_decimal(data.get('cost_price'), 'cost_price')
                if cp < 0:
                    return jsonify({"error": "cost_price cannot be negative"}), 400
                effective_cost = cp
                cur.execute("UPDATE products SET stock_quantity = stock_quantity + %s, cost_price=%s WHERE product_id=%s",
                            (qty, cp, pid))
            else:
                cur.execute("UPDATE products SET stock_quantity = stock_quantity + %s WHERE product_id=%s", (qty, pid))
            cur.execute(
                """INSERT INTO purchases (product_id, quantity, cost_price, vendor, bill_no, user_id)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (pid, qty, effective_cost, vendor, bill_no, session.get('user_id')))
        from .activity import log_activity
        log_activity("product.stock_in", entity="product", entity_id=pid,
                     detail=f"+{qty} @ {effective_cost}" + (f" ({vendor})" if vendor else ""))
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@products_bp.route('/api/products/<int:pid>/purchases', methods=['GET'])
@login_required
def purchase_history(pid):
    """Procurement history for one product (newest first). Admin only (has cost rates)."""
    if session.get('role') != ROLE_ADMIN:
        return jsonify({"error": "Admin access required"}), 403
    page, per_page = get_pagination()
    try:
        with db_cursor() as cur:
            cur.execute("SELECT product_id, name FROM products WHERE product_id=%s", (pid,))
            prod = cur.fetchone()
            if not prod:
                return jsonify({"error": "Product not found"}), 404
            cur.execute("SELECT COUNT(*) AS total FROM purchases WHERE product_id=%s", (pid,))
            meta = page_meta(cur.fetchone()['total'], page, per_page)
            cur.execute(
                """SELECT pu.*, u.full_name AS added_by FROM purchases pu
                   LEFT JOIN app_users u ON u.user_id = pu.user_id
                   WHERE pu.product_id=%s ORDER BY pu.created_at DESC LIMIT %s OFFSET %s""",
                (pid, per_page, meta["offset"]))
            rows = cur.fetchall()
        return jsonify({"product": prod, "purchases": rows, **meta})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@products_bp.route('/api/products/<int:pid>/barcode/assign', methods=['POST'])
@login_required
def assign_barcode(pid):
    """Auto-assign a random non-sequential barcode to a codeless product."""
    if session.get('role') != ROLE_ADMIN:
        return jsonify({"error": "Admin access required"}), 403
    try:
        with db_cursor(commit=True) as cur:
            cur.execute("SELECT product_id, barcode FROM products WHERE product_id=%s FOR UPDATE", (pid,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Product not found"}), 404
            if row['barcode']:
                return jsonify({"error": "Product already has a barcode"}), 400
            code = auto_barcode(cur)
            cur.execute("UPDATE products SET barcode=%s WHERE product_id=%s", (code, pid))
        from .activity import log_activity
        log_activity("product.barcode_assign", entity="product", entity_id=pid, detail=code)
        return jsonify({"status": "success", "barcode": code})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@products_bp.route('/api/products/barcode/<barcode>', methods=['GET'])
@login_required
def get_product_by_barcode(barcode):
    try:
        with db_cursor() as cur:
            cur.execute("SELECT * FROM products WHERE barcode = %s", (barcode,))
            product = cur.fetchone()
        if product:
            return jsonify(_strip_cost_for_staff(product))
        return jsonify({"error": "Product not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@products_bp.route('/api/categories', methods=['GET', 'POST'])
@login_required
def manage_categories():
    if request.method == 'GET':
        try:
            with db_cursor() as cur:
                cur.execute("""SELECT c.category_id, c.name,
                                      (SELECT COUNT(*) FROM products p WHERE p.category = c.name) AS product_count
                               FROM categories c ORDER BY c.name ASC""")
                rows = cur.fetchall()
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        return jsonify({"categories": rows})
    # POST - admin only: add a category
    if session.get('role') != ROLE_ADMIN:
        return jsonify({"error": "Admin access required"}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({"error": "Category name required"}), 400
    if len(name) > MAX_LEN_CATEGORY:
        return jsonify({"error": f"Category too long (max {MAX_LEN_CATEGORY})"}), 400
    try:
        with db_cursor(commit=True) as cur:
            cur.execute("INSERT INTO categories (name) VALUES (%s) ON CONFLICT (name) DO NOTHING RETURNING category_id", (name,))
            row = cur.fetchone()
            if row:
                cid = row['category_id']
            else:
                cur.execute("SELECT category_id FROM categories WHERE name=%s", (name,))
                cid = cur.fetchone()['category_id']
        from .activity import log_activity
        log_activity("category.create", entity="category", entity_id=cid, detail=name)
        return jsonify({"status": "success", "category_id": cid, "name": name}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@products_bp.route('/api/categories/<int:cid>', methods=['PUT', 'DELETE'])
@login_required
def category_detail(cid):
    if session.get('role') != ROLE_ADMIN:
        return jsonify({"error": "Admin access required"}), 403
    if request.method == 'PUT':
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({"error": "Category name required"}), 400
        if len(name) > MAX_LEN_CATEGORY:
            return jsonify({"error": f"Category too long (max {MAX_LEN_CATEGORY})"}), 400
        try:
            with db_cursor(commit=True) as cur:
                cur.execute("SELECT name FROM categories WHERE category_id=%s", (cid,))
                old = cur.fetchone()
                if not old:
                    return jsonify({"error": "Category not found"}), 404
                cur.execute("UPDATE categories SET name=%s WHERE category_id=%s", (name, cid))
                # keep product labels in sync on rename
                cur.execute("UPDATE products SET category=%s WHERE category=%s", (name, old['name']))
            from .activity import log_activity
            log_activity("category.rename", entity="category", entity_id=cid,
                         detail=f"{old['name']} -> {name}")
            return jsonify({"status": "success", "name": name})
        except UNIQUE_ERRORS:
            return jsonify({"error": "Category name already exists"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    # DELETE
    try:
        with db_cursor(commit=True) as cur:
            cur.execute("SELECT name FROM categories WHERE category_id=%s", (cid,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Category not found"}), 404
            cur.execute("SELECT COUNT(*) AS n FROM products WHERE category=%s", (row['name'],))
            n = cur.fetchone()['n']
            if n > 0:
                return jsonify({"error": f"Cannot delete: {n} product(s) use this category. Move them first."}), 400
            cur.execute("DELETE FROM categories WHERE category_id=%s", (cid,))
        from .activity import log_activity
        log_activity("category.delete", entity="category", entity_id=cid,
                     detail=row['name'])
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@products_bp.route('/api/vendors', methods=['GET'])
@login_required
@admin_required
def list_vendors():
    """Distinct distributors saved on products, with product counts."""
    try:
        with db_cursor() as cur:
            cur.execute("""
                SELECT NULLIF(TRIM(distributor_name), '') AS name,
                       COUNT(*) AS product_count
                FROM products
                WHERE distributor_name IS NOT NULL AND TRIM(distributor_name) <> ''
                GROUP BY NULLIF(TRIM(distributor_name), '')
                ORDER BY name ASC""")
            rows = cur.fetchall()
        return jsonify({"vendors": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@products_bp.route('/api/inventory/low-stock', methods=['GET'])
@login_required
@admin_required
def get_low_stock():
    page, per_page = get_pagination()
    try:
        with db_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM products WHERE stock_quantity <= min_threshold")
            meta = page_meta(cur.fetchone()['total'], page, per_page)
            cur.execute("SELECT * FROM products WHERE stock_quantity <= min_threshold ORDER BY stock_quantity ASC LIMIT %s OFFSET %s",
                        (per_page, meta["offset"]))
            low_stock = cur.fetchall()
        return jsonify({"products": low_stock, **meta})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@products_bp.route('/api/inventory/purchase-order', methods=['GET'])
@login_required
@admin_required
def purchase_order_csv():
    """Download low-stock purchase order as CSV."""
    try:
        with db_cursor() as cur:
            cur.execute("SELECT name, barcode, stock_quantity, min_threshold, distributor_name FROM products WHERE stock_quantity <= min_threshold ORDER BY distributor_name NULLS LAST, name")
            rows = cur.fetchall()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    lines = ["Product,Barcode,Current Stock,Suggest Order Qty,Vendor"]
    for r in rows:
        need = (r['min_threshold'] or 0) * 2 - (r['stock_quantity'] or 0)
        try:
            need_f = float(need)
        except Exception:
            need_f = 0
        lines.append(f"\"{r['name']}\",{r['barcode'] or ''},{r['stock_quantity']},{max(need_f, 0):.0f},\"{r['distributor_name'] or ''}\"")
    csv_data = "\n".join(lines)
    return Response(csv_data, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=purchase_order.csv"})


@products_bp.route('/api/products/export', methods=['GET'])
@login_required
@admin_required
def products_export():
    try:
        with db_cursor() as cur:
            cur.execute("SELECT name, barcode, unit, stock_quantity, cost_price, unit_price, gst_slab, min_threshold, distributor_name, category FROM products ORDER BY name")
            rows = cur.fetchall()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=['name', 'barcode', 'unit', 'stock_quantity', 'cost_price', 'unit_price', 'gst_slab', 'min_threshold', 'distributor_name', 'category'])
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k) for k in w.fieldnames})
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=products.csv"})




@products_bp.route('/api/products/import', methods=['POST'])
@login_required
@admin_required
def products_import():
    if 'file' not in request.files:
        return jsonify({"error": "CSV file required (field name 'file')"}), 400
    try:
        raw = request.files['file'].read(MAX_IMPORT_BYTES + 1)
        if len(raw) > MAX_IMPORT_BYTES:
            return jsonify({"error": "File too large (max 2MB)"}), 400
        content = raw.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))
        created, updated, skipped = 0, 0, 0
        dflt_unit = get_setting("default_unit", SETTING_DEFAULTS["default_unit"])
        dflt_gst = get_setting("default_gst_slab", SETTING_DEFAULTS["default_gst_slab"])
        dflt_thresh = get_setting("default_min_threshold", SETTING_DEFAULTS["default_min_threshold"])
        with db_cursor(commit=True) as cur:
            for i, row in enumerate(reader):
                if i >= MAX_IMPORT_ROWS:
                    break
                if not (row.get('name') or '').strip():
                    skipped += 1
                    continue
                try:
                    payload = validate_product_payload({
                        'name': row['name'], 'barcode': row.get('barcode') or None, 'unit': row.get('unit') or dflt_unit,
                        'stock_quantity': row.get('stock_quantity') or 0, 'cost_price': row.get('cost_price') or 0,
                        'unit_price': row.get('unit_price') or 0, 'gst_slab': row.get('gst_slab') or dflt_gst,
                        'min_threshold': row.get('min_threshold') or dflt_thresh,
                        'distributor_name': row.get('distributor_name'), 'category': row.get('category')})
                except ValueError:
                    skipped += 1
                    continue
                if payload.get('category'):
                    payload['category'] = ensure_category(cur, payload['category'])
                if payload.get('barcode'):
                    cur.execute("SELECT product_id FROM products WHERE barcode=%s", (payload['barcode'],))
                    existing = cur.fetchone()
                    if existing:
                        cur.execute("""UPDATE products SET name=%s, unit=%s, stock_quantity=%s, cost_price=%s, unit_price=%s,
                                       gst_slab=%s, min_threshold=%s, distributor_name=%s, category=%s WHERE barcode=%s""",
                                    (payload['name'], payload['unit'], payload['stock_quantity'], payload['cost_price'],
                                     payload['unit_price'], payload['gst_slab'], payload.get('min_threshold', get_decimal_setting("default_min_threshold")),
                                     payload.get('distributor_name'), payload.get('category'), payload['barcode']))
                        updated += 1
                        continue
                cur.execute("""INSERT INTO products (name, barcode, unit, stock_quantity, cost_price, unit_price, gst_slab, min_threshold, distributor_name, category)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (barcode) DO NOTHING RETURNING product_id""",
                            (payload['name'], payload.get('barcode'), payload['unit'], payload['stock_quantity'],
                             payload['cost_price'], payload['unit_price'], payload['gst_slab'],
                             payload.get('min_threshold', get_decimal_setting("default_min_threshold")), payload.get('distributor_name'), payload.get('category')))
                inserted = cur.fetchone()  # renamed from 'row' to avoid shadowing the CSV loop variable
                if inserted:
                    if not payload.get('barcode'):
                        code = auto_barcode(cur)
                        cur.execute("UPDATE products SET barcode=%s WHERE product_id=%s", (code, inserted['product_id']))
                    created += 1
                # else: ON CONFLICT DO NOTHING → nothing was inserted, do not count as created
        return jsonify({"status": "success", "created": created, "updated": updated, "skipped": skipped})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
