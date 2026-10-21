#!/bin/sh
# Docker entrypoint: wait for Postgres, apply schema (idempotent), seed, start app.
set -e

echo ">>> KiranaPro entrypoint: waiting for database..."

python3 - <<'PY'
import os, sys, time
from kirana.db import db_mode, ensure_local_database, get_db_connection

print(f">>> Database mode: {db_mode()}")
ensure_local_database()

deadline = time.time() + int(os.getenv("DB_WAIT_TIMEOUT", "60"))
while True:
    try:
        conn = get_db_connection()
        conn.close()
        print(">>> Database reachable.")
        break
    except Exception as e:
        if time.time() > deadline:
            print(f"!!! Could not reach database in time: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"    ... waiting ({e})")
        time.sleep(2)

# SQLite is initialized automatically. PostgreSQL uses init_db.sql (idempotent).
if db_mode() != "sqlite":
    print(">>> Applying schema (init_db.sql)...")
    conn = get_db_connection()
    conn.autocommit = True
    try:
        with open("init_db.sql", "r", encoding="utf-8") as f:
            with conn.cursor() as cur:
                cur.execute(f.read())
    finally:
        conn.close()
    print(">>> Schema OK.")
PY

echo ">>> Seeding demo data (idempotent)..."
python3 seed.py || echo "!!! seed.py failed — continuing anyway (DB may already be seeded)."

echo ">>> Starting: $@"
exec "$@"
