"""Persistent store defaults (Settings menu).

Single source of truth for everything the admin can tune in the UI:
store profile, billing, loyalty/Udhaar and inventory defaults.

Stored in the ``store_settings`` table as TEXT key/value rows so new keys can
be added without migrations. ``get_all_settings()`` merges DB rows over
builtin defaults, with ``STORE_*`` env vars as first-run fallbacks for the
store profile (so existing .env installs keep working).
"""
import os
from decimal import Decimal, InvalidOperation

from .constants import (
    ALL_PAYMENT_MODES,
    ALL_UNITS,
    DEFAULT_EXPENSE_CATEGORY,
    DEFAULT_INVOICE_FOOTER,
    DEFAULT_PAYMENT_MODE,
    DEFAULT_STORE_LOCATION,
    DEFAULT_STORE_NAME,
    DEFAULT_UNIT,
    MAX_DISCOUNT_ALLOWED_PCT,
    MAX_GST_SLAB,
    MAX_LEN_EXPENSE_CATEGORY,
    MAX_LEN_GSTIN,
    MAX_LEN_INVOICE_FOOTER,
    MAX_LEN_STORE_ADDRESS,
    MAX_LEN_STORE_LOCATION,
    MAX_LEN_STORE_NAME,
    MAX_LEN_STORE_PHONE_COL,
    MAX_LEN_STORE_PHONE_MAX,
    MAX_LEN_STORE_PHONE_MIN,
    MAX_LEN_UPI_ID,
    MAX_LOYALTY_EARN_PER_RS,
    MAX_REDEEM_CAP_PCT,
    MIN_DISCOUNT_PCT,
    MIN_GST_SLAB,
    MIN_LOYALTY_EARN_PER_RS,
)
from .db import db_cursor
from .utils import to_decimal

SETTINGS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS store_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

# Canonical defaults (strings — the table stores TEXT).
SETTING_DEFAULTS = {
    # --- Store profile ---
    "store_name": DEFAULT_STORE_NAME,
    "store_location": DEFAULT_STORE_LOCATION,
    "store_address": "",
    "store_phone": "",
    "store_gstin": "",
    "upi_id": "",
    "invoice_footer": DEFAULT_INVOICE_FOOTER,
    # --- Billing ---
    "default_payment_mode": DEFAULT_PAYMENT_MODE,
    "max_discount_pct": "50",
    "default_expense_category": DEFAULT_EXPENSE_CATEGORY,
    "gst_slabs": "0,5,12,18,28",
    # --- Loyalty & Udhaar ---
    "default_credit_limit": "10000",
    "loyalty_earn_per_rs": "100",
    "loyalty_redeem_cap_pct": "20",
    # --- Inventory (new-product defaults) ---
    "default_unit": DEFAULT_UNIT,
    "default_gst_slab": "5",
    "default_min_threshold": "5",
}

PAYMENT_MODES = ALL_PAYMENT_MODES
UNITS = ALL_UNITS


def ensure_settings_table():
    with db_cursor(commit=True) as cur:
        cur.execute(SETTINGS_TABLE_DDL)


def _env_fallback(key):
    mapping = {
        "store_name": os.getenv("STORE_NAME", ""),
        "store_location": os.getenv("STORE_LOCATION", ""),
        "store_address": os.getenv("STORE_ADDRESS", ""),
        "store_phone": os.getenv("STORE_PHONE", ""),
    }
    return mapping.get(key, "")


def get_all_settings():
    """Return {key: value} merged as DB row > env (store_*) > builtin default."""
    ensure_settings_table()
    try:
        with db_cursor() as cur:
            cur.execute("SELECT key, value FROM store_settings")
            rows = cur.fetchall()
    except Exception:
        rows = []
    db_vals = {r["key"]: r["value"] for r in (rows or []) if r.get("key") in SETTING_DEFAULTS}
    out = {}
    for key, default in SETTING_DEFAULTS.items():
        if key in db_vals and db_vals[key] is not None:
            out[key] = db_vals[key]
        elif key.startswith("store_") and _env_fallback(key):
            out[key] = _env_fallback(key)
        else:
            out[key] = default
    # STORE_* env documented as first-run fallback; empty env falls back to default.
    if not out.get("store_name"):
        out["store_name"] = SETTING_DEFAULTS["store_name"]
    if not out.get("store_location"):
        out["store_location"] = SETTING_DEFAULTS["store_location"]
    return out


def get_setting(key, default=None):
    vals = get_all_settings()
    if key in vals:
        return vals[key]
    return default if default is not None else SETTING_DEFAULTS.get(key)


def validate_settings(payload):
    """Validate a partial/full settings dict. Returns cleaned {key: str} or raises ValueError."""
    if not isinstance(payload, dict):
        raise ValueError("Settings payload must be a JSON object")
    unknown = [k for k in payload if k not in SETTING_DEFAULTS]
    if unknown:
        raise ValueError(f"Unknown setting(s): {', '.join(unknown)}")
    cleaned = {}
    for key, raw in payload.items():
        v = "" if raw is None else str(raw).strip()
        if key == "store_name":
            if not v:
                raise ValueError("Store name is required")
            if len(v) > MAX_LEN_STORE_NAME:
                raise ValueError(f"Store name too long (max {MAX_LEN_STORE_NAME})")
            cleaned[key] = v
        elif key in ("store_location",):
            if len(v) > MAX_LEN_STORE_LOCATION:
                raise ValueError(f"Store location too long (max {MAX_LEN_STORE_LOCATION})")
            cleaned[key] = v
        elif key == "store_address":
            if len(v) > MAX_LEN_STORE_ADDRESS:
                raise ValueError(f"Store address too long (max {MAX_LEN_STORE_ADDRESS})")
            cleaned[key] = v
        elif key == "store_phone":
            if v and (len(v) < MAX_LEN_STORE_PHONE_MIN or len(v) > MAX_LEN_STORE_PHONE_MAX):
                raise ValueError(f"Phone must be {MAX_LEN_STORE_PHONE_MIN}–{MAX_LEN_STORE_PHONE_MAX} characters")
            if len(v) > MAX_LEN_STORE_PHONE_COL:
                raise ValueError("Phone too long")
            cleaned[key] = v
        elif key == "invoice_footer":
            if len(v) > MAX_LEN_INVOICE_FOOTER:
                raise ValueError(f"Invoice footer too long (max {MAX_LEN_INVOICE_FOOTER})")
            cleaned[key] = v
        elif key == "store_gstin":
            if v:
                compact = v.replace(" ", "").upper()
                if len(compact) != MAX_LEN_GSTIN or not compact.isalnum():
                    raise ValueError(f"GSTIN must be {MAX_LEN_GSTIN} letters/digits (or blank)")
                cleaned[key] = compact
            else:
                cleaned[key] = ""
        elif key == "upi_id":
            if v:
                if "@" not in v or len(v) > MAX_LEN_UPI_ID:
                    raise ValueError(f"UPI ID looks like name@bank (max {MAX_LEN_UPI_ID})")
                cleaned[key] = v
            else:
                cleaned[key] = ""
        elif key == "default_payment_mode":
            if v not in PAYMENT_MODES:
                raise ValueError(f"Payment mode must be one of {', '.join(PAYMENT_MODES)}")
            cleaned[key] = v
        elif key == "default_expense_category":
            if not v:
                raise ValueError("Default expense category is required")
            if len(v) > MAX_LEN_EXPENSE_CATEGORY:
                raise ValueError(f"Expense category too long (max {MAX_LEN_EXPENSE_CATEGORY})")
            cleaned[key] = v
        elif key == "gst_slabs":
            parts = [p.strip() for p in v.split(",") if p.strip()]
            if not parts:
                raise ValueError("Enter at least one GST slab (e.g. 0,5,12,18,28)")
            cleaned_parts = []
            for p in parts:
                d = to_decimal(p, "gst_slabs")
                if d < MIN_GST_SLAB or d > MAX_GST_SLAB:
                    raise ValueError(f"Each GST slab must be {MIN_GST_SLAB}–{MAX_GST_SLAB}")
                cleaned_parts.append(str(d))
            cleaned[key] = ",".join(cleaned_parts)
        elif key == "max_discount_pct":
            d = to_decimal(v, key)
            if d < MIN_DISCOUNT_PCT or d > MAX_DISCOUNT_ALLOWED_PCT:
                raise ValueError(f"Max discount must be {MIN_DISCOUNT_PCT}–{MAX_DISCOUNT_ALLOWED_PCT}%")
            cleaned[key] = str(d)
        elif key == "default_credit_limit":
            d = to_decimal(v, key)
            if d < 0:
                raise ValueError("Default credit limit cannot be negative")
            cleaned[key] = str(d)
        elif key == "loyalty_earn_per_rs":
            try:
                n = int(float(v))
            except (TypeError, ValueError):
                raise ValueError("Loyalty earn rate must be a number")
            if n < MIN_LOYALTY_EARN_PER_RS or n > MAX_LOYALTY_EARN_PER_RS:
                raise ValueError(f"Spend per point must be {MIN_LOYALTY_EARN_PER_RS}–{MAX_LOYALTY_EARN_PER_RS}")
            cleaned[key] = str(n)
        elif key == "loyalty_redeem_cap_pct":
            d = to_decimal(v, key)
            if d < 0 or d > MAX_REDEEM_CAP_PCT:
                raise ValueError(f"Redeem cap must be 0–{MAX_REDEEM_CAP_PCT}%")
            cleaned[key] = str(d)
        elif key == "default_unit":
            if v not in UNITS:
                raise ValueError(f"Unit must be one of {', '.join(UNITS)}")
            cleaned[key] = v
        elif key == "default_gst_slab":
            d = to_decimal(v, key)
            if d < MIN_GST_SLAB or d > MAX_GST_SLAB:
                raise ValueError(f"GST slab must be between {MIN_GST_SLAB} and {MAX_GST_SLAB}")
            cleaned[key] = str(d)
        elif key == "default_min_threshold":
            d = to_decimal(v, key)
            if d < 0:
                raise ValueError("Default threshold cannot be negative")
            cleaned[key] = str(d)
    return cleaned


def save_settings(cleaned):
    ensure_settings_table()
    with db_cursor(commit=True) as cur:
        for key, value in cleaned.items():
            cur.execute(
                """INSERT INTO store_settings (key, value, updated_at)
                   VALUES (%s, %s, CURRENT_TIMESTAMP)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,
                   updated_at = CURRENT_TIMESTAMP""",
                (key, value),
            )


# Typed accessors used by checkout / customers / products.
def get_decimal_setting(key):
    try:
        return Decimal(str(get_setting(key)))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(str(SETTING_DEFAULTS[key]))


def gst_slab_list():
    raw = str(get_setting("gst_slabs", SETTING_DEFAULTS["gst_slabs"]))
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts or SETTING_DEFAULTS["gst_slabs"].split(",")


def catalog_meta():
    """Lists the UI must not hardcode: payment modes, units, GST slabs, page sizes."""
    from .utils import ALLOWED_PER_PAGE
    from .config import app_version
    return {
        "version": app_version(),
        "payment_modes": list(PAYMENT_MODES),
        "units": list(UNITS),
        "gst_slabs": gst_slab_list(),
        "page_sizes": list(ALLOWED_PER_PAGE),
    }


def get_int_setting(key):
    try:
        return int(float(get_setting(key)))
    except (TypeError, ValueError):
        return int(float(SETTING_DEFAULTS[key]))
