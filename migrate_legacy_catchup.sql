-- Catch-up for DBs created before total_profit / cost_price columns existed
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='orders' AND column_name='total_profit') THEN
    ALTER TABLE orders ADD COLUMN total_profit NUMERIC(10,2) NOT NULL DEFAULT 0;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='order_items' AND column_name='cost_price') THEN
    ALTER TABLE order_items ADD COLUMN cost_price NUMERIC(10,2) NOT NULL DEFAULT 0;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='products' AND column_name='updated_at') THEN
    ALTER TABLE products ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='products' AND column_name='cost_price') THEN
    ALTER TABLE products ADD COLUMN cost_price NUMERIC(10,2) NOT NULL DEFAULT 0;
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='customers' AND column_name='lifetime_spend') THEN
    ALTER TABLE customers ADD COLUMN lifetime_spend NUMERIC(10,2) DEFAULT 0.00;
  END IF;
END $$;
