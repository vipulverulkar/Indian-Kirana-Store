-- Store defaults (Settings menu): key/value table, no seed rows needed
-- (get_all_settings() falls back to builtins + STORE_* env vars).
CREATE TABLE IF NOT EXISTS store_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
