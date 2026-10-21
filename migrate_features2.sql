-- Feature pack 2: discounts, loyalty redemption, returns, expenses
-- Idempotent: safe to run multiple times (uses DO blocks).

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='orders' AND column_name='discount_amount') THEN
    ALTER TABLE orders ADD COLUMN discount_amount NUMERIC(10,2) NOT NULL DEFAULT 0;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='orders' AND column_name='loyalty_redeemed') THEN
    ALTER TABLE orders ADD COLUMN loyalty_redeemed INTEGER NOT NULL DEFAULT 0;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='orders' AND column_name='order_status') THEN
    ALTER TABLE orders ADD COLUMN order_status VARCHAR(20) NOT NULL DEFAULT 'Completed';
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS returns (
    return_id BIGSERIAL PRIMARY KEY,
    order_id BIGINT REFERENCES orders(order_id),
    product_id BIGINT REFERENCES products(product_id),
    quantity NUMERIC(10,3) NOT NULL CHECK (quantity > 0),
    refund_amount NUMERIC(10,2) NOT NULL CHECK (refund_amount >= 0),
    reason TEXT,
    user_id BIGINT REFERENCES app_users(user_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_returns_order ON returns(order_id);

CREATE TABLE IF NOT EXISTS expenses (
    expense_id BIGSERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    amount NUMERIC(10,2) NOT NULL CHECK (amount > 0),
    category VARCHAR(100) DEFAULT 'General',
    notes TEXT,
    user_id BIGINT REFERENCES app_users(user_id),
    expense_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_expense_date ON expenses(expense_date);
