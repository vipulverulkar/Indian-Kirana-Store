"""Shared database helpers + project paths.

Local ("primary") storage can be either PostgreSQL or a single-file SQLite
database. A remote database is always PostgreSQL and lives behind the same
Store Settings -> Database switch used before. SQLite needs no server and no
`pg_dump`/`psql`: it is the standalone mode.

Selection:
    DB_BACKEND=sqlite            → local SQLite (default when no DB config)
    DB_BACKEND=postgres          → local PostgreSQL
    SQLITE_PATH=/path/store.db   → SQLite file (default: <project>/kirana.db)
    DATABASE_URL=sqlite:///...   → SQLite via URL
    DATABASE_URL=postgresql://…  → local PostgreSQL via URL
    DB_NAME/DB_USER/…            → local PostgreSQL via split vars

Remote stays PostgreSQL because the switch endpoint validates/stores a
postgresql:// URL.
"""
import os
import re
import sqlite3
import sys
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlparse

try:  # Optional: SQLite-only installs do not need PostgreSQL support.
    import psycopg2
    import psycopg2.errors
    from psycopg2.extras import RealDictCursor
except Exception:  # pragma: no cover - exercised only by SQLite-only installs
    psycopg2 = None
    RealDictCursor = None

# Code/resources live inside the source tree (or the PyInstaller bundle).
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCE_DIR = getattr(sys, "_MEIPASS", _PROJECT_DIR) if getattr(sys, "frozen", False) else _PROJECT_DIR
# Backwards-compatible name: templates/, static/ and *.sql are read-only assets.
BASE_DIR = RESOURCE_DIR


def _default_data_dir():
    """Writable per-user directory for the SQLite file, uploads and secret."""
    override = (os.getenv("KIRANA_DATA_DIR") or "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if not getattr(sys, "frozen", False):
        return BASE_DIR  # source runs keep using the project folder
    if os.name == "nt":
        root = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or os.path.expanduser("~")
        return os.path.join(root, "KiranaPro")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~/Library/Application Support"), "KiranaPro")
    root = os.getenv("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(root, "kiranapro")


# Writable runtime data (SQLite DB, uploaded logo). Never inside _MEIPASS:
# one-file bundles extract to a temporary directory that is deleted on exit.
DATA_DIR = _default_data_dir()
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError:
    pass

# ---------- Database ----------
# Two server-configured modes (read lazily on every call so tests / workers
# can override env vars without reimporting). Together they are the PRIMARY
# ("Local") database — the anchor the app always boots from:
#   1. DATABASE_URL (preferred) — one connection string for local AND remote
#      managed Postgres (Neon, Supabase, RDS, Render, ...).
#      e.g. postgresql://user:password@host:5432/dbname?sslmode=require
#   2. Legacy split vars DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT.
#      Works for local AND remote hosts — just point DB_HOST at the server.
#
# SQLite (standalone):
#   DB_BACKEND=sqlite [+ SQLITE_PATH=...] or DATABASE_URL=sqlite:///...
#   No PostgreSQL server/client is required for normal app use.
#
# SSL (needed by most managed providers, harmless for local):
#   DB_SSLMODE=require  → enforced even if the URL has no ?sslmode= param,
#                         and passed as `sslmode=` kwarg in split-vars mode.
#   Leave empty for plain local Postgres (default).
#
# ---------- Runtime DB selection (Store Settings → Database) ----------
# The admin can switch the app between the PRIMARY database above ("local")
# and a SECONDARY remote database ("remote") whose URL is saved in the
# PRIMARY's store_settings table. The pointer MUST live in the primary:
# it is the only database guaranteed reachable (a dead remote must never
# block switching back). The remote URL is a secret — it is never returned
# by any API, only a `remote_configured` boolean.
POINTER_ACTIVE_KEY = "db.active"      # "local" | "remote"
POINTER_URL_KEY = "db.remote_url"     # full URL, secret
POINTER_TTL_SECONDS = 30

_POINTER_DDL = """
CREATE TABLE IF NOT EXISTS store_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

_pointer_cache = {"active": "local", "expires": 0.0}
_sqlite_init_lock = threading.Lock()
_sqlite_initialized = set()

# Exceptions callers can catch without importing psycopg2/sqlite3.
class DuplicateKeyError(Exception):
    """Raised for a UNIQUE/primary-key violation on SQLite."""


class ForeignKeyError(Exception):
    """Raised for a foreign-key violation on SQLite."""


UNIQUE_ERRORS = (DuplicateKeyError,)
FK_ERRORS = (ForeignKeyError,)
if psycopg2 is not None:
    UNIQUE_ERRORS += (psycopg2.errors.UniqueViolation,)
    FK_ERRORS += (psycopg2.errors.ForeignKeyViolation,)


def _require_pg():
    if psycopg2 is None:
        raise RuntimeError(
            "PostgreSQL support requires psycopg2-binary. "
            "Install it, or use SQLite with DB_BACKEND=sqlite."
        )
    return psycopg2


def _database_url():
    return os.getenv("DATABASE_URL", "").strip() or None


def _is_sqlite_url(url):
    return (url or "").strip().lower().startswith("sqlite:")


def _sqlite_path_from_url(url):
    raw = (url or "").strip()
    if raw.startswith("sqlite:////"):
        # sqlite:////absolute/path.db → /absolute/path.db
        return raw[len("sqlite:///"):]
    if raw.startswith("sqlite:///"):
        rest = raw[len("sqlite:///"):]
        if rest == ":memory:":
            return ":memory:"
        return os.path.join(DATA_DIR, rest)
    raise ValueError("SQLite URL must look like sqlite:///relative.db or sqlite:////absolute.db")


def _sqlite_path():
    raw = (os.getenv("SQLITE_PATH") or "").strip()
    if raw:
        if raw == ":memory:":
            return raw
        return raw if os.path.isabs(raw) else os.path.join(DATA_DIR, raw)
    url = _database_url()
    if url and _is_sqlite_url(url):
        return _sqlite_path_from_url(url)
    return os.path.join(DATA_DIR, "kirana.db")


def _local_backend():
    """'sqlite' or 'postgres' for the server-configured LOCAL database."""
    explicit = (os.getenv("DB_BACKEND") or "").strip().lower()
    if explicit in ("sqlite", "sqlite3"):
        return "sqlite"
    if explicit in ("postgres", "postgresql", "pg"):
        return "postgres"
    if _is_sqlite_url(_database_url()):
        return "sqlite"
    if _database_url() or os.getenv("DB_NAME"):
        return "postgres"
    # Zero-config standalone launch: no DB settings at all → SQLite file.
    return "sqlite"


def active_backend():
    """Backend currently serving requests: 'sqlite' or 'postgres'."""
    if _active_remote_url():
        return "postgres"
    return _local_backend()


def _sqlite_display_name(path):
    if path == ":memory:":
        return ":memory:"
    return os.path.basename(path) or path


def _sslmode():
    return (os.getenv("DB_SSLMODE", "") or "").strip().lower() or None


def _effective_url(url):
    """Append ?sslmode=DB_SSLMODE to a URL that doesn't already set it."""
    mode = _sslmode()
    if not mode or "sslmode=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}sslmode={mode}"


def _db_config():
    cfg = {
        "dbname": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT"),
    }
    if _sslmode():
        cfg["sslmode"] = _sslmode()
    return cfg


def db_mode():
    """Which server-configured mode backs the PRIMARY database."""
    if _local_backend() == "sqlite":
        return "sqlite"
    return "url" if _database_url() else "split_vars"


def _primary_connection():
    """Connect to the PRIMARY database (env config only — never routed)."""
    if _local_backend() == "sqlite":
        return _sqlite_connection()
    _require_pg()
    url = _database_url()
    if url:
        return psycopg2.connect(_effective_url(url), cursor_factory=RealDictCursor)
    cfg = _db_config()
    if not cfg.get("dbname"):
        raise RuntimeError(
            "Database not configured. Set DATABASE_URL, "
            "DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT, or DB_BACKEND=sqlite."
        )
    return psycopg2.connect(**cfg, cursor_factory=RealDictCursor)


# ---------- SQLite compatibility layer ----------
def _sqlite_dict_factory(cursor, row):
    return {d[0]: value for d, value in zip(cursor.description, row)}


def _sqlite_statements(sql):
    """Yield complete SQLite statements; understands quoted/comment-heavy DDL."""
    buf = []
    for ch in sql:
        buf.append(ch)
        if ch == ";" and sqlite3.complete_statement("".join(buf)):
            stmt = "".join(buf).strip()
            if stmt:
                yield stmt
            buf = []
    tail = "".join(buf).strip()
    if tail:
        yield tail


def _sqlite_adapt_param(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    return value


def _raise_sqlite_error(exc):
    """Map SQLite integrity errors onto the backend-neutral exceptions that
    route handlers already catch (UNIQUE_ERRORS / FK_ERRORS)."""
    msg = str(exc)
    if "UNIQUE constraint failed" in msg or "PRIMARY KEY constraint failed" in msg:
        raise DuplicateKeyError(msg) from exc
    if "FOREIGN KEY constraint failed" in msg:
        raise ForeignKeyError(msg) from exc
    raise exc


def _sqlite_adapt_params(params):
    if params is None:
        return ()
    if isinstance(params, dict):
        return {k: _sqlite_adapt_param(v) for k, v in params.items()}
    return tuple(_sqlite_adapt_param(v) for v in params)


_EXTRACT_FORMATS = {"HOUR": "%H", "DAY": "%d", "MONTH": "%m", "YEAR": "%Y"}


def _sqlite_translate(sql, has_params=True):
    """Translate the small PostgreSQL SQL dialect used by KiranaPro.

    Kept deliberately close to the queries instead of a full SQL parser: the
    app uses simple SELECT/INSERT/UPDATE/DELETE plus a handful of date helpers.
    Placeholders are only rewritten when parameters are actually supplied, so
    literal ``%s`` inside restored data is preserved.
    """
    s = sql.replace("%s", "?") if has_params else sql

    # PostgreSQL row locking is a no-op in SQLite's single-writer model.
    s = re.sub(r"\s+FOR\s+UPDATE\b", "", s, flags=re.I)

    # LIKE is case-insensitive for ASCII in SQLite, matching ILIKE closely.
    s = re.sub(r"\bILIKE\b", "LIKE", s, flags=re.I)

    # Date helpers.
    s = re.sub(
        r"CURRENT_DATE\s*-\s*INTERVAL\s*'(\d+)\s+days?'",
        r"date('now','localtime','-\1 days')", s, flags=re.I)
    s = re.sub(r"\bCURRENT_DATE\b", "date('now','localtime')", s, flags=re.I)
    s = re.sub(
        r"\bto_char\s*\(\s*([^,()]+?)\s*,\s*'YYYY-MM'\s*\)",
        r"strftime('%Y-%m', \1)", s, flags=re.I)
    s = re.sub(
        r"EXTRACT\s*\(\s*(HOUR|DAY|MONTH|YEAR)\s+FROM\s+([^)]+?)\)",
        lambda m: "CAST(strftime('{fmt}', {expr}) AS INTEGER)".format(
            fmt=_EXTRACT_FORMATS[m.group(1).upper()], expr=m.group(2).strip()),
        s, flags=re.I)
    s = re.sub(r"\?\s*::\s*int(?:eger)?\b", "CAST(? AS INTEGER)", s, flags=re.I)
    s = re.sub(r"\?\s*::\s*date\b", "date(?)", s, flags=re.I)
    s = re.sub(r"(?P<expr>\([^()]*\)|[A-Za-z_][\w.]*)\s*::\s*date\b",
               lambda m: "date(%s)" % m.group("expr"), s, flags=re.I)
    s = re.sub(r"\s*::\s*(?:int|integer)\b", "", s, flags=re.I)
    s = re.sub(r"\s*::\s*(?:numeric|decimal|text|varchar|timestamp(?:tz)?)\b",
               "", s, flags=re.I)
    s = re.sub(r"\bNOW\s*\(\s*\)", "CURRENT_TIMESTAMP", s, flags=re.I)

    # PostgreSQL scalar functions with direct SQLite equivalents.
    s = re.sub(r"\bGREATEST\s*\(", "MAX(", s, flags=re.I)
    s = re.sub(r"\bLEAST\s*\(", "MIN(", s, flags=re.I)

    # pg_dump-style schema qualification + TRUNCATE.
    s = re.sub(r"\b(INTO|FROM|JOIN|UPDATE|TABLE)\s+public\.", r"\1 ", s, flags=re.I)
    s = re.sub(r"\bTRUNCATE\s+(?:TABLE\s+)?([\"\w.]+)(?:\s+CASCADE)?",
               r"DELETE FROM \1", s, flags=re.I)
    return s


class SQLiteCursor:
    def __init__(self, cursor):
        self._cur = cursor

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def description(self):
        return self._cur.description

    def execute(self, sql, params=None):
        statements = list(_sqlite_statements(sql))
        if not statements:
            return self
        adapted = _sqlite_adapt_params(params)
        for stmt in statements:
            low = " ".join(stmt.strip().split()).lower()
            # pg_dump / psql preamble: harmless here, unsupported by SQLite.
            if low.startswith(("set ", "select pg_catalog.setval",
                               "select pg_catalog.set_config")) or \
                    low in ("begin", "begin transaction", "start transaction",
                            "commit", "end"):
                continue
            single = len(statements) == 1
            try:
                self._cur.execute(
                    _sqlite_translate(stmt, has_params=params is not None and single),
                    adapted if single else ())
            except sqlite3.IntegrityError as e:
                _raise_sqlite_error(e)
        return self

    def executemany(self, sql, seq_of_params):
        stmt = _sqlite_translate(sql)
        try:
            self._cur.executemany(stmt, [_sqlite_adapt_params(p) for p in seq_of_params])
        except sqlite3.IntegrityError as e:
            _raise_sqlite_error(e)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, size=None):
        return self._cur.fetchmany(size) if size is not None else self._cur.fetchmany()

    def __iter__(self):
        return iter(self._cur)

    def close(self):
        self._cur.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


class SQLiteConnection:
    def __init__(self, path):
        if path != ":memory:":
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(path, timeout=30)
        self._conn.row_factory = _sqlite_dict_factory
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=10000")
        if path != ":memory:":
            try:
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
            except sqlite3.DatabaseError:
                pass
        # FK checks stay immediate for normal app writes; restore paths call
        # begin(), which defers them until commit after journal_mode is set.
        self.autocommit = False

    def cursor(self):
        return SQLiteCursor(self._conn.cursor())

    def begin(self):
        self._conn.execute("PRAGMA defer_foreign_keys=ON")
        self._conn.execute("BEGIN")

    def commit(self):
        try:
            self._conn.commit()
        except sqlite3.IntegrityError as e:
            _raise_sqlite_error(e)

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def _sqlite_connection():
    return SQLiteConnection(_sqlite_path())


def _seed_sqlite_catalog(conn):
    """Reuse the product seed INSERTs from init_db.sql (kept in one place)."""
    schema_path = os.path.join(BASE_DIR, "init_db.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        text = f.read()
    for stmt in _sqlite_statements(text):
        lines = stmt.splitlines()
        while lines and (not lines[0].strip() or lines[0].lstrip().startswith("--")):
            lines.pop(0)
        clean = "\n".join(lines).strip()
        if " ".join(clean.split()).lower().startswith("insert into products"):
            conn.execute(clean)


def ensure_local_database():
    """Create/bootstrap a standalone SQLite database. No-op for PostgreSQL.

    Runs automatically from create_app(), so `python app.py` works on a fresh
    checkout with no database server. The schema and product catalog are
    applied once; login accounts are only created if the database has none.
    """
    if _local_backend() != "sqlite":
        return False
    path = _sqlite_path()
    if path == ":memory:":
        raise RuntimeError("SQLITE_PATH=:memory: is not supported by the web app")
    with _sqlite_init_lock:
        if path in _sqlite_initialized:
            return True
        schema_path = os.path.join(BASE_DIR, "init_db_sqlite.sql")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(path, timeout=30)
        try:
            had_products = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='products'"
            ).fetchone() is not None
            conn.executescript(schema)
            if not had_products:
                _seed_sqlite_catalog(conn)
                conn.execute(
                    "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('catalog', 'init_db.sql')"
                )
            # Keep category dropdowns in sync with product categories.
            conn.execute(
                """INSERT INTO categories (name)
                   SELECT DISTINCT TRIM(category) FROM products
                   WHERE category IS NOT NULL AND TRIM(category) <> ''
                   ON CONFLICT (name) DO NOTHING"""
            )
            n_users = conn.execute("SELECT COUNT(*) FROM app_users").fetchone()[0]
            if not n_users:
                from werkzeug.security import generate_password_hash
                users = [
                    (os.getenv("SEED_ADMIN_USER", "admin"),
                     generate_password_hash(os.getenv("SEED_ADMIN_PASSWORD", "admin123")),
                     "admin", "Store Owner"),
                    (os.getenv("SEED_STAFF_USER", "staff"),
                     generate_password_hash(os.getenv("SEED_STAFF_PASSWORD", "staff123")),
                     "staff", "Counter Staff"),
                ]
                for username, pw_hash, role, full_name in users:
                    conn.execute(
                        """INSERT INTO app_users (username, password_hash, role, full_name)
                           VALUES (?, ?, ?, ?) ON CONFLICT (username) DO NOTHING""",
                        (username, pw_hash, role, full_name))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Could not initialize SQLite database at {path}: {e}")
        finally:
            conn.close()
        _sqlite_initialized.add(path)
    return True


def parse_db_url(url):
    """Validate a postgresql:// URL. Returns {host, dbname} or raises ValueError."""
    url = (url or "").strip()
    if not url:
        raise ValueError("Database URL is required")
    try:
        parts = urlparse(url)
    except Exception:
        raise ValueError("Invalid database URL")
    if parts.scheme not in ("postgresql", "postgres"):
        raise ValueError("URL must start with postgresql:// (remote database is PostgreSQL)")
    if not parts.hostname:
        raise ValueError("URL must include a host")
    dbname = (parts.path or "").lstrip("/") or None
    if not dbname:
        raise ValueError("URL must include a database name")
    return {"host": parts.hostname, "dbname": dbname}


def test_db_url(url, timeout=5):
    """Open a short-lived connection to a candidate remote URL.

    Returns {"host":..., "dbname":..., "version":...} or raises RuntimeError
    with a short, password-free message."""
    parse_db_url(url)  # raises ValueError on bad shape
    _require_pg()
    try:
        conn = psycopg2.connect(_effective_url(url.strip()),
                                cursor_factory=RealDictCursor,
                                connect_timeout=timeout)
    except Exception as e:
        raise RuntimeError(f"Could not connect: {str(e)[:200]}")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT version() AS v")
            version = (cur.fetchone() or {}).get("v", "")
    except Exception as e:
        raise RuntimeError(f"Connected but query failed: {str(e)[:200]}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
    info = parse_db_url(url)
    info["version"] = (version or "")[:120]
    return info


def get_db_pointer():
    """Which database the app should use: {"active": "local"|"remote"}.

    Read from the PRIMARY database (never routed) with a short TTL cache,
    so a dead remote can never block pointer reads. Never raises —
    any failure means "local"."""
    now = time.monotonic()
    if now < _pointer_cache["expires"]:
        return {"active": _pointer_cache["active"]}
    active = "local"
    try:
        conn = _primary_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(_POINTER_DDL)
                conn.commit()
                cur.execute("SELECT value FROM store_settings WHERE key = %s",
                            (POINTER_ACTIVE_KEY,))
                row = cur.fetchone()
                if row and (row.get("value") or "") in ("local", "remote"):
                    active = row["value"]
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        active = "local"
    _pointer_cache["active"] = active
    _pointer_cache["expires"] = now + POINTER_TTL_SECONDS
    return {"active": active}


def get_remote_url():
    """Full remote URL from the PRIMARY database, or None. Secret: never
    log it, never return it from an API."""
    try:
        conn = _primary_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM store_settings WHERE key = %s",
                            (POINTER_URL_KEY,))
                row = cur.fetchone()
                url = ((row or {}).get("value") or "").strip()
                return url or None
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        return None


def set_db_pointer(active, remote_url=None):
    """Save the DB selection to the PRIMARY database (never routed) and
    drop the pointer cache so the switch takes effect immediately."""
    if active not in ("local", "remote"):
        raise ValueError("active must be 'local' or 'remote'")
    if active == "remote":
        parse_db_url(remote_url)  # raises ValueError on bad shape
    conn = _primary_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(_POINTER_DDL)
            cur.execute(
                """INSERT INTO store_settings (key, value, updated_at)
                   VALUES (%s, %s, CURRENT_TIMESTAMP)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,
                   updated_at = CURRENT_TIMESTAMP""",
                (POINTER_ACTIVE_KEY, active))
            if remote_url is not None:
                cur.execute(
                    """INSERT INTO store_settings (key, value, updated_at)
                       VALUES (%s, %s, CURRENT_TIMESTAMP)
                       ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,
                       updated_at = CURRENT_TIMESTAMP""",
                    (POINTER_URL_KEY, remote_url.strip()))
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass
    _pointer_cache["active"] = active
    _pointer_cache["expires"] = time.monotonic() + POINTER_TTL_SECONDS


def _active_remote_url():
    """Effective remote URL if the pointer selects it, else None."""
    if get_db_pointer()["active"] != "remote":
        return None
    return get_remote_url()


def db_target_info():
    """Safe display info for the database currently in use (no secrets):
    {active, mode, host, dbname}. Best-effort — never raises."""
    try:
        url = _active_remote_url()
        if url:
            info = parse_db_url(url)
            return {"active": "remote", "mode": "url",
                    "host": info["host"], "dbname": info["dbname"]}
        if _local_backend() == "sqlite":
            path = _sqlite_path()
            return {"active": "local", "mode": "sqlite",
                    "host": None, "dbname": _sqlite_display_name(path)}
        if _database_url():
            info = parse_db_url(_database_url())
            return {"active": "local", "mode": "url",
                    "host": info["host"], "dbname": info["dbname"]}
        cfg = _db_config()
        return {"active": "local", "mode": "split_vars",
                "host": cfg.get("host"), "dbname": cfg.get("dbname")}
    except Exception:
        return {"active": "local", "mode": db_mode(),
                "host": None, "dbname": None}


def get_db_connection():
    """Connect to the ACTIVE database (Store Settings → Database selection).

    Raises RuntimeError with a clear message when the remote is selected but
    unreachable — never silently falls back, so bills can't land in the
    wrong database."""
    url = _active_remote_url()
    if url:
        _require_pg()
        try:
            return psycopg2.connect(_effective_url(url),
                                    cursor_factory=RealDictCursor)
        except Exception as e:
            raise RuntimeError(
                "Remote database unreachable. Switch back to Local in "
                f"Store Settings → Database. ({str(e)[:200]})"
            )
    return _primary_connection()


def db_dsn():
    """libpq connection string / path for the ACTIVE database (pg_dump/psql)."""
    if active_backend() == "sqlite":
        return _sqlite_path()
    _require_pg()
    url = _active_remote_url() or _database_url()
    if url:
        return _effective_url(url)
    cfg = _db_config()
    if not cfg.get("dbname"):
        raise RuntimeError(
            "Database not configured. Set DATABASE_URL "
            "or DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT in .env."
        )
    return " ".join(
        f"{kw}={_pq_escape(val)}" for kw, val in
        (("host", cfg.get("host")), ("port", cfg.get("port")),
         ("dbname", cfg.get("dbname")), ("user", cfg.get("user")),
         ("password", cfg.get("password")),
         ("sslmode", cfg.get("sslmode"))) if val)


def _pq_escape(value):
    s = str(value)
    needs = not s or any(c in s for c in " \\'")
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'" if needs else s


@contextmanager
def db_cursor(commit=False):
    conn = get_db_connection()
    cur = None
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            if cur is not None:
                cur.close()
        except Exception:
            pass
        conn.close()
