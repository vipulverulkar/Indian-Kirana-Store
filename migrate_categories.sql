-- Categories as first-class table (source of truth for dropdowns)
CREATE TABLE IF NOT EXISTS categories (
    category_id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Backfill from existing product categories
INSERT INTO categories (name)
SELECT DISTINCT TRIM(category) FROM products
WHERE category IS NOT NULL AND TRIM(category) <> ''
ON CONFLICT (name) DO NOTHING;
