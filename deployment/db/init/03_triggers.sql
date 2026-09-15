-- =============================================================================
-- 03_triggers.sql  -  DB-LEVEL audit triggers
-- -----------------------------------------------------------------------------
-- These fire inside MySQL itself, so they record changes to sensitive tables
-- EVEN IF an attacker bypasses the Flask app and runs SQL directly (e.g. after
-- "DB Console Access"). Each row records CURRENT_USER() (the MySQL account) and
-- the timestamp into db_change_log.
--
-- This is the database-layer half of the logging deliverable; the Flask app
-- writes richer, app-aware events into audit_log separately.
-- =============================================================================

DELIMITER //

-- ---- users -----------------------------------------------------------------
CREATE TRIGGER trg_users_ai AFTER INSERT ON users
FOR EACH ROW
BEGIN
    INSERT INTO db_change_log (db_user, table_name, op, row_pk, detail)
    VALUES (CURRENT_USER(), 'users', 'INSERT', NEW.id,
            CONCAT('username=', NEW.username, ' role=', NEW.role, ' shop_id=', NEW.shop_id));
END//

-- Only log SECURITY-RELEVANT updates. Every successful login updates
-- last_login/failed_logins, and logging those would bury real tampering under
-- thousands of routine rows. Role / password / active-flag / username / 2FA
-- changes are what matter for the audit trail.
CREATE TRIGGER trg_users_au AFTER UPDATE ON users
FOR EACH ROW
BEGIN
    IF  OLD.role          <> NEW.role
     OR OLD.password_hash <> NEW.password_hash
     OR OLD.is_active     <> NEW.is_active
     OR OLD.username      <> NEW.username
     OR OLD.twofa_enabled <> NEW.twofa_enabled
     OR NOT (OLD.email <=> NEW.email)
    THEN
        INSERT INTO db_change_log (db_user, table_name, op, row_pk, detail)
        VALUES (CURRENT_USER(), 'users', 'UPDATE', NEW.id,
                CONCAT('role: ', OLD.role, '->', NEW.role,
                       ', active: ', OLD.is_active, '->', NEW.is_active,
                       ', pw_changed: ', IF(OLD.password_hash <> NEW.password_hash, 'YES', 'no'),
                       ', 2fa: ', OLD.twofa_enabled, '->', NEW.twofa_enabled));
    END IF;
END//

CREATE TRIGGER trg_users_ad AFTER DELETE ON users
FOR EACH ROW
BEGIN
    INSERT INTO db_change_log (db_user, table_name, op, row_pk, detail)
    VALUES (CURRENT_USER(), 'users', 'DELETE', OLD.id,
            CONCAT('username=', OLD.username, ' role=', OLD.role));
END//

-- ---- plugins (attacker enabling / importing a malicious plugin) ------------
CREATE TRIGGER trg_plugins_ai AFTER INSERT ON plugins
FOR EACH ROW
BEGIN
    INSERT INTO db_change_log (db_user, table_name, op, row_pk, detail)
    VALUES (CURRENT_USER(), 'plugins', 'INSERT', NEW.id,
            CONCAT('name=', NEW.name, ' enabled=', NEW.enabled,
                   ' third_party=', NEW.is_third_party, ' shop_id=', NEW.shop_id));
END//

CREATE TRIGGER trg_plugins_au AFTER UPDATE ON plugins
FOR EACH ROW
BEGIN
    INSERT INTO db_change_log (db_user, table_name, op, row_pk, detail)
    VALUES (CURRENT_USER(), 'plugins', 'UPDATE', NEW.id,
            CONCAT('name=', NEW.name, ' enabled: ', OLD.enabled, '->', NEW.enabled));
END//

DELIMITER ;
