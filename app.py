"""KiranaPro entry point.

All routes live in the kirana/ package (one blueprint module per area):
    kirana/auth.py      - login, logout, session, role guards
    kirana/activity.py  - admin audit trail
    kirana/users.py     - login-account management
    kirana/core.py      - dashboard shell (/), health check
    kirana/store.py     - store info, settings API, logo upload, backup/restore
    kirana/config.py    - version, license and developer metadata
    kirana/settings.py  - persistent store defaults (store_settings table)
    kirana/products.py  - products, categories, inventory, CSV import/export
    kirana/customers.py - customers, Udhaar ledger, repayments
    kirana/orders.py    - orders, checkout, returns
    kirana/expenses.py  - daily expenses
    kirana/reports.py   - Z-report, dashboard stats, dues aging
    kirana/db.py        - SQLite/PostgreSQL connection and schema bootstrap
    kirana/utils.py     - validation, pagination, formatting helpers
"""
import os

from kirana import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=os.getenv("FLASK_DEBUG", "1") == "1", port=int(os.getenv("PORT", 5000)))
