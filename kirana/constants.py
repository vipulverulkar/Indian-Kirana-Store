"""Application-wide constants.

All magic numbers, default values, and system limits live here so they
are easy to locate, maintain, and configure from one source.
"""

# ---------------------------------------------------------------------------
# Server & App Defaults
# ---------------------------------------------------------------------------
DEFAULT_PORT = 5000
DEFAULT_SECRET_KEY = "kirana-super-secret-key"
DEFAULT_APP_NAME = "KiranaPro"
DEFAULT_VERSION = "1.0.0"
DEFAULT_LICENSE = "GPL-3.0"
DEFAULT_DEVELOPER_NAME = "Vipul Verulkar"
DEFAULT_DEVELOPER_CONTACT = "vipulverulkar@gmail.com"
DEFAULT_DEVELOPER_LOCATION = "India"

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
ROLE_ADMIN = "admin"
ROLE_STAFF = "staff"
ROLES = (ROLE_ADMIN, ROLE_STAFF)

# ---------------------------------------------------------------------------
# Order / payment statuses
# ---------------------------------------------------------------------------
PAYMENT_STATUS_PAID = "Paid"
PAYMENT_STATUS_PENDING = "Pending"
PAYMENT_STATUS_REFUNDED = "Refunded"

ORDER_STATUS_COMPLETED = "Completed"
ORDER_STATUS_RETURNED = "Returned"
ORDER_STATUS_PARTIALLY_RETURNED = "Partially Returned"

# ---------------------------------------------------------------------------
# Ledger transaction types
# ---------------------------------------------------------------------------
TXN_DEBIT = "Debit"
TXN_CREDIT = "Credit"

# ---------------------------------------------------------------------------
# Payment modes
# ---------------------------------------------------------------------------
PAYMENT_MODE_CASH = "Cash"
PAYMENT_MODE_UPI = "UPI"
PAYMENT_MODE_CARD = "Card"
PAYMENT_MODE_UDHAAR = "Udhaar"
ALL_PAYMENT_MODES = (PAYMENT_MODE_CASH, PAYMENT_MODE_UPI, PAYMENT_MODE_CARD, PAYMENT_MODE_UDHAAR)

# ---------------------------------------------------------------------------
# Default store & business text
# ---------------------------------------------------------------------------
DEFAULT_STORE_NAME = "KiranaPro"
DEFAULT_STORE_LOCATION = "Default Location"
DEFAULT_INVOICE_FOOTER = "Thank you, visit again!"
DEFAULT_RETURN_REASON = "Customer return"
DEFAULT_REPAYMENT_REMARK = "Cash repayment (Jama)"
DEFAULT_PURCHASE_REMARK = "Purchase on credit"
DEFAULT_EXPENSE_CATEGORY = "General"
DEFAULT_PAYMENT_MODE = "Cash"
DEFAULT_UNIT = "packet"
ALL_UNITS = ("kg", "packet", "bottle", "piece", "L", "g")

# ---------------------------------------------------------------------------
# Barcode generation
# ---------------------------------------------------------------------------
BARCODE_PREFIX = "KP"
BARCODE_DIGIT_COUNT = 8          # digits after prefix -> e.g. KP00012345
BARCODE_MAX_RETRIES = 20         # max generation collisions before error

# ---------------------------------------------------------------------------
# File / upload limits
# ---------------------------------------------------------------------------
MAX_LOGO_BYTES = 2 * 1024 * 1024        # 2 MB
MAX_IMPORT_BYTES = 2 * 1024 * 1024      # 2 MB
MAX_IMPORT_ROWS = 2_000
LOGO_CACHE_SECONDS = 3_600              # 1 hour
ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

# ---------------------------------------------------------------------------
# Field length limits (mirroring DB schema)
# ---------------------------------------------------------------------------
MAX_LEN_PRODUCT_NAME = 255
MAX_LEN_CATEGORY = 100
MAX_LEN_VENDOR = 255
MAX_LEN_BILL_NO = 100
MAX_LEN_EXPENSE_TITLE = 255
MAX_LEN_EXPENSE_CATEGORY = 100
MAX_LEN_EXPENSE_NOTES = 1_000
MAX_LEN_RETURN_REASON = 500
MAX_LEN_STORE_NAME = 100
MAX_LEN_STORE_LOCATION = 200
MAX_LEN_STORE_ADDRESS = 500
MAX_LEN_STORE_PHONE_MIN = 6
MAX_LEN_STORE_PHONE_MAX = 15
MAX_LEN_STORE_PHONE_COL = 30
MAX_LEN_INVOICE_FOOTER = 500
MAX_LEN_GSTIN = 15
MAX_LEN_UPI_ID = 100
MAX_LEN_ACTIVITY_ACTION = 100
MAX_LEN_ACTIVITY_ENTITY = 100
MAX_LEN_ACTIVITY_ENTITY_ID = 100
MAX_LEN_ACTIVITY_DETAIL = 2_000
MAX_LEN_DB_VERSION = 120
MAX_LEN_USERNAME = 50
MAX_LEN_FULL_NAME = 100
MAX_LEN_PHONE_MIN = 6
MAX_LEN_PHONE_MAX = 15

# ---------------------------------------------------------------------------
# Validation ranges & business limits
# ---------------------------------------------------------------------------
MIN_PASSWORD_LEN = 6
MIN_GST_SLAB = 0
MAX_GST_SLAB = 100
MIN_DISCOUNT_PCT = 0
MAX_DISCOUNT_ALLOWED_PCT = 90
MAX_REDEEM_CAP_PCT = 100
MIN_LOYALTY_EARN_PER_RS = 1
MAX_LOYALTY_EARN_PER_RS = 100_000

# ---------------------------------------------------------------------------
# Pagination & Query Limits
# ---------------------------------------------------------------------------
ALLOWED_PER_PAGE = (15, 25, 50, 100)
DEFAULT_PER_PAGE = 15
MAX_ORDER_FETCH_LIMIT = 500
DEFAULT_ORDER_LIMIT = 100

# ---------------------------------------------------------------------------
# Report Ranges
# ---------------------------------------------------------------------------
MIN_REPORT_YEAR = 2000
MAX_REPORT_YEAR = 2100

# ---------------------------------------------------------------------------
# Backup / Restore Process Settings
# ---------------------------------------------------------------------------
BACKUP_PG_DUMP_TIMEOUT = 300      # seconds
BACKUP_PSQL_TIMEOUT = 120         # seconds
BACKUP_STDERR_PREVIEW_LEN = 500   # chars of stderr shown in error message

# ---------------------------------------------------------------------------
# Default Seed Credentials (can be overridden via SEED_* env vars)
# ---------------------------------------------------------------------------
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"
DEFAULT_ADMIN_FULL_NAME = "Store Owner"
DEFAULT_STAFF_USERNAME = "staff"
DEFAULT_STAFF_PASSWORD = "staff123"
DEFAULT_STAFF_FULL_NAME = "Counter Staff"

# ---------------------------------------------------------------------------
# Database Settings
# ---------------------------------------------------------------------------
SQLITE_DB_FILENAME = "kirana.db"
SQLITE_CONNECT_TIMEOUT = 30
