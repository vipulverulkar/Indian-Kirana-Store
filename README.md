# 🏪 KiranaPro — Enterprise Kirana Store Management

> 📖 End-user guide: [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) ·
> 🏗️ Architecture & diagrams: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
> 🌐 GitHub: https://github.com/vipulverulkar/Indian-Kirana-Store

A Flask + SQLite/PostgreSQL billing, inventory, and credit-ledger (Udhaar Khata) app for
Indian grocery stores. Handles GST billing, discounts, loyalty points, customer
credit, returns, expenses, and day-close Z-reports — with role-based access for
owners (admin) and counter staff.

| Login | Dashboard (admin) |
|---|---|
| ![Login](docs/screenshots/01-login.png) | ![Dashboard](docs/screenshots/02-dashboard.png) |

| Billing Terminal | Store Settings → Database (admin) |
|---|---|
| ![Billing](docs/screenshots/03-billing.png) | ![Database](docs/screenshots/04-database.png) |

## Features

**Billing terminal**
- Barcode scan (camera) + manual entry, live search (name/barcode), category filter
- Customer picker dropdown (or phone fetch / + New) with live dues + loyalty badge
- Cart with GST (CGST/SGST split) computed per item
- Bill discount % (default cap 50%, configurable) + loyalty redemption (1 pt = ₹1, capped at 20% of bill by default)
- Payment modes: Cash, UPI, Card, Udhaar (credit)
- Printable GST invoice + WhatsApp share (invoice text / dues reminders)
- Keyboard shortcuts: `Ctrl+Enter` checkout, `Ctrl+S` search, `Esc` clear/close

**Customers & Udhaar Khata**
- Full customer management: add, edit (name/phone), delete; credit limits (admin-only changes, never below outstanding dues)
- Delete is blocked while dues are outstanding or order history exists
- Live dues, loyalty points, lifetime spend; repayments (Jama) with overpayment guard
- Credit-limit enforcement at checkout; dues-aging report with WhatsApp reminders

**Inventory & catalog**
- Product CRUD (cost + sell price, GST slab, stock, threshold, barcode, vendor)
- 135-SKU Indian grocery master catalog (grains, dals, spices, oils, dairy,
  beverages, biscuits, instant, dry fruits, health, snacks, household,
  personal care, sweets, frozen, pooja essentials, baby care) with realistic
  prices, GST slabs, thresholds and vendors
- Barcodes auto-generated (random non-sequential `KP…`) when left blank — on add form and CSV import
- Procurement log: every Stock In records qty + cost + vendor + bill (same
  product at different rates stays traceable; per-product 🧾 history, admin-only)
- Barcode-label generator (🏷 Labels): name + price + CODE128 barcode on a
  printable sheet (1–200 labels, 2 sizes); auto-assigns codes for codeless products;
  🖨 Print All Barcodes sheets the whole catalog at once
- First-class **categories** table: dropdowns everywhere + add/rename/delete UI;
  new names auto-register when saving products or importing CSV
- Stock-in (purchase/correction), low-stock alerts, purchase-order CSV export
- Products CSV export + import (upsert on barcode, skips bad rows with counts)

**Orders & returns**
- Order history with invoice view; partial/full returns with prorated refunds
  (discount/loyalty-adjusted), automatic restock + Udhaar dues correction

**Expenses & reports**
- Daily expense tracking (admin-only delete)
- Financial reports for **day / month / year** with revenue-trend charts:
  revenue, GST, discounts, orders, payment mix (+ gross − expenses = net profit for admin)
- Dashboard: 7-day revenue/profit chart, payment mix, top products, stock value
- Staff-safe catalog: staff see sell prices/stock only; cost prices are stripped from product APIs

**Platform**
- Pagination everywhere (`?page=&per_page=`, sizes 15/25/50/100, remembered per table)
- Roles: `admin` (everything) vs `staff` (billing, orders, customers, read-only inventory)
- Themes: light/dark mode + 4 accent colours + text-size (80–120%) and Comfortable/Compact density (header controls, remembered per browser)
- JSON-safe Decimal/datetime serialization; validated inputs with 400s (no 500s on bad input)
- Version, license and developer credits shown on login + sidebar; configurable via `APP_VERSION`, `APP_LICENSE`, `DEVELOPER_*`

## Tech stack

| Layer    | Choice                                      |
|----------|---------------------------------------------|
| Backend  | Flask 3, Werkzeug security; psycopg2 for PostgreSQL |
| Database | SQLite (standalone, no server) or PostgreSQL — local/external (`DATABASE_URL` or `DB_*` vars); remote databases are PostgreSQL |
| Deploy   | Standalone SQLite/desktop build, or Dockerfile + `docker-compose.yml` (PostgreSQL + gunicorn) |
| Desktop  | PyInstaller one-file launcher (`desktop.py`), optional `pywebview` window |
| Frontend | Tailwind CDN, vanilla JS, Chart.js, html5-qrcode |
| Server   | `app.py`/`desktop.py`, or gunicorn (in requirements) |

## Project structure

```
├── app.py                     # web entry point (creates app from kirana/, exposes `app`)
├── desktop.py                 # desktop entry point (local server + window/browser)
├── kirana.spec                # PyInstaller build recipe for Windows/Linux
├── build_desktop.sh / .bat    # one-command desktop builds
├── kirana/                    # backend, one module per route area (Flask blueprints)
│   ├── __init__.py            # app factory: config, JSON provider, blueprint registry
│   ├── auth.py                # login/logout/session, login_required/admin_required
│   ├── users.py               # user management (admin only)
│   ├── activity.py            # activity-log audit trail + /api/activity (admin)
│   ├── core.py                # dashboard shell (/), health check
│   ├── store.py               # store info, /api/settings, logo upload, /api/backup + /api/restore
│   ├── settings.py            # persistent store defaults (validation + typed accessors)
│   ├── products.py            # products, categories, inventory, CSV import/export
│   ├── customers.py           # customers, Udhaar ledger, repayments
│   ├── orders.py              # orders, checkout, returns
│   ├── expenses.py            # daily expenses
│   ├── reports.py             # Z-report, dashboard stats, dues aging
│   ├── config.py              # app version, developer, contact, license
│   ├── db.py                  # SQLite/PostgreSQL connection + schema bootstrap
│   └── utils.py               # validation, pagination, formatting helpers
├── init_db.sql                # PostgreSQL schema + product seeds (fresh installs)
├── init_db_sqlite.sql         # SQLite standalone schema (seeded from init_db.sql)
├── migrate_features2.sql      # discounts/loyalty cols + returns + expenses tables
├── migrate_legacy_catchup.sql # backfills total_profit / cost_price / lifetime_spend
├── migrate_categories.sql     # categories table + backfill
├── migrate_settings.sql       # store_settings table (Settings menu)
├── migrate_activity.sql       # activity_log table (audit trail)
├── migrate_purchases.sql      # procurement log table
├── seed.py                    # idempotent demo data (users, customers, categories)
├── LICENSE                    # GNU GPL v3.0
├── requirements.txt
├── Dockerfile                 # gunicorn image (auto-migrate + seed via docker-entrypoint.sh)
├── docker-compose.yml         # local stack: app + Postgres (`docker compose up --build`)
├── docker-entrypoint.sh       # wait for Postgres → apply schema → seed → start app
├── .env.example               # sample config — copy to .env and fill in
├── .env                       # DB credentials, secret, store location (not committed)
└── templates/                 # login.html, index.html (dashboard SPA)
```

## Setup

### 1. Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Standalone mode (SQLite — no database server)

```bash
cp .env.example .env   # DB_BACKEND=sqlite + SQLITE_PATH=kirana.db
.venv/bin/python app.py
# → http://localhost:5000  (first login: admin / admin123)
```

The SQLite file, all tables, the product catalog and the default admin/staff
accounts are created automatically on first launch. No `init_db.sql`, no
`psql`, no PostgreSQL server is needed. `python seed.py` is optional and only
adds the two demo customers. Back up via **Master Data → Backup & Restore**;
SQL/CSV backups work in standalone mode without `pg_dump`/`psql`. Backups exclude login accounts and the database pointer; restore into an install whose login accounts (and user IDs) match the source.

To use a different file, set `SQLITE_PATH=/absolute/path/kirana.db` (or
`DATABASE_URL=sqlite:///kirana.db`). Keep `DB_BACKEND=sqlite` explicit so a
stray `DB_NAME` in the environment cannot override it.

### 3. Desktop app (Windows / Linux)

Build a single-file executable that starts KiranaPro locally and opens it in a
native window (if `pywebview` is installed) or the default browser. It binds
only to `127.0.0.1`, uses SQLite by default, and stores data outside the
bundle.

```bash
python -m pip install pyinstaller
python -m pip install pywebview   # optional native window
./build_desktop.sh                # Linux/macOS
build_desktop.bat                 # Windows
```

Run `dist/KiranaPro` (`dist\KiranaPro.exe` on Windows). PyInstaller is not a
cross-compiler: build on each OS you want to ship.

Data locations (override with `KIRANA_DATA_DIR`):

- Windows: `%LOCALAPPDATA%\KiranaPro`
- Linux: `~/.local/share/kiranapro`
- macOS: `~/Library/Application Support/KiranaPro`

To use PostgreSQL in the desktop build, place a `.env` next to the executable
with `DB_BACKEND=postgres` and either `DATABASE_URL` or the `DB_*` variables.

### 4. PostgreSQL mode (local server or split vars)

`.env` (see `.env.example` — the source of truth for all variables):

```
DB_BACKEND=postgres
DB_NAME=kiranapro
DB_USER=kiranapro
DB_PASSWORD=change-me
DB_HOST=localhost
DB_PORT=5432
SECRET_KEY=change-me-to-a-long-random-string
FLASK_DEBUG=1
PORT=5000
STORE_NAME="KiranaPro"
STORE_LOCATION="Mumbai, Maharashtra"
STORE_ADDRESS="123 MG Road, Mumbai, Maharashtra 400001"
STORE_PHONE="9876543210"
#STORE_LOGO=""   # optional logo URL; else upload via Store Settings (admin)
COOKIE_SECURE=0   # set to 1 when serving over HTTPS
```

`STORE_NAME` / `STORE_LOCATION` / `STORE_ADDRESS` / `STORE_PHONE` in the
env file are only **first-run fallbacks**. Once the app runs, the
**Store Settings** menu (admin, sidebar) owns all store defaults, persisted
in the `store_settings` table:
- **Store:** name, location, address, phone, invoice footer + logo upload
  (PNG/JPG/WEBP/GIF, max 2 MB, writable data dir — `static/uploads/` in source/Docker). Name/address/phone/footer
  print on GST invoices (print + WhatsApp) and in the sidebar.
- **Billing:** default payment mode (Cash/UPI/Card/Udhaar), max discount %
- **Loyalty & Udhaar:** default credit limit for new customers, spend-per-point
  earn rate, max % of a bill redeemable as points (1 pt = ₹1)
- **Inventory:** default unit / GST slab / low-stock threshold for new
  products and blank CSV-import cells
- `GET /api/settings` (any role) reads them; `PUT /api/settings`
  (admin only) saves them. Checkout enforces max-discount and redeem-cap;
  billing/product/customer forms prefill the defaults.

### 5a. Fresh PostgreSQL database

```bash
psql -h localhost -U kiranapro -d kiranapro -f init_db.sql
.venv/bin/python seed.py
```

### 5b. Existing PostgreSQL database (upgrade in order)

```bash
psql -h localhost -U kiranapro -d kiranapro -f migrate_features2.sql
psql -h localhost -U kiranapro -d kiranapro -f migrate_legacy_catchup.sql
psql -h localhost -U kiranapro -d kiranapro -f migrate_categories.sql
psql -h localhost -U kiranapro -d kiranapro -f migrate_settings.sql
psql -h localhost -U kiranapro -d kiranapro -f migrate_activity.sql
psql -h localhost -U kiranapro -d kiranapro -f migrate_purchases.sql
.venv/bin/python seed.py
```

(`init_db.sql` already contains all migrations appended, so new installs need
only step 5a.)

### 6. Run

```bash
.venv/bin/python app.py   # http://localhost:5000
```

Health check: `GET /api/health` → `{"status":"ok","db":"up","db_mode":"sqlite","version":"1.0.0","target":{...}}`.

## Docker (PostgreSQL)

The Docker image is PostgreSQL-only. For SQLite use the standalone or desktop
build above. The image runs gunicorn, waits for Postgres, applies `init_db.sql`
(idempotent) and seeds demo data on every boot.

### Option 0 — Local Postgres via compose (easiest)

```bash
cp .env.example .env   # then edit secrets; leave DATABASE_URL empty, DB_SSLMODE empty
docker compose up --build
# → http://localhost:5000 (compose forces DB_HOST=db + plain local connection)
```

### Option 1 — Remote managed Postgres (Neon / Supabase / RDS / Render / ...)

```bash
# .env:
DATABASE_URL=postgresql://user:password@host:5432/dbname
DB_SSLMODE=require
SECRET_KEY=change-me-to-a-long-random-string
```

```bash
docker run --env-file .env -p 5000:5000 -v kiranapro_uploads:/app/static/uploads kiranapro
# → http://localhost:5000
```

### Option 2 — Local Postgres on the host

Point `DATABASE_URL` at the host machine. From inside the container,
`localhost` means the container itself, so use `host.docker.internal`:

```bash
# .env:
DATABASE_URL=postgresql://kiranapro:kiranapro@host.docker.internal:5432/kiranapro
```

```bash
docker run --env-file .env -p 5000:5000 \
  --add-host=host.docker.internal:host-gateway \
  -v kiranapro_uploads:/app/static/uploads kiranapro
```

(Alternatively leave `DATABASE_URL` empty and set `DB_HOST=host.docker.internal`
+ `DB_NAME/DB_USER/DB_PASSWORD/DB_PORT` with the same `--add-host` flag.)

> `DATABASE_URL` takes precedence over `DB_NAME/DB_USER/...` everywhere
> (`app.py` + `seed.py`). `DB_SSLMODE=require` is enforced on top of either
> mode — set it for managed providers that enforce TLS, leave it empty for
> plain local Postgres.

### Option 3 — No Docker (local Postgres)

```bash
# .env: leave DATABASE_URL empty, set DB_HOST=localhost + credentials
psql -h localhost -U kiranapro -d kiranapro -f init_db.sql
.venv/bin/python seed.py
.venv/bin/python app.py
```

### Default logins

| User    | Password   | Role  |
|---------|------------|-------|
| admin   | admin123   | admin |
| staff   | staff123   | staff |

Reset demo passwords anytime: `.venv/bin/python seed.py --reset-passwords`

## Roles & permissions

| Capability                        | staff | admin |
|-----------------------------------|-------|-------|
| Billing / checkout                | ✅    | ✅    |
| Customers (add/lookup/edit)       | ✅    | ✅    |
| Credit limits / customer delete   | ❌    | ✅    |
| Udhaar ledger, repayments         | ✅    | ✅    |
| Order history + invoices          | ✅    | ✅    |
| Returns                           | ✅    | ✅    |
| Inventory (view-only, no margins) | ✅    | ✅    |
| Expenses                          | ❌    | ✅    |
| Reports / dashboard               | ❌    | ✅    |
| Products, categories, stock-in    | ❌    | ✅    |
| CSV import, expense delete        | ❌    | ✅    |
| User management (add/edit/delete/reset password) | ❌ | ✅ |

## Business rules

- **Loyalty:** earn 1 pt per ₹X (Settings → spend-per-point, default ₹100, on final amount); redeem 1 pt = ₹1, max Y% of bill (Settings → redeem cap, default 20%) and never more than the balance.
- **Discounts:** 0–max% per bill (Settings → max discount, default 50%), applied before loyalty redemption.
- **Store defaults:** everything under Settings is DB-backed and editable by admin at runtime; `.env` `STORE_*` values only seed first-run blanks.
- **Returns:** refund = item rate × qty, prorated by `paid ÷ gross` so discounted bills can't refund more than paid.
- **Udhaar:** checkout blocked past credit limit; returns auto-credit dues + ledger.
- **Pagination:** `per_page` must be 15/25/50/100 (anything else → 15); out-of-range pages clamp to the last page.

## API reference

All `/api/*` return JSON; unauthenticated → 401. List endpoints return
`{items…, page, per_page, total, pages}`.

| Method | Endpoint | Role | Notes |
|--------|----------|------|-------|
| GET/POST | `/api/products?search=&category=&low_stock=1&page=&per_page=` | any/admin✎ | POST/PUT/DELETE admin only |
| PUT/DELETE | `/api/products/<id>` | admin | full payload validated |
| POST | `/api/products/<id>/stock` | admin | `{quantity, cost_price?, vendor?, bill_no?}` — logs procurement |
| GET | `/api/products/<id>/purchases` | admin | procurement history (qty/cost/vendor/bill, newest first) |
| GET | `/api/products/barcode/<code>` | any | scanner lookup (cost stripped for staff) |
| POST | `/api/products/<id>/barcode/assign` | admin | random non-sequential barcode for codeless products |
| GET | `/api/products/export` | admin | CSV, 2 MB cap |
| POST | `/api/products/import` | admin | CSV, 2000-row cap |
| GET/POST | `/api/categories` | any/admin✎ | `{categories:[{category_id,name,product_count}]}` |
| PUT/DELETE | `/api/categories/<id>` | admin | rename syncs products; delete blocked if in use |
| GET/POST | `/api/customers?search=&page=&per_page=` | any | POST validates phone/limit |
| PUT | `/api/customers/<id>` | any/admin✎ | name/phone any staff; credit-limit change admin-only, never below dues |
| GET/POST | `/api/customers/<phone>`, `/api/customers/<id>/ledger` | any | billing lookup + timeline |
| DELETE | `/api/customers/<id>` | admin | blocked if dues outstanding or order history exists |
| POST | `/api/checkout` | any | `{items, payment_mode, discount_pct?, redeem_points?, customer_id?}` |
| POST | `/api/repayment` | any | `{customer_id, amount, remarks?}` |
| GET | `/api/orders?page=&per_page=`, `/api/orders/<id>` | any | detail includes items + returns |
| POST | `/api/orders/<id>/return` | any | `{items:[{product_id,quantity}], reason?}` |
| GET | `/api/returns?page=&per_page=` | any | returns log |
| GET/POST | `/api/expenses?month=YYYY-MM&page=&per_page=` | admin |  |
| GET | `/api/reports/z-report?period=day&date=YYYY-MM-DD` | admin | daily (default today), hourly series |
| GET | `/api/reports/z-report?period=month&month=YYYY-MM` | admin | monthly, per-day series |
| GET | `/api/reports/z-report?period=year&year=YYYY` | admin | yearly, per-month series |
| GET | `/api/reports/dues?page=&per_page=` | admin | outstanding Udhaar |
| GET | `/api/dashboard/stats` | admin | weekly, top products, stock value |
| GET | `/api/inventory/low-stock?page=&per_page=` | admin |  |
| GET | `/api/inventory/purchase-order` | admin | PO CSV download |
| GET | `/api/me`, `/api/health` | any/open | session info; health returns status, DB target and app version |
| GET/POST | `/api/users` | admin | login accounts (list/create; min 6-char password) |
| PUT/DELETE | `/api/users/<id>` | admin | edit / reset password / delete; can't self-demote, self-delete or remove the last admin |
| GET/PUT | `/api/settings` | any/admin✎ | store defaults (Settings menu); PUT admin only |
| GET | `/api/store-info` | any | store profile + GSTIN/UPI + invoice footer + logo |
| GET | `/api/backup?format=sql\|csv` | admin | SQL dump or CSV-zip export (password hashes excluded) |
| POST | `/api/restore` | admin | restore a .sql dump or CSV .zip — replaces all business data, keeps login accounts (target must have matching users) |
| GET | `/api/activity?action=&search=` | admin | audit trail of admin actions |
| GET | `/api/vendors` | admin | distinct distributors with product counts |
| GET | `/api/settings/database` | admin | which DB is active + reachable (no secrets) |
| PUT | `/api/settings/database` | admin | `{active_db: local\|remote, remote_database_url?}` — switch DB |
| POST | `/api/settings/database/test` | admin | test a candidate remote URL (not stored) |

## Version & credits

- **Version:** `APP_VERSION` in `.env` (default `1.0.0`) — shown on the login
  screen, in the sidebar, and by `/api/health` + `/api/meta`.
- **Developer:** Vipul Verulkar · India · <vipulverulkar@gmail.com>

## License

Copyright (C) 2026 Vipul Verulkar.

This project is free software: you can redistribute it and/or modify it under
the terms of the **GNU General Public License v3.0 (GPL-3.0)**. See
[`LICENSE`](LICENSE) for the full text.

## Switching databases (Store Settings → Database, admin)

The app boots from the server-configured **Local** database (`.env`), but the
admin can switch it to a **Remote** Postgres (Neon / Supabase / RDS / …) at
runtime — no `.env` edit or restart:

1. Open Store Settings → **Database** tab, paste the remote
   `postgresql://…` URL, **Test Connection**, then **Switch Database**.
2. Switching validates + connects, applies the schema, and syncs login
   accounts (server-side, hashes never leave the server) so nobody gets
   locked out — then new bills go to the remote.
3. Switching never moves business data: each database keeps its own bills,
   customers and stock. Switch back to Local anytime; a dead remote never
   blocks switching back.

The remote URL is stored in the local database only and is never returned by
any API (responses carry host/dbname, never the password). `GET /api/health`
reports the active target. For production, prefer `DATABASE_URL` +
`DB_SSLMODE=require` in `.env` instead of a settings-stored URL.
