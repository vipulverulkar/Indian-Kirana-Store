-- Procurement log: the same product can be purchased at different rates over
-- time (vendors / price changes). Every stock-in records which qty came in at
-- which cost, from whom, against which bill.
CREATE TABLE IF NOT EXISTS purchases (
    purchase_id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity NUMERIC(10, 3) NOT NULL CHECK (quantity > 0),
    cost_price NUMERIC(10, 2) NOT NULL CHECK (cost_price >= 0),
    vendor VARCHAR(255),
    bill_no VARCHAR(100),
    user_id BIGINT REFERENCES app_users(user_id),
    purchase_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_purchases_product ON purchases(product_id);
CREATE INDEX IF NOT EXISTS idx_purchases_date ON purchases(purchase_date);
