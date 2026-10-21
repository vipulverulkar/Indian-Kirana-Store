"""Shared validation, pagination and formatting helpers."""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import request

from .constants import ALLOWED_PER_PAGE, DEFAULT_PER_PAGE, MAX_LEN_CATEGORY


def to_decimal(value, field_name="value"):
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"Invalid number for {field_name}")
    if not d.is_finite():
        raise ValueError(f"Invalid number for {field_name}")
    return d


def parse_date_yyyy_mm_dd(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# ---------- Pagination (page sizes selectable: 15 / 25 / 50 / 100) ----------
def get_pagination():
    try:
        page = int(request.args.get("page", 1))
        if page < 1:
            page = 1
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = int(request.args.get("per_page", DEFAULT_PER_PAGE))
    except (ValueError, TypeError):
        per_page = DEFAULT_PER_PAGE
    if per_page not in ALLOWED_PER_PAGE:
        per_page = DEFAULT_PER_PAGE
    return page, per_page


def page_meta(total, page, per_page):
    pages = max(1, -(-int(total or 0) // per_page))
    page = min(page, pages)
    return {"page": page, "per_page": per_page, "total": int(total or 0), "pages": pages,
            "offset": (page - 1) * per_page}


def fmt_money(value):
    try:
        return f"₹{float(value):.2f}"
    except (TypeError, ValueError):
        return "₹0.00"


def ensure_category(cur, name):
    """Auto-register a product category so the categories table stays the source of truth."""
    name = (name or '').strip()
    if not name:
        return None
    if len(name) > MAX_LEN_CATEGORY:
        raise ValueError(f"Category too long (max {MAX_LEN_CATEGORY})")
    cur.execute("INSERT INTO categories (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (name,))
    return name
