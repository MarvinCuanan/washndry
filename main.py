"""Wash 'n Dry - Laundry Shop Management System
Python + Tkinter + MySQL (XAMPP).  Run:  python main.py
Tables are created from database/schema.sql the first time the app starts.
"""
import csv
import functools
import hashlib
import hmac
import re
import secrets
import tkinter as tk
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import mysql.connector
from mysql.connector import Error

# -------------------- DATABASE SETTINGS --------------------
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""  # XAMPP's default MySQL root password is usually blank.
DB_NAME = "washndry"
SCHEMA_FILE = Path(__file__).resolve().parent / "database" / "schema.sql"

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
              "Picked Up": MUTED, "Cancelled": "#94a3b8",
              "Unpaid": RED, "Partial": ORANGE, "Paid": GREEN}

UNIT_TYPES = ["per kg", "per piece", "per load"]
PAYMENT_METHODS = ["Cash", "GCash", "Maya", "Bank Transfer"]
PROGRESS = ["Received", "Washing", "Drying", "Ready", "Picked Up"]
FINAL_STATUSES = {"Picked Up", "Cancelled"}


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


def parse_quantity(value, unit_type):
    """Per-kg services allow decimals (2.5 kg); per piece / per load must be whole numbers."""
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


def check_status_change(current, new, current_seq, new_seq, payment_status):
    """Business rules for moving an order to a new status."""
    if current in FINAL_STATUSES:
        raise UserError(f"This order is already {current} and can no longer be changed.")
    if new == current:
        raise UserError(f"The order is already {current}.")
    if new_seq < current_seq:
        raise UserError(f"An order cannot go back from {current} to {new}.")
    if new == "Picked Up" and payment_status != "Paid":
        raise UserError("This order still has an unpaid balance. Record the full payment "
                        "before marking it Picked Up.")


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


# -------------------- DATABASE --------------------
def server_connection():
    return mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD)


def db_connection():
    return mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)


def schema_statements():
    text = re.sub(r"--[^\n]*", "", SCHEMA_FILE.read_text(encoding="utf-8"))
    for raw in text.split(";"):
        stmt = raw.strip()
        if not stmt:
            continue
        upper = stmt.upper()
        if upper.startswith("CREATE DATABASE") or upper.startswith("USE "):
            continue
        yield stmt


def initialize_database():
    """Create the database, all tables, seed data and a default admin account if needed."""
    conn = server_connection()
    cur = conn.cursor()
    try:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.commit()
    finally:
        cur.close()
        conn.close()

    conn = db_connection()
    cur = conn.cursor()
    try:
        for statement in schema_statements():
            cur.execute(statement)

        cur.execute("SELECT COUNT(*) FROM user_account")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO user_account (full_name, username, password_hash, role) "
                "VALUES (%s, %s, %s, 'Admin')",
                ("System Administrator", "admin", password_hash("admin123")))

        # Project requirement: at least 200 customer records for demonstration.
        cur.execute("SELECT COUNT(*) FROM customer")
        if cur.fetchone()[0] < 200:
            cur.executemany(
                "INSERT IGNORE INTO customer (first_name, last_name, contact_no, address) "
                "VALUES (%s, %s, %s, %s)",
                [("Demo", f"Customer {n:03d}", f"09{n:09d}",
                  "DEMO DATA - generated for project requirement") for n in range(1, 201)])
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


# -------------------- REUSABLE WIDGETS --------------------
def make_button(parent, text, command, kind="primary", padx=16, pady=7, **kw):
    colors = {"primary": (TEAL, TEAL_HOVER, WHITE), "danger": (RED, RED_HOVER, WHITE),
              "secondary": (WHITE, "#e8f0f4", TEXT)}
    bg, hover, fg = colors[kind]
    btn = tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=hover,
                    activeforeground=fg, relief="flat", bd=0, cursor="hand2", padx=padx, pady=pady,
                    font=F(10, "bold"), highlightthickness=1 if kind == "secondary" else 0,
                    highlightbackground=BORDER, **kw)
    btn.bind("<Enter>", lambda _e: btn.config(bg=hover))
    btn.bind("<Leave>", lambda _e: btn.config(bg=bg))
    return btn


def draw_logo(parent, size=64, bg=SIDEBAR):
    """Teal rounded square with a white water drop (drawn in code, no image file needed)."""
    c = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0)
    s, r = size, size * 0.24
    pts = [r, 0, r, 0, s - r, 0, s - r, 0, s, 0, s, r, s, r, s, s - r, s, s - r, s, s, s - r, s,
           s - r, s, r, s, r, s, 0, s, 0, s - r, 0, s - r, 0, r, 0, r, 0, 0]
    c.create_polygon(pts, smooth=True, fill=TEAL, outline=TEAL)
    c.create_polygon(s * .5, s * .17, s * .30, s * .56, s * .70, s * .56, fill=WHITE, outline=WHITE)
    c.create_oval(s * .28, s * .38, s * .72, s * .82, fill=WHITE, outline=WHITE)
    return c


class PlaceholderEntry(tk.Frame):
    """Bordered entry with grey placeholder text and an optional Show/Hide password toggle."""

    def __init__(self, master, placeholder="", password=False, width=30, bg=WHITE):
        super().__init__(master, bg=bg, highlightthickness=1, highlightbackground=BORDER)
        self.placeholder, self.password = placeholder, password
        self._showing_placeholder, self._revealed = False, False
        self.entry = tk.Entry(self, relief="flat", bd=0, font=F(10), bg=bg, fg=TEXT,
                              insertbackground=TEXT, width=width)
        self.entry.pack(side="left", fill="x", expand=True, padx=(10, 4), pady=9)
        if password:
            self.toggle = tk.Label(self, text="Show", fg=TEAL, bg=bg, cursor="hand2", font=F(9))
            self.toggle.pack(side="right", padx=(0, 10))
            self.toggle.bind("<Button-1>", lambda _e: self._toggle_reveal())
        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)
        self._show_placeholder()

    def _mask(self):
        return "" if (not self.password or self._revealed) else "\u2022"

    def _show_placeholder(self):
        if not self.entry.get() and self.placeholder:
            self._showing_placeholder = True
            self.entry.config(show="", fg=MUTED)
            self.entry.insert(0, self.placeholder)

    def _focus_in(self, _e=None):
        self.config(highlightbackground=TEAL)
        if self._showing_placeholder:
            self.entry.delete(0, "end")
            self._showing_placeholder = False
            self.entry.config(fg=TEXT, show=self._mask())

    def _focus_out(self, _e=None):
        self.config(highlightbackground=BORDER)
        if not self.entry.get():
            self._show_placeholder()

    def _toggle_reveal(self):
        self._revealed = not self._revealed
        self.toggle.config(text="Hide" if self._revealed else "Show")
        if not self._showing_placeholder:
            self.entry.config(show=self._mask())

    def get(self):
        return "" if self._showing_placeholder else self.entry.get()

    def set(self, text):
        self._showing_placeholder = False
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.config(fg=TEXT, show=self._mask())

    def clear(self):
        self.entry.delete(0, "end")
        self._showing_placeholder = False
        self.entry.config(fg=TEXT, show=self._mask())
        try:
            focused = self.focus_get()
        except KeyError:
            focused = None
        if focused is not self.entry:
            self._show_placeholder()

    def focus(self):
        self.entry.focus_set()

    def on_return(self, callback):
        self.entry.bind("<Return>", lambda _e: callback())

    def on_key(self, callback):
        self.entry.bind("<KeyRelease>", lambda _e: callback())


class SearchCombo(ttk.Combobox):
    """Combobox you can type in to filter. ``items`` maps the text shown -> a value."""
    _NAV_KEYS = {"Up", "Down", "Left", "Right", "Return", "Tab", "Escape", "Shift_L", "Shift_R",
                 "Control_L", "Control_R", "Home", "End", "Prior", "Next"}

    def __init__(self, master, items=None, width=40, on_select=None):
        super().__init__(master, font=F(10), width=width)
        self._items = {}
        self.set_items(items or {})
        self._on_select = on_select
        self.bind("<KeyRelease>", self._filter)
        self.bind("<<ComboboxSelected>>", lambda _e: self._on_select and self._on_select())
        self.bind("<FocusOut>", lambda _e: self._on_select and self._on_select())

    def set_items(self, mapping):
        self._items = dict(mapping)
        self["values"] = list(self._items)

    def _filter(self, event):
        if event.keysym in self._NAV_KEYS:
            if event.keysym == "Return" and self._on_select:
                self._on_select()
            return
        typed = self.get().strip().lower()
        self["values"] = [k for k in self._items if typed in k.lower()] if typed else list(self._items)

    def selected(self):
        typed = self.get().strip().lower()
        for text, value in self._items.items():
            if text.lower() == typed:
                return value
        return None

    def select_value(self, value):
        for text, v in self._items.items():
            if v == value:
                self.set(text)
                return


class ChipGroup(tk.Frame):
    """Row of pill buttons where exactly one is selected (Pickup/Delivery, order statuses...)."""

    def __init__(self, master, options, default=None, command=None, bg=WHITE):
        super().__init__(master, bg=bg)
        self.options, self.command, self.value = options, command, default or options[0]
        self.buttons = {}
        for option in options:
            btn = tk.Button(self, text=option, relief="flat", bd=0, cursor="hand2", padx=14, pady=4,
                            font=F(9), highlightthickness=1, highlightbackground=BORDER,
                            command=lambda o=option: self.set(o))
            btn.pack(side="left", padx=(0, 6))
            self.buttons[option] = btn
        self._paint()

    def _paint(self):
        for option, btn in self.buttons.items():
            active = option == self.value
            btn.config(bg=TEAL if active else WHITE, fg=WHITE if active else TEXT,
                       activebackground=TEAL_HOVER if active else "#e8f0f4",
                       activeforeground=WHITE if active else TEXT)

    def set(self, value):
        self.value = value
        self._paint()
        if self.command:
            self.command(value)

    def get(self):
        return self.value


def build_table(parent, columns, height=10):
    """columns = [(key, heading, width), ...]. Returns the Treeview."""
    box = tk.Frame(parent, bg=WHITE, highlightthickness=1, highlightbackground=BORDER)
    box.pack(fill="both", expand=True)
    tree = ttk.Treeview(box, columns=[c[0] for c in columns], show="headings", height=height,
                        selectmode="browse")
    for key, heading, width in columns:
        tree.heading(key, text=heading, anchor="w")
        tree.column(key, width=width, minwidth=60, anchor="w", stretch=True)
    scroll = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    tree.tag_configure("odd", background="#f8fbfc")
    for name, color in ROW_COLORS.items():
        tree.tag_configure(name, foreground=color)
    return tree


def fill_table(tree, rows, keys, iid_key, color_key=None):
    tree.delete(*tree.get_children())
    for i, row in enumerate(rows):
        tags = []
        if color_key and row.get(color_key) in ROW_COLORS:
            tags.append(row[color_key])
        if i % 2:
            tags.append("odd")
        tree.insert("", "end", iid=str(row[iid_key]), values=tuple(row[k] for k in keys), tags=tuple(tags))


def field_label(parent, text, bg=WHITE):
    tk.Label(parent, text=text, bg=bg, fg=TEXT, font=F(10)).pack(anchor="w", pady=(10, 3))


# -------------------- THE APPLICATION --------------------
class LaundryManagementApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} | {APP_SUBTITLE}")
        width = min(1200, max(900, self.root.winfo_screenwidth() - 60))
        height = min(740, max(600, self.root.winfo_screenheight() - 100))
        self.root.geometry(f"{width}x{height}+{max((self.root.winfo_screenwidth() - width) // 2, 0)}+20")
        self.root.minsize(900, 600)
        self.root.configure(bg=BG)
        self.current_user = None

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", rowheight=32, font=F(10), background=WHITE, fieldbackground=WHITE,
                        foreground=TEXT, borderwidth=0)
        style.configure("Treeview.Heading", font=F(10, "bold"), background=WHITE, foreground=MUTED,
                        relief="flat", padding=(8, 8))
        style.map("Treeview", background=[("selected", "#d6edf4")], foreground=[("selected", TEXT)])
        style.map("Treeview.Heading", background=[("active", WHITE)])
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure("TCombobox", padding=6, fieldbackground=WHITE, bordercolor=BORDER,
                        lightcolor=BORDER, darkcolor=BORDER, arrowcolor=MUTED)
        self.root.option_add("*TCombobox*Listbox.font", F(10))
        self.show_login()

    # -------------------- GENERAL HELPERS --------------------
    def clear_root(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def query(self, sql, params=(), fetch=False, many=False):
        conn = db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            if many:
                cur.executemany(sql, params)
            else:
                cur.execute(sql, params)
            result = cur.fetchall() if fetch else cur.lastrowid
            conn.commit()
            return result
        finally:
            cur.close()
            conn.close()

    @contextmanager
    def transaction(self):
        """Everything done on the yielded cursor is saved together, or not at all."""
        conn = db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            conn.start_transaction()
            yield cur
            conn.commit()
        except BaseException:
            try:
                conn.rollback()
            except Error:
                pass
            raise
        finally:
            cur.close()
            conn.close()

    def can_write(self):
        return bool(self.current_user) and self.current_user["role"] in ("Admin", "Staff")

    def is_admin(self):
        return bool(self.current_user) and self.current_user["role"] == "Admin"

    def require_role(self, *roles):
        if not self.current_user:
            messagebox.showerror("Access denied", "Please log in to continue.")
            return False
        if self.current_user.get("role") not in roles:
            messagebox.showerror("Access denied",
                                 f"This action is restricted to {' or '.join(roles)} users.")
            return False
        return True

    def nav_items(self):
        role = self.current_user["role"]
        items = [("Dashboard", self.show_dashboard), ("Customers", self.show_customers),
                 ("Services", self.show_services), ("Orders", self.show_orders),
                 ("Payments", self.show_payments), ("Order Status", self.show_status)]
        if role in ("Admin", "Viewer"):
            items.append(("Reports", self.show_reports))
        if role == "Admin":
            items.append(("Users", self.show_users))
        return items

    def page_shell(self, heading, active):
        """Sidebar + white content area. Returns the body frame to put the page into."""
        self.clear_root()
        outer = tk.Frame(self.root, bg=WHITE)
        outer.pack(fill="both", expand=True)
        sidebar = tk.Frame(outer, bg=SIDEBAR, width=200)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg=SIDEBAR)
        brand.pack(fill="x", padx=14, pady=(20, 18))
        draw_logo(brand, 30).pack(side="left")
        tk.Label(brand, text=APP_NAME, bg=SIDEBAR, fg=WHITE, font=F(13, "bold")).pack(side="left", padx=8)

        for label, callback in self.nav_items() + [("Logout", self.logout)]:
            is_active = label == active
            btn = tk.Button(sidebar, text=label, command=callback, anchor="w", relief="flat", bd=0,
                            cursor="hand2", font=F(11), padx=16, pady=9,
                            bg=TEAL if is_active else SIDEBAR, fg=WHITE,
                            activebackground=TEAL if is_active else SIDEBAR_HOVER, activeforeground=WHITE)
            btn.pack(fill="x", padx=8, pady=2)
            if not is_active:
                btn.bind("<Enter>", lambda _e, b=btn: b.config(bg=SIDEBAR_HOVER))
                btn.bind("<Leave>", lambda _e, b=btn: b.config(bg=SIDEBAR))
        tk.Label(sidebar, text=f'{self.current_user["username"]}  \u00b7  {self.current_user["role"]}',
                 bg=SIDEBAR, fg="#8fb3c4", font=F(9)).pack(side="bottom", pady=14)

        content = tk.Frame(outer, bg=WHITE)
        content.pack(side="left", fill="both", expand=True, padx=26, pady=20)
        self.header = tk.Frame(content, bg=WHITE)
        self.header.pack(fill="x")
        tk.Label(self.header, text=heading, bg=WHITE, fg=TEXT, font=F(17, "bold")).pack(side="left")
        body = tk.Frame(content, bg=WHITE)
        body.pack(fill="both", expand=True, pady=(14, 0))
        return body

    def toolbar(self, body):
        bar = tk.Frame(body, bg=WHITE)
        bar.pack(fill="x", pady=(0, 10))
        return bar

    def selected_id(self, tree, what):
        selection = tree.selection()
        if not selection:
            raise UserError(f"Please select a {what} from the table first.")
        return int(selection[0])

    def form_buttons(self, parent, save_cmd, cancel_cmd, save_text="Save"):
        row = tk.Frame(parent, bg=WHITE)
        row.pack(anchor="w", pady=(18, 0))
        make_button(row, save_text, save_cmd).pack(side="left")
        make_button(row, "Cancel", cancel_cmd, kind="secondary").pack(side="left", padx=8)

    def logout(self):
        if not messagebox.askyesno("Confirm logout", "Are you sure you want to log out?"):
            return
        self.current_user = None
        self.show_login()

    # -------------------- LOGIN / CREATE ACCOUNT --------------------
    def auth_card(self, heading):
        """The centred card with the teal-navy header used by Login and Create Account."""
        self.clear_root()
        bg = tk.Frame(self.root, bg=BG)
        bg.pack(fill="both", expand=True)
        card = tk.Frame(bg, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        card.place(relx=0.5, rely=0.5, anchor="center", width=560)
        band = tk.Frame(card, bg=SIDEBAR)
        band.pack(fill="x")
        inner = tk.Frame(band, bg=SIDEBAR)
        inner.pack(pady=22)
        draw_logo(inner, 52).pack()
        tk.Label(inner, text=APP_NAME, bg=SIDEBAR, fg=WHITE, font=F(13, "bold")).pack(pady=(8, 0))
        tk.Label(inner, text=APP_SUBTITLE, bg=SIDEBAR, fg="#cfe3ea", font=F(10)).pack()
        form = tk.Frame(card, bg=WHITE, padx=34, pady=22)
        form.pack(fill="x")
        tk.Label(form, text=heading, bg=WHITE, fg=TEXT, font=F(22, "bold")).pack(anchor="w", pady=(0, 14))
        return form

    def link_row(self, parent, prefix, text, command):
        row = tk.Frame(parent, bg=WHITE)
        row.pack(pady=(10, 0))
        tk.Label(row, text=prefix, bg=WHITE, fg=MUTED, font=F(10)).pack(side="left")
        link = tk.Label(row, text=text, bg=WHITE, fg=TEAL, font=F(10, "bold"), cursor="hand2")
        link.pack(side="left", padx=(4, 0))
        link.bind("<Button-1>", lambda _e: command())

    def show_login(self, username=""):
        form = self.auth_card("Login")
        self.login_user = PlaceholderEntry(form, "Username")
        self.login_user.pack(fill="x", pady=(0, 10))
        self.login_pass = PlaceholderEntry(form, "Password", password=True)
        self.login_pass.pack(fill="x", pady=(0, 14))
        make_button(form, "Login", self.handle_login, pady=10).pack(fill="x")
        self.login_message = tk.Label(form, text="", bg=WHITE, fg=RED, font=F(10), wraplength=480)
        self.login_message.pack(pady=(10, 0))
        self.link_row(form, "Don't have an account?", "Create your own account.", self.show_register)
        exit_link = tk.Label(form, text="Exit", bg=WHITE, fg=MUTED, font=F(10), cursor="hand2")
        exit_link.pack(pady=(10, 0))
        exit_link.bind("<Button-1>", lambda _e: self.root.destroy())
        self.login_user.on_return(self.login_pass.focus)
        self.login_pass.on_return(self.handle_login)
        if username:
            self.login_user.set(username)
            self.login_pass.focus()
        else:
            self.login_user.focus()

    def handle_login(self):
        username, password = self.login_user.get().strip(), self.login_pass.get()
        if not username or not password:
            self.login_message.config(text="Please enter your username and password.")
            return
        try:
            rows = self.query(
                "SELECT user_id, full_name, username, password_hash, role, is_active "
                "FROM user_account WHERE username=%s", (username,), fetch=True)
            ok, needs_rehash = (False, False)
            if rows:
                ok, needs_rehash = verify_password(password, rows[0]["password_hash"])
            if not rows or not ok:
                self.login_message.config(text="Invalid username or password")
                self.login_pass.clear()
                return
            if not rows[0]["is_active"]:
                self.login_message.config(text="This account is deactivated. Please contact the administrator.")
                return
            self.current_user = rows[0]
            if needs_rehash:
                self.query("UPDATE user_account SET password_hash=%s WHERE user_id=%s",
                           (password_hash(password), rows[0]["user_id"]))
            self.show_dashboard()
        except Error as exc:
            messagebox.showerror("Database error", f"Could not log in.\n\n{exc}")

    def show_register(self):
        form = self.auth_card("Create account")
        self.reg_user = PlaceholderEntry(form, "Username")
        self.reg_user.pack(fill="x", pady=(0, 10))
        self.reg_pass = PlaceholderEntry(form, "Password", password=True)
        self.reg_pass.pack(fill="x", pady=(0, 10))
        self.reg_confirm = PlaceholderEntry(form, "Confirm password", password=True)
        self.reg_confirm.pack(fill="x", pady=(0, 14))
        make_button(form, "Create account", self.handle_register, pady=10).pack(fill="x")
        self.reg_message = tk.Label(form, text="", bg=WHITE, fg=RED, font=F(10), wraplength=480)
        self.reg_message.pack(pady=(10, 0))
        self.link_row(form, "Already have an account?", "Log in.", self.show_login)
        self.reg_user.on_return(self.reg_pass.focus)
        self.reg_pass.on_return(self.reg_confirm.focus)
        self.reg_confirm.on_return(self.handle_register)
        self.reg_user.focus()

    def handle_register(self):
        username, password, confirm = self.reg_user.get().strip(), self.reg_pass.get(), self.reg_confirm.get()
        try:
            if not username or not password or not confirm:
                raise UserError("Please fill in all fields.")
            if not re.fullmatch(r"[A-Za-z0-9_.]{3,30}", username):
                raise UserError("Username must be 3-30 characters: letters, numbers, dots or underscores.")
            if len(password) < 6:
                raise UserError("Password must be at least 6 characters.")
            if password != confirm:
                raise UserError("Passwords do not match")
            if self.query("SELECT 1 AS x FROM user_account WHERE username=%s", (username,), fetch=True):
                raise UserError("That username is already taken. Please choose another one.")
            self.query("INSERT INTO user_account (full_name, username, password_hash, role) "
                       "VALUES (%s,%s,%s,'Staff')", (username, username, password_hash(password)))
        except UserError as exc:
            self.reg_message.config(text=str(exc))
            return
        except Error as exc:
            messagebox.showerror("Database error", str(exc))
            return
        messagebox.showinfo("Account created", "Your account was created. You can log in now.")
        self.show_login(username)

    # -------------------- DASHBOARD --------------------
    @guarded
    def show_dashboard(self):
        body = self.page_shell("Dashboard", "Dashboard")
        tk.Label(self.header, text=self.current_user["username"], bg=WHITE, fg=TEXT,
                 font=F(12, "bold")).pack(side="right")
        stats = self.query(
            """SELECT (SELECT COUNT(*) FROM customer) AS customers,
                      (SELECT COUNT(*) FROM laundry_order WHERE status_id <> 6) AS orders,
                      (SELECT COUNT(*) FROM laundry_order WHERE status_id NOT IN (5, 6)) AS pending,
                      (SELECT COALESCE(SUM(amount_paid), 0) FROM payment) AS payments""", fetch=True)[0]
        grid = tk.Frame(body, bg=WHITE)
        grid.pack(fill="x")
        grid.columnconfigure((0, 1), weight=1, uniform="cards")
        cards = [("Total Customers", f'{stats["customers"]:,}', "blue"),
                 ("Total Orders", f'{stats["orders"]:,}', "green"),
                 ("Pending Orders", f'{stats["pending"]:,}', "amber"),
                 ("Total Payments", peso(stats["payments"]), "purple")]
        for i, (label, value, color) in enumerate(cards):
            bg, fg = CARD_COLORS[color]
            card = tk.Frame(grid, bg=bg, padx=16, pady=10)
            card.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 10) if i % 2 == 0 else 0, pady=(0, 10))
            tk.Label(card, text=label, bg=bg, fg=fg, font=F(9)).pack(anchor="w")
            tk.Label(card, text=value, bg=bg, fg=fg, font=F(22, "bold")).pack(anchor="w")

        quick = tk.Frame(body, bg=WHITE)
        quick.pack(fill="x", pady=(2, 12))
        for label, callback in self.nav_items()[1:]:
            make_button(quick, label, callback, kind="secondary", padx=12, pady=5).pack(side="left", padx=(0, 8))

        tk.Label(body, text="Recent Orders", bg=WHITE, fg=TEXT, font=F(13, "bold")).pack(anchor="w", pady=(4, 6))
        tree = build_table(body, [("order", "Order No.", 110), ("customer", "Customer", 240),
                                  ("total", "Total", 110), ("option", "Pickup / Delivery", 140),
                                  ("status", "Status", 120)], height=6)
        rows = self.fetch_orders(limit=8)
        fill_table(tree, [dict(r, order=order_code(r["order_id"]), total=peso(r["total_amount"]),
                               option=r["fulfillment_type"], status=r["status_name"]) for r in rows],
                   ("order", "customer", "total", "option", "status"), "order_id", "status_name")

    # -------------------- CUSTOMERS --------------------
    @guarded
    def show_customers(self, keyword=""):
        body = self.page_shell("Customer Management", "Customers")
        bar = self.toolbar(body)
        if self.can_write():
            make_button(bar, "+ Add", self.show_customer_form).pack(side="left")
        self.cust_search = PlaceholderEntry(bar, "Search name, mobile no. or address", width=32)
        self.cust_search.pack(side="left", padx=(8, 6))
        self.cust_search.on_return(self.search_customers)
        make_button(bar, "Search", self.search_customers).pack(side="left")
        make_button(bar, "Show All", self.refresh_customers, kind="secondary").pack(side="left", padx=6)
        if self.is_admin():
            make_button(bar, "Delete", self.delete_customer, kind="danger").pack(side="right")
        if self.can_write():
            make_button(bar, "Edit", self.edit_customer, kind="secondary").pack(side="right", padx=8)

        self.customer_tree = build_table(body, [("code", "ID", 80), ("name", "Name", 230),
                                                ("contact", "Contact No.", 150), ("address", "Address", 420)], 12)
        self.customer_tree.bind("<Double-1>", lambda _e: self.edit_customer() if self.can_write() else None)
        self.customer_status = tk.Label(body, text="", bg=WHITE, fg=MUTED, font=F(9))
        self.customer_status.pack(anchor="w", pady=(6, 0))
        self.refresh_customers()

    def refresh_customers(self, keyword=None):
        sql = ("SELECT customer_id, first_name, last_name, contact_no, address FROM customer")
        params = ()
        if keyword:
            like = "%" + keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            sql += (" WHERE CONCAT(first_name, ' ', last_name) LIKE %s OR contact_no LIKE %s"
                    " OR address LIKE %s OR CONCAT('C-', LPAD(customer_id, 3, '0')) LIKE %s")
            params = (like, like, like, like)
        rows = self.query(sql + " ORDER BY customer_id", params, fetch=True)
        fill_table(self.customer_tree,
                   [dict(r, code=customer_code(r["customer_id"]), name=f'{r["first_name"]} {r["last_name"]}',
                         contact=r["contact_no"]) for r in rows],
                   ("code", "name", "contact", "address"), "customer_id")
        if keyword:
            self.customer_status.config(text=f'{len(rows)} customer(s) found for "{keyword}".' if rows
                                        else "No customer found.")
        else:
            self.customer_status.config(text=f"{len(rows)} customer(s).")

    @guarded
    def search_customers(self):
        keyword = self.cust_search.get().strip()
        if not keyword:
            raise UserError("Please enter a keyword to search.")
        self.refresh_customers(keyword)

    @guarded
    def edit_customer(self):
        self.show_customer_form(self.selected_id(self.customer_tree, "customer"))

    @guarded
    def delete_customer(self):
        if not self.require_role("Admin"):
            return
        customer_id = self.selected_id(self.customer_tree, "customer")
        if not messagebox.askyesno("Delete customer", "Are you sure you want to delete this customer?"):
            return
        try:
            self.query("DELETE FROM customer WHERE customer_id=%s", (customer_id,))
        except Error as exc:
            if getattr(exc, "errno", None) == 1451:
                raise UserError("This customer has orders and cannot be deleted.") from None
            raise
        self.refresh_customers()
        messagebox.showinfo("Customer deleted", "The customer was deleted.")

    @guarded
    def show_customer_form(self, customer_id=None):
        if not self.require_role("Admin", "Staff"):
            return
        data = {}
        if customer_id:
            rows = self.query("SELECT * FROM customer WHERE customer_id=%s", (customer_id,), fetch=True)
            if not rows:
                raise UserError("This customer no longer exists.")
            data = rows[0]
        body = self.page_shell("Edit Customer" if customer_id else "Add Customer", "Customers")
        form = tk.Frame(body, bg=WHITE)
        form.pack(fill="x")
        street, barangay = (data.get("address", ""), "")
        if ", Brgy. " in street:
            street, barangay = street.rsplit(", Brgy. ", 1)
        fields = {}
        for key, label, hint, value in [
                ("name", "Full Name", "Maria Santos", f'{data.get("first_name", "")} {data.get("last_name", "")}'.strip()),
                ("mobile", "PH Mobile No.", "0917 123 4567", data.get("contact_no", "")),
                ("street", "House / Unit, Street", "12 Rizal St", street),
                ("barangay", "Barangay", "Commonwealth", barangay)]:
            field_label(form, label)
            fields[key] = PlaceholderEntry(form, hint, width=60)
            fields[key].pack(fill="x")
            if value:
                fields[key].set(value)
        fields["name"].focus()
        self.form_buttons(form, lambda: self.save_customer(customer_id, fields), self.show_customers)

    @guarded
    def save_customer(self, customer_id, fields):
        name = clean_text(fields["name"].get(), "Full name", 101)
        parts = name.split(" ")
        if len(parts) < 2:
            raise UserError("Please enter the first and last name, for example Maria Santos.")
        first, last = " ".join(parts[:-1]), parts[-1]
        if len(first) > 50 or len(last) > 50:
            raise UserError("Each part of the name must be 50 characters or fewer.")
        if not re.fullmatch(r"[^\d_!@#$%^&*()+=\[\]{};:\"\\|<>?/~`]+", name):
            raise UserError("Full name may only contain letters, spaces, dots, apostrophes and hyphens.")
        mobile = parse_phone(fields["mobile"].get())
        street = clean_text(fields["street"].get(), "House / Unit, Street", 150)
        barangay = clean_text(fields["barangay"].get(), "Barangay", 80)
        address = f"{street}, Brgy. {barangay}"
        clash = self.query("SELECT customer_id FROM customer WHERE contact_no=%s AND customer_id<>%s",
                           (mobile, customer_id or 0), fetch=True)
        if clash:
            raise UserError("A customer with this mobile number already exists.")
        if customer_id:
            self.query("UPDATE customer SET first_name=%s, last_name=%s, contact_no=%s, address=%s "
                       "WHERE customer_id=%s", (first, last, mobile, address, customer_id))
        else:
            self.query("INSERT INTO customer (first_name, last_name, contact_no, address) VALUES (%s,%s,%s,%s)",
                       (first, last, mobile, address))
        self.show_customers()
        messagebox.showinfo("Customer saved", "Customer saved successfully.")

    # -------------------- SERVICES --------------------
    @guarded
    def show_services(self):
        body = self.page_shell("Service Management", "Services")
        if self.is_admin():
            bar = self.toolbar(body)
            make_button(bar, "+ Add", self.show_service_form).pack(side="left")
            make_button(bar, "Edit", self.edit_service, kind="secondary").pack(side="left", padx=8)
            make_button(bar, "Delete", self.delete_service, kind="danger").pack(side="left")
        self.service_tree = build_table(body, [("code", "ID", 80), ("name", "Service Name", 240),
                                               ("brand", "Soap Brand", 160), ("unit", "Unit", 110),
                                               ("price", "Price", 100), ("category", "Category", 200)], 12)
        if self.is_admin():
            self.service_tree.bind("<Double-1>", lambda _e: self.edit_service())
        rows = self.query(
            """SELECT s.service_id, s.service_name, s.soap_brand, s.unit_type, s.unit_price,
                      CASE WHEN p.category_name IS NULL THEN COALESCE(c.category_name, '-')
                           ELSE CONCAT(p.category_name, ' > ', c.category_name) END AS category
               FROM service s
               LEFT JOIN service_category c ON c.category_id = s.category_id
               LEFT JOIN service_category p ON p.category_id = c.parent_category_id
               WHERE s.is_active = 1 ORDER BY s.service_id""", fetch=True)
        fill_table(self.service_tree,
                   [dict(r, code=service_code(r["service_id"]), name=r["service_name"],
                         brand=r["soap_brand"] or "-", unit=r["unit_type"], price=peso(r["unit_price"]))
                    for r in rows],
                   ("code", "name", "brand", "unit", "price", "category"), "service_id")

    @guarded
    def edit_service(self):
        self.show_service_form(self.selected_id(self.service_tree, "service"))

    @guarded
    def delete_service(self):
        if not self.require_role("Admin"):
            return
        service_id = self.selected_id(self.service_tree, "service")
        if not messagebox.askyesno("Delete service", "Delete this service?\n\nOld orders that used it are kept."):
            return
        self.query("UPDATE service SET is_active=0 WHERE service_id=%s", (service_id,))
        self.show_services()
        messagebox.showinfo("Service deleted", "The service was deleted.")

    def category_choices(self):
        rows = self.query(
            """SELECT c.category_id, c.category_name, p.category_name AS parent_name
               FROM service_category c LEFT JOIN service_category p ON p.category_id = c.parent_category_id
               ORDER BY COALESCE(p.category_name, c.category_name), p.category_name IS NOT NULL, c.category_name""",
            fetch=True)
        return {(f'{r["parent_name"]} > {r["category_name"]}' if r["parent_name"] else r["category_name"]):
                r["category_id"] for r in rows}

    @guarded
    def show_service_form(self, service_id=None):
        if not self.require_role("Admin"):
            return
        data = {}
        if service_id:
            rows = self.query("SELECT * FROM service WHERE service_id=%s AND is_active=1", (service_id,), fetch=True)
            if not rows:
                raise UserError("This service no longer exists.")
            data = rows[0]
        categories = self.category_choices()
        body = self.page_shell("Edit Service" if service_id else "Add Service", "Services")
        form = tk.Frame(body, bg=WHITE)
        form.pack(fill="x")
        field_label(form, "Service Name")
        name = PlaceholderEntry(form, "Wash and Fold", width=60)
        name.pack(fill="x")
        field_label(form, "Soap Brand")
        brand = PlaceholderEntry(form, "Tide", width=60)
        brand.pack(fill="x")
        field_label(form, "Category (pick one, or type a new name to create it)")
        category = ttk.Combobox(form, values=list(categories), font=F(10))
        category.pack(fill="x", ipady=4)
        field_label(form, "Unit")
        unit = ttk.Combobox(form, values=UNIT_TYPES, state="readonly", font=F(10))
        unit.pack(fill="x", ipady=4)
        unit.set(data.get("unit_type", "per kg"))
        field_label(form, "Price (\u20b1)")
        price = PlaceholderEntry(form, "35", width=60)
        price.pack(fill="x")
        if data:
            name.set(data["service_name"])
            if data["soap_brand"]:
                brand.set(data["soap_brand"])
            price.set(f'{data["unit_price"]:.2f}')
            for text, cid in categories.items():
                if cid == data["category_id"]:
                    category.set(text)
        name.focus()
        self.form_buttons(form, lambda: self.save_service(
            service_id, name.get(), brand.get(), category.get(), unit.get(), price.get(), categories),
            self.show_services)

    @guarded
    def save_service(self, service_id, name, brand, category, unit, price, categories):
        if not self.require_role("Admin"):
            return
        name = clean_text(name, "Service name", 100)
        brand = clean_text(brand, "Soap brand", 50, required=False)
        category = clean_text(category, "Category", 80, required=False)
        if unit not in UNIT_TYPES:
            raise UserError("Please choose a unit.")
        price = parse_money(price, "Price")
        with self.transaction() as cur:
            category_id = categories.get(category)
            if category and category_id is None:
                cur.execute("SELECT category_id FROM service_category WHERE category_name=%s", (category,))
                found = cur.fetchone()
                if found:
                    category_id = found["category_id"]
                else:
                    cur.execute("INSERT INTO service_category (category_name) VALUES (%s)", (category,))
                    category_id = cur.lastrowid
            cur.execute("SELECT service_id, is_active FROM service WHERE service_name=%s AND soap_brand=%s "
                        "AND unit_type=%s", (name, brand, unit))
            clash = cur.fetchone()
            if service_id:
                if clash and clash["service_id"] != service_id:
                    raise UserError("A service with the same name, soap brand and unit already exists.")
                cur.execute("UPDATE service SET service_name=%s, soap_brand=%s, category_id=%s, unit_type=%s, "
                            "unit_price=%s WHERE service_id=%s", (name, brand, category_id, unit, price, service_id))
            elif clash and clash["is_active"]:
                raise UserError("A service with the same name, soap brand and unit already exists.")
            elif clash:      # a deleted service with the same details: bring it back
                cur.execute("UPDATE service SET category_id=%s, unit_price=%s, is_active=1 WHERE service_id=%s",
                            (category_id, price, clash["service_id"]))
            else:
                cur.execute("INSERT INTO service (category_id, service_name, soap_brand, unit_type, unit_price) "
                            "VALUES (%s,%s,%s,%s,%s)", (category_id, name, brand, unit, price))
        self.show_services()
        messagebox.showinfo("Service saved", "Service saved successfully.")

    # -------------------- ORDERS --------------------
    def fetch_orders(self, keyword=None, limit=None, exclude_cancelled=False, order_id=None):
        sql = """SELECT o.order_id, o.customer_id, CONCAT(c.first_name, ' ', c.last_name) AS customer,
                        o.total_amount, o.fulfillment_type, o.pickup_date, o.payment_status, o.order_date,
                        o.status_id, s.status_name, s.sequence_no
                 FROM laundry_order o
                 JOIN customer c ON c.customer_id = o.customer_id
                 JOIN order_status s ON s.status_id = o.status_id WHERE 1=1"""
        params = []
        if exclude_cancelled:
            sql += " AND o.status_id <> 6"
        if order_id:
            sql += " AND o.order_id = %s"
            params.append(order_id)
        if keyword:
            like = "%" + keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            sql += (" AND (CONCAT(c.first_name, ' ', c.last_name) LIKE %s"
                    " OR CONCAT('WD-', LPAD(o.order_id, 4, '0')) LIKE %s)")
            params += [like, like]
        sql += " ORDER BY o.order_id DESC"
        if limit:
            sql += " LIMIT %s"
            params.append(limit)
        return self.query(sql, params, fetch=True)

    @guarded
    def show_orders(self):
        body = self.page_shell("Order Management", "Orders")
        bar = self.toolbar(body)
        if self.can_write():
            make_button(bar, "+ Create Order", self.show_order_form).pack(side="left")
        self.order_search = PlaceholderEntry(bar, "Search order no. or customer", width=28)
        self.order_search.pack(side="left", padx=(8, 6))
        self.order_search.on_return(self.search_orders)
        make_button(bar, "Search", self.search_orders).pack(side="left")
        make_button(bar, "Show All", self.refresh_orders, kind="secondary").pack(side="left", padx=6)
        if self.can_write():
            make_button(bar, "Cancel Order", self.cancel_order, kind="danger").pack(side="right")
            make_button(bar, "Edit", self.edit_order, kind="secondary").pack(side="right", padx=8)
        self.order_tree = build_table(body, [("code", "Order No.", 100), ("customer", "Customer", 220),
                                             ("total", "Total", 100), ("option", "Pickup / Delivery", 130),
                                             ("schedule", "Schedule", 150), ("payment", "Payment", 90),
                                             ("status", "Status", 100)], 12)
        self.order_tree.bind("<Double-1>", lambda _e: self.view_order())
        self.order_status_label = tk.Label(body, text="Double-click an order to see its full details.",
                                           bg=WHITE, fg=MUTED, font=F(9))
        self.order_status_label.pack(anchor="w", pady=(6, 0))
        self.refresh_orders()

    def refresh_orders(self, keyword=None):
        rows = self.fetch_orders(keyword)
        fill_table(self.order_tree,
                   [dict(r, code=order_code(r["order_id"]), total=peso(r["total_amount"]),
                         option=r["fulfillment_type"], payment=r["payment_status"], status=r["status_name"],
                         schedule=r["pickup_date"].strftime("%Y-%m-%d %H:%M") if r["pickup_date"] else "-")
                    for r in rows],
                   ("code", "customer", "total", "option", "schedule", "payment", "status"),
                   "order_id", "status_name")
        if keyword:
            self.order_status_label.config(text=f'{len(rows)} order(s) found for "{keyword}".' if rows
                                           else "No order found.")
        else:
            self.order_status_label.config(text="Double-click an order to see its full details.")

    @guarded
    def search_orders(self):
        keyword = self.order_search.get().strip()
        if not keyword:
            raise UserError("Please enter a keyword to search.")
        self.refresh_orders(keyword)

    @guarded
    def edit_order(self):
        self.show_order_form(self.selected_id(self.order_tree, "order"))

    @guarded
    def view_order(self):
        selection = self.order_tree.selection()
        if selection:
            self.show_order_details(int(selection[0]))

    @guarded
    def cancel_order(self):
        if not self.require_role("Admin", "Staff"):
            return
        order_id = self.selected_id(self.order_tree, "order")
        if not messagebox.askyesno("Cancel order", f"Cancel order {order_code(order_id)}?\n\n"
                                   "Only orders that are still Received and unpaid can be cancelled."):
            return
        with self.transaction() as cur:
            cur.execute("SELECT s.status_name FROM laundry_order o JOIN order_status s ON s.status_id=o.status_id "
                        "WHERE o.order_id=%s FOR UPDATE", (order_id,))
            row = cur.fetchone()
            if not row:
                raise UserError("This order no longer exists.")
            cur.execute("SELECT COUNT(*) AS n FROM payment WHERE order_id=%s", (order_id,))
            check_editable(row["status_name"], cur.fetchone()["n"], "cancelled")
            cur.execute("UPDATE laundry_order SET status_id=6 WHERE order_id=%s", (order_id,))
            cur.execute("INSERT INTO order_status_log (order_id, status_id, changed_by) VALUES (%s, 6, %s)",
                        (order_id, self.current_user["user_id"]))
        self.refresh_orders()
        messagebox.showinfo("Order cancelled", f"Order {order_code(order_id)} was cancelled.")

    @guarded
    def show_order_form(self, order_id=None):
        """Create Order page (also used for Edit): customer, services + quantities, option, schedule."""
        if not self.require_role("Admin", "Staff"):
            return
        customers = self.query("SELECT customer_id, CONCAT(first_name, ' ', last_name) AS name, contact_no "
                               "FROM customer ORDER BY first_name, last_name", fetch=True)
        services = self.query("SELECT service_id, service_name, soap_brand, unit_type, unit_price FROM service "
                              "WHERE is_active=1 ORDER BY service_name, soap_brand", fetch=True)
        if not services:
            raise UserError("There are no services yet. Ask the Admin to add services first.")
        existing, items = None, []
        if order_id:
            existing = next(iter(self.fetch_orders(order_id=order_id)), None)
            if not existing:
                raise UserError("This order no longer exists.")
            paid = self.query("SELECT COUNT(*) AS n FROM payment WHERE order_id=%s", (order_id,), fetch=True)[0]["n"]
            check_editable(existing["status_name"], paid, "edited")
            items = self.query("SELECT service_id, quantity FROM order_item WHERE order_id=%s", (order_id,), fetch=True)

        customer_map = {f'{c["name"]} ({c["contact_no"]})': c["customer_id"] for c in customers}

        def label(s):
            return ", ".join(p for p in (s["service_name"], s["soap_brand"], s["unit_type"]) if p)
        service_map = {label(s): s for s in services}

        body = self.page_shell("Edit Order" if order_id else "Create Order", "Orders")
        grid = tk.Frame(body, bg=WHITE)
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=2, uniform="cols")
        grid.columnconfigure(1, weight=3, uniform="cols")
        left = tk.Frame(grid, bg=WHITE)
        left.grid(row=0, column=0, sticky="new", padx=(0, 24))
        right = tk.Frame(grid, bg=WHITE)
        right.grid(row=0, column=1, sticky="new")

        field_label(left, "Customer")
        customer_box = SearchCombo(left, customer_map, width=34)
        customer_box.pack(fill="x", ipady=4)
        if existing:
            customer_box.select_value(existing["customer_id"])
        field_label(left, "Option")
        option = ChipGroup(left, ["Pickup", "Delivery"], existing["fulfillment_type"] if existing else "Pickup")
        option.pack(anchor="w")
        field_label(left, "Schedule (YYYY-MM-DD HH:MM, 24-hour)")
        schedule = PlaceholderEntry(left, "2025-09-01 09:00", width=30)
        schedule.pack(fill="x")
        default_time = existing["pickup_date"] if existing and existing["pickup_date"] else \
            (datetime.now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        schedule.set(default_time.strftime("%Y-%m-%d %H:%M"))

        tk.Label(right, text="Service, soap brand, unit", bg=WHITE, fg=TEXT, font=F(10)).pack(anchor="w", pady=(10, 3))
        rows_frame = tk.Frame(right, bg=WHITE)
        rows_frame.pack(fill="x")
        total_label = tk.Label(right, text="Total: \u20b10", bg=WHITE, fg=TEXT, font=F(12, "bold"))
        rows = []

        def recalc(_e=None):
            total = Decimal("0")
            for row in rows:
                service = row["combo"].selected()
                try:
                    qty = Decimal(row["qty"].get().strip() or "0")
                except InvalidOperation:
                    qty = Decimal("0")
                amount = qty * Decimal(str(service["unit_price"])) if service and qty > 0 else Decimal("0")
                row["sub"].config(text=peso(amount) if amount else "")
                total += amount
            total_label.config(text=f"Total: {peso(total)}")

        def add_row(service_id=None, qty=None):
            frame = tk.Frame(rows_frame, bg=WHITE)
            frame.pack(fill="x", pady=(0, 6))
            combo = SearchCombo(frame, service_map, width=38, on_select=recalc)
            combo.pack(side="left", fill="x", expand=True, ipady=4)
            qty_entry = PlaceholderEntry(frame, "Qty / kg", width=9)
            qty_entry.pack(side="left", padx=8)
            qty_entry.on_key(recalc)
            sub = tk.Label(frame, text="", bg=WHITE, fg=MUTED, font=F(10), width=9, anchor="e")
            sub.pack(side="left")
            row = {"frame": frame, "combo": combo, "qty": qty_entry, "sub": sub}
            if len(rows) > 0:
                def remove():
                    frame.destroy()
                    rows.remove(row)
                    recalc()
                tk.Button(frame, text="\u2715", command=remove, relief="flat", bd=0, bg=WHITE, fg=RED,
                          cursor="hand2", font=F(10, "bold")).pack(side="left", padx=(6, 0))
            rows.append(row)
            if service_id:
                for text, s in service_map.items():
                    if s["service_id"] == service_id:
                        combo.set(text)
            if qty is not None:
                qty_entry.set(qty_text(qty))

        if items:
            for item in items:
                add_row(item["service_id"], item["quantity"])
        else:
            add_row()
        make_button(right, "+ Add another service", lambda: (len(rows) < 8 and add_row()) or recalc(),
                    kind="secondary", pady=5).pack(anchor="w", pady=(2, 8))
        total_label.pack(anchor="w")
        recalc()
        self.form_buttons(body, lambda: self.save_order(order_id, customer_box, rows, option, schedule),
                          self.show_orders)

    @guarded
    def save_order(self, order_id, customer_box, rows, option, schedule_entry):
        customer_id = customer_box.selected()
        if customer_id is None:
            raise UserError("Please choose a customer from the list.")
        lines, seen = [], set()
        for row in rows:
            service = row["combo"].selected()
            if service is None and not row["combo"].get().strip() and not row["qty"].get().strip():
                continue                                    # an empty row is ignored
            if service is None:
                raise UserError("Please choose a service from the list in every row.")
            if service["service_id"] in seen:
                raise UserError("The same service was added twice. Put the total quantity in one row.")
            seen.add(service["service_id"])
            lines.append((service, parse_quantity(row["qty"].get(), service["unit_type"])))
        if not lines:
            raise UserError("Please add at least one service.")
        when = parse_schedule(schedule_entry.get())
        if when.date() < date.today():
            raise UserError("The schedule cannot be in the past.")
        fulfillment = option.get()

        with self.transaction() as cur:
            cur.execute("SELECT customer_id FROM customer WHERE customer_id=%s", (customer_id,))
            if not cur.fetchone():
                raise UserError("This customer no longer exists.")
            if order_id:
                cur.execute("SELECT s.status_name FROM laundry_order o JOIN order_status s "
                            "ON s.status_id=o.status_id WHERE o.order_id=%s FOR UPDATE", (order_id,))
                current = cur.fetchone()
                if not current:
                    raise UserError("This order no longer exists.")
                cur.execute("SELECT COUNT(*) AS n FROM payment WHERE order_id=%s", (order_id,))
                check_editable(current["status_name"], cur.fetchone()["n"], "edited")
                cur.execute("DELETE FROM order_item WHERE order_id=%s", (order_id,))
                cur.execute("UPDATE laundry_order SET customer_id=%s, fulfillment_type=%s, pickup_date=%s "
                            "WHERE order_id=%s", (customer_id, fulfillment, when, order_id))
            else:
                cur.execute("INSERT INTO laundry_order (customer_id, user_id, status_id, pickup_date, "
                            "fulfillment_type) VALUES (%s, %s, 1, %s, %s)",
                            (customer_id, self.current_user["user_id"], when, fulfillment))
                order_id = cur.lastrowid
                cur.execute("INSERT INTO order_status_log (order_id, status_id, changed_by) VALUES (%s, 1, %s)",
                            (order_id, self.current_user["user_id"]))
            total = Decimal("0.00")
            for service, qty in lines:
                cur.execute("SELECT unit_price FROM service WHERE service_id=%s AND is_active=1",
                            (service["service_id"],))
                current_price = cur.fetchone()
                if not current_price:
                    raise UserError(f'"{service["service_name"]}" is no longer available.')
                price = current_price["unit_price"]
                cur.execute("INSERT INTO order_item (order_id, service_id, quantity, unit_price) "
                            "VALUES (%s, %s, %s, %s)", (order_id, service["service_id"], qty, price))
                total += (qty * price).quantize(Decimal("0.01"))
            cur.execute("UPDATE laundry_order SET total_amount=%s WHERE order_id=%s", (total, order_id))
        self.show_orders()
        messagebox.showinfo("Order saved", f"Order {order_code(order_id)} saved.\nTotal: {peso(total)}")

    @guarded
    def show_order_details(self, order_id):
        order = next(iter(self.fetch_orders(order_id=order_id)), None)
        if not order:
            raise UserError("This order no longer exists.")
        customer = self.query("SELECT contact_no, address FROM customer WHERE customer_id=%s",
                              (order["customer_id"],), fetch=True)[0]
        items = self.query("SELECT s.service_name, s.soap_brand, s.unit_type, oi.quantity, oi.unit_price "
                           "FROM order_item oi JOIN service s ON s.service_id=oi.service_id "
                           "WHERE oi.order_id=%s ORDER BY s.service_name", (order_id,), fetch=True)
        payments = self.query("SELECT payment_date, payment_method, amount_paid FROM payment "
                              "WHERE order_id=%s ORDER BY payment_id", (order_id,), fetch=True)
        history = self.query("SELECT s.status_name, l.changed_at, u.username FROM order_status_log l "
                             "JOIN order_status s ON s.status_id=l.status_id JOIN user_account u "
                             "ON u.user_id=l.changed_by WHERE l.order_id=%s ORDER BY l.log_id",
                             (order_id,), fetch=True)
        paid = sum((p["amount_paid"] for p in payments), Decimal("0"))
        lines = [f"{APP_NAME.upper()}  -  ORDER {order_code(order_id)}", "=" * 54,
                 f'Customer : {order["customer"]}', f'Contact  : {customer["contact_no"]}',
                 f'Address  : {customer["address"]}',
                 f'Ordered  : {order["order_date"]:%Y-%m-%d %H:%M}',
                 f'{order["fulfillment_type"]:<9}: ' + (f'{order["pickup_date"]:%Y-%m-%d %H:%M}' if order["pickup_date"] else "-"),
                 f'Status   : {order["status_name"]}     Payment: {order["payment_status"]}', "", "Services", "-" * 54]
        for it in items:
            name = it["service_name"] + (f' ({it["soap_brand"]})' if it["soap_brand"] else "")
            lines.append(f'{name}\n    {qty_text(it["quantity"])} {it["unit_type"].replace("per ", "")} x '
                         f'{peso(it["unit_price"])} = {peso(it["quantity"] * it["unit_price"])}')
        lines += ["-" * 54, f'TOTAL    : {peso(order["total_amount"])}', f"PAID     : {peso(paid)}",
                  f'BALANCE  : {peso(order["total_amount"] - paid)}', "", "Payments", "-" * 54]
        lines += [f'{p["payment_date"]:%Y-%m-%d %H:%M}  {p["payment_method"]:<14}{peso(p["amount_paid"])}'
                  for p in payments] or ["No payments yet."]
        lines += ["", "Status history", "-" * 54]
        lines += [f'{h["changed_at"]:%Y-%m-%d %H:%M}  {h["status_name"]:<10} by {h["username"]}' for h in history]
        text = "\n".join(lines)

        win = tk.Toplevel(self.root)
        win.title(f"Order {order_code(order_id)}")
        win.geometry("560x560")
        win.transient(self.root)
        win.configure(bg=WHITE)
        box = tk.Text(win, font=("Consolas", 10), bg="#fbfdfe", fg=TEXT, relief="flat", padx=14, pady=12, wrap="none")
        box.insert("1.0", text)
        box.config(state="disabled")
        box.pack(fill="both", expand=True)

        def save_receipt():
            path = filedialog.asksaveasfilename(parent=win, defaultextension=".txt", filetypes=[("Text file", "*.txt")],
                                                initialfile=f"{order_code(order_id)}.txt")
            if path:
                Path(path).write_text(text, encoding="utf-8")
                messagebox.showinfo("Saved", "Receipt saved.", parent=win)
        bar = tk.Frame(win, bg=WHITE, pady=8)
        bar.pack(fill="x")
        make_button(bar, "Save as .txt", save_receipt).pack(side="left", padx=12)
        make_button(bar, "Close", win.destroy, kind="secondary").pack(side="left")

    # -------------------- PAYMENTS --------------------
    @guarded
    def show_payments(self):
        body = self.page_shell("Payment Management", "Payments")
        if self.can_write():
            bar = self.toolbar(body)
            make_button(bar, "+ Record Payment", self.show_payment_form).pack(side="left")
            make_button(bar, "Update Status", self.update_payment_status).pack(side="left", padx=8)
        self.payment_tree = build_table(body, [("code", "Order No.", 100), ("customer", "Customer", 220),
                                               ("total", "Total", 100), ("paid", "Paid", 100),
                                               ("balance", "Balance", 100), ("method", "Method", 120),
                                               ("status", "Status", 90)], 12)
        rows = self.query(
            """SELECT o.order_id, CONCAT(c.first_name, ' ', c.last_name) AS customer, o.total_amount,
                      COALESCE(p.paid, 0) AS paid, o.total_amount - COALESCE(p.paid, 0) AS balance,
                      COALESCE(lp.payment_method, '-') AS method, o.payment_status
               FROM laundry_order o
               JOIN customer c ON c.customer_id = o.customer_id
               LEFT JOIN (SELECT order_id, SUM(amount_paid) AS paid FROM payment GROUP BY order_id) p
                      ON p.order_id = o.order_id
               LEFT JOIN payment lp ON lp.payment_id = (SELECT MAX(payment_id) FROM payment WHERE order_id = o.order_id)
               WHERE o.status_id <> 6 ORDER BY o.order_id DESC""", fetch=True)
        self.payment_rows = {r["order_id"]: r for r in rows}
        fill_table(self.payment_tree,
                   [dict(r, code=order_code(r["order_id"]), total=peso(r["total_amount"]), paid=peso(r["paid"]),
                         balance=peso(r["balance"]), status=r["payment_status"]) for r in rows],
                   ("code", "customer", "total", "paid", "balance", "method", "status"), "order_id", "payment_status")
        tk.Label(body, text="Update Status records the remaining balance of the selected order as paid.",
                 bg=WHITE, fg=MUTED, font=F(9)).pack(anchor="w", pady=(6, 0))

    @guarded
    def update_payment_status(self):
        order_id = self.selected_id(self.payment_tree, "payment record")
        if self.payment_rows[order_id]["payment_status"] == "Paid":
            raise UserError("This order is already fully paid.")
        self.show_payment_form(order_id, pay_full=True)

    @guarded
    def show_payment_form(self, order_id=None, pay_full=False):
        if not self.require_role("Admin", "Staff"):
            return
        rows = self.query(
            """SELECT o.order_id, CONCAT(c.first_name, ' ', c.last_name) AS customer, o.total_amount,
                      COALESCE((SELECT SUM(amount_paid) FROM payment WHERE order_id = o.order_id), 0) AS paid
               FROM laundry_order o JOIN customer c ON c.customer_id = o.customer_id
               WHERE o.status_id <> 6 AND o.payment_status <> 'Paid' ORDER BY o.order_id DESC""", fetch=True)
        if not rows:
            raise UserError("There are no orders with an unpaid balance.")
        for r in rows:
            r["balance"] = r["total_amount"] - r["paid"]
        order_map = {f'{order_code(r["order_id"])} - {r["customer"]} (balance {peso(r["balance"])})': r for r in rows}

        body = self.page_shell("Record Payment", "Payments")
        form = tk.Frame(body, bg=WHITE)
        form.pack(fill="x")
        field_label(form, "Order")
        info = tk.Label(form, text="", bg=WHITE, fg=MUTED, font=F(10))

        def show_info():
            r = order_box.selected()
            if r:
                info.config(text=f'Total {peso(r["total_amount"])}   |   Paid {peso(r["paid"])}   |   '
                                 f'Balance {peso(r["balance"])}')
            else:
                info.config(text="")
        order_box = SearchCombo(form, order_map, width=70, on_select=show_info)
        order_box.pack(fill="x", ipady=4)
        info.pack(anchor="w", pady=(4, 0))
        field_label(form, "Amount Paid (\u20b1)")
        row = tk.Frame(form, bg=WHITE)
        row.pack(fill="x")
        amount = PlaceholderEntry(row, "e.g. 200", width=30)
        amount.pack(side="left", fill="x", expand=True)

        def fill_balance():
            r = order_box.selected()
            if r:
                amount.set(f'{r["balance"]:.2f}')
        make_button(row, "Pay full balance", fill_balance, kind="secondary", pady=6).pack(side="left", padx=(8, 0))
        field_label(form, "Payment Method")
        method = ttk.Combobox(form, values=PAYMENT_METHODS, state="readonly", font=F(10))
        method.pack(fill="x", ipady=4)
        method.set("Cash")
        if order_id:
            for text, r in order_map.items():
                if r["order_id"] == order_id:
                    order_box.set(text)
            show_info()
            if pay_full:
                fill_balance()
        self.form_buttons(form, lambda: self.save_payment(order_box, amount, method.get()),
                          self.show_payments, "Save Payment")

    @guarded
    def save_payment(self, order_box, amount_entry, method):
        order = order_box.selected()
        if order is None:
            raise UserError("Please choose an order from the list.")
        amount = parse_money(amount_entry.get(), "Amount paid")
        if method not in PAYMENT_METHODS:
            raise UserError("Please choose a payment method.")
        order_id = order["order_id"]
        with self.transaction() as cur:
            cur.execute("SELECT total_amount, status_id FROM laundry_order WHERE order_id=%s FOR UPDATE", (order_id,))
            row = cur.fetchone()
            if not row or row["status_id"] == 6:
                raise UserError("This order is cancelled or no longer exists.")
            cur.execute("SELECT COALESCE(SUM(amount_paid), 0) AS paid FROM payment WHERE order_id=%s", (order_id,))
            paid = cur.fetchone()["paid"]
            balance = row["total_amount"] - paid
            if balance <= 0:
                raise UserError("This order is already fully paid.")
            if amount > balance:
                raise UserError(f"The amount is more than the balance of {peso(balance)}.")
            cur.execute("INSERT INTO payment (order_id, user_id, amount_paid, payment_method) VALUES (%s,%s,%s,%s)",
                        (order_id, self.current_user["user_id"], amount, method))
            new_status = payment_status_for(row["total_amount"], paid + amount)
            cur.execute("UPDATE laundry_order SET payment_status=%s WHERE order_id=%s", (new_status, order_id))
        self.show_payments()
        messagebox.showinfo("Payment recorded", f"Payment saved. {order_code(order_id)} is now {new_status}.")

    # -------------------- ORDER STATUS TRACKING --------------------
    @guarded
    def show_status(self):
        body = self.page_shell("Order Status Tracking", "Order Status")
        bar = self.toolbar(body)
        self.status_search = PlaceholderEntry(bar, "Search order no. or customer", width=30)
        self.status_search.pack(side="left")
        self.status_search.on_return(self.search_status)
        make_button(bar, "Search", self.search_status).pack(side="left", padx=6)
        make_button(bar, "Show All", self.refresh_status, kind="secondary").pack(side="left")
        self.status_tree = build_table(body, [("code", "Order No.", 120), ("customer", "Customer", 320),
                                              ("status", "Current Status", 160), ("payment", "Payment", 120)], 10)
        self.status_label = tk.Label(body, text="", bg=WHITE, fg=MUTED, font=F(9))
        self.status_label.pack(anchor="w", pady=(6, 0))
        if self.can_write():
            tk.Label(body, text="New status", bg=WHITE, fg=TEXT, font=F(10)).pack(anchor="w", pady=(6, 4))
            self.status_chips = ChipGroup(body, PROGRESS, "Washing")
            self.status_chips.pack(anchor="w")
            make_button(body, "Update Status", self.update_status).pack(anchor="w", pady=(12, 0))

            def preselect(_e=None):
                sel = self.status_tree.selection()
                if sel:
                    current = self.status_rows[int(sel[0])]["status_name"]
                    if current in PROGRESS:
                        self.status_chips.set(PROGRESS[min(PROGRESS.index(current) + 1, len(PROGRESS) - 1)])
            self.status_tree.bind("<<TreeviewSelect>>", preselect)
        self.refresh_status()

    def refresh_status(self, keyword=None):
        rows = self.fetch_orders(keyword, exclude_cancelled=True)
        self.status_rows = {r["order_id"]: r for r in rows}
        fill_table(self.status_tree,
                   [dict(r, code=order_code(r["order_id"]), status=r["status_name"], payment=r["payment_status"])
                    for r in rows], ("code", "customer", "status", "payment"), "order_id", "status_name")
        if keyword:
            self.status_label.config(text=f'{len(rows)} order(s) found for "{keyword}".' if rows else "No order found.")
        else:
            self.status_label.config(text="Select an order, choose its new status, then click Update Status.")

    @guarded
    def search_status(self):
        keyword = self.status_search.get().strip()
        if not keyword:
            raise UserError("Please enter a keyword to search.")
        self.refresh_status(keyword)

    @guarded
    def update_status(self):
        if not self.require_role("Admin", "Staff"):
            return
        order_id = self.selected_id(self.status_tree, "order")
        new = self.status_chips.get()
        with self.transaction() as cur:
            cur.execute("SELECT o.payment_status, s.status_name, s.sequence_no FROM laundry_order o "
                        "JOIN order_status s ON s.status_id=o.status_id WHERE o.order_id=%s FOR UPDATE", (order_id,))
            current = cur.fetchone()
            if not current:
                raise UserError("This order no longer exists.")
            cur.execute("SELECT status_id, sequence_no FROM order_status WHERE status_name=%s", (new,))
            target = cur.fetchone()
            check_status_change(current["status_name"], new, current["sequence_no"], target["sequence_no"],
                                current["payment_status"])
            cur.execute("UPDATE laundry_order SET status_id=%s WHERE order_id=%s", (target["status_id"], order_id))
            cur.execute("INSERT INTO order_status_log (order_id, status_id, changed_by) VALUES (%s,%s,%s)",
                        (order_id, target["status_id"], self.current_user["user_id"]))
        self.refresh_status()
        messagebox.showinfo("Status updated", f"Order {order_code(order_id)} is now {new}.")

    # -------------------- REPORTS --------------------
    @guarded
    def show_reports(self):
        if not self.require_role("Admin", "Viewer"):
            return
        body = self.page_shell("Reports", "Reports")
        bar = self.toolbar(body)
        self.report_tabs = ChipGroup(bar, ["Sales Summary", "Order Summary", "Payment Summary"],
                                     command=lambda _v: self.generate_report())
        self.report_tabs.pack(side="left")
        make_button(bar, "Back", self.show_dashboard, kind="secondary", padx=14, pady=4).pack(side="left", padx=(8, 0))

        filters = tk.Frame(body, bg=WHITE)
        filters.pack(fill="x", pady=(0, 10))
        today = date.today()
        self.rep_from = PlaceholderEntry(filters, "From (YYYY-MM-DD)", width=16)
        self.rep_from.pack(side="left")
        self.rep_to = PlaceholderEntry(filters, "To (YYYY-MM-DD)", width=16)
        self.rep_to.pack(side="left", padx=8)
        self.rep_from.set(today.replace(day=1).isoformat())
        self.rep_to.set(today.isoformat())
        self.rep_from.on_return(self.generate_report)
        self.rep_to.on_return(self.generate_report)
        make_button(filters, "Generate", self.generate_report).pack(side="left")
        make_button(filters, "Export CSV", self.export_report, kind="secondary").pack(side="left", padx=8)
        self.report_area = tk.Frame(body, bg=WHITE)
        self.report_area.pack(fill="both", expand=True)
        self.report_export = None
        self.generate_report()

    @guarded
    def generate_report(self):
        start = parse_date(self.rep_from.get(), "From date")
        end = parse_date(self.rep_to.get(), "To date")
        if start > end:
            raise UserError("The From date must not be later than the To date.")
        begin = datetime.combine(start, datetime.min.time())
        finish = datetime.combine(end + timedelta(days=1), datetime.min.time())
        kind = self.report_tabs.get()
        for widget in self.report_area.winfo_children():
            widget.destroy()

        if kind == "Sales Summary":
            cards = self.query("SELECT COALESCE(SUM(total_amount), 0) AS a, COUNT(*) AS n FROM laundry_order "
                               "WHERE status_id <> 6 AND order_date >= %s AND order_date < %s",
                               (begin, finish), fetch=True)[0]
            card_data = [("Total Sales", peso(cards["a"]), "blue"), ("Number of Orders", f'{cards["n"]:,}', "green")]
            rows = self.query(
                """SELECT s.service_name, s.soap_brand, s.unit_type, COUNT(DISTINCT oi.order_id) AS orders,
                          SUM(oi.quantity) AS qty, SUM(oi.quantity * oi.unit_price) AS sales
                   FROM order_item oi JOIN laundry_order o ON o.order_id = oi.order_id
                   JOIN service s ON s.service_id = oi.service_id
                   WHERE o.status_id <> 6 AND o.order_date >= %s AND o.order_date < %s
                   GROUP BY s.service_id, s.service_name, s.soap_brand, s.unit_type ORDER BY sales DESC""",
                (begin, finish), fetch=True)
            headers = ["Service", "Orders", "Quantity", "Sales"]
            table = [(r["service_name"] + (f' ({r["soap_brand"]})' if r["soap_brand"] else ""), r["orders"],
                      f'{qty_text(r["qty"])} {r["unit_type"].replace("per ", "")}', peso(r["sales"])) for r in rows]
        elif kind == "Order Summary":
            cards = self.query("SELECT COUNT(*) AS n, COALESCE(SUM(status_id NOT IN (5, 6)), 0) AS pending "
                               "FROM laundry_order WHERE status_id <> 6 AND order_date >= %s AND order_date < %s",
                               (begin, finish), fetch=True)[0]
            card_data = [("Total Orders", f'{cards["n"]:,}', "blue"), ("Pending Orders", f'{int(cards["pending"]):,}', "amber")]
            rows = self.query("SELECT s.status_name, COUNT(o.order_id) AS n FROM order_status s "
                              "LEFT JOIN laundry_order o ON o.status_id = s.status_id AND o.order_date >= %s "
                              "AND o.order_date < %s GROUP BY s.status_id, s.status_name, s.sequence_no "
                              "ORDER BY s.sequence_no", (begin, finish), fetch=True)
            headers = ["Status", "Orders"]
            table = [(r["status_name"], r["n"]) for r in rows]
        else:
            collected = self.query("SELECT COALESCE(SUM(amount_paid), 0) AS a FROM payment "
                                   "WHERE payment_date >= %s AND payment_date < %s", (begin, finish), fetch=True)[0]["a"]
            owed = self.query("SELECT COALESCE(SUM(o.total_amount), 0) - COALESCE((SELECT SUM(p.amount_paid) "
                              "FROM payment p JOIN laundry_order o2 ON o2.order_id = p.order_id "
                              "WHERE o2.status_id <> 6), 0) AS a FROM laundry_order o WHERE o.status_id <> 6",
                              fetch=True)[0]["a"]
            card_data = [("Payments Collected", peso(collected), "green"),
                         ("Outstanding Balance (all orders)", peso(owed), "amber")]
            rows = self.query("SELECT payment_method, COUNT(*) AS n, SUM(amount_paid) AS a FROM payment "
                              "WHERE payment_date >= %s AND payment_date < %s GROUP BY payment_method "
                              "ORDER BY a DESC", (begin, finish), fetch=True)
            headers = ["Method", "Payments", "Amount"]
            table = [(r["payment_method"], r["n"], peso(r["a"])) for r in rows]

        grid = tk.Frame(self.report_area, bg=WHITE)
        grid.pack(fill="x", pady=(0, 10))
        grid.columnconfigure((0, 1), weight=1, uniform="rc")
        for i, (label, value, color) in enumerate(card_data):
            bg, fg = CARD_COLORS[color]
            card = tk.Frame(grid, bg=bg, padx=16, pady=10)
            card.grid(row=0, column=i, sticky="ew", padx=(0, 10) if i == 0 else 0)
            tk.Label(card, text=label, bg=bg, fg=fg, font=F(9)).pack(anchor="w")
            tk.Label(card, text=value, bg=bg, fg=fg, font=F(22, "bold")).pack(anchor="w")
        widths = [300] + [140] * (len(headers) - 1)
        tree = build_table(self.report_area, [(f"c{i}", h, widths[i]) for i, h in enumerate(headers)], 9)
        for i, values in enumerate(table):
            tree.insert("", "end", values=values, tags=("odd",) if i % 2 else ())
        if not table:
            tk.Label(self.report_area, text="No records in this date range.", bg=WHITE, fg=MUTED,
                     font=F(10)).pack(anchor="w", pady=8)
        self.report_export = (kind, start, end, headers, table)

    @guarded
    def export_report(self):
        if not self.report_export or not self.report_export[4]:
            raise UserError("Generate a report with at least one row first.")
        kind, start, end, headers, table = self.report_export
        path = filedialog.asksaveasfilename(title="Save report", defaultextension=".csv",
                                            filetypes=[("CSV file", "*.csv")],
                                            initialfile=f'{kind.lower().replace(" ", "_")}_{start}_to_{end}.csv')
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(headers)
                writer.writerows(table)
        except OSError as exc:
            raise UserError(f"Could not save the file: {exc}") from None
        messagebox.showinfo("Export", "Report saved.")

    # -------------------- USERS (ADMIN ONLY) --------------------
    @guarded
    def show_users(self):
        if not self.require_role("Admin"):
            return
        body = self.page_shell("User Accounts", "Users")
        bar = self.toolbar(body)
        make_button(bar, "+ Add User", self.show_user_form).pack(side="left")
        make_button(bar, "Activate / Deactivate", self.toggle_user, kind="secondary").pack(side="left", padx=8)
        self.user_tree = build_table(body, [("id", "ID", 60), ("name", "Full Name", 240), ("username", "Username", 180),
                                            ("role", "Role", 100), ("state", "Status", 100)], 12)
        rows = self.query("SELECT user_id, full_name, username, role, is_active FROM user_account ORDER BY user_id",
                          fetch=True)
        self.user_rows = {r["user_id"]: r for r in rows}
        fill_table(self.user_tree, [dict(r, id=r["user_id"], name=r["full_name"],
                                         state="Active" if r["is_active"] else "Inactive") for r in rows],
                   ("id", "name", "username", "role", "state"), "user_id")
        tk.Label(body, text="Accounts are never deleted so that past orders keep their history. "
                            "Deactivate an account to stop it from logging in.",
                 bg=WHITE, fg=MUTED, font=F(9)).pack(anchor="w", pady=(6, 0))

    @guarded
    def toggle_user(self):
        if not self.require_role("Admin"):
            return
        user_id = self.selected_id(self.user_tree, "user")
        if user_id == self.current_user["user_id"]:
            raise UserError("You cannot deactivate your own account while logged in.")
        row = self.user_rows[user_id]
        self.query("UPDATE user_account SET is_active=%s WHERE user_id=%s", (0 if row["is_active"] else 1, user_id))
        self.show_users()

    @guarded
    def show_user_form(self):
        if not self.require_role("Admin"):
            return
        body = self.page_shell("Add User", "Users")
        form = tk.Frame(body, bg=WHITE)
        form.pack(fill="x")
        field_label(form, "Full Name")
        name = PlaceholderEntry(form, "Juan Dela Cruz", width=60)
        name.pack(fill="x")
        field_label(form, "Username")
        username = PlaceholderEntry(form, "juan", width=60)
        username.pack(fill="x")
        field_label(form, "Temporary Password (at least 6 characters)")
        password = PlaceholderEntry(form, "Password", password=True, width=60)
        password.pack(fill="x")
        field_label(form, "Role")
        role = ttk.Combobox(form, values=["Staff", "Viewer", "Admin"], state="readonly", font=F(10))
        role.pack(fill="x", ipady=4)
        role.set("Staff")
        self.form_buttons(form, lambda: self.save_user(name.get(), username.get(), password.get(), role.get()),
                          self.show_users)

    @guarded
    def save_user(self, name, username, password, role):
        if not self.require_role("Admin"):
            return
        name = clean_text(name, "Full name", 100)
        username = username.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.]{3,30}", username):
            raise UserError("Username must be 3-30 characters: letters, numbers, dots or underscores.")
        if len(password) < 6:
            raise UserError("Password must be at least 6 characters.")
        if self.query("SELECT 1 AS x FROM user_account WHERE username=%s", (username,), fetch=True):
            raise UserError("That username is already taken.")
        self.query("INSERT INTO user_account (full_name, username, password_hash, role) VALUES (%s,%s,%s,%s)",
                   (name, username, password_hash(password), role))
        self.show_users()
        messagebox.showinfo("User created", "The account was created.")


def main():
    try:
        initialize_database()
    except Error as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "MySQL connection failed",
            "Could not connect to MySQL.\n\n"
            "Check that MySQL is running in XAMPP and that DB_PASSWORD in main.py "
            "matches your MySQL root password.\n\n"
            f"Details: {exc}")
        root.destroy()
        return
    except OSError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Missing file", f"Could not read database/schema.sql.\n\n{exc}")
        root.destroy()
        return
    root = tk.Tk()
    LaundryManagementApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
