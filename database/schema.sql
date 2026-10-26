-- ============================================================
--  Wash n Dry Laundry Shop Management System - database schema
--  Target: MySQL / MariaDB (XAMPP + phpMyAdmin)
--  9 tables, normalised to 3NF/BCNF. Safe to run more than once.
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
    CONSTRAINT chk_user_role CHECK (role IN ('Admin', 'Staff'))
) ENGINE=InnoDB;

-- ---------- Customers ----------
CREATE TABLE IF NOT EXISTS customer (
    customer_id  INT AUTO_INCREMENT PRIMARY KEY,
    first_name   VARCHAR(50)  NOT NULL,
    last_name    VARCHAR(50)  NOT NULL,
    contact_no   VARCHAR(15)  NOT NULL UNIQUE,
    address      VARCHAR(255) NOT NULL,
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    soap_brand    VARCHAR(50)   NOT NULL DEFAULT '',
    unit_type     VARCHAR(10)   NOT NULL,
    unit_price    DECIMAL(10,2) NOT NULL,
    is_active     TINYINT(1)    NOT NULL DEFAULT 1,           -- 0 = deleted (kept for old orders)
    CONSTRAINT fk_service_category FOREIGN KEY (category_id)
        REFERENCES service_category(category_id) ON DELETE SET NULL,
    CONSTRAINT uq_service UNIQUE (service_name, soap_brand, unit_type),
    CONSTRAINT chk_service_unit  CHECK (unit_type IN ('per kg', 'per piece', 'per load')),
    CONSTRAINT chk_service_price CHECK (unit_price > 0)
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
    quantity    DECIMAL(8,2)  NOT NULL,
    unit_price  DECIMAL(10,2) NOT NULL,                       -- price at the time of the order
    PRIMARY KEY (order_id, service_id),
    CONSTRAINT fk_item_order   FOREIGN KEY (order_id)   REFERENCES laundry_order(order_id) ON DELETE CASCADE,
    CONSTRAINT fk_item_service FOREIGN KEY (service_id) REFERENCES service(service_id)     ON DELETE RESTRICT,
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

-- ---------- Seed data (idempotent) ----------
INSERT IGNORE INTO order_status (status_id, status_name, sequence_no) VALUES
    (1, 'Received', 1), (2, 'Washing', 2), (3, 'Drying', 3),
    (4, 'Ready', 4), (5, 'Picked Up', 5), (6, 'Cancelled', 6);

INSERT IGNORE INTO service_category (category_name) VALUES
    ('Washing'), ('Drying'), ('Full Service'), ('Bedding');

INSERT IGNORE INTO service_category (category_name, parent_category_id)
    SELECT 'Comforters', p.category_id
    FROM (SELECT category_id FROM service_category WHERE category_name = 'Bedding') AS p;

INSERT IGNORE INTO service (category_id, service_name, soap_brand, unit_type, unit_price)
    SELECT category_id, 'Wash and Fold', 'Tide', 'per kg', 35 FROM service_category WHERE category_name = 'Washing';
INSERT IGNORE INTO service (category_id, service_name, soap_brand, unit_type, unit_price)
    SELECT category_id, 'Dry Only', 'Downy', 'per kg', 25 FROM service_category WHERE category_name = 'Drying';
INSERT IGNORE INTO service (category_id, service_name, soap_brand, unit_type, unit_price)
    SELECT category_id, 'Comforter Wash', 'Surf', 'per piece', 150 FROM service_category WHERE category_name = 'Comforters';
INSERT IGNORE INTO service (category_id, service_name, soap_brand, unit_type, unit_price)
    SELECT category_id, 'Full Service', 'Ariel', 'per load', 180 FROM service_category WHERE category_name = 'Full Service';
