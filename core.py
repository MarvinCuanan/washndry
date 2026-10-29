"""Wash 'n Dry - Laundry Shop Management System
Python + Tkinter + MySQL (XAMPP).  Run:  python main.py
Tables are created from database/schema.sql the first time the app starts.
"""
import csv
import functools
import hashlib
import hmac
import os
import re
import secrets
import tkinter as tk
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import mysql.connector
from cryptography.fernet import Fernet, InvalidToken
from mysql.connector import Error

# -------------------- DATABASE SETTINGS --------------------
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""  # XAMPP's default MySQL root password is usually blank.
DB_NAME = "washndry"
SCHEMA_FILE = Path(__file__).resolve().parent / "database" / "schema.sql"
CONTACT_KEY_FILE = Path(__file__).resolve().parent / ".contact.key"

APP_NAME = "Wash 'n Dry"
APP_SUBTITLE = "Laundry Shop Management System"

# -------------------- LOOK (matches the system design) --------------------
SIDEBAR = "#0b3a4d"
SIDEBAR_HOVER = "#13506a"
TEAL = "#0f87a8"
TEAL_HOVER = "#0c6f8b"
BG = "#eef3f6"
WHITE = "#ffffff"
TEXT = "#0b2f3f"
MUTED = "#5b7083"
BORDER = "#d5e3ea"
RED = "#d92d20"
RED_HOVER = "#b42318"
GREEN = "#15803d"
ORANGE = "#d97706"
BLUE = "#0369a1"
CARD_COLORS = {            # background, text colour
    "blue": ("#d6edf4", "#0b3a4d"), "green": ("#dcf5e4", "#166534"),
    "amber": ("#fdf1d0", "#8a5a00"), "purple": ("#ece7fb", "#5b21b6"),
}
ROW_COLORS = {"Received": RED, "Washing": ORANGE, "Drying": BLUE, "Ready": GREEN,
              "Picked Up": MUTED, "Delivered": GREEN, "Cancelled": "#94a3b8",
              "Unpaid": RED, "Partial": ORANGE, "Paid": GREEN}

UNIT_TYPES = ["per kg", "per piece", "per set"]
CONDITIONER_BRANDS = ["Downy", "Del"]
PAYMENT_METHODS = ["Cash", "GCash", "Maya", "Bank Transfer"]
PROGRESS = ["Received", "Washing", "Drying", "Ready", "Picked Up", "Delivered"]
FINAL_STATUSES = {"Picked Up", "Delivered", "Cancelled"}


def F(size=10, weight="normal"):
    return ("Segoe UI", size, weight)


# -------------------- SMALL HELPERS --------------------
class UserError(Exception):
    """A problem with what the user typed or did. The message is shown to them."""


def peso(value):
    amount = Decimal(str(value or 0))
    if amount == amount.to_integral_value():
        return f"\u20b1{int(amount):,}"
    return f"\u20b1{amount:,.2f}"


def qty_text(value):
    amount = Decimal(str(value))
    return str(int(amount)) if amount == amount.to_integral_value() else f"{amount:.2f}".rstrip("0")


def order_code(order_id):
    return f"WD-{int(order_id):04d}"


def customer_code(customer_id):
    return f"C-{int(customer_id):03d}"


def service_code(service_id):
    return f"S-{int(service_id):02d}"


def clean_text(value, label, max_len, required=True):
    text = " ".join(str(value or "").split())
    if not text and required:
        raise UserError(f"{label} is required.")
    if len(text) > max_len:
        raise UserError(f"{label} must be {max_len} characters or fewer.")
    return text


def parse_phone(value):
    """0917 123 4567 / 0917-123-4567 / +63 917 123 4567  ->  09171234567"""
    text = re.sub(r"[\s\-()]", "", str(value or ""))
    if not text:
        raise UserError("Mobile number is required.")
    if text.startswith("+63"):
        text = "0" + text[3:]
    elif text.startswith("63") and len(text) == 12:
        text = "0" + text[2:]
    if not re.fullmatch(r"09\d{9}", text):
        raise UserError("Enter a valid PH mobile number, for example 0917 123 4567.")
    return text


def parse_money(value, label="Amount"):
    text = str(value or "").strip().replace(",", "").lstrip("\u20b1").strip()
    if not text:
        raise UserError(f"{label} is required.")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise UserError(f"{label} must be a number, for example 150 or 150.50.") from None
    if not amount.is_finite() or amount <= 0:
        raise UserError(f"{label} must be greater than zero.")
    if amount > Decimal("9999999.99"):
        raise UserError(f"{label} is too large.")
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_nonnegative_money(value, label="Amount"):
    text = str(value or "").strip().replace(",", "").lstrip("\u20b1").strip()
    if not text:
        raise UserError(f"{label} is required.")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise UserError(f"{label} must be a number, for example 0 or 5.") from None
    if not amount.is_finite() or amount < 0:
        raise UserError(f"{label} cannot be negative.")
    if amount > Decimal("9999999.99"):
        raise UserError(f"{label} is too large.")
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_quantity(value, unit_type):
    """Per-kg services allow decimals (2.5 kg); per piece / per set must be whole numbers."""
    text = str(value or "").strip()
    if not text:
        raise UserError("Quantity is required for every service.")
    try:
        qty = Decimal(text)
    except InvalidOperation:
        raise UserError("Quantity must be a number.") from None
    if not qty.is_finite() or qty <= 0:
        raise UserError("Quantity must be greater than zero.")
    if qty > 500:
        raise UserError("Quantity must not be more than 500.")
    if unit_type == "per kg":
        return qty.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if qty != qty.to_integral_value():
        raise UserError(f"Quantity must be a whole number for services priced {unit_type}.")
    return qty.quantize(Decimal("1"))


def parse_date(value, label):
    text = str(value or "").strip()
    if not text:
        raise UserError(f"Please select both a From date and a To date.")
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise UserError(f"{label} must be a valid date in YYYY-MM-DD format.") from None


def parse_schedule(value):
    text = " ".join(str(value or "").split())
    if not text:
        raise UserError("Schedule is required (example: 2025-09-01 09:00).")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M %p"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise UserError("Schedule must look like 2025-09-01 09:00 (YYYY-MM-DD HH:MM, 24-hour).")


def payment_status_for(total, paid):
    total, paid = Decimal(str(total)), Decimal(str(paid))
    if paid <= 0:
        return "Unpaid"
    return "Paid" if paid >= total else "Partial"


def check_status_change(current, new, current_seq, new_seq, payment_status, fulfillment_type="Pickup"):
    """Business rules for moving an order to a new status."""
    if current in FINAL_STATUSES:
        raise UserError(f"This order is already {current} and can no longer be changed.")
    if new == current:
        raise UserError(f"The order is already {current}.")
    if new_seq < current_seq:
        raise UserError(f"An order cannot go back from {current} to {new}.")
    if new == "Picked Up" and fulfillment_type != "Pickup":
        raise UserError("Delivery orders must be marked Delivered, not Picked Up.")
    if new == "Delivered" and fulfillment_type != "Delivery":
        raise UserError("Pickup orders must be marked Picked Up, not Delivered.")
    if new in {"Picked Up", "Delivered"} and payment_status != "Paid":
        raise UserError("This order still has an unpaid balance. Record the full payment "
                        f"before marking it {new}.")


def check_editable(status, payment_count, action):
    if status != "Received":
        raise UserError(f"Only orders that are still Received can be {action}. This one is {status}.")
    if payment_count:
        raise UserError(f"This order already has a payment, so it cannot be {action}.")


# -------------------- PASSWORDS --------------------
def password_hash(password):
    """Create a salted PBKDF2 hash suitable for storing passwords."""
    salt = secrets.token_bytes(16)
    rounds = 600_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}"


def verify_password(password, stored_hash):
    """Verify current PBKDF2 hashes and support one-time upgrade of old SHA-256 hashes."""
    try:
        algorithm, rounds, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False, False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)
        ).hex()
        return hmac.compare_digest(candidate, digest_hex), False
    except ValueError:
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy, stored_hash), True


def contact_cipher():
    """Load an application encryption key, creating it once with restricted local storage."""
    encoded = os.environ.get("WASHNDRY_CONTACT_KEY")
    if encoded:
        return Fernet(encoded.encode("ascii"))
    if not CONTACT_KEY_FILE.exists():
        CONTACT_KEY_FILE.write_bytes(Fernet.generate_key())
        try:
            os.chmod(CONTACT_KEY_FILE, 0o600)
        except OSError:
            pass
    return Fernet(CONTACT_KEY_FILE.read_bytes().strip())


def encrypt_contact(value):
    return contact_cipher().encrypt(value.encode("utf-8"))


def decrypt_contact(value):
    if value is None:
        return ""
    try:
        return contact_cipher().decrypt(bytes(value)).decode("utf-8")
    except InvalidToken:
        raise Error("The contact encryption key does not match the database.") from None


# -------------------- DATABASE --------------------
def server_connection():
    return mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD)


def db_connection():
    return mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)


def schema_statements():
    text = SCHEMA_FILE.read_text(encoding="utf-8")
    text = text.split("These objects are also installed")[0]
    text = re.sub(r"--[^\n]*", "", text)
    for raw in text.split(";"):
        stmt = raw.strip()
        if not stmt:
            continue
        upper = stmt.upper()
        # Stored programs/triggers are installed separately because their
        # compound bodies contain semicolons.
        if upper.startswith(("DROP VIEW", "CREATE VIEW", "DELIMITER", "CREATE FUNCTION",
                             "CREATE PROCEDURE", "CREATE TRIGGER", "DROP FUNCTION",
                             "DROP PROCEDURE", "DROP TRIGGER")):
            continue
        if upper.startswith("CREATE DATABASE") or upper.startswith("USE "):
            continue
        # Service seed rows are installed after the compatibility migration below.
        if upper.startswith("INSERT IGNORE INTO SERVICE "):
            continue
        yield stmt


def database_objects():
    """Return idempotent views, routines, and triggers as complete statements."""
    return [
        "CREATE OR REPLACE VIEW v_order_summary AS "
        "SELECT o.order_id, CONCAT(c.first_name, ' ', c.last_name) AS customer_name, "
        "u.username AS created_by, s.status_name, o.order_date, o.pickup_date, "
        "o.fulfillment_type, o.delivery_address, o.total_amount, o.payment_status "
        "FROM laundry_order o JOIN customer c ON c.customer_id=o.customer_id "
        "JOIN user_account u ON u.user_id=o.user_id JOIN order_status s ON s.status_id=o.status_id",
        "CREATE OR REPLACE VIEW v_sales_by_service AS "
        "SELECT s.service_id, s.service_name, s.unit_type, COUNT(DISTINCT oi.order_id) AS order_count, "
        "SUM(oi.quantity) AS quantity_sold, SUM(oi.quantity * oi.unit_price) AS sales_amount "
        "FROM order_item oi JOIN laundry_order o ON o.order_id=oi.order_id "
        "JOIN service s ON s.service_id=oi.service_id WHERE o.status_id<>6 "
        "GROUP BY s.service_id, s.service_name, s.unit_type",
        "DROP FUNCTION IF EXISTS fn_order_balance",
        "CREATE FUNCTION fn_order_balance(p_order_id INT) RETURNS DECIMAL(10,2) "
        "READS SQL DATA RETURN (SELECT GREATEST(o.total_amount-COALESCE(SUM(p.amount_paid),0),0) "
        "FROM laundry_order o LEFT JOIN payment p ON p.order_id=o.order_id "
        "WHERE o.order_id=p_order_id GROUP BY o.order_id,o.total_amount)",
        "DROP PROCEDURE IF EXISTS sp_refresh_payment_status",
        "CREATE PROCEDURE sp_refresh_payment_status(IN p_order_id INT) "
        "UPDATE laundry_order o SET payment_status=CASE "
        "WHEN COALESCE((SELECT SUM(amount_paid) FROM payment WHERE order_id=p_order_id),0)<=0 THEN 'Unpaid' "
        "WHEN COALESCE((SELECT SUM(amount_paid) FROM payment WHERE order_id=p_order_id),0)>=o.total_amount THEN 'Paid' "
        "ELSE 'Partial' END WHERE o.order_id=p_order_id",
        "DROP PROCEDURE IF EXISTS sp_order_sales_report",
        "CREATE PROCEDURE sp_order_sales_report(IN p_from DATETIME, IN p_to DATETIME) "
        "SELECT * FROM v_sales_by_service v WHERE EXISTS "
        "(SELECT 1 FROM laundry_order o JOIN order_item oi ON oi.order_id=o.order_id "
        "WHERE oi.service_id=v.service_id AND o.order_date>=p_from AND o.order_date<p_to) "
        "ORDER BY sales_amount DESC",
        "DROP PROCEDURE IF EXISTS sp_record_payment",
        "CREATE PROCEDURE sp_record_payment(IN p_order_id INT, IN p_amount DECIMAL(10,2), "
        "IN p_method VARCHAR(20)) "
        "MODIFIES SQL DATA "
        "BEGIN "
        "DECLARE v_total DECIMAL(10,2); DECLARE v_paid DECIMAL(10,2); "
        "SELECT total_amount INTO v_total FROM laundry_order WHERE order_id=p_order_id AND status_id<>6 FOR UPDATE; "
        "IF v_total IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Order is cancelled or does not exist'; END IF; "
        "SELECT COALESCE(SUM(amount_paid),0) INTO v_paid FROM payment WHERE order_id=p_order_id; "
        "IF p_amount<=0 OR p_amount>v_total-v_paid THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Payment exceeds the outstanding balance'; END IF; "
        "IF p_method NOT IN ('Cash','GCash','Maya','Bank Transfer') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid payment method'; END IF; "
        "INSERT INTO payment (order_id,user_id,amount_paid,payment_method) VALUES (p_order_id,@app_user_id,p_amount,p_method); "
        "UPDATE laundry_order SET payment_status=CASE WHEN v_paid+p_amount>=v_total THEN 'Paid' ELSE 'Partial' END WHERE order_id=p_order_id; "
        "END",
        "DROP TRIGGER IF EXISTS trg_customer_audit_insert",
        "CREATE TRIGGER trg_customer_audit_insert AFTER INSERT ON customer FOR EACH ROW "
        "INSERT INTO audit_log (user_id, action, table_name, record_id, details) "
        "VALUES (@app_user_id, 'CREATE', 'customer', NEW.customer_id, "
        "CONCAT('Created customer ', NEW.first_name, ' ', NEW.last_name))",
        "DROP TRIGGER IF EXISTS trg_customer_audit_update",
        "CREATE TRIGGER trg_customer_audit_update AFTER UPDATE ON customer FOR EACH ROW "
        "INSERT INTO audit_log (user_id, action, table_name, record_id, details) "
        "VALUES (@app_user_id, 'UPDATE', 'customer', NEW.customer_id, 'Customer profile updated')",
        "DROP TRIGGER IF EXISTS trg_customer_audit_delete",
        "CREATE TRIGGER trg_customer_audit_delete AFTER DELETE ON customer FOR EACH ROW "
        "INSERT INTO audit_log (user_id, action, table_name, record_id, details) "
        "VALUES (@app_user_id, 'DELETE', 'customer', OLD.customer_id, "
        "CONCAT('Deleted customer ', OLD.first_name, ' ', OLD.last_name))",
        "DROP TRIGGER IF EXISTS trg_payment_audit_insert",
        "CREATE TRIGGER trg_payment_audit_insert AFTER INSERT ON payment FOR EACH ROW "
        "INSERT INTO audit_log (user_id, action, table_name, record_id, details) "
        "VALUES (COALESCE(@app_user_id, NEW.user_id), 'CREATE', 'payment', NEW.payment_id, "
        "CONCAT('Payment recorded for order ', NEW.order_id))",
        "DROP TRIGGER IF EXISTS trg_order_audit_insert",
        "CREATE TRIGGER trg_order_audit_insert AFTER INSERT ON laundry_order FOR EACH ROW "
        "INSERT INTO audit_log (user_id, action, table_name, record_id, details) "
        "VALUES (COALESCE(@app_user_id, NEW.user_id), 'CREATE', 'laundry_order', NEW.order_id, 'Order created')",
        "DROP TRIGGER IF EXISTS trg_order_audit_update",
        "CREATE TRIGGER trg_order_audit_update AFTER UPDATE ON laundry_order FOR EACH ROW "
        "INSERT INTO audit_log (user_id, action, table_name, record_id, details) "
        "VALUES (@app_user_id, 'UPDATE', 'laundry_order', NEW.order_id, 'Order or payment status updated')",
    ]


def demo_customer_data():
    """Return 200 fictional customer records for the project demonstration."""
    first_names = [
        "Adrian", "Althea", "Andrea", "Ariana", "Beatriz", "Bianca", "Carlo",
        "Catherine", "Christian", "Clarisse", "Daniel", "Diana", "Elaine",
        "Emmanuel", "Faith", "Gabriel", "Hannah", "Irene", "Jasmine", "Joshua",
    ]
    last_names = [
        "Aguilar", "Bautista", "Cabrera", "Castillo", "Cruz", "Dela Cruz",
        "Garcia", "Gonzales", "Mendoza", "Reyes",
    ]
    barangays = [
        "San Antonio", "San Isidro", "Bagong Pag-asa", "Santa Cruz",
        "Santo Nino", "Balingasa", "Commonwealth", "Payatas",
        "Tandang Sora", "Fairview",
    ]
    streets = [
        "Mabini Street", "Rizal Avenue", "Bonifacio Street", "Luna Street",
        "Del Pilar Street", "Aguinaldo Avenue", "Quezon Street",
        "Magsaysay Street", "Katipunan Avenue", "Roxas Street",
    ]
    return [
        (
            first_names[index % len(first_names)],
            last_names[index // len(first_names)],
            encrypt_contact(f"0917{index + 1:07d}"),
            hashlib.sha256(f"0917{index + 1:07d}".encode()).hexdigest(),
            f"{(index % 99) + 1} {streets[index % len(streets)]}, "
            f"Barangay {barangays[index % len(barangays)]}, Quezon City, Metro Manila",
        )
        for index in range(200)
    ]


def initialize_database():
    """Create the database, all tables, seed data and a default admin account if needed."""
    conn = server_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.commit()
    finally:
        cur.close()
        conn.close()

    conn = db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        for statement in schema_statements():
            cur.execute(statement)
        try:
            cur.execute("ALTER TABLE customer ADD COLUMN contact_hash CHAR(64) NOT NULL DEFAULT '' AFTER contact_no")
        except Error as exc:
            if getattr(exc, "errno", None) != 1060:
                raise
        try:
            cur.execute("ALTER TABLE laundry_order ADD COLUMN delivery_address VARCHAR(255) NULL "
                        "AFTER fulfillment_type")
        except Error as exc:
            if getattr(exc, "errno", None) != 1060:
                raise
        try:
            cur.execute("ALTER TABLE service ADD COLUMN description VARCHAR(255) NOT NULL DEFAULT '' "
                        "AFTER service_name")
        except Error as exc:
            if getattr(exc, "errno", None) != 1060:
                raise
        try:
            cur.execute("ALTER TABLE order_item ADD COLUMN soap_brand VARCHAR(50) NOT NULL DEFAULT '' "
                        "AFTER service_id")
        except Error as exc:
            if getattr(exc, "errno", None) != 1060:
                raise
        try:
            cur.execute("ALTER TABLE order_item ADD COLUMN fabric_conditioner VARCHAR(50) NOT NULL DEFAULT '' "
                        "AFTER soap_brand")
        except Error as exc:
            if getattr(exc, "errno", None) != 1060:
                raise
        try:
            cur.execute("ALTER TABLE service ADD COLUMN fabric_conditioner VARCHAR(50) NOT NULL DEFAULT '' "
                        "AFTER soap_brand")
        except Error as exc:
            if getattr(exc, "errno", None) != 1060:
                raise
        try:
            cur.execute("ALTER TABLE service ADD COLUMN requires_soap TINYINT(1) NOT NULL DEFAULT 1 "
                        "AFTER is_active")
        except Error as exc:
            if getattr(exc, "errno", None) != 1060:
                raise
        try:
            cur.execute("ALTER TABLE order_item ADD COLUMN soap_id INT NULL AFTER service_id")
        except Error as exc:
            if getattr(exc, "errno", None) != 1060:
                raise
        cur.execute(
            "SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA=%s AND TABLE_NAME='order_item' "
            "AND CONSTRAINT_NAME IN ('fk_item_soap', 'fk_order_item_soap') LIMIT 1",
            (DB_NAME,))
        if not cur.fetchone():
            cur.execute("ALTER TABLE order_item ADD CONSTRAINT fk_order_item_soap "
                        "FOREIGN KEY (soap_id) REFERENCES soap_brand(soap_id) ON DELETE RESTRICT")
        try:
            cur.execute("ALTER TABLE service DROP CONSTRAINT chk_service_unit")
        except Error as exc:
            if getattr(exc, "errno", None) not in (1091, 1507):
                raise
        cur.execute("UPDATE service SET unit_type='per set' WHERE unit_type='per load'")
        cur.execute("ALTER TABLE service ADD CONSTRAINT chk_service_unit "
                    "CHECK (unit_type IN ('per kg', 'per piece', 'per set'))")
        cur.execute("ALTER TABLE customer MODIFY contact_no VARBINARY(255) NOT NULL")
        cur.execute("SELECT customer_id, contact_no FROM customer")
        for customer in cur.fetchall():
            raw_contact = bytes(customer["contact_no"] or b"")
            try:
                plain_contact = contact_cipher().decrypt(raw_contact).decode("utf-8")
            except InvalidToken:
                plain_contact = raw_contact.decode("utf-8")
                cur.execute("UPDATE customer SET contact_no=%s WHERE customer_id=%s",
                            (encrypt_contact(plain_contact), customer["customer_id"]))
            cur.execute("UPDATE customer SET contact_hash=%s WHERE customer_id=%s",
                        (hashlib.sha256(plain_contact.encode("utf-8")).hexdigest(), customer["customer_id"]))
        try:
            cur.execute("ALTER TABLE customer ADD CONSTRAINT uq_customer_contact_hash UNIQUE (contact_hash)")
        except Error as exc:
            if getattr(exc, "errno", None) not in (1061, 1826):
                raise
        try:
            cur.execute("ALTER TABLE user_account DROP CONSTRAINT chk_user_role")
        except Error as exc:
            if getattr(exc, "errno", None) not in (1091, 1507):
                raise
        cur.execute("ALTER TABLE user_account ADD CONSTRAINT chk_user_role "
                    "CHECK (role IN ('Admin', 'Staff', 'Viewer'))")
        cur.execute("UPDATE order_status SET sequence_no=7 WHERE status_id=6")
        cur.execute("INSERT IGNORE INTO order_status (status_id, status_name, sequence_no) "
                    "VALUES (7, 'Delivered', 6)")
        for statement in database_objects():
            cur.execute(statement)

        # Retire legacy names while preserving their rows for historical orders.
        cur.execute("UPDATE service SET is_active=0 WHERE service_name IN "
                    "('Wash and Fold', 'Full Service Plus')")
        # Keep one active offering per service name and unit. Older versions
        # stored a separate row for each soap brand; retain those rows for
        # historical orders but hide the redundant active offerings.
        cur.execute(
            "UPDATE service older "
            "JOIN service newer ON newer.service_name=older.service_name "
            "AND newer.unit_type=older.unit_type "
            "AND newer.is_active=1 AND newer.service_id>older.service_id "
            "SET older.is_active=0 WHERE older.is_active=1")
        # Service rows no longer own a detergent choice. Remove unused legacy
        # rows, but retain any row referenced by an old order.
        cur.execute(
            "DELETE FROM service WHERE is_active=0 AND NOT EXISTS "
            "(SELECT 1 FROM order_item WHERE order_item.service_id=service.service_id)")
        cur.execute("UPDATE service SET soap_brand='', fabric_conditioner=''")
        try:
            cur.execute("ALTER TABLE service DROP INDEX uq_service")
        except Error as exc:
            if getattr(exc, "errno", None) not in (1091,):
                raise
        try:
            cur.execute("ALTER TABLE service ADD UNIQUE KEY uq_service (service_name, unit_type)")
        except Error as exc:
            if getattr(exc, "errno", None) not in (1061,):
                raise
        soap_brands = [("Ariel", 0), ("Surf", 0), ("Tide", 5), ("Breeze", 0), ("Champion", 0)]
        for brand_name, additional_price in soap_brands:
            cur.execute(
                "INSERT INTO soap_brand (brand_name, additional_price) VALUES (%s,%s) "
                "ON DUPLICATE KEY UPDATE additional_price=VALUES(additional_price), is_active=1",
                (brand_name, additional_price))
        catalog = [
            ("Washing", "Wash Only", "Washing clothes only", "per kg", 45, "", 1),
            ("Drying", "Dry Only", "Machine drying only", "per kg", 40, "", 0),
            ("Washing", "Fold Only", "Folding clean clothes", "per kg", 15, "", 0),
            ("Full Service", "Wash & Dry", "Washing and drying", "per kg", 70, "", 1),
            ("Full Service", "Wash, Dry & Fold", "Complete laundry service", "per kg", 85, "", 1),
            ("Full Service", "Full Service", "Wash, dry, fold, detergent and fabric conditioner",
             "per kg", 100, "", 1),
            ("Comforters", "Comforter Wash", "Washing bulky comforters", "per piece", 180, "", 1),
            ("Bedding", "Bedsheet & Pillowcase", "Washing bedding items", "per set", 120, "", 1),
            ("Washing", "Ironing / Pressing", "Ironing clothes", "per piece", 30, "", 0),
            ("Full Service", "Express Laundry", "Priority wash, dry and fold", "per kg", 120, "", 1),
        ]
        for category_name, name, _description, unit, price, brand, requires_soap in catalog:
            cur.execute("SELECT category_id FROM service_category WHERE category_name=%s", (category_name,))
            category = cur.fetchone()
            if category:
                cur.execute(
                    "INSERT INTO service (category_id, service_name, description, soap_brand, fabric_conditioner, "
                    "unit_type, unit_price, requires_soap) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                    "category_id=VALUES(category_id), description=VALUES(description), "
                    "soap_brand=VALUES(soap_brand), fabric_conditioner=VALUES(fabric_conditioner), "
                    "unit_price=VALUES(unit_price), requires_soap=VALUES(requires_soap), is_active=1",
                    (category["category_id"], name, _description, brand, "", unit, price, requires_soap))

        cur.execute("SELECT COUNT(*) FROM user_account")
        if cur.fetchone()["COUNT(*)"] == 0:
            cur.execute(
                "INSERT INTO user_account (full_name, username, password_hash, role) "
                "VALUES (%s, %s, %s, 'Admin')",
                ("System Administrator", "admin", password_hash("admin123")))

        # Project requirement: keep at least 200 clearly fictional records for demonstration.
        demo_rows = demo_customer_data()
        cur.execute(
            "SELECT customer_id FROM customer "
            "WHERE first_name='Demo' OR address='DEMO DATA - generated for project requirement' "
            "ORDER BY customer_id LIMIT 200"
        )
        demo_ids = [row["customer_id"] for row in cur.fetchall()]
        for customer_id, row in zip(demo_ids, demo_rows):
            cur.execute(
                "UPDATE customer SET first_name=%s, last_name=%s, contact_no=%s, "
                "contact_hash=%s, address=%s WHERE customer_id=%s",
                (*row, customer_id),
            )
        if len(demo_ids) < 200:
            cur.executemany(
                "INSERT INTO customer (first_name, last_name, contact_no, contact_hash, address) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE contact_hash=VALUES(contact_hash)",
                demo_rows[len(demo_ids):],
            )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def guarded(method):
    """Shows friendly messages instead of crashing when something goes wrong."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except UserError as exc:
            messagebox.showwarning("Please check", str(exc))
        except Error as exc:
            messagebox.showerror("Database error", f"Something went wrong with the database.\n\n{exc}")
    return wrapper
