# Wash 'n Dry - Laundry Shop Management System

Python + Tkinter + MySQL (XAMPP). The code is organized into `core.py`
(configuration, validation, database setup), `widgets.py` (shared UI widgets),
and `app.py` (application screens). `main.py` is the launcher. Layout and
colours follow the IM2 system design.

## Run it (Windows + XAMPP + VS Code)
1. XAMPP Control Panel -> **Start MySQL**.
2. VS Code -> File > Open Folder -> this folder.
3. In the VS Code terminal (Ctrl+`):
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python main.py
   ```
4. First run creates the `washndry` database and all 9 tables from `database/schema.sql`
   (you can also import that file in phpMyAdmin).
5. Log in: **admin / admin123** (or "Create your own account" for a Staff account).

The schema also installs reporting views, stored routines, an order-balance
function, and audit triggers. See [COMPLIANCE.md](COMPLIANCE.md) for the ERD,
normalization walkthrough, security notes, backup/restore procedure, and
performance evidence checklist.

MySQL root has a password? Change `DB_PASSWORD` at the top of `core.py`.
The old `wash_n_dry_db` database is no longer used - drop it in phpMyAdmin if you like.

## Pages (as in the design)
Login, Create Account, Dashboard, Customer Management, Service Management, Order Management
(+ Create Order page), Payment Management, Order Status Tracking, Reports (Sales / Order / Payment summary).
Extras: Users page (Admin), soap-brand management (Admin), order details + receipt
(double-click an order), CSV export.

## Roles
| | Admin | Staff | Viewer |
|---|---|---|---|
| View everything | yes | most (no Reports/Users) | yes (no Users) |
| Add/edit customers, create/edit/cancel orders, payments, status | yes | yes | no |
| Delete customers, manage services & prices, users | yes | no | no |

## Business rules
- An order can be edited or cancelled only while it is *Received* and has no payment.
- Status only moves forward (Received > Washing > Drying > Ready > Picked Up for pickup orders, or Delivered for delivery orders); the final status needs full payment.
- A payment cannot be more than the balance. Payment status (Unpaid/Partial/Paid) is computed automatically.
- Delivery orders require a delivery address. It is pre-filled from the customer's saved address, can be edited for that order, and is shown in the order list and receipt.
- The default service catalog includes the requested laundry services, descriptions, units, and prices. Admins can edit service prices and choose whether a service requires detergent.
- Soap brands are managed separately by Admins under **Services > Soap Brands**. Each brand can have an optional additional price per unit.
- When creating an order, the service, soap brand, and fabric conditioner are selected separately for each service line. Detergent is required only for services marked as requiring it; dry-only and pressing services do not show a detergent choice.
- The selected soap brand and its surcharge are saved on the order line and shown on the receipt. Removing a brand affects new orders only; existing orders keep their recorded choice.
- Deleting a service hides it (old orders keep it). A customer with orders cannot be deleted.
- Every status change is logged in `order_status_log`.
