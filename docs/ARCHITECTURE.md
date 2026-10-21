# KiranaPro — Architecture

## 1. System overview

```mermaid
flowchart TB
    subgraph Client["Browser (single page)"]
        UI["index.html + vanilla JS<br/>Tailwind · Chart.js · html5-qrcode"]
        LOGIN["login.html"]
    end
    subgraph Server["Flask (gunicorn, :5000)"]
        FACT["create_app()<br/>kirana/__init__.py"]
        BP["Blueprints (10)<br/>auth · activity · core · store<br/>users · products · customers<br/>orders · expenses · reports"]
        SET["settings.py<br/>store_settings defaults"]
        DBH["db.py<br/>psycopg2"]
    end
    PG[("PostgreSQL<br/>10 tables")]
    UP["static/uploads/<br/>logo files (volume)"]

    UI <-->|fetch /api/* JSON<br/>session cookie| BP
    LOGIN -->|POST /login| BP
    FACT --> BP
    BP --> SET
    BP --> DBH
    SET --> DBH
    DBH <--> PG
    BP --> UP
```

- **Frontend:** server-rendered shell (`GET /` injects store name/location/logo via
  Jinja), then a vanilla-JS SPA — sections toggled client-side, all data via
  `fetch` to `/api/*`. No build step; CDN libs (Tailwind, Chart.js, html5-qrcode).
- **Backend:** Flask 3 app factory (`kirana/__init__.py`), one blueprint module per
  domain, shared `db.py` (psycopg2 + `RealDictCursor`; `DATABASE_URL` or `DB_*`
  vars plus optional `DB_SSLMODE`, with runtime Local/Remote selection via a
  pointer in the primary DB) and `utils.py` (validation, pagination, money formatting).
- **Deploy:** `docker-entrypoint.sh` waits for Postgres → applies `init_db.sql`
  (idempotent) → `seed.py` (idempotent demo users/customers/categories) →
  gunicorn `app:app` (2 workers). Logo uploads persist via named volume on
  `/app/static/uploads`. `docker-compose.yml` provides a one-command local
   stack (app + Postgres).

## 2. Backend modules

```mermaid
flowchart LR
    APP["app.py<br/>create_app() + app"] --> INIT["kirana/__init__.py<br/>JSON provider · blueprint registry · 404 handler"]
    INIT --> AUTH["auth.py<br/>/login · /api/logout · /api/me<br/>login_required · admin_required"]
    INIT --> ACT["activity.py<br/>/api/activity (admin)<br/>log_activity() audit helper"]
    INIT --> USR["users.py<br/>/api/users (admin)<br/>login-account CRUD"]
    INIT --> CORE["core.py<br/>/ (shell) · /api/health"]
    INIT --> STORE["store.py<br/>/api/store-info<br/>/api/settings<br/>/api/store-logo · /api/backup"]
    INIT --> PROD["products.py<br/>products · categories<br/>inventory · CSV"]
    INIT --> CUST["customers.py<br/>customers · ledger<br/>repayment"]
    INIT --> ORD["orders.py<br/>checkout · orders<br/>returns"]
    INIT --> EXP["expenses.py<br/>expenses"]
    INIT --> REP["reports.py<br/>z-report · dashboard<br/>dues"]
    STORE -.uses.-> SETM["settings.py<br/>validate · get · save"]
    ORD -.uses.-> SETM
    CUST -.uses.-> SETM
    PROD -.uses.-> SETM
    CORE -.uses.-> SETM
```

| Module | Routes | Guard |
|---|---|---|
| `auth.py` | `GET/POST /login`, `POST /api/logout`, `GET /api/me` | session cookie, Werkzeug hash |
| `activity.py` | `GET /api/activity` | admin; write paths call `log_activity()` (best-effort, never raises) |
| `users.py` | `GET/POST /api/users`, `PUT/DELETE /api/users/<id>` | admin; guards: no self-demote/self-delete, last admin kept, unique username, min 6-char password |
| `core.py` | `GET /`, `GET /api/health` | login (shell), open (health) |
| `store.py` | `GET /api/store-info`, `GET/PUT /api/settings`, `POST/DELETE /api/store-logo`, `GET /api/backup`, `POST /api/restore`, `GET/PUT /api/settings/database`, `POST /api/settings/database/test` | login; PUT/logo/backup/restore/database admin |
| `products.py` | `/api/products*`, `/api/categories*`, `/api/inventory/*`, CSV export/import | read: login (`cost_price` stripped for staff); write/export/vendors/low-stock: admin |
| `customers.py` | `/api/customers*`, `/api/repayment` | login; limit-change + delete: admin |
| `orders.py` | `POST /api/checkout`, `/api/orders*`, returns | login (any role can bill/return) |
| `expenses.py` | `/api/expenses*` | admin |
| `reports.py` | `/api/reports/z-report`, `/api/reports/dues`, `/api/dashboard/stats` | admin |

## 3. Key flows

### 3.1 Checkout (most complex transaction)

```mermaid
sequenceDiagram
    participant JS as Billing JS
    participant ORD as orders.py /api/checkout
    participant SET as settings.py
    participant DB as PostgreSQL
    JS->>ORD: POST {items, customer_id?, payment_mode, discount_pct, redeem_points}
    ORD->>SET: max_discount_pct, redeem_cap_pct, earn_per_rs
    ORD->>DB: BEGIN · SELECT products FOR UPDATE
    Note over ORD,DB: per item: subtotal, CGST/SGST split,<br/>profit = sell − cost; stock check
    ORD->>DB: SELECT customer FOR UPDATE (if any)<br/>validate points ≤ balance, ≤ cap%<br/>Udhaar: balance + bill ≤ limit?
    ORD->>DB: INSERT orders → order_items<br/>UPDATE products stock<br/>Udhaar? ledger Debit + balance+<br/>loyalty: points − used + earned (final ÷ earn_per_rs)
    ORD->>DB: COMMIT
    ORD->>JS: {order_id, final_amount, discount, redeemed}
```

Discount is applied on (subtotal + GST) before loyalty redemption.
Returns reuse the order + prorate refunds by `paid ÷ gross`.

### 3.2 Settings (store defaults)

```mermaid
flowchart LR
    ENV[".env STORE_*<br/>(first-run fallback)"] --> MERGE
    DEF["SETTING_DEFAULTS<br/>(15 builtin keys)"] --> MERGE
    TBL[("store_settings<br/>key/value rows")] --> MERGE
    MERGE["get_all_settings()<br/>DB > env > builtin"] --> API["GET /api/settings<br/>PUT /api/settings (admin)"]
    API --> USE["checkout caps · form prefills<br/>invoice footer · store profile"]
```

### 3.3 Auth

`POST /login` (JSON or form) → Werkzeug `check_password_hash` → Flask
`session{user_id, username, role}` (HttpOnly, SameSite=Lax, Secure flag via
`COOKIE_SECURE`). `login_required` returns 401 JSON for `/api/*`, redirect for
pages; `admin_required` adds 403 for non-admins.

### 3.4 Runtime database selection

```mermaid
flowchart LR
    ENV[".env PRIMARY<br/>DATABASE_URL or DB_*"] --> PRI[("Primary DB<br/>(Local)")]
    PTR["store_settings<br/>db.active + db.remote_url"] --> ROUTE
    PRI --> PTR
    ROUTE["db.py routing<br/>get_db_connection()"] --> ACT[("Active DB<br/>local or remote")]
    UI["Settings → Database<br/>(admin)"] -->|test + switch| REMOTE[("Remote Postgres")]
    REMOTE -.->|schema + user sync| ACT
```

- The pointer (`db.active`, `db.remote_url`) lives in the **primary** DB and is
  read via a dedicated unrouted connection with a 30s TTL cache — a dead
  remote can never block reads or switching back, and there is no silent
  fallback (remote errors fail loudly so bills can't land in the wrong DB).
- Activating remote: URL validation → `test_db_url()` (5s timeout) → apply
  `init_db.sql` → upsert `app_users` primary→remote (explicit `user_id`s so
  sessions survive and `user_id` FKs hold) → refuse when zero admins remain.
- The URL is a secret: accepted on PUT/test, stored server-side, never
  returned (APIs expose host/dbname only). `GET /api/health` reports the
  active target.

## 4. Database schema

```mermaid
erDiagram
    app_users ||--o{ orders : bills
    app_users ||--o{ returns : processes
    app_users ||--o{ expenses : logs
    customers ||--o{ orders : places
    customers ||--o{ udhaar_ledger : "owes / repays"
    orders ||--o{ order_items : contains
    orders ||--o{ udhaar_ledger : "debits (Udhaar)"
    orders ||--o{ returns : "partial/full"
    products ||--o{ order_items : sold_as
    products ||--o{ returns : restocked
    categories ||--o{ products : labels
    app_users ||--o{ activity_log : performed
    activity_log {
        BIGSERIAL log_id PK
        VARCHAR action
        VARCHAR entity
        TEXT detail
    }
    store_settings {
        TEXT key PK
        TEXT value
        TIMESTAMPTZ updated_at
    }
    app_users {
        BIGSERIAL user_id PK
        VARCHAR username UK
        VARCHAR password_hash
        VARCHAR role
    }
    customers {
        BIGSERIAL customer_id PK
        VARCHAR phone UK
        NUMERIC credit_limit
        NUMERIC current_balance
        INT loyalty_points
        NUMERIC lifetime_spend
    }
    products {
        BIGSERIAL product_id PK
        VARCHAR barcode UK
        NUMERIC stock_quantity
        NUMERIC cost_price
        NUMERIC unit_price
        NUMERIC gst_slab
        NUMERIC min_threshold
    }
    orders {
        BIGSERIAL order_id PK
        NUMERIC total_amount
        NUMERIC total_cgst
        NUMERIC total_sgst
        NUMERIC total_profit
        NUMERIC discount_amount
        INT loyalty_redeemed
        VARCHAR payment_mode
        VARCHAR payment_status
        VARCHAR order_status
    }
    udhaar_ledger {
        BIGSERIAL transaction_id PK
        VARCHAR transaction_type
        NUMERIC amount
    }
```

Applied by `init_db.sql` (fresh) or `migrate_*.sql` in order
(features2 → legacy_catchup → categories → settings → activity); `seed.py` adds
admin/staff users, demo customers, base categories. All scripts idempotent.
`store_settings` also holds the `db.active` / `db.remote_url` database-selection
pointer (primary DB only — see §3.4).

## 5. Frontend structure (`templates/index.html`)

- **Sidebar:** store branding block, section buttons (Dashboard, Billing, Udhaar,
  Inventory, Master Data, Orders, Expenses, Reports, Users, Activity — admin-only
  ones auto-hide for staff; staff land on Billing), user chip, Store Settings + Logout.
- **Sections** (`*-section`): dashboard, billing, udhaar, inventory, master,
  orders, expenses, reports, users, activity — toggled by `showSection()`
  (staff blocked from non-billing/udhaar/orders/inventory; master has
  Products/Categories/Vendors/Backup sub-tabs via `switchMasterTab()`).
- **Modals:** scanner, product, category, store-settings (5 tabs: Store, Billing,
  Loyalty & Udhaar, Inventory, Database), customer, user, order/invoice, labels,
  purchases, stock-in.
- **State:** `STORE`, `SETTINGS`, `cart`, `PG` (per-table pagination, sizes
  15/25/50/100 in `localStorage`), `REP` (report period); `Chart.js` instances
  for weekly / payment-mix / report trend.
- **Conventions:** `fmt` (₹), `esc` (HTML), `jsq` (inline-JS strings), `pagerHTML`,
  `showToast`; invoice print via hidden `#invoice-print` + `@media print`.

## 6. Configuration & operations

- **Config:** `DATABASE_URL` wins; else `DB_NAME/USER/PASSWORD/HOST/PORT`.
  `DB_SSLMODE=require` enforces TLS on either mode (managed providers); empty
  for plain local Postgres. Runtime Local/Remote selection lives in the
  primary DB (§3.4) and overrides per-process with a 30s cache.
  `SECRET_KEY`, `FLASK_DEBUG`, `PORT`, `STORE_*` fallbacks, `COOKIE_SECURE=1`
  behind HTTPS. Never commit `.env` (see `.env.example`).
- **Run local:** `pip install -r requirements.txt` → `psql -f init_db.sql` →
  `python seed.py` → `python app.py`; health at `GET /api/health`.
- **Scaling notes:** stateless app (only local state is logo files → shared volume);
  safe to add gunicorn workers. DB access is one connection per request
  (no pool) — fine for single-store counter load.
