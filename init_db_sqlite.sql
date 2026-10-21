-- SQLite schema for standalone KiranaPro.
-- Applied automatically by kirana.db.ensure_local_database().
-- Product catalog seeds are reused from init_db.sql (single source of truth).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS app_users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'staff' CHECK (role IN ('admin', 'staff')),
    full_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT UNIQUE NOT NULL,
    credit_limit NUMERIC(10, 2) DEFAULT 10000.00 CHECK (credit_limit >= 0),
    current_balance NUMERIC(10, 2) DEFAULT 0.00,
    loyalty_points INTEGER DEFAULT 0,
    lifetime_spend NUMERIC(10, 2) DEFAULT 0.00,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    barcode TEXT UNIQUE,
    unit TEXT NOT NULL,
    stock_quantity NUMERIC(10, 3) NOT NULL CHECK (stock_quantity >= 0),
    cost_price NUMERIC(10, 2) NOT NULL CHECK (cost_price >= 0),
    unit_price NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0),
    gst_slab NUMERIC(5, 2) NOT NULL CHECK (gst_slab >= 0 AND gst_slab <= 100),
    min_threshold NUMERIC(10, 3) DEFAULT 5.000,
    distributor_name TEXT,
    category TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER REFERENCES customers(customer_id),
    user_id INTEGER REFERENCES app_users(user_id),
    order_date TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    total_amount NUMERIC(10, 2) NOT NULL,
    total_cgst NUMERIC(10, 2) NOT NULL,
    total_sgst NUMERIC(10, 2) NOT NULL,
    total_profit NUMERIC(10, 2) NOT NULL,
    payment_mode TEXT NOT NULL,
    payment_status TEXT NOT NULL,
    final_invoice_amount NUMERIC(10, 2) NOT NULL,
    discount_amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    loyalty_redeemed INTEGER NOT NULL DEFAULT 0,
    order_status TEXT NOT NULL DEFAULT 'Completed'
);

CREATE TABLE IF NOT EXISTS order_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(product_id),
    quantity NUMERIC(10, 3) NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(10, 2) NOT NULL,
    cost_price NUMERIC(10, 2) NOT NULL,
    gst_slab NUMERIC(5, 2) NOT NULL,
    subtotal NUMERIC(10, 2) NOT NULL,
    cgst_amount NUMERIC(10, 2) NOT NULL,
    sgst_amount NUMERIC(10, 2) NOT NULL,
    line_total NUMERIC(10, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS udhaar_ledger (
    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER REFERENCES customers(customer_id),
    order_id INTEGER REFERENCES orders(order_id),
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('Debit', 'Credit')),
    transaction_date TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    remarks TEXT
);

CREATE TABLE IF NOT EXISTS returns (
    return_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER REFERENCES orders(order_id),
    product_id INTEGER REFERENCES products(product_id),
    quantity NUMERIC(10, 3) NOT NULL CHECK (quantity > 0),
    refund_amount NUMERIC(10, 2) NOT NULL CHECK (refund_amount >= 0),
    reason TEXT,
    user_id INTEGER REFERENCES app_users(user_id),
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS expenses (
    expense_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    category TEXT DEFAULT 'General',
    notes TEXT,
    user_id INTEGER REFERENCES app_users(user_id),
    expense_date TEXT NOT NULL DEFAULT (date('now','localtime')),
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS store_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

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

CREATE TABLE IF NOT EXISTS purchases (
    purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity NUMERIC(10, 3) NOT NULL CHECK (quantity > 0),
    cost_price NUMERIC(10, 2) NOT NULL CHECK (cost_price >= 0),
    vendor TEXT,
    bill_no TEXT,
    user_id INTEGER REFERENCES app_users(user_id),
    purchase_date TEXT NOT NULL DEFAULT (date('now','localtime')),
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_customer_phone ON customers(phone);
CREATE INDEX IF NOT EXISTS idx_product_barcode ON products(barcode);
CREATE INDEX IF NOT EXISTS idx_order_date ON orders(order_date);
CREATE INDEX IF NOT EXISTS idx_ledger_customer ON udhaar_ledger(customer_id);
CREATE INDEX IF NOT EXISTS idx_returns_order ON returns(order_id);
CREATE INDEX IF NOT EXISTS idx_expense_date ON expenses(expense_date);
CREATE INDEX IF NOT EXISTS idx_activity_date ON activity_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_purchases_product ON purchases(product_id);
CREATE INDEX IF NOT EXISTS idx_purchases_date ON purchases(purchase_date);
