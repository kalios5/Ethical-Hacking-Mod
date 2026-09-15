-- =============================================================================
-- 02_seed.sql  -  starter data for the vulnerable e-commerce SaaS
-- -----------------------------------------------------------------------------
-- Runs after 01_schema.sql (before triggers), so these inserts are NOT logged
-- to db_change_log - keeps the change log clean for the demo.
--
-- Passwords below are stored as UNSALTED SHA-256 (hash_mode='weak') so the
-- "dump DB -> crack hashes" attack path works. Cleartext is in the comment for
-- YOUR reference only - obviously remove these comments from any handed-in copy.
-- =============================================================================

-- --- Tenants ----------------------------------------------------------------
INSERT INTO shops (id, name, domain) VALUES
    (1, 'Roses 4 Sale',   'roses-4-sale.com'),
    (2, 'Poppies 2 Buy',  'poppies-2-buy.com');

-- --- Users ------------------------------------------------------------------
-- role ENUM: guest / customer / admin / superadmin
INSERT INTO users (shop_id, username, email, password_hash, hash_mode, role, twofa_enabled) VALUES
    -- Platform super-admin (target of the infra hack). pw: SuperSecret@2026
    (1, 'superadmin', 'root@saas.local',
        '6ef0b9132d9872269e28d8022868f2044fe398c3ad2a790e820933d5e1d352c5', 'weak', 'superadmin', 0),

    -- Shop admins (target of "Broken Access into Admin Account" / IDOR).
    (1, 'admin', 'admin@roses-4-sale.com',
        'e86f78a8a3caf0b60d8e74e5942aa6d86dc150cd3c03338aef25b7d2d7e3acc7', 'weak', 'admin', 0),   -- pw: Admin@123
    (2, 'admin', 'admin@poppies-2-buy.com',
        '60cce01d143008b7967f92d632ee5920d6e0b6e06edb163858e2d3d99f22d6d2', 'weak', 'admin', 0),   -- pw: Petal!2026

    -- Regular customers.
    (1, 'alice',   'alice@example.com',
        '0b14d501a594442a01c6859541bcb3e8164d183d32937b851835442f69d5c94e', 'weak', 'customer', 0), -- pw: password1
    (1, 'bob',     'bob@example.com',
        '1c8bfe8f801d79745c4631d09fff36c82aa37fc4cce4fc946683d7b336b63032', 'weak', 'customer', 0), -- pw: letmein
    (2, 'charlie', 'charlie@example.com',
        'a941a4c4fd0c01cddef61b8be963bf4c1e2b0811c037ce3f1835fddf6ef6c223', 'weak', 'customer', 0); -- pw: sunshine

-- --- Products ---------------------------------------------------------------
INSERT INTO products (shop_id, name, description, price_cents, stock) VALUES
    (1, 'Red Rose Bouquet',   'A dozen long-stem red roses.',      2999, 50),
    (1, 'White Rose Single',  'A single white rose.',               399, 200),
    (1, 'Rose Gift Box',      'Roses in a keepsake box.',          4599, 25),
    (2, 'Poppy Seed Packet',  'Grow your own poppies.',             299, 500),
    (2, 'Wild Poppy Bunch',   'Freshly cut wild poppies.',         1899, 40),
    (2, 'Poppy Wreath',       'Remembrance wreath.',               3599, 15);

-- --- Plugins (per shop) -----------------------------------------------------
-- Matches the plugin folders in the repo: welcome_message, discount_banner,
-- newsletter_signup, _template_plugin.
INSERT INTO plugins (shop_id, name, enabled, is_third_party) VALUES
    (1, 'welcome_message',   1, 0),
    (1, 'discount_banner',   1, 0),
    (1, 'newsletter_signup', 0, 0),
    (2, 'welcome_message',   1, 0),
    (2, 'newsletter_signup', 1, 0);

-- --- One sample order so reports/CRUD have data ------------------------------
INSERT INTO orders (id, user_id, shop_id, total_cents, status) VALUES
    (1, (SELECT id FROM users WHERE username='alice' AND shop_id=1), 1, 3398, 'paid');
INSERT INTO order_items (order_id, product_id, quantity, unit_price_cents) VALUES
    (1, (SELECT id FROM products WHERE name='Red Rose Bouquet'), 1, 2999),
    (1, (SELECT id FROM products WHERE name='White Rose Single'), 1, 399);
