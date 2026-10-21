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
    "store_name": "KiranaPro",
    "store_location": "Default Location",
    "store_address": "",
    "store_phone": "",
    "store_gstin": "",
    "upi_id": "",
    "invoice_footer": "Thank you, visit again!",
    # --- Billing ---
    "default_payment_mode": "Cash",
    "max_discount_pct": "50",
    "default_expense_category": "General",
    "gst_slabs": "0,5,12,18,28",
    # --- Loyalty & Udhaar ---
    "default_credit_limit": "10000",
    "loyalty_earn_per_rs": "100",
    "loyalty_redeem_cap_pct": "20",
    # --- Inventory (new-product defaults) ---
    "default_unit": "packet",
    "default_gst_slab": "5",
    "default_min_threshold": "5",
}

PAYMENT_MODES = ("Cash", "UPI", "Card", "Udhaar")
UNITS = ("kg", "packet", "bottle", "piece", "L", "g")


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
            if len(v) > 100:
                raise ValueError("Store name too long (max 100)")
            cleaned[key] = v
        elif key in ("store_location",):
            if len(v) > 200:
                raise ValueError("Store location too long (max 200)")
            cleaned[key] = v
        elif key == "store_address":
            if len(v) > 500:
                raise ValueError("Store address too long (max 500)")
            cleaned[key] = v
        elif key == "store_phone":
            if v and (len(v) < 6 or len(v) > 15):
                raise ValueError("Phone must be 6–15 characters")
            if len(v) > 30:
                raise ValueError("Phone too long")
            cleaned[key] = v
        elif key == "invoice_footer":
            if len(v) > 500:
                raise ValueError("Invoice footer too long (max 500)")
            cleaned[key] = v
        elif key == "store_gstin":
            if v:
                compact = v.replace(" ", "").upper()
                if len(compact) != 15 or not compact.isalnum():
                    raise ValueError("GSTIN must be 15 letters/digits (or blank)")
                cleaned[key] = compact
            else:
                cleaned[key] = ""
        elif key == "upi_id":
            if v:
                if "@" not in v or len(v) > 100:
                    raise ValueError("UPI ID looks like name@bank (max 100)")
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
            if len(v) > 100:
                raise ValueError("Expense category too long (max 100)")
            cleaned[key] = v
        elif key == "gst_slabs":
            parts = [p.strip() for p in v.split(",") if p.strip()]
            if not parts:
                raise ValueError("Enter at least one GST slab (e.g. 0,5,12,18,28)")
            cleaned_parts = []
            for p in parts:
                d = to_decimal(p, "gst_slabs")
                if d < 0 or d > 100:
                    raise ValueError("Each GST slab must be 0–100")
                cleaned_parts.append(str(d))
            cleaned[key] = ",".join(cleaned_parts)
        elif key == "max_discount_pct":
            d = to_decimal(v, key)
            if d < 0 or d > 90:
                raise ValueError("Max discount must be 0–90%")
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
            if n < 1 or n > 100000:
                raise ValueError("Spend per point must be 1–100000")
            cleaned[key] = str(n)
        elif key == "loyalty_redeem_cap_pct":
            d = to_decimal(v, key)
            if d < 0 or d > 100:
                raise ValueError("Redeem cap must be 0–100%")
            cleaned[key] = str(d)
        elif key == "default_unit":
            if v not in UNITS:
                raise ValueError(f"Unit must be one of {', '.join(UNITS)}")
            cleaned[key] = v
        elif key == "default_gst_slab":
            d = to_decimal(v, key)
            if d < 0 or d > 100:
                raise ValueError("GST slab must be between 0 and 100")
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
