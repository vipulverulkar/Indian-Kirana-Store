-- Staff activity log (who changed what, when). Idempotent.
CREATE TABLE IF NOT EXISTS activity_log (
    log_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES app_users(user_id),
    username VARCHAR(50),
    role VARCHAR(20),
    action VARCHAR(100) NOT NULL,
    entity VARCHAR(100),
    entity_id VARCHAR(100),
    detail TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_activity_date ON activity_log(created_at DESC);
