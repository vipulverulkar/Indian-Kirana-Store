-- PostgreSQL Database Schema for Kirana Store Application

CREATE TABLE IF NOT EXISTS app_users (
    user_id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'staff' CHECK (role IN ('admin', 'staff')),
    full_name VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(15) UNIQUE NOT NULL,
    credit_limit NUMERIC(10, 2) DEFAULT 10000.00 CHECK (credit_limit >= 0),
    current_balance NUMERIC(10, 2) DEFAULT 0.00,
    loyalty_points INTEGER DEFAULT 0,
    lifetime_spend NUMERIC(10, 2) DEFAULT 0.00,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    product_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    barcode VARCHAR(50) UNIQUE,
    unit VARCHAR(20) NOT NULL,
    stock_quantity NUMERIC(10, 3) NOT NULL CHECK (stock_quantity >= 0),
    cost_price NUMERIC(10, 2) NOT NULL CHECK (cost_price >= 0),
    unit_price NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0),
    gst_slab NUMERIC(5, 2) NOT NULL CHECK (gst_slab >= 0 AND gst_slab <= 100),
    min_threshold NUMERIC(10, 3) DEFAULT 5.000,
    distributor_name VARCHAR(255),
    category VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    order_id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT REFERENCES customers(customer_id),
    user_id BIGINT REFERENCES app_users(user_id),
    order_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    total_amount NUMERIC(10, 2) NOT NULL,
    total_cgst NUMERIC(10, 2) NOT NULL,
    total_sgst NUMERIC(10, 2) NOT NULL,
    total_profit NUMERIC(10, 2) NOT NULL,
    payment_mode VARCHAR(20) NOT NULL,
    payment_status VARCHAR(20) NOT NULL,
    final_invoice_amount NUMERIC(10, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    item_id BIGSERIAL PRIMARY KEY,
    order_id BIGINT REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id BIGINT REFERENCES products(product_id),
    quantity NUMERIC(10, 3) NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(10, 2) NOT NULL,
    cost_price NUMERIC(10, 2) NOT NULL,
    gst_slab NUMERIC(5, 2) NOT NULL,
    subtotal NUMERIC(10, 2) NOT NULL,
    cgst_amount NUMERIC(10, 2) NOT NULL,
    sgst_amount NUMERIC(10, 2) NOT NULL,
    line_total NUMERIC(10, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS udhaar_ledger (
    transaction_id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT REFERENCES customers(customer_id),
    order_id BIGINT REFERENCES orders(order_id),
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    transaction_type VARCHAR(10) NOT NULL CHECK (transaction_type IN ('Debit', 'Credit')),
    transaction_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    remarks TEXT
);

CREATE INDEX IF NOT EXISTS idx_customer_phone ON customers(phone);
CREATE INDEX IF NOT EXISTS idx_product_barcode ON products(barcode);
CREATE INDEX IF NOT EXISTS idx_order_date ON orders(order_date);
CREATE INDEX IF NOT EXISTS idx_ledger_customer ON udhaar_ledger(customer_id);

-- Seed Data: Indian Grocery Products (idempotent via ON CONFLICT DO NOTHING)
INSERT INTO products (name, barcode, unit, stock_quantity, cost_price, unit_price, gst_slab, min_threshold, distributor_name, category) VALUES
('Toor Dal', '1001', 'kg', 50.000, 80.00, 120.00, 0, 10, 'Bharat Grains', 'Pulses'),
('Basmati Rice', '1002', 'kg', 100.000, 60.00, 95.00, 5, 20, 'Indus Rice Co', 'Grains'),
('Mustard Oil', '1003', 'L', 30.000, 110.00, 150.00, 12, 5, 'Fortune Oils', 'Oil'),
('Tata Salt', '1004', 'packet', 40.000, 15.00, 25.00, 0, 10, 'Tata Consumer', 'Spices'),
('Sugar', '1005', 'kg', 200.000, 30.00, 45.00, 5, 20, 'Local Mill', 'Grains'),
('Amul Butter', '1006', 'packet', 20.000, 45.00, 60.00, 12, 5, 'Amul Dairy', 'Dairy'),
('Maggi Noodles', '1007', 'packet', 60.000, 10.00, 14.00, 12, 15, 'Nestle India', 'Instant'),
('Parle-G', '1008', 'packet', 100.000, 3.00, 5.00, 18, 20, 'Parle Products', 'Biscuits'),
('Tea Powder', '1009', 'packet', 25.000, 80.00, 110.00, 5, 5, 'Tata Tea', 'Beverages'),
('Turmeric Powder', '1010', 'packet', 30.000, 20.00, 35.00, 5, 10, 'Everest Spices', 'Spices'),
('Moong Dal', '1011', 'kg', 40.000, 70.00, 110.00, 0, 10, 'Bharat Grains', 'Pulses'),
('Sona Masoori Rice', '1012', 'kg', 150.000, 40.00, 65.00, 5, 20, 'Indus Rice Co', 'Grains'),
('Sunflower Oil', '1013', 'L', 25.000, 100.00, 140.00, 12, 5, 'Fortune Oils', 'Oil'),
('Black Pepper', '1014', 'packet', 20.000, 40.00, 70.00, 5, 5, 'Everest Spices', 'Spices'),
('Ghee (Pure Cow)', '1015', 'L', 15.000, 450.00, 600.00, 12, 5, 'Amul Dairy', 'Dairy'),
('Paneer', '1016', 'packet', 10.000, 180.00, 250.00, 5, 5, 'Amul Dairy', 'Dairy'),
('Red Chili Powder', '1017', 'packet', 35.000, 30.00, 55.00, 5, 10, 'Everest Spices', 'Spices'),
('Cloves', '1018', 'packet', 15.000, 120.00, 180.00, 5, 5, 'Everest Spices', 'Spices'),
('Digestive Biscuits', '1019', 'packet', 50.000, 20.00, 30.00, 18, 10, 'Britannia', 'Biscuits'),
('Green Tea', '1020', 'packet', 20.000, 90.00, 140.00, 5, 5, 'Lipton India', 'Beverages'),
('Honey', '1021', 'bottle', 12.000, 150.00, 220.00, 12, 5, 'Dabur', 'Health'),
('Almonds (Badam)', '1022', 'kg', 10.000, 600.00, 850.00, 12, 2, 'DryFruit Co', 'Dry Fruits'),
('Cashews (Kaju)', '1023', 'kg', 8.000, 700.00, 950.00, 12, 2, 'DryFruit Co', 'Dry Fruits'),
('Poha', '1024', 'kg', 30.000, 35.00, 55.00, 0, 10, 'Bharat Grains', 'Grains'),
('Wheat Flour (Atta)', '1025', 'kg', 200.000, 25.00, 40.00, 0, 50, 'Aashirvaad', 'Grains')
ON CONFLICT (barcode) DO NOTHING;
-- Indian grocery master catalog (idempotent via ON CONFLICT DO NOTHING).
-- Barcodes 2001+ never clash with the base seeds (1001-1025) or auto KP codes.
INSERT INTO products (name, barcode, unit, stock_quantity, cost_price, unit_price, gst_slab, min_threshold, distributor_name, category) VALUES
-- Grains
('India Gate Rozzana Rice', '2001', 'kg', 80.000, 62.00, 78.00, 5, 15, 'KRBL', 'Grains'),
('Daawat Brown Rice', '2002', 'kg', 30.000, 105.00, 130.00, 5, 8, 'LT Foods', 'Grains'),
('Idli Rice', '2003', 'kg', 60.000, 52.00, 65.00, 5, 12, 'Bharat Grains', 'Grains'),
('Sooji (Rava)', '2004', 'kg', 40.000, 38.00, 48.00, 5, 8, 'Bharat Grains', 'Grains'),
('Maida', '2005', 'kg', 40.000, 40.00, 50.00, 5, 8, 'Bharat Grains', 'Grains'),
('Besan', '2006', 'kg', 35.000, 72.00, 90.00, 5, 8, 'Bharat Grains', 'Grains'),
('Murmura (Puffed Rice)', '2007', 'packet', 40.000, 30.00, 42.00, 5, 10, 'Local Mill', 'Grains'),
('Sabudana', '2008', 'kg', 20.000, 80.00, 100.00, 5, 5, 'Bharat Grains', 'Grains'),
('Dalia (Broken Wheat)', '2009', 'kg', 25.000, 45.00, 58.00, 5, 5, 'Bharat Grains', 'Grains'),
('Seviyan (Vermicelli)', '2010', 'packet', 30.000, 35.00, 45.00, 12, 8, 'Bambino', 'Grains'),
('Lijjat Papad', '2011', 'packet', 30.000, 42.00, 55.00, 5, 8, 'Lijjat', 'Grains'),
('Cornflakes', '2012', 'packet', 15.000, 180.00, 225.00, 18, 5, 'Kellogg India', 'Grains'),
-- Pulses
('Chana Dal', '2013', 'kg', 40.000, 95.00, 118.00, 5, 10, 'Bharat Grains', 'Pulses'),
('Urad Dal Split', '2014', 'kg', 30.000, 110.00, 135.00, 5, 8, 'Bharat Grains', 'Pulses'),
('Urad Whole (Sabut)', '2015', 'kg', 25.000, 105.00, 130.00, 5, 6, 'Bharat Grains', 'Pulses'),
('Masoor Dal Split', '2016', 'kg', 35.000, 88.00, 110.00, 5, 8, 'Bharat Grains', 'Pulses'),
('Masoor Whole (Sabut)', '2017', 'kg', 25.000, 85.00, 105.00, 5, 6, 'Bharat Grains', 'Pulses'),
('Kabuli Chana', '2018', 'kg', 30.000, 92.00, 115.00, 5, 8, 'Bharat Grains', 'Pulses'),
('Rajma (Red Kidney Beans)', '2019', 'kg', 30.000, 108.00, 135.00, 5, 8, 'Bharat Grains', 'Pulses'),
('Green Moong Whole', '2020', 'kg', 25.000, 98.00, 122.00, 5, 6, 'Bharat Grains', 'Pulses'),
('Lobia (Black Eyed Peas)', '2021', 'kg', 20.000, 90.00, 112.00, 5, 5, 'Bharat Grains', 'Pulses'),
-- Spices
('Jeera (Cumin)', '2022', 'packet', 40.000, 38.00, 48.00, 5, 10, 'Everest Spices', 'Spices'),
('Dhania Powder', '2023', 'packet', 40.000, 22.00, 28.00, 5, 10, 'Everest Spices', 'Spices'),
('Garam Masala', '2024', 'packet', 30.000, 32.00, 42.00, 5, 8, 'MDH', 'Spices'),
('Chhole Masala', '2025', 'packet', 25.000, 35.00, 45.00, 5, 6, 'MDH', 'Spices'),
('Sambar Powder', '2026', 'packet', 20.000, 30.00, 40.00, 5, 6, 'MTR Foods', 'Spices'),
('Rai (Mustard Seeds)', '2027', 'packet', 30.000, 12.00, 16.00, 5, 8, 'Everest Spices', 'Spices'),
('Methi Seeds', '2028', 'packet', 20.000, 14.00, 18.00, 5, 5, 'Everest Spices', 'Spices'),
('Saunf (Fennel)', '2029', 'packet', 20.000, 28.00, 36.00, 5, 5, 'Everest Spices', 'Spices'),
('Elaichi (Green Cardamom)', '2030', 'packet', 10.000, 140.00, 180.00, 5, 3, 'Everest Spices', 'Spices'),
('Dalchini (Cinnamon)', '2031', 'packet', 15.000, 30.00, 40.00, 5, 4, 'Everest Spices', 'Spices'),
('Tej Patta (Bay Leaves)', '2032', 'packet', 15.000, 18.00, 25.00, 5, 4, 'Everest Spices', 'Spices'),
('Hing (Asafoetida)', '2033', 'packet', 12.000, 55.00, 72.00, 12, 3, 'MDH', 'Spices'),
('Pav Bhaji Masala', '2034', 'packet', 20.000, 30.00, 40.00, 5, 5, 'MDH', 'Spices'),
('Biryani Masala', '2035', 'packet', 20.000, 32.00, 42.00, 5, 5, 'MDH', 'Spices'),
('Sendha Namak (Rock Salt)', '2036', 'packet', 25.000, 22.00, 30.00, 5, 6, 'Tata Consumer', 'Spices'),
('Kala Namak (Black Salt)', '2037', 'packet', 15.000, 14.00, 18.00, 5, 4, 'MDH', 'Spices'),
('Amchur (Dry Mango Powder)', '2038', 'packet', 15.000, 25.00, 32.00, 5, 4, 'Everest Spices', 'Spices'),
('Kasuri Methi', '2039', 'packet', 15.000, 22.00, 30.00, 5, 4, 'MDH', 'Spices'),
-- Oil
('Groundnut Oil', '2040', 'L', 25.000, 135.00, 165.00, 5, 6, 'Fortune Oils', 'Oil'),
('Soybean Oil', '2041', 'L', 25.000, 125.00, 155.00, 5, 6, 'Fortune Oils', 'Oil'),
('Til (Sesame) Oil', '2042', 'bottle', 15.000, 150.00, 190.00, 5, 4, 'Idhayam', 'Oil'),
('Coconut Oil', '2043', 'bottle', 20.000, 160.00, 200.00, 5, 5, 'Marico', 'Oil'),
('Olive Oil', '2044', 'bottle', 8.000, 550.00, 699.00, 5, 2, 'Figaro', 'Oil'),
('Vanaspati (Dalda)', '2045', 'packet', 15.000, 120.00, 150.00, 5, 4, 'Bunge India', 'Oil'),
('Rice Bran Oil', '2046', 'L', 15.000, 140.00, 175.00, 5, 4, 'Fortune Oils', 'Oil'),
-- Dairy
('Toned Milk', '2047', 'packet', 30.000, 26.00, 30.00, 0, 10, 'Amul Dairy', 'Dairy'),
('Curd Cup', '2048', 'packet', 25.000, 30.00, 35.00, 5, 8, 'Amul Dairy', 'Dairy'),
('Chaas (Buttermilk)', '2049', 'packet', 30.000, 12.00, 15.00, 5, 10, 'Amul Dairy', 'Dairy'),
('Cheese Slices', '2050', 'packet', 15.000, 60.00, 75.00, 12, 5, 'Amul Dairy', 'Dairy'),
('Milk Powder', '2051', 'packet', 12.000, 170.00, 210.00, 5, 4, 'Amul Dairy', 'Dairy'),
('Condensed Milk', '2052', 'bottle', 10.000, 110.00, 135.00, 12, 3, 'Nestle India', 'Dairy'),
-- Beverages
('Tata Tea Gold', '2053', 'packet', 30.000, 130.00, 155.00, 5, 8, 'Tata Consumer', 'Beverages'),
('Wagh Bakri Tea', '2054', 'packet', 20.000, 240.00, 285.00, 5, 5, 'Wagh Bakri', 'Beverages'),
('Bru Instant Coffee', '2055', 'packet', 20.000, 140.00, 165.00, 5, 5, 'HUL', 'Beverages'),
('Nescafe Classic', '2056', 'packet', 18.000, 150.00, 180.00, 5, 5, 'Nestle India', 'Beverages'),
('Bournvita', '2057', 'packet', 18.000, 210.00, 255.00, 18, 5, 'Cadbury', 'Beverages'),
('Horlicks', '2058', 'packet', 15.000, 215.00, 260.00, 18, 5, 'HUL', 'Beverages'),
('Rooh Afza', '2059', 'bottle', 15.000, 140.00, 165.00, 12, 4, 'Hamdard', 'Beverages'),
('Mango Drink (Frooti)', '2060', 'bottle', 25.000, 95.00, 115.00, 12, 8, 'Parle Agro', 'Beverages'),
('Cola', '2061', 'bottle', 40.000, 38.00, 45.00, 28, 12, 'Coca-Cola India', 'Beverages'),
('Filter Coffee Powder', '2062', 'packet', 12.000, 110.00, 135.00, 5, 4, 'Tata Consumer', 'Beverages'),
-- Biscuits
('Marie Gold', '2063', 'packet', 40.000, 28.00, 35.00, 18, 10, 'Britannia', 'Biscuits'),
('Bourbon', '2064', 'packet', 35.000, 32.00, 40.00, 18, 10, 'Britannia', 'Biscuits'),
('Oreo', '2065', 'packet', 30.000, 38.00, 48.00, 18, 8, 'Cadbury', 'Biscuits'),
('Salted Crackers (Monaco)', '2066', 'packet', 35.000, 25.00, 32.00, 18, 10, 'Parle Products', 'Biscuits'),
('Rusk', '2067', 'packet', 30.000, 35.00, 45.00, 18, 8, 'Britannia', 'Biscuits'),
('Hide & Seek', '2068', 'packet', 30.000, 30.00, 38.00, 18, 8, 'Parle Products', 'Biscuits'),
-- Instant
('Yippee Noodles', '2069', 'packet', 40.000, 48.00, 58.00, 12, 10, 'ITC', 'Instant'),
('Pasta', '2070', 'packet', 25.000, 55.00, 70.00, 12, 6, 'ITC', 'Instant'),
('Upma Mix (MTR)', '2071', 'packet', 20.000, 60.00, 75.00, 18, 5, 'MTR Foods', 'Instant'),
('Idli Mix', '2072', 'packet', 20.000, 55.00, 70.00, 18, 5, 'MTR Foods', 'Instant'),
('Dosa Mix', '2073', 'packet', 20.000, 58.00, 72.00, 18, 5, 'MTR Foods', 'Instant'),
('Gulab Jamun Mix', '2074', 'packet', 15.000, 95.00, 120.00, 18, 4, 'MTR Foods', 'Instant'),
('Cup Noodles', '2075', 'packet', 25.000, 45.00, 55.00, 12, 8, 'Nestle India', 'Instant'),
-- Dry Fruits
('Kishmish (Raisins)', '2076', 'packet', 20.000, 70.00, 90.00, 12, 5, 'DryFruit Co', 'Dry Fruits'),
('Pista (Pistachios)', '2077', 'packet', 12.000, 120.00, 150.00, 12, 3, 'DryFruit Co', 'Dry Fruits'),
('Walnuts (Akhrot)', '2078', 'packet', 12.000, 150.00, 190.00, 12, 3, 'DryFruit Co', 'Dry Fruits'),
('Khajur (Dates)', '2079', 'packet', 15.000, 110.00, 140.00, 12, 4, 'DryFruit Co', 'Dry Fruits'),
('Anjeer (Figs)', '2080', 'packet', 8.000, 130.00, 165.00, 12, 2, 'DryFruit Co', 'Dry Fruits'),
('Groundnuts (Raw Peanuts)', '2081', 'packet', 25.000, 55.00, 70.00, 5, 6, 'DryFruit Co', 'Dry Fruits'),
-- Health
('Instant Oats', '2082', 'packet', 18.000, 95.00, 120.00, 18, 5, 'Marico', 'Health'),
('Roasted Makhana', '2083', 'packet', 15.000, 80.00, 105.00, 12, 4, 'Farmley', 'Health'),
('Sugar-Free Sweetener', '2084', 'packet', 12.000, 95.00, 120.00, 18, 3, 'Zydus Wellness', 'Health'),
('Chyawanprash', '2085', 'packet', 12.000, 160.00, 200.00, 12, 3, 'Dabur', 'Health'),
('Jaggery Powder', '2086', 'packet', 25.000, 35.00, 45.00, 5, 6, 'Organic India', 'Health'),
-- Snacks
('Potato Wafers', '2087', 'packet', 40.000, 18.00, 25.00, 12, 12, 'Balaji Wafers', 'Snacks'),
('Aloo Bhujia', '2088', 'packet', 30.000, 40.00, 52.00, 12, 8, 'Haldiram''s', 'Snacks'),
('Mixture (South Indian)', '2089', 'packet', 25.000, 55.00, 70.00, 12, 8, 'Haldiram''s', 'Snacks'),
('Banana Chips', '2090', 'packet', 25.000, 35.00, 45.00, 12, 6, 'Balaji Wafers', 'Snacks'),
('Khakhra', '2091', 'packet', 20.000, 45.00, 58.00, 12, 6, 'Haldiram''s', 'Snacks'),
('Masala Peanuts', '2092', 'packet', 25.000, 38.00, 50.00, 12, 6, 'Haldiram''s', 'Snacks'),
('Popcorn Kernels', '2093', 'packet', 20.000, 40.00, 55.00, 5, 5, 'ACT II', 'Snacks'),
('Ratlam Sev', '2094', 'packet', 25.000, 35.00, 45.00, 12, 6, 'Haldiram''s', 'Snacks'),
-- Household
('Detergent Powder', '2095', 'packet', 25.000, 110.00, 135.00, 18, 6, 'HUL', 'Household'),
('Detergent Bar', '2096', 'packet', 40.000, 28.00, 35.00, 18, 10, 'HUL', 'Household'),
('Dishwash Bar (Vim)', '2097', 'packet', 40.000, 32.00, 40.00, 18, 10, 'HUL', 'Household'),
('Floor Cleaner (Lizol)', '2098', 'bottle', 15.000, 85.00, 105.00, 18, 4, 'Reckitt', 'Household'),
('Toilet Cleaner (Harpic)', '2099', 'bottle', 15.000, 88.00, 108.00, 18, 4, 'Reckitt', 'Household'),
('Scrub Pads (3 pc)', '2100', 'packet', 20.000, 30.00, 42.00, 18, 5, 'Scotch-Brite', 'Household'),
('Agarbatti', '2101', 'packet', 30.000, 35.00, 50.00, 12, 8, 'Cycle Pure', 'Household'),
('Mosquito Coil', '2102', 'packet', 25.000, 55.00, 72.00, 12, 6, 'Good Knight', 'Household'),
('Matchbox (10 pc)', '2103', 'packet', 50.000, 12.00, 15.00, 12, 12, 'Ship', 'Household'),
('Garbage Bags', '2104', 'packet', 15.000, 90.00, 120.00, 18, 4, 'Ezee', 'Household'),
-- Personal Care
('Bath Soap (Lux)', '2105', 'packet', 50.000, 32.00, 40.00, 18, 12, 'HUL', 'Personal Care'),
('Shampoo', '2106', 'bottle', 18.000, 150.00, 185.00, 18, 5, 'HUL', 'Personal Care'),
('Toothpaste', '2107', 'packet', 25.000, 95.00, 120.00, 18, 6, 'Colgate India', 'Personal Care'),
('Toothbrush', '2108', 'piece', 30.000, 28.00, 40.00, 18, 8, 'Colgate India', 'Personal Care'),
('Coconut Hair Oil', '2109', 'bottle', 20.000, 95.00, 118.00, 18, 5, 'Marico', 'Personal Care'),
('Sanitary Pads', '2110', 'packet', 15.000, 110.00, 135.00, 0, 4, 'P&G', 'Personal Care')
ON CONFLICT (barcode) DO NOTHING;
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
-- Store defaults (Settings menu): key/value table, no seed rows needed
-- (get_all_settings() falls back to builtins + STORE_* env vars).
CREATE TABLE IF NOT EXISTS store_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
-- Staff activity log (who changed what, when)
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
