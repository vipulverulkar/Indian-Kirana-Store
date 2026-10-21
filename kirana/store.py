"""Store branding + persistent settings: logo upload, store-info and /api/settings."""
import os

from flask import Blueprint, Response, jsonify, request, send_from_directory

from .auth import admin_required, login_required
from .constants import (
    ALLOWED_LOGO_EXTENSIONS,
    BACKUP_PG_DUMP_TIMEOUT,
    BACKUP_PSQL_TIMEOUT,
    BACKUP_STDERR_PREVIEW_LEN,
    LOGO_CACHE_SECONDS,
    MAX_LOGO_BYTES,
    ROLE_ADMIN,
)
from .db import BASE_DIR, DATA_DIR, POINTER_ACTIVE_KEY, POINTER_URL_KEY, db_cursor
from .settings import SETTING_DEFAULTS, catalog_meta, get_all_settings, save_settings, validate_settings

store_bp = Blueprint("store", __name__)

LOGO_DIR = os.path.join(DATA_DIR, "static", "uploads")
try:
    os.makedirs(LOGO_DIR, exist_ok=True)
except OSError:
    pass
ALLOWED_LOGO_EXTS = ALLOWED_LOGO_EXTENSIONS


def uploaded_logo_url():
    """URL of the admin-uploaded logo, or '' if none."""
    try:
        for fn in os.listdir(LOGO_DIR):
            if fn.startswith("store_logo.") and fn.rsplit(".", 1)[-1].lower() in ALLOWED_LOGO_EXTS:
                return f"/uploads/{fn}"
    except OSError:
        pass
    return ""


def store_info():
    s = get_all_settings()
    return {
        "name": s.get("store_name") or os.getenv("STORE_NAME", SETTING_DEFAULTS["store_name"]),
        "location": s.get("store_location") or os.getenv("STORE_LOCATION", SETTING_DEFAULTS["store_location"]),
        "address": s.get("store_address", ""),
        "phone": s.get("store_phone", ""),
        "gstin": s.get("store_gstin", ""),
        "upi_id": s.get("upi_id", ""),
        "invoice_footer": s.get("invoice_footer", SETTING_DEFAULTS["invoice_footer"]),
        "logo": os.getenv("STORE_LOGO", "") or uploaded_logo_url(),
    }


@store_bp.route('/uploads/<path:filename>')
def uploaded_logo_file(filename):
    """Serve logos from the writable data dir (works in bundled desktop mode)."""
    return send_from_directory(LOGO_DIR, filename, max_age=LOGO_CACHE_SECONDS)


@store_bp.route('/api/store-info', methods=['GET'])
@login_required
def get_store_info():
    return jsonify(store_info())


@store_bp.route('/api/meta', methods=['GET'])
@login_required
def get_meta():
    """Lookup lists (payment modes, units, GST slabs, page sizes) — single source for the UI."""
    return jsonify(catalog_meta())


@store_bp.route('/api/settings', methods=['GET', 'PUT'])
@login_required
def manage_settings():
    if request.method == 'GET':
        out = get_all_settings()
        # Database selection rides along (read-only here) — the remote URL
        # itself is NEVER exposed; only whether one is saved.
        try:
            from .db import get_db_pointer, get_remote_url
            out["active_db"] = get_db_pointer()["active"]
            out["remote_configured"] = bool(get_remote_url())
        except Exception:
            out["active_db"] = "local"
            out["remote_configured"] = False
        return jsonify(out)
    # PUT - admin only
    from flask import session
    if session.get('role') != ROLE_ADMIN:
        return jsonify({"error": "Administrator privileges required"}), 403
    data = request.get_json(silent=True) or {}
    if any(k in data for k in ("active_db", "remote_database_url",
                               "db.active", "db.remote_url")):
        return jsonify({"error": "Database selection is managed via PUT /api/settings/database"}), 400
    try:
        cleaned = validate_settings(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not cleaned:
        return jsonify({"error": "No settings provided"}), 400
    try:
        save_settings(cleaned)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    from .activity import log_activity
    log_activity("settings.update", entity="settings",
                 detail=", ".join(sorted(cleaned.keys())))
    return jsonify({"status": "success", "settings": get_all_settings()})


# --- Database selection (which Postgres the app uses) ---
# The pointer + remote URL live in the PRIMARY database (never routed), so a
# dead remote can never block reading or switching the selection. The URL is
# a secret: it is accepted on PUT/test, stored server-side, and never
# returned by any endpoint (responses carry only host/dbname, no password).
def _db_status_payload():
    from .db import db_target_info, get_remote_url
    info = db_target_info()
    try:
        remote_configured = bool(get_remote_url())
    except Exception:
        remote_configured = False
    info["remote_configured"] = remote_configured
    try:
        from .db import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                cur.fetchone()
            info["reachable"] = True
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception as e:
        info["reachable"] = False
        info["reach_error"] = str(e)[:200]
    return info


def _apply_schema_to_url(url):
    """Apply init_db.sql (idempotent) to the database at url."""
    import psycopg2
    from .db import _effective_url
    schema_path = os.path.join(BASE_DIR, "init_db.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = f.read()
    conn = psycopg2.connect(_effective_url(url.strip()))
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(schema)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _sync_users_to_url(url):
    """Copy login accounts (primary → remote) so logins keep working and
    user_id FKs (orders/returns/purchases/activity) stay valid after a
    switch. Existing remote usernames keep their user_id; new rows reuse the
    primary's user_id so live sessions survive the switch. Returns the
    remote admin count. Server-side only — hashes never touch the API."""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from .db import _effective_url
    with db_cursor() as cur:
        cur.execute("SELECT user_id, username, password_hash, role, full_name FROM app_users")
        users = cur.fetchall()
    if not users:
        raise RuntimeError("Primary database has no login accounts — cannot switch")
    conn = psycopg2.connect(_effective_url(url.strip()), cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            for u in users:
                cur.execute(
                    """INSERT INTO app_users (user_id, username, password_hash, role, full_name)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (username) DO UPDATE SET
                         password_hash = EXCLUDED.password_hash,
                         role = EXCLUDED.role,
                         full_name = EXCLUDED.full_name""",
                    (u["user_id"], u["username"], u["password_hash"],
                     u["role"], u["full_name"]))
            cur.execute("SELECT setval(pg_get_serial_sequence('app_users', 'user_id'), "
                        "(SELECT COALESCE(MAX(user_id), 1) FROM app_users))")
            cur.execute("SELECT COUNT(*) AS n FROM app_users WHERE role = %s", (ROLE_ADMIN,))
            admins = cur.fetchone()["n"]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return admins


@store_bp.route('/api/settings/database', methods=['GET'])
@login_required
@admin_required
def db_status():
    """Which database the app uses + whether it is reachable. No secrets."""
    return jsonify(_db_status_payload())


@store_bp.route('/api/settings/database/test', methods=['POST'])
@login_required
@admin_required
def db_test():
    """Test a candidate remote URL (connect + SELECT version). Not stored."""
    data = request.get_json(silent=True) or {}
    url = (data.get("remote_database_url") or "").strip()
    if not url:
        return jsonify({"error": "remote_database_url is required"}), 400
    try:
        from .db import test_db_url
        info = test_db_url(url)
    except (ValueError, RuntimeError) as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"status": "success", **info})


@store_bp.route('/api/settings/database', methods=['PUT'])
@login_required
@admin_required
def db_switch():
    """Switch the active database. Body: {active_db: local|remote,
    remote_database_url?: string (required to configure remote)}.

    Switching TO remote: validates + connects, applies schema, syncs login
    accounts (primary wins on conflict), refuses when the target ends up
    with no admin. Switching never moves business data — each database keeps
    its own bills; only new writes go to the newly active one."""
    from .db import get_remote_url, set_db_pointer
    data = request.get_json(silent=True) or {}
    active = (data.get("active_db") or "").strip()
    if active not in ("local", "remote"):
        return jsonify({"error": "active_db must be 'local' or 'remote'"}), 400
    if active == "local":
        try:
            set_db_pointer("local")
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        from .activity import log_activity
        log_activity("db.switch", entity="database", detail="active: remote → local")
        return jsonify({"status": "success", **_db_status_payload()})
    # active == "remote"
    url = (data.get("remote_database_url") or "").strip() or get_remote_url()
    if not url:
        return jsonify({"error": "remote_database_url is required (none saved yet)"}), 400
    try:
        from .db import test_db_url
        test_db_url(url)
    except (ValueError, RuntimeError) as e:
        return jsonify({"error": str(e)}), 400
    try:
        _apply_schema_to_url(url)
    except Exception as e:
        return jsonify({"error": f"Remote connected but schema setup failed: {str(e)[:200]}"}), 400
    try:
        admins = _sync_users_to_url(url)
    except Exception as e:
        return jsonify({"error": f"Remote ready but login sync failed: {str(e)[:200]}"}), 400
    if not admins:
        return jsonify({"error": "Remote has no admin user — refusing to switch"}), 400
    try:
        set_db_pointer("remote", url)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    from .activity import log_activity as _log
    from .db import parse_db_url as _parse
    try:
        _info = _parse(url)
        detail = f"active: local → remote ({_info['host']}/{_info['dbname']})"
    except Exception:
        detail = "active: local → remote"
    _log("db.switch", entity="database", detail=detail)
    return jsonify({"status": "success", **_db_status_payload()})


@store_bp.route('/api/store-logo', methods=['POST', 'DELETE'])
@login_required
@admin_required
def manage_store_logo():
    from .activity import log_activity
    if request.method == 'DELETE':
        try:
            for fn in os.listdir(LOGO_DIR):
                if fn.startswith("store_logo."):
                    os.remove(os.path.join(LOGO_DIR, fn))
        except OSError:
            pass
        log_activity("store.logo_remove", entity="store")
        return jsonify({"status": "success", "logo": ""})
    # POST: upload image (field name 'file')
    if 'file' not in request.files:
        return jsonify({"error": "Image file required (field name 'file')"}), 400
    f = request.files['file']
    ext = (f.filename or '').rsplit('.', 1)[-1].lower() if '.' in (f.filename or '') else ''
    if ext not in ALLOWED_LOGO_EXTS:
        return jsonify({"error": "Only PNG, JPG, WEBP or GIF images allowed"}), 400
    raw = f.read(MAX_LOGO_BYTES + 1)
    if len(raw) > MAX_LOGO_BYTES:
        return jsonify({"error": "Image too large (max 2MB)"}), 400
    if not raw:
        return jsonify({"error": "Empty file"}), 400
    try:
        os.makedirs(LOGO_DIR, exist_ok=True)
        for fn in os.listdir(LOGO_DIR):
            if fn.startswith("store_logo."):
                os.remove(os.path.join(LOGO_DIR, fn))
        with open(os.path.join(LOGO_DIR, f"store_logo.{ext}"), "wb") as out:
            out.write(raw)
    except OSError as e:
        return jsonify({"error": f"Could not save logo: {e}"}), 500
    log_activity("store.logo_upload", entity="store", detail=f"store_logo.{ext}")
    return jsonify({"status": "success", "logo": f"/uploads/store_logo.{ext}"})


# --- Backup / restore (SQL dump + CSV zip) ---
# Tables that may be written by a restore, in FK-safe order (children first).
# app_users / activity_log are excluded — restore replaces business data only,
# login accounts stay untouched.
BACKUP_TABLES = ("order_items", "udhaar_ledger", "returns", "orders",
                 "expenses", "products", "purchases", "customers", "categories", "store_settings")
# Tables exported by /api/backup (CSV mode; SQL mode dumps everything except credentials).
CSV_TABLES = ("app_users",) + BACKUP_TABLES
MAX_BACKUP_BYTES = 50 * 1024 * 1024
DUMP_MARKER = "-- KIRANAPRO DATA DUMP v1"


def _capture_db_pointer():
    """Snapshot the active-DB pointer stored in the PRIMARY database.

    store_settings is part of a backup/restore, but the pointer keys are
    infrastructure state (they hold the remote URL secret). They must survive
    a restore instead of being wiped or replaced by an old backup."""
    try:
        from .db import get_db_pointer, get_remote_url
        return get_db_pointer()["active"], get_remote_url()
    except Exception:
        return None, None


def _restore_db_pointer(active, remote_url):
    """Re-apply the pointer snapshot after a restore. Best effort."""
    if active not in ("local", "remote") or (active == "remote" and not remote_url):
        return
    try:
        from .db import set_db_pointer
        set_db_pointer(active, remote_url)
    except Exception:
        pass


def _strip_pointer_rows(dump):
    """Drop store_settings INSERT lines that hold database-pointer secrets.

    pg_dump runs with --column-inserts, so each row is a single line."""
    needles = (f"'{POINTER_ACTIVE_KEY}'", f"'{POINTER_URL_KEY}'")
    kept = []
    for line in dump.splitlines(keepends=True):
        if line.lstrip().lower().startswith("insert into public.store_settings") and \
                any(n in line for n in needles):
            continue
        kept.append(line)
    return "".join(kept)


def _dump_argv(dsn):
    # Data-only, one INSERT per row (--column-inserts). app_users (credentials)
    # and activity_log (audit) are excluded.
    return ["pg_dump", "--data-only", "--no-owner", "--no-privileges",
            "--no-tablespaces", "--column-inserts",
            "-T", "activity_log", "-T", "app_users", dsn]


@store_bp.route('/api/backup', methods=['GET'])
@login_required
@admin_required
def download_backup():
    """Backup business data. ?format=sql -> portable INSERT dump;
    ?format=csv -> zip with one .csv per table. Password hashes and the
    activity log are never exported. Works for SQLite and PostgreSQL."""
    import io
    import subprocess
    import zipfile
    from datetime import datetime
    from .db import active_backend

    fmt = (request.args.get('format') or 'sql').lower()
    if fmt not in ('sql', 'csv'):
        return jsonify({"error": "format must be sql or csv"}), 400
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    from .activity import log_activity

    try:
        if active_backend() == "sqlite":
            if fmt == 'sql':
                body, counts = _sqlite_sql_dump()
                log_activity("store.backup", entity="store",
                             detail="SQLite SQL dump downloaded: " +
                                    ", ".join(f"{t}={n}" for t, n in counts.items()))
                return Response(body, mimetype="application/sql",
                                headers={"Content-Disposition":
                                         f"attachment; filename=kiranapro-backup-{stamp}.sql"})
            data, counts = _sqlite_csv_zip()
            log_activity("store.backup", entity="store",
                         detail="SQLite CSV zip downloaded: " +
                                ", ".join(f"{t}={n}" for t, n in counts.items()))
            return Response(data, mimetype="application/zip",
                            headers={"Content-Disposition":
                                     f"attachment; filename=kiranapro-backup-{stamp}-csv.zip"})

        # ---- PostgreSQL: use the real pg_dump/psql tools ----
        import shutil
        from .db import db_dsn
        if not shutil.which("pg_dump") or not shutil.which("psql"):
            return jsonify({"error": "postgresql-client (pg_dump/psql) not found on the server"}), 500
        try:
            dsn = db_dsn()
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        if fmt == 'sql':
            proc = subprocess.run(_dump_argv(dsn), capture_output=True, text=True, timeout=BACKUP_PG_DUMP_TIMEOUT)
            if proc.returncode != 0:
                return jsonify({"error": f"pg_dump failed: {(proc.stderr or '')[:BACKUP_STDERR_PREVIEW_LEN]}"}), 500
            body = "\n".join([DUMP_MARKER,
                              f"-- exported: {datetime.now().isoformat(timespec='seconds')} — restore via Master Data ▸ Backup & Restore",
                              _strip_pointer_rows(proc.stdout)])
            log_activity("store.backup", entity="store",
                         detail=f"SQL dump downloaded ({len(body)} chars)")
            return Response(body, mimetype="application/sql",
                            headers={"Content-Disposition": f"attachment; filename=kiranapro-backup-{stamp}.sql"})

        buf = io.BytesIO()
        counts = {}
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("README.txt",
                        "KiranaPro CSV backup. This whole .zip can be restored via "
                        "Master Data > Backup & Restore (login accounts are kept).\n"
                        "app_users.csv omits password hashes; activity_log is not exported.\n")
            for table in CSV_TABLES:
                select = _csv_select(table)
                p = subprocess.run(["psql", dsn, "-q", "-c",
                                    f"COPY ({select}) TO STDOUT WITH (FORMAT csv, HEADER true)"],
                                   capture_output=True, timeout=BACKUP_PSQL_TIMEOUT)
                if p.returncode != 0:
                    return jsonify({"error": f"psql COPY {table} failed: {(p.stderr or b'')[:BACKUP_STDERR_PREVIEW_LEN]!r}"}), 500
                zf.writestr(f"{table}.csv", p.stdout)
                counts[table] = max(0, p.stdout.count(b"\n") - 1)
        log_activity("store.backup", entity="store",
                     detail="CSV zip downloaded: " + ", ".join(f"{t}={n}" for t, n in counts.items()))
        return Response(buf.getvalue(), mimetype="application/zip",
                        headers={"Content-Disposition": f"attachment; filename=kiranapro-backup-{stamp}-csv.zip"})
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Backup timed out (large database?)"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _sqlite_columns(cur, table):
    cur.execute(f'PRAGMA table_info("{table}")')
    return [r['name'] for r in cur.fetchall()]


def _sql_literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, bytes):
        return f"X'{value.hex()}'"
    if hasattr(value, "isoformat"):
        value = value.isoformat()
    return "'" + str(value).replace("'", "''") + "'"


def _sqlite_sql_dump():
    """Portable INSERT dump (no app_users / activity_log / DB pointer)."""
    from .db import db_cursor
    lines = [DUMP_MARKER,
             "-- exported from SQLite — restore via Master Data > Backup & Restore"]
    counts = {}
    with db_cursor() as cur:
        for table in CSV_RESTORE_ORDER:
            cur.execute(_csv_select(table))
            rows = cur.fetchall()
            cols = list(rows[0].keys()) if rows else _sqlite_columns(cur, table)
            col_sql = ", ".join(f'"{c}"' for c in cols)
            for row in rows:
                values = ", ".join(_sql_literal(row.get(c)) for c in cols)
                lines.append(f"INSERT INTO public.{table} ({col_sql}) VALUES ({values});")
            counts[table] = len(rows)
    return "\n".join(lines) + "\n", counts


def _sqlite_csv_zip():
    import csv
    import io
    import zipfile
    from .db import db_cursor
    buf = io.BytesIO()
    counts = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt",
                    "KiranaPro CSV backup. This whole .zip can be restored via "
                    "Master Data > Backup & Restore (login accounts are kept).\n"
                    "app_users.csv omits password hashes; activity_log is not exported.\n")
        with db_cursor() as cur:
            for table in CSV_TABLES:
                cur.execute(_csv_select(table))
                rows = cur.fetchall()
                header = [d[0] for d in cur.description]
                out = io.StringIO()
                w = csv.DictWriter(out, fieldnames=header, extrasaction='ignore')
                w.writeheader()
                for row in rows:
                    w.writerow({k: row.get(k) for k in header})
                zf.writestr(f"{table}.csv", out.getvalue())
                counts[table] = len(rows)
    return buf.getvalue(), counts


def _reset_pg_sequences():
    """Explicit IDs restored from a SQLite dump don't advance Postgres sequences."""
    from .db import db_cursor
    try:
        with db_cursor(commit=True) as cur:
            for table, pk in CSV_PK_COL.items():
                cur.execute(
                    f"""SELECT setval(pg_get_serial_sequence(%s, %s),
                                      COALESCE((SELECT MAX("{pk}") FROM "{table}"), 1),
                                      (SELECT COUNT(*) FROM "{table}") > 0)""",
                    (table, pk))
    except Exception:
        pass


def _csv_select(table):
    if table == "app_users":
        return ("SELECT user_id, username, role, full_name, created_at "
                "FROM app_users ORDER BY user_id")
    if table == "store_settings":
        # Pointer keys hold the remote database URL (secret): never export.
        return ("SELECT * FROM store_settings WHERE key NOT IN "
                f"('{POINTER_ACTIVE_KEY}', '{POINTER_URL_KEY}') ORDER BY key")
    return f"SELECT * FROM {table}"


@store_bp.route('/api/restore', methods=['POST'])
@login_required
@admin_required
def upload_restore():
    """Restore a backup from /api/backup. Replaces all business data in
    one transaction (psycopg2); login accounts and the activity log are
    untouched.
    Two formats (auto-detected):
    - .sql dump: tokenised into statements and shape-checked — only INSERTs
      into whitelisted tables, SET preamble and sequence setvals are
      executed; anything else aborts the whole restore.
    - .zip CSV backup: one <table>.csv per business table (with header row,
      as produced by /api/backup?format=csv). Headers are validated against
      the live schema and rows are loaded with COPY, so NULLs survive the
      round-trip. app_users.csv (credential-free) is informational only and
      never restored.
    Body: multipart file field 'file'."""
    if 'file' not in request.files:
        return jsonify({"error": "Backup file required (field name 'file')"}), 400
    f = request.files['file']
    raw = f.read(MAX_BACKUP_BYTES + 1)
    if len(raw) > MAX_BACKUP_BYTES:
        return jsonify({"error": "File too large (max 50MB)"}), 400
    if not raw:
        return jsonify({"error": "Empty file"}), 400
    fname = (f.filename or '').lower()
    if fname.endswith('.zip') or raw[:2] == b'PK':
        return _restore_csv_zip(raw)
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return jsonify({"error": "Not a .sql dump or CSV .zip backup file"}), 400

    try:
        stmts = _split_statements(text)
    except ValueError as e:
        return jsonify({"error": f"Invalid SQL file: {e}"}), 400

    tables, ok_stmts = set(), []
    for stmt in stmts:
        kind = _classify_stmt(stmt)
        if kind == "skip":
            continue
        if kind == "app_users":
            if "password_hash" in _strip_quotes(stmt).lower():
                return jsonify({"error": "Dump contains app_users credential columns — not allowed"}), 400
            continue  # informational only; never restored
        if kind == "bad":
            return jsonify({"error": "Only data dumps (INSERT / SET / setval) from /api/backup "
                                     "can be restored"}), 400
        for t in BACKUP_TABLES:
            if stmt.lower().startswith(f"insert into public.{t} "):
                tables.add(t)
        ok_stmts.append(stmt)
    if not ok_stmts or not tables:
        return jsonify({"error": "No business-table INSERT statements found — not a data dump"}), 400

    counts = {t: sum(1 for x in ok_stmts if x.lower().startswith(f"insert into public.{t} ")) for t in tables}
    from .db import active_backend, get_db_connection
    sqlite_backend = active_backend() == "sqlite"
    pointer = _capture_db_pointer()
    try:
        conn = get_db_connection()
        conn.autocommit = False
        if sqlite_backend:
            conn.begin()
        cur = None
        try:
            cur = conn.cursor()
            for t in BACKUP_TABLES:  # wipe everything first, then load the dump
                cur.execute(f'DELETE FROM "{t}"' if sqlite_backend
                            else f'TRUNCATE TABLE "{t}" CASCADE')
            for stmt in ok_stmts:
                cur.execute(stmt)
            conn.commit()
        except Exception as e:
            conn.rollback()
            return jsonify({"error": f"Restore failed (rolled back): {e}"}), 400
        finally:
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    pass
            conn.close()
    except Exception as e:
        return jsonify({"error": f"Restore failed: {e}"}), 400

    _restore_db_pointer(*pointer)
    if active_backend() == "postgres":
        _reset_pg_sequences()
    from .activity import log_activity
    log_activity("store.restore", entity="store",
                 detail="restored from SQL dump: " + ", ".join(f"{t}={n}" for t, n in sorted(counts.items())))
    return jsonify({"status": "success", "restored": counts})


# --- CSV-zip restore (.zip from /api/backup?format=csv) ---
# Load order: parents before children so immediate FK checks pass.
# (TRUNCATE uses BACKUP_TABLES order with CASCADE; loading is reversed.)
CSV_RESTORE_ORDER = ("categories", "customers", "products", "purchases", "store_settings",
                     "expenses", "orders",
                     "order_items", "udhaar_ledger", "returns")
# Serial PK per table, for sequence reset after COPY (store_settings has a TEXT PK).
CSV_PK_COL = {"categories": "category_id", "customers": "customer_id",
              "products": "product_id", "purchases": "purchase_id", "orders": "order_id",
              "order_items": "item_id", "udhaar_ledger": "transaction_id",
              "returns": "return_id", "expenses": "expense_id"}
MAX_CSV_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


def _restore_csv_zip(raw):
    """Restore business data from a CSV-backup zip (see upload_restore)."""
    import csv
    import io
    import zipfile

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return jsonify({"error": "Not a valid .zip backup file"}), 400
    try:
        infos = zf.infolist()
    except Exception:
        return jsonify({"error": "Could not read .zip backup file"}), 400
    if len(infos) > 32:
        return jsonify({"error": "Too many files in backup zip"}), 400
    if sum(i.file_size for i in infos) > MAX_CSV_UNCOMPRESSED_BYTES:
        return jsonify({"error": "Uncompressed backup too large (max 200MB)"}), 400

    wanted = {}
    for info in infos:
        name = info.filename.rsplit('/', 1)[-1]
        if not name or info.is_dir() or name == 'README.txt':
            continue
        if not name.endswith('.csv'):
            return jsonify({"error": f"Unexpected file in backup: {name}"}), 400
        table = name[:-4]
        if table == 'app_users':
            continue  # credential-free info only; login accounts are never restored
        if table not in BACKUP_TABLES:
            return jsonify({"error": f"Unexpected table in backup: {table}"}), 400
        if table in wanted:
            return jsonify({"error": f"Duplicate table in backup: {table}"}), 400
        try:
            wanted[table] = zf.read(info.filename)
        except Exception:
            return jsonify({"error": f"Could not read {name} from backup"}), 400
    # Validate CSV shape before touching any data (column names are checked
    # against the live schema below). Tables missing from the zip (e.g. older
    # backups predating a new table) restore as empty, like the .sql path.
    staged = {}
    try:
        for table in CSV_RESTORE_ORDER:
            if table not in wanted:
                continue
            try:
                text = wanted[table].decode('utf-8-sig')
            except UnicodeDecodeError:
                return jsonify({"error": f"{table}.csv is not valid UTF-8 text"}), 400
            head, _, body = text.partition('\n')
            header = next(csv.reader([head]))
            header = [h.strip() for h in header if h.strip()]
            if not header:
                return jsonify({"error": f"{table}.csv has no header row"}), 400
            if len(set(header)) != len(header):
                return jsonify({"error": f"{table}.csv has duplicate columns"}), 400
            if any('"' in h for h in header):
                return jsonify({"error": f"{table}.csv has an invalid column name"}), 400
            staged[table] = (header, body)
    except ValueError as e:
        return jsonify({"error": f"Invalid CSV in backup: {e}"}), 400

    from .db import active_backend, get_db_connection
    sqlite_backend = active_backend() == "sqlite"
    pointer = _capture_db_pointer()
    try:
        conn = get_db_connection()
        conn.autocommit = False
        if sqlite_backend:
            conn.begin()
        cur = None
        try:
            cur = conn.cursor()
            live_cols = {}
            for table in CSV_RESTORE_ORDER:
                if sqlite_backend:
                    live_cols[table] = _sqlite_columns(cur, table)
                else:
                    cur.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = %s "
                        "ORDER BY ordinal_position", (table,))
                    live_cols[table] = [r['column_name'] for r in cur.fetchall()]
            for table in CSV_RESTORE_ORDER:
                unknown = [h for h in staged[table][0] if h not in live_cols[table]] if table in staged else []
                if unknown:
                    raise ValueError(
                        f"{table}.csv has unknown column(s): {', '.join(unknown)}")
            emptied = [t for t in BACKUP_TABLES if t not in staged]
            for table in emptied:
                staged[table] = (live_cols[table], "")
            for t in BACKUP_TABLES:  # wipe everything first, then load the dump
                cur.execute(f'DELETE FROM "{t}"' if sqlite_backend
                            else f'TRUNCATE TABLE "{t}" CASCADE')
            counts = {}
            for table in CSV_RESTORE_ORDER:
                header, body = staged[table]
                cols = ", ".join(f'"{h}"' for h in header)
                if sqlite_backend:
                    rows = [r for r in csv.reader(io.StringIO(body)) if r]
                    placeholders = ", ".join("?" for _ in header)
                    insert = f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders})'
                    for row in rows:
                        if len(row) != len(header):
                            raise ValueError(
                                f"{table}.csv has a row with {len(row)} values "
                                f"(expected {len(header)})")
                        cur.execute(insert, [None if v == '' else v for v in row])
                    counts[table] = len(rows)
                else:
                    cur.copy_expert(
                        f'COPY "{table}" ({cols}) FROM STDIN WITH (FORMAT csv)',
                        io.StringIO(body))
                    counts[table] = cur.rowcount
            if not sqlite_backend:
                for table, pk in CSV_PK_COL.items():
                    cur.execute(
                        f"""SELECT setval(pg_get_serial_sequence(%s, %s),
                                          COALESCE((SELECT MAX("{pk}") FROM "{table}"), 1),
                                          (SELECT COUNT(*) FROM "{table}") > 0)""",
                        (table, pk))
            conn.commit()
        except Exception as e:
            conn.rollback()
            msg = str(e)
            if 'violates foreign key constraint' in msg and 'app_users' in msg:
                msg += (" — backup references login accounts that don't exist here; "
                        "recreate matching users first")
            return jsonify({"error": f"Restore failed (rolled back): {msg}"}), 400
        finally:
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    pass
            conn.close()
    except Exception as e:
        return jsonify({"error": f"Restore failed: {e}"}), 400

    _restore_db_pointer(*pointer)
    from .activity import log_activity
    detail = "restored from CSV backup: " + ", ".join(f"{t}={n}" for t, n in sorted(counts.items()))
    if emptied:
        detail += f" (not in backup, restored empty: {', '.join(sorted(emptied))})"
    log_activity("store.restore", entity="store", detail=detail)
    out = {"status": "success", "restored": counts, "format": "csv"}
    if emptied:
        out["warning"] = f"Tables not in backup, restored empty: {', '.join(sorted(emptied))}"
    return jsonify(out)


_BAD_TOKENS = ("drop ", "alter ", "grant ", "revoke ", "create ", "truncate ",
               "vacuum ", "cluster ", "reindex ", "comment on ", "security label",
               "set role", "session authorization", "copy ", "pg_sleep", "dblink",
               "lo_open", "lo_write", "lo_import", "lo_export", "exec ", "utl_")


def _classify_stmt(stmt):
    """Return 'skip' / 'app_users' / 'bad' / 'ok' for one tokenised statement."""
    collapsed = " ".join(stmt.split())
    low = collapsed.lower()
    if not collapsed or collapsed.startswith("--") or collapsed.startswith("\\"):
        return "skip"
    if low.startswith("insert into public.app_users "):
        return "app_users"
    if any(w in _strip_quotes(collapsed).lower() for w in _BAD_TOKENS):
        return "bad"
    if low.startswith("insert into public."):
        table = collapsed[len("INSERT INTO public."):].split(" ")[0].strip("(").lower()
        return "ok" if table in BACKUP_TABLES else "bad"
    if low.startswith("set ") or low.startswith("select pg_catalog.setval") or \
            low.startswith("select pg_catalog.set_config"):
        return "ok"
    if low in ("begin", "commit", "start transaction"):
        return "skip"
    return "bad"


def _split_statements(text):
    """Split SQL into statements with a quote/comment-aware scanner (no
    dollar-quoting support — pg_dump --column-inserts never emits it)."""
    stmts, buf, i, n = [], [], 0, len(text)
    in_str = False
    while i < n:
        ch = text[i]
        if in_str:
            if ch == "'":
                if i + 1 < n and text[i + 1] == "'":
                    buf.append("''"); i += 2; continue
                in_str = False
            buf.append(ch); i += 1; continue
        if ch == "'":
            in_str = True; buf.append(ch); i += 1; continue
        if ch == "-" and text[i:i + 2] == "--":
            j = text.find("\n", i)
            i = n if j < 0 else j; continue
        if ch == "/" and text[i:i + 2] == "/*":
            j = text.find("*/", i + 2)
            if j < 0:
                raise ValueError("unterminated block comment")
            i = j + 2; continue
        if ch == ";":
            buf.append(ch)
            stmts.append("".join(buf).strip())
            buf = []; i += 1; continue
        buf.append(ch); i += 1
    if in_str:
        raise ValueError("unterminated string literal")
    rest = "".join(buf).strip()
    if rest:
        stmts.append(rest)
    return stmts


def _strip_quotes(s):
    """Blank out string literal contents so keyword checks only see code."""
    out, in_str, i, n = [], False, 0, len(s)
    while i < n:
        ch = s[i]
        if in_str:
            if ch == "'":
                if i + 1 < n and s[i + 1] == "'":
                    i += 2; continue
                in_str = False
            i += 1; continue
        if ch == "'":
            in_str = True; out.append("''"); i += 1; continue
        out.append(ch); i += 1
    return "".join(out)
