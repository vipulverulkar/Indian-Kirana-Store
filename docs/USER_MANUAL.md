# KiranaPro — User Manual

Enterprise kirana store management: GST billing, inventory, Udhaar Khata (credit ledger),
returns, expenses and Z-reports. Single-page app at `http://localhost:5000`.

**Appearance:** the header has a 🌙/☀️ toggle for light/dark mode plus 4 accent
colour dots (Emerald, Indigo, Amber, Rose). The **Aa** menu next to it adjusts
text size (80–120%) and switches Comfortable/Compact density. All choices are
remembered per browser.

## Screenshots

| Login | Dashboard (admin) |
|---|---|
| ![Login](screenshots/01-login.png) | ![Dashboard](screenshots/02-dashboard.png) |

| Billing Terminal | Store Settings → Database (admin) |
|---|---|
| ![Billing](screenshots/03-billing.png) | ![Database](screenshots/04-database.png) |

## 1. Logging in

- Open `/login`. Demo logins (created by `python seed.py`):
  | User | Password | Role |
  |------|----------|------|
  | `admin` | `admin123` | Owner — everything |
  | `staff` | `staff123` | Counter — billing, Udhaar, orders/returns, read-only inventory |
- Wrong credentials show an error; the session keeps you logged in until **Logout**.

## 2. Roles & permissions

| Capability | staff | admin |
|---|---|---|
| Billing / checkout | ✅ | ✅ |
| Customers (add / lookup / edit name-phone) | ✅ | ✅ |
| Credit-limit change / customer delete | ❌ | ✅ |
| Udhaar ledger + repayments (Jama) | ✅ | ✅ |
| Order history + invoices + returns | ✅ | ✅ |
| Inventory (view-only, no cost prices) | ✅ | ✅ |
| Expenses | ❌ | ✅ |
| Z-Reports / dashboard | ❌ | ✅ |
| Products, categories, stock-in, CSV import/export | ❌ | ✅ |
| Purchase-order export | ❌ | ✅ |
| Store Settings (incl. Database selection) | ❌ | ✅ |
| User management (add/edit/delete/reset password) | ❌ | ✅ |

Admin-only sidebar items and buttons auto-hide for staff.

## 3. Screen-by-screen guide

### 3.1 Dashboard (🏠)
- **Cards:** Today's Revenue (+ profit/net for admin), Udhaar Outstanding (+ stock value),
  Low Stock Items (+ today's expenses), Orders in last 7 days.
- **Charts:** last-7-days revenue/profit bars, today's payment-mix doughnut,
  top-5 products, weekly revenue bars.

### 3.2 Billing Terminal (🛒)
Scan-first counter flow:
1. **Scan bar (top):** scan or type a barcode + `Enter` — the item drops straight
   into the cart (quantity steps up if already there), the cart total updates,
   and the bar clears itself for the next scan. `F2` jumps back to it anytime.
   Unknown codes offer **+ Add as new product** (admin, barcode prefilled).
2. Browse below: type in search, filter by category, or **📷 Scan** (camera).
   Typing an exact barcode + `Enter` adds it directly. Use **↑/↓** + **Enter**
   or click any row to add. Out-of-stock items are labelled and blocked.
2. Attach a customer (optional, required for Udhaar): pick from the dropdown,
   or type phone → **Fetch**, or **+ New**.
3. **Add** items to the cart; adjust quantities with `−`/`+` or type an exact
   quantity (decimals allowed, e.g. 0.5 kg) — stock limits are enforced.
4. Set **Discount %** (capped by Settings → max discount) and **Redeem pts**
   (1 pt = ₹1, capped at Settings → redeem % of bill, and by the customer's balance).
5. Choose payment: **Cash / UPI / Card / Udhaar** (keys `1–4`), then **🎉 Finalize Order**
   (`Ctrl+Enter`). The invoice pops up automatically. Double-clicks are ignored —
   an order is never billed twice. For Cash, enter **Tendered** (or tap Exact /
   a denomination) to see the **Change** due.
6. **Clear cart** with the link or `Esc`.

### 3.3 Udhaar Khata (📒)
- **Left:** Post Repayment (Jama) — select customer, amount, remarks → Confirm.
  Overpaying beyond dues is rejected. **Ledger** timeline shows debits/credits.
- **Right:** searchable customer table with balance, limit, and per-row
  **Ledger / Edit / WhatsApp reminder / Delete** (delete: admin only, only with
  zero dues and no order history).
- **+ Add Customer:** name + phone required; credit limit defaults from Settings
  (staff cannot change limits — admin only, and never below outstanding dues).

### 3.4 Inventory (📦)
- Stock table with barcode, selling price, quantity and **OK / CRITICAL**
  status (CRITICAL = stock ≤ threshold). Staff see this same table read-only
  (no cost prices, no action buttons).
- **+ Add Product** (admin): create a new product without leaving Inventory.
- **📦 Stock In** (admin, per row): add purchased/corrected quantity, optionally
  updating the cost price — no need to open the full Edit form. Record the
  **vendor + bill no** each time: the same product bought at different rates
  stays traceable under per-row **🧾 Purchases** (newest first, with who added it).
- **⬇ Products CSV** (admin: export, includes cost prices), **⬆ Import CSV** (admin: upsert on barcode,
  max 2 MB / 2000 rows, bad rows skipped with counts), **⬇ PO** (admin:
  low-stock purchase-order CSV grouped by vendor).

### 3.5 Master Data (🗄️, admin)
- Expandable sidebar menu with three sub-items (also switchable via tabs on page):
  - **📦 Products:** searchable catalog; **+ Add New Product** (name*,
    barcode (blank = auto-generated `KP…` code), unit*, cost*, sell price*,
    GST %*, stock*, threshold, category, distributor).
    New-product blanks prefill from Settings → Inventory defaults. Editing a
    product reveals **📦 Stock In** (quantity + optional new cost price).
    **🏷 Labels** opens the barcode-label generator: product name + selling
    price + scannable barcode (CODE128) on a printable sheet — choose 1–200
    labels and Medium 52×32mm / Small 40×25mm size. Products without a barcode
    get an **✨ Auto-assign** button (random non-sequential `KP…` code).
    **🖨 Print All Barcodes** (catalog header) builds one sheet for the whole
    catalog — 1–12 labels per product, codeless products are skipped with a count.
  - **Categories:** add / rename (renames sync all products) / delete (blocked
    while products use it). Used in product dropdowns, billing filter, CSV import.
  - **Vendors:** distributors derived from products (read-only; set the
    distributor on a product to add one here) — handy for the low-stock
    purchase order.
  - **💾 Backup & Restore:** ⬇ export all business data as SQL (.sql dump)
    or CSV (.zip, one file per table; passwords never included), ⬆ restore
    either format — it replaces all current data (login accounts are kept).
    Download a fresh backup before restoring.

### 3.6 Orders & Returns (📜)
- Order history (newest first): id, date, customer, amount, mode, Paid/Pending status.
- **View** opens the GST invoice: line items with GST %, subtotal, CGST+SGST,
  discount + loyalty lines, total, store GSTIN, and a scan-to-pay **UPI QR**
  (when a UPI ID is set in Settings). Actions: **🖨 Print** (thermal-friendly
  slip with logo, GSTIN and UPI QR), **📲 WhatsApp** (invoice text incl. GSTIN
  and UPI payment line), per-item **↩ return** (enter qty + reason).
- **↩ View Returns Log** toggles the returns history.
- Return refunds are prorated (`paid ÷ gross`) so discounted bills never refund
  more than paid; stock is restocked and Udhaar dues auto-credited.

### 3.7 Expenses (💸, admin)
- Header shows **today's total**; filter by month (or **Clear** for all time).
- Add: title* + amount* + category (default `General`). Delete is admin-only.

### 3.8 Z-Reports (📊, admin)
- **Daily / Monthly / Yearly** toggle + date / month / year pickers + **Current** reset.
- Revenue-trend chart, cards for Revenue / GST collected / Net Profit /
  Orders, payment-channel breakdown, **Dues Aging** (with WhatsApp reminders),
  **Critical Restock** table with PO export.

### 3.9 Store Settings (🏬, admin, sidebar bottom)
The single place for all store defaults (persisted in DB, applied immediately):

| Tab | Fields |
|---|---|
| 🏪 Store | Name*, location, address (on invoice), phone, GSTIN (on invoice), invoice footer, logo upload (PNG/JPG/WEBP/GIF ≤ 2 MB) / remove |
| 🧾 Billing | Default payment mode, max discount % (0–90), UPI ID (scan-to-pay QR on invoices) |
| ⭐ Loyalty & Udhaar | Default credit limit for new customers, spend-per-point (₹X = 1 pt), max redeem % of bill |
| 📦 Inventory | Default unit, default GST %, default low-stock threshold |
| 🗄️ Database | **Local** (server `.env` config) vs **Remote** (cloud Postgres URL): Test Connection, then Switch Database. Switching never moves existing data — each DB keeps its own bills; login accounts sync automatically. The remote URL is stored on this server only and never shown again. A dead remote never blocks switching back. |

`.env` `STORE_*` values only seed first-run blanks — afterwards the menu owns them.

### 3.10 Users (👥, admin)
- Add / edit / delete login accounts for staff. Fields: username*, full name,
  password* (min 6 chars), role (admin / staff).
- Edit lets you change name, role and (optionally) reset the password —
  leave the password box blank to keep the current one.
- Guards: you can't demote or delete your own account, delete the last admin,
  or reuse an existing username. All changes appear in the Activity Log.

### 3.11 Activity Log (📝, admin)
- Every admin change (settings, products, categories, vendors via products,
  user accounts, customer deletes, expense deletes, repayments, returns, logo,
  backups) is recorded with user, role and timestamp.
- Filter by action type or search by user/detail; paginated like other tables.

## 4. Keyboard shortcuts

| Keys | Action |
|---|---|
| `Ctrl+Enter` | Finalize order (billing) |
| `Ctrl+S` | Go to billing + focus scan bar |
| `F2` | Focus scan bar (billing) |
| `↑` / `↓` + `Enter` | Highlight / add search result (billing) |
| `1` `2` `3` `4` | Payment: Cash / UPI / Card / Udhaar (billing) |
| `Esc` | Close open modal, else clear cart |

## 5. Business rules (cheat sheet)

- **Loyalty:** earn 1 pt per ₹X of final bill (default X=100); redeem 1 pt = ₹1,
  max Y% of bill (default 20%), never more than the customer's point balance.
- **Discounts:** 0–max% per bill (default 50%), applied before loyalty redemption.
- **Udhaar:** checkout on credit needs a customer and is blocked past their limit;
  returns on Udhaar bills credit dues back + ledger entry.
- **Lists:** page sizes 15/25/50/100 (remembered per table); out-of-range pages
  clamp to the last page.

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `Database error` / degraded health | Check Store Settings → Database tab (active DB reachable?), `.env` (`DATABASE_URL` or `DB_*`), Postgres running, `GET /api/health` |
| Login fails on fresh install | Run `python seed.py` (creates admin/staff); `--reset-passwords` to restore demo passwords |
| Camera scan fails | Serve over localhost/HTTPS; grant camera permission; use manual barcode fallback |
| CSV import reports skipped rows | Required `name`; check numeric columns; ≤ 2 MB / 2000 rows |
| Staff can't see a button | Expected — admin-only capability (see §2) |
| Logo missing on invoice | Upload via Store Settings; or set `STORE_LOGO` URL |
