-- ============================================================
--  Wash n Dry Laundry Shop Management System - database schema
--  Target: MySQL / MariaDB (XAMPP + phpMyAdmin)
--  11 tables, normalised to 3NF/BCNF. Safe to run more than once.
--  Import in phpMyAdmin (Import tab) or let the app create it on first run.
-- ============================================================

CREATE DATABASE IF NOT EXISTS washndry CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE washndry;

-- ---------- Users ----------
CREATE TABLE IF NOT EXISTS user_account (
    user_id        INT AUTO_INCREMENT PRIMARY KEY,
    username       VARCHAR(50)  NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,                 -- salted PBKDF2, never plain text
    full_name      VARCHAR(100) NOT NULL,
    role           VARCHAR(20)  NOT NULL DEFAULT 'Staff',
    is_active      TINYINT(1)   NOT NULL DEFAULT 1,
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_user_role CHECK (role IN ('Admin', 'Staff', 'Viewer'))
) ENGINE=InnoDB;

-- ---------- Customers ----------
CREATE TABLE IF NOT EXISTS customer (
    customer_id  INT AUTO_INCREMENT PRIMARY KEY,
    first_name   VARCHAR(50)  NOT NULL,
    last_name    VARCHAR(50)  NOT NULL,
    contact_no   VARBINARY(255) NOT NULL,
    contact_hash CHAR(64)     NOT NULL,
    address      VARCHAR(255) NOT NULL,
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
    ,CONSTRAINT uq_customer_contact_hash UNIQUE (contact_hash)
) ENGINE=InnoDB;

-- ---------- Services (category table is hierarchical / self-referencing) ----------
CREATE TABLE IF NOT EXISTS service_category (
    category_id         INT AUTO_INCREMENT PRIMARY KEY,
    category_name       VARCHAR(80) NOT NULL UNIQUE,
    parent_category_id  INT NULL,
    CONSTRAINT fk_category_parent FOREIGN KEY (parent_category_id)
        REFERENCES service_category(category_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS service (
    service_id    INT AUTO_INCREMENT PRIMARY KEY,
    category_id   INT NULL,
    service_name  VARCHAR(100)  NOT NULL,
    description   VARCHAR(255)  NOT NULL DEFAULT '',
    soap_brand    VARCHAR(50)   NOT NULL DEFAULT '',
    fabric_conditioner VARCHAR(50) NOT NULL DEFAULT '',
    unit_type     VARCHAR(10)   NOT NULL,
    unit_price    DECIMAL(10,2) NOT NULL,
    is_active     TINYINT(1)    NOT NULL DEFAULT 1,           -- 0 = deleted (kept for old orders)
    requires_soap TINYINT(1)    NOT NULL DEFAULT 1,
    CONSTRAINT fk_service_category FOREIGN KEY (category_id)
        REFERENCES service_category(category_id) ON DELETE SET NULL,
    CONSTRAINT uq_service UNIQUE (service_name, unit_type),
    CONSTRAINT chk_service_unit  CHECK (unit_type IN ('per kg', 'per piece', 'per set')),
    CONSTRAINT chk_service_price CHECK (unit_price > 0)
) ENGINE=InnoDB;

-- ---------- Soap brands ----------
CREATE TABLE IF NOT EXISTS soap_brand (
    soap_id         INT AUTO_INCREMENT PRIMARY KEY,
    brand_name      VARCHAR(50) NOT NULL UNIQUE,
    additional_price DECIMAL(10,2) NOT NULL DEFAULT 0,
    is_active       TINYINT(1) NOT NULL DEFAULT 1,
    CONSTRAINT chk_soap_price CHECK (additional_price >= 0)
) ENGINE=InnoDB;

-- ---------- Orders ----------
CREATE TABLE IF NOT EXISTS order_status (
    status_id    INT PRIMARY KEY,
    status_name  VARCHAR(30) NOT NULL UNIQUE,
    sequence_no  INT         NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS laundry_order (
    order_id          INT AUTO_INCREMENT PRIMARY KEY,
    customer_id       INT           NOT NULL,
    user_id           INT           NOT NULL,
    status_id         INT           NOT NULL DEFAULT 1,
    order_date        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    pickup_date       DATETIME      NULL,                     -- the pickup / delivery schedule
    fulfillment_type  VARCHAR(10)   NOT NULL DEFAULT 'Pickup',
    delivery_address  VARCHAR(255)  NULL,                     -- required when fulfillment_type is Delivery
    total_amount      DECIMAL(10,2) NOT NULL DEFAULT 0,
    payment_status    VARCHAR(10)   NOT NULL DEFAULT 'Unpaid',
    CONSTRAINT fk_order_customer FOREIGN KEY (customer_id) REFERENCES customer(customer_id)     ON DELETE RESTRICT,
    CONSTRAINT fk_order_user     FOREIGN KEY (user_id)     REFERENCES user_account(user_id)     ON DELETE RESTRICT,
    CONSTRAINT fk_order_status   FOREIGN KEY (status_id)   REFERENCES order_status(status_id)   ON DELETE RESTRICT,
    CONSTRAINT chk_order_fulfillment CHECK (fulfillment_type IN ('Pickup', 'Delivery')),
    CONSTRAINT chk_order_total   CHECK (total_amount >= 0),
    CONSTRAINT chk_order_payment CHECK (payment_status IN ('Unpaid', 'Partial', 'Paid')),
    INDEX idx_order_date (order_date)
) ENGINE=InnoDB;

-- junction table: many orders <-> many services
CREATE TABLE IF NOT EXISTS order_item (
    order_id    INT           NOT NULL,
    service_id  INT           NOT NULL,
    soap_id     INT           NULL,
    soap_brand  VARCHAR(50)   NOT NULL DEFAULT '',
    fabric_conditioner VARCHAR(50) NOT NULL DEFAULT '',
    quantity    DECIMAL(8,2)  NOT NULL,
    unit_price  DECIMAL(10,2) NOT NULL,                       -- price at the time of the order
    PRIMARY KEY (order_id, service_id),
    CONSTRAINT fk_item_order   FOREIGN KEY (order_id)   REFERENCES laundry_order(order_id) ON DELETE CASCADE,
    CONSTRAINT fk_item_service FOREIGN KEY (service_id) REFERENCES service(service_id)     ON DELETE RESTRICT,
    CONSTRAINT fk_order_item_soap FOREIGN KEY (soap_id) REFERENCES soap_brand(soap_id)    ON DELETE RESTRICT,
    CONSTRAINT chk_item_qty   CHECK (quantity > 0),
    CONSTRAINT chk_item_price CHECK (unit_price >= 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS payment (
    payment_id      INT AUTO_INCREMENT PRIMARY KEY,
    order_id        INT           NOT NULL,
    user_id         INT           NOT NULL,
    amount_paid     DECIMAL(10,2) NOT NULL,
    payment_method  VARCHAR(20)   NOT NULL,
    payment_date    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_payment_order FOREIGN KEY (order_id) REFERENCES laundry_order(order_id) ON DELETE RESTRICT,
    CONSTRAINT fk_payment_user  FOREIGN KEY (user_id)  REFERENCES user_account(user_id)   ON DELETE RESTRICT,
    CONSTRAINT chk_payment_amount CHECK (amount_paid > 0),
    CONSTRAINT chk_payment_method CHECK (payment_method IN ('Cash', 'GCash', 'Maya', 'Bank Transfer')),
    INDEX idx_payment_date (payment_date)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS order_status_log (
    log_id      INT AUTO_INCREMENT PRIMARY KEY,
    order_id    INT      NOT NULL,
    status_id   INT      NOT NULL,
    changed_by  INT      NOT NULL,
    changed_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_log_order  FOREIGN KEY (order_id)   REFERENCES laundry_order(order_id) ON DELETE CASCADE,
    CONSTRAINT fk_log_status FOREIGN KEY (status_id)  REFERENCES order_status(status_id) ON DELETE RESTRICT,
    CONSTRAINT fk_log_user   FOREIGN KEY (changed_by) REFERENCES user_account(user_id)   ON DELETE RESTRICT
) ENGINE=InnoDB;

-- ---------- Audit log ----------
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id       BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id        INT NULL,
    action         VARCHAR(20) NOT NULL,
    table_name     VARCHAR(64) NOT NULL,
    record_id      VARCHAR(64) NOT NULL,
    details        VARCHAR(255) NULL,
    occurred_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_user FOREIGN KEY (user_id) REFERENCES user_account(user_id)
        ON DELETE SET NULL,
    INDEX idx_audit_occurred_at (occurred_at),
    INDEX idx_audit_user_action (user_id, action)
) ENGINE=InnoDB;

-- These objects are also installed by the Python initializer. The DELIMITER
-- blocks make this file directly importable through phpMyAdmin.
DROP VIEW IF EXISTS v_order_summary;
DROP VIEW IF EXISTS v_sales_by_service;
CREATE VIEW v_order_summary AS
SELECT o.order_id, CONCAT(c.first_name, ' ', c.last_name) AS customer_name,
       u.username AS created_by, s.status_name, o.order_date, o.pickup_date,
       o.fulfillment_type, o.total_amount, o.payment_status
FROM laundry_order o
JOIN customer c ON c.customer_id = o.customer_id
JOIN user_account u ON u.user_id = o.user_id
JOIN order_status s ON s.status_id = o.status_id;

CREATE VIEW v_sales_by_service AS
SELECT s.service_id, s.service_name, s.unit_type,
       COUNT(DISTINCT oi.order_id) AS order_count,
       SUM(oi.quantity) AS quantity_sold,
       SUM(oi.quantity * oi.unit_price) AS sales_amount
FROM order_item oi
JOIN laundry_order o ON o.order_id = oi.order_id
JOIN service s ON s.service_id = oi.service_id
WHERE o.status_id <> 6
GROUP BY s.service_id, s.service_name, s.unit_type;

DELIMITER $$
CREATE FUNCTION fn_order_balance(p_order_id INT)
RETURNS DECIMAL(10,2)
READS SQL DATA
BEGIN
    RETURN (
        SELECT GREATEST(o.total_amount - COALESCE(SUM(p.amount_paid), 0), 0)
        FROM laundry_order o
        LEFT JOIN payment p ON p.order_id = o.order_id
        WHERE o.order_id = p_order_id
        GROUP BY o.order_id, o.total_amount
    );
END$$

CREATE PROCEDURE sp_refresh_payment_status(IN p_order_id INT)
MODIFIES SQL DATA
BEGIN
    UPDATE laundry_order o
    SET payment_status = CASE
        WHEN COALESCE((SELECT SUM(amount_paid) FROM payment WHERE order_id = p_order_id), 0) <= 0 THEN 'Unpaid'
        WHEN COALESCE((SELECT SUM(amount_paid) FROM payment WHERE order_id = p_order_id), 0) >= o.total_amount THEN 'Paid'
        ELSE 'Partial'
    END
    WHERE o.order_id = p_order_id;
END$$

CREATE PROCEDURE sp_order_sales_report(IN p_from DATETIME, IN p_to DATETIME)
READS SQL DATA
BEGIN
    SELECT * FROM v_sales_by_service
    WHERE EXISTS (
        SELECT 1 FROM laundry_order o
        JOIN order_item oi ON oi.order_id = o.order_id
        WHERE oi.service_id = v_sales_by_service.service_id
          AND o.order_date >= p_from AND o.order_date < p_to
    )
    ORDER BY sales_amount DESC;
END$$

CREATE PROCEDURE sp_record_payment(
    IN p_order_id INT,
    IN p_amount DECIMAL(10,2),
    IN p_method VARCHAR(20)
)
MODIFIES SQL DATA
BEGIN
    DECLARE v_total DECIMAL(10,2);
    DECLARE v_paid DECIMAL(10,2);
    SELECT total_amount INTO v_total FROM laundry_order
    WHERE order_id=p_order_id AND status_id<>6 FOR UPDATE;
    IF v_total IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Order is cancelled or does not exist';
    END IF;
    SELECT COALESCE(SUM(amount_paid), 0) INTO v_paid FROM payment WHERE order_id=p_order_id;
    IF p_amount <= 0 OR p_amount > v_total-v_paid THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Payment exceeds the outstanding balance';
    END IF;
    IF p_method NOT IN ('Cash', 'GCash', 'Maya', 'Bank Transfer') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid payment method';
    END IF;
    INSERT INTO payment (order_id, user_id, amount_paid, payment_method)
    VALUES (p_order_id, @app_user_id, p_amount, p_method);
    UPDATE laundry_order
    SET payment_status=CASE WHEN v_paid+p_amount>=v_total THEN 'Paid' ELSE 'Partial' END
    WHERE order_id=p_order_id;
END$$

CREATE TRIGGER trg_customer_audit_insert
AFTER INSERT ON customer
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (user_id, action, table_name, record_id, details)
    VALUES (@app_user_id, 'CREATE', 'customer', NEW.customer_id,
            CONCAT('Created customer ', NEW.first_name, ' ', NEW.last_name));
END$$

CREATE TRIGGER trg_customer_audit_update
AFTER UPDATE ON customer
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (user_id, action, table_name, record_id, details)
    VALUES (@app_user_id, 'UPDATE', 'customer', NEW.customer_id,
            'Customer profile updated');
END$$

CREATE TRIGGER trg_customer_audit_delete
AFTER DELETE ON customer
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (user_id, action, table_name, record_id, details)
    VALUES (@app_user_id, 'DELETE', 'customer', OLD.customer_id,
            CONCAT('Deleted customer ', OLD.first_name, ' ', OLD.last_name));
END$$

CREATE TRIGGER trg_payment_audit_insert
AFTER INSERT ON payment
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (user_id, action, table_name, record_id, details)
    VALUES (COALESCE(@app_user_id, NEW.user_id), 'CREATE', 'payment', NEW.payment_id,
            CONCAT('Payment recorded for order ', NEW.order_id));
END$$

CREATE TRIGGER trg_order_audit_insert
AFTER INSERT ON laundry_order
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (user_id, action, table_name, record_id, details)
    VALUES (COALESCE(@app_user_id, NEW.user_id), 'CREATE', 'laundry_order', NEW.order_id,
            'Order created');
END$$

CREATE TRIGGER trg_order_audit_update
AFTER UPDATE ON laundry_order
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (user_id, action, table_name, record_id, details)
    VALUES (@app_user_id, 'UPDATE', 'laundry_order', NEW.order_id,
            'Order or payment status updated');
END$$
DELIMITER ;

-- ---------- Seed data (idempotent) ----------
INSERT IGNORE INTO order_status (status_id, status_name, sequence_no) VALUES
    (1, 'Received', 1), (2, 'Washing', 2), (3, 'Drying', 3),
    (4, 'Ready', 4), (5, 'Picked Up', 5), (7, 'Delivered', 6), (6, 'Cancelled', 7);

INSERT IGNORE INTO service_category (category_name) VALUES
    ('Washing'), ('Drying'), ('Full Service'), ('Bedding');

INSERT IGNORE INTO service_category (category_name, parent_category_id)
    SELECT 'Comforters', p.category_id
    FROM (SELECT category_id FROM service_category WHERE category_name = 'Bedding') AS p;

INSERT IGNORE INTO service (category_id, service_name, soap_brand, unit_type, unit_price)
    SELECT category_id, 'Wash Only', 'Ariel', 'per kg', 40 FROM service_category WHERE category_name = 'Washing';
INSERT IGNORE INTO service (category_id, service_name, soap_brand, unit_type, unit_price)
    SELECT category_id, 'Dry Only', 'Downy', 'per kg', 40 FROM service_category WHERE category_name = 'Drying';
INSERT IGNORE INTO service (category_id, service_name, soap_brand, unit_type, unit_price)
    SELECT category_id, 'Fold Only', '', 'per kg', 15 FROM service_category WHERE category_name = 'Washing';
INSERT IGNORE INTO service (category_id, service_name, soap_brand, unit_type, unit_price)
    SELECT category_id, 'Wash & Dry', 'Tide', 'per kg', 70 FROM service_category WHERE category_name = 'Full Service';
INSERT IGNORE INTO service (category_id, service_name, soap_brand, unit_type, unit_price)
    SELECT category_id, 'Wash, Dry & Fold', 'Tide', 'per kg', 85 FROM service_category WHERE category_name = 'Full Service';
INSERT IGNORE INTO service (category_id, service_name, soap_brand, unit_type, unit_price)
    SELECT category_id, 'Full Service Plus', 'Downy', 'per kg', 100 FROM service_category WHERE category_name = 'Full Service';
INSERT IGNORE INTO service (category_id, service_name, soap_brand, unit_type, unit_price)
    SELECT category_id, 'Comforter Wash', 'Surf', 'per piece', 180 FROM service_category WHERE category_name = 'Comforters';
INSERT IGNORE INTO service (category_id, service_name, soap_brand, unit_type, unit_price)
    SELECT category_id, 'Bedsheet & Pillowcase', 'Breeze', 'per set', 120 FROM service_category WHERE category_name = 'Bedding';
INSERT IGNORE INTO service (category_id, service_name, soap_brand, unit_type, unit_price)
    SELECT category_id, 'Ironing / Pressing', '', 'per piece', 25 FROM service_category WHERE category_name = 'Washing';
INSERT IGNORE INTO service (category_id, service_name, soap_brand, unit_type, unit_price)
    SELECT category_id, 'Express Laundry', 'Del', 'per kg', 120 FROM service_category WHERE category_name = 'Full Service';
