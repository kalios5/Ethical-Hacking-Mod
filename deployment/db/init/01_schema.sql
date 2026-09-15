-- =============================================================================
-- 01_schema.sql  -  ICT2212 vulnerable e-commerce SaaS  -  DATABASE SCHEMA
-- -----------------------------------------------------------------------------
-- Runs automatically the first time the MySQL data volume is empty
-- (mounted into /docker-entrypoint-initdb.d). Owned by the DB-container member.
--
-- Design notes:
--   * Multi-tenant SaaS: one `shops` row per hosted store (e.g. roses-4-sale,
--     poppies-2-buy). Every user/product/order belongs to a shop.
--   * IDs are sequential AUTO_INCREMENT integers ON PURPOSE - this is what makes
--     the IDOR attack path in the plan possible. Do not switch to UUIDs.
--   * The `users.password_hash` column is what the "dump DB -> crack hashes"
--     attack targets. See DB_SETUP_GUIDE.md for the hashing toggle.
-- =============================================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- -----------------------------------------------------------------------------
-- Tenants (the shops hosted on our SaaS)
-- -----------------------------------------------------------------------------
CREATE TABLE shops (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(120)  NOT NULL,
    domain      VARCHAR(190)  NOT NULL UNIQUE,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- Users  (guest / customer / admin / superadmin)
-- -----------------------------------------------------------------------------
CREATE TABLE users (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    shop_id        INT           NOT NULL,
    username       VARCHAR(80)   NOT NULL,
    email          VARCHAR(190)  NOT NULL,
    -- The hash string itself. Format depends on PASSWORD_HASH_MODE:
    --   secure -> pbkdf2:sha256:...   weak -> 64-char sha256 hex   md5 -> 32-char hex
    password_hash  VARCHAR(255)  NOT NULL,
    hash_mode      VARCHAR(16)   NOT NULL DEFAULT 'weak',
    role           ENUM('guest','customer','admin','superadmin') NOT NULL DEFAULT 'customer',
    is_active      TINYINT(1)    NOT NULL DEFAULT 1,
    -- 2FA (plugin framework: "2FA" branch off Login)
    twofa_enabled  TINYINT(1)    NOT NULL DEFAULT 0,
    twofa_secret   VARCHAR(64)   NULL,
    failed_logins  INT           NOT NULL DEFAULT 0,
    last_login     DATETIME      NULL,
    created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_users_shop FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user_per_shop (shop_id, username)
) ENGINE=InnoDB;

CREATE INDEX ix_users_email ON users(email);
CREATE INDEX ix_users_role  ON users(role);

-- -----------------------------------------------------------------------------
-- Catalogue
-- -----------------------------------------------------------------------------
CREATE TABLE products (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    shop_id      INT           NOT NULL,
    name         VARCHAR(160)  NOT NULL,
    description  TEXT          NULL,
    price_cents  INT           NOT NULL DEFAULT 0,   -- store money as integer cents
    stock        INT           NOT NULL DEFAULT 0,
    image_path   VARCHAR(255)  NULL,                 -- "Video/Document Attachment" branch
    created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_products_shop FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE INDEX ix_products_shop ON products(shop_id);

-- -----------------------------------------------------------------------------
-- Cart  (one open row per user+product; "Add to cart" in the plugin framework)
-- -----------------------------------------------------------------------------
CREATE TABLE cart_items (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT   NOT NULL,
    product_id  INT   NOT NULL,
    quantity    INT   NOT NULL DEFAULT 1,
    added_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_cart_user    FOREIGN KEY (user_id)    REFERENCES users(id)    ON DELETE CASCADE,
    CONSTRAINT fk_cart_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    UNIQUE KEY uq_cart_user_product (user_id, product_id)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- Orders  ("Purchase")
-- -----------------------------------------------------------------------------
CREATE TABLE orders (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT   NOT NULL,
    shop_id      INT   NOT NULL,
    total_cents  INT   NOT NULL DEFAULT 0,
    status       ENUM('pending','paid','shipped','cancelled') NOT NULL DEFAULT 'pending',
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_orders_shop FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE order_items (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    order_id         INT NOT NULL,
    product_id       INT NOT NULL,
    quantity         INT NOT NULL DEFAULT 1,
    unit_price_cents INT NOT NULL DEFAULT 0,
    CONSTRAINT fk_oi_order   FOREIGN KEY (order_id)   REFERENCES orders(id)   ON DELETE CASCADE,
    CONSTRAINT fk_oi_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- Plugin framework  (per-shop plugin enable/disable + JSON config)
-- Mirrors pluginmanager.models.PluginToggle but scoped to a shop.
-- -----------------------------------------------------------------------------
CREATE TABLE plugins (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    shop_id     INT           NOT NULL,
    name        VARCHAR(100)  NOT NULL,      -- folder name, e.g. 'newsletter_signup'
    enabled     TINYINT(1)    NOT NULL DEFAULT 0,
    is_third_party TINYINT(1) NOT NULL DEFAULT 0,  -- attacker imports a malicious one
    config_json JSON          NULL,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_plugins_shop FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE,
    UNIQUE KEY uq_plugin_per_shop (shop_id, name)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- APPLICATION AUDIT LOG  (written by the Flask app - security-relevant events)
-- This is the "application logging" deliverable at the DB layer. The Python
-- side (logging_setup/) writes both here AND to logs/app.log.
-- -----------------------------------------------------------------------------
CREATE TABLE audit_log (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    ts           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor_user_id INT          NULL,               -- NULL = anonymous / guest
    actor_ip     VARCHAR(45)   NULL,               -- IPv4/IPv6
    shop_id      INT           NULL,
    action       VARCHAR(80)   NOT NULL,           -- e.g. LOGIN_SUCCESS, ADMIN_VIEW, PLUGIN_IMPORT
    target_type  VARCHAR(40)   NULL,               -- e.g. 'user', 'product', 'plugin'
    target_id    VARCHAR(64)   NULL,
    success      TINYINT(1)    NOT NULL DEFAULT 1,
    detail       TEXT          NULL,               -- free text / JSON
    INDEX ix_audit_ts (ts),
    INDEX ix_audit_action (action),
    INDEX ix_audit_actor (actor_user_id)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- DB-LEVEL CHANGE LOG  (written by TRIGGERS, independent of the app)
-- This is the "DB logging" deliverable: even if an attacker bypasses the app
-- and talks to MySQL directly, changes to sensitive tables are still recorded
-- here with the MySQL account and timestamp. See 03_triggers.sql.
-- -----------------------------------------------------------------------------
CREATE TABLE db_change_log (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    ts          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    db_user     VARCHAR(128) NOT NULL,     -- CURRENT_USER() = MySQL account used
    table_name  VARCHAR(64)  NOT NULL,
    op          VARCHAR(10)  NOT NULL,     -- INSERT / UPDATE / DELETE
    row_pk      VARCHAR(64)  NULL,
    detail      TEXT         NULL,
    INDEX ix_change_ts (ts),
    INDEX ix_change_table (table_name)
) ENGINE=InnoDB;
