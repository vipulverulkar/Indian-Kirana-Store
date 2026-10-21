"""Seed demo data for KiranaPro. Safe to re-run (all inserts are idempotent).

Usage:
    .venv/bin/python seed.py                    # seed users, customers, categories
    .venv/bin/python seed.py --reset-passwords  # also reset demo passwords to defaults

Demo logins default to admin/admin123 (admin) and staff/staff123 (staff);
override with SEED_ADMIN_USER / SEED_ADMIN_PASSWORD / SEED_STAFF_USER /
SEED_STAFF_PASSWORD env vars (e.g. in .env) to harden a real install.

Seeds:
    - app_users: admin + staff login accounts
    - customers: two demo customers with credit limits
    - categories: backfilled from existing products + base set,
      so category dropdowns work even on a fresh database.
"""
import os
import sys
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

from kirana.db import db_mode, ensure_local_database, get_db_connection

ensure_local_database()

if db_mode() == "split_vars":
    required = ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT")
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        sys.exit(
            f"Missing DB config: set DATABASE_URL or {', '.join(missing)} in .env"
        )

RESET_PASSWORDS = "--reset-passwords" in sys.argv

BASE_CATEGORIES = [
    "Grains", "Pulses", "Spices", "Oil", "Dairy",
    "Beverages", "Biscuits", "Instant", "Dry Fruits", "Health",
    "Snacks", "Household", "Personal Care",
    "Sweets & Confectionery", "Frozen Foods", "Pooja Essentials", "Baby Care",
]

conn = get_db_connection()
try:
    cur = conn.cursor()
    try:
        # --- Users (usernames/passwords overridable via env; defaults are demo-only) ---
        users = [
            (os.getenv("SEED_ADMIN_USER", "admin"),
             generate_password_hash(os.getenv("SEED_ADMIN_PASSWORD", "admin123")),
             "admin", "Store Owner"),
            (os.getenv("SEED_STAFF_USER", "staff"),
             generate_password_hash(os.getenv("SEED_STAFF_PASSWORD", "staff123")),
             "staff", "Counter Staff"),
        ]
        for username, pw_hash, role, full_name in users:
            if RESET_PASSWORDS:
                cur.execute(
                    """INSERT INTO app_users (username, password_hash, role, full_name)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (username) DO UPDATE
                       SET password_hash = EXCLUDED.password_hash, role = EXCLUDED.role""",
                    (username, pw_hash, role, full_name),
                )
            else:
                cur.execute(
                    """INSERT INTO app_users (username, password_hash, role, full_name)
                       VALUES (%s, %s, %s, %s) ON CONFLICT (username) DO NOTHING""",
                    (username, pw_hash, role, full_name),
                )

        # --- Customers ---
        customers = [
            ("Ramesh Kumar", "9876500001", 10000),
            ("Suresh Patel", "9876500002", 5000),
        ]
        for name, phone, limit in customers:
            cur.execute(
                "INSERT INTO customers (name, phone, credit_limit) VALUES (%s, %s, %s) ON CONFLICT (phone) DO NOTHING",
                (name, phone, limit),
            )

        # --- Categories (source of truth for dropdowns) ---
        for name in BASE_CATEGORIES:
            cur.execute(
                "INSERT INTO categories (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                (name,),
            )
        # Backfill any categories used by products but missing from the table
        cur.execute(
            """INSERT INTO categories (name)
               SELECT DISTINCT TRIM(category) FROM products
               WHERE category IS NOT NULL AND TRIM(category) <> ''
               ON CONFLICT (name) DO NOTHING"""
        )

        conn.commit()

        cur.execute("SELECT count(*) AS n FROM app_users")
        n_users = cur.fetchone()['n']
        cur.execute("SELECT count(*) AS n FROM customers")
        n_customers = cur.fetchone()['n']
        cur.execute("SELECT count(*) AS n FROM categories")
        n_categories = cur.fetchone()['n']
    finally:
        cur.close()
finally:
    conn.close()

print(f"Seeded: {n_users} users ({', '.join(u[0] for u in users)})"
      f" + {n_customers} customers + {n_categories} categories")
if RESET_PASSWORDS:
    print("Demo passwords were reset to defaults.")
