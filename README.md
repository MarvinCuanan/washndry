# Wash 'n Dry - Laundry Shop Management System

Python + Tkinter + MySQL (XAMPP), one file: `main.py`.  Layout and colours follow the IM2 system design.

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

MySQL root has a password? Change `DB_PASSWORD` at the top of `main.py`.
The old `wash_n_dry_db` database is no longer used - drop it in phpMyAdmin if you like.

## Pages (as in the design)
Login, Create Account, Dashboard, Customer Management, Service Management, Order Management
(+ Create Order page), Payment Management, Order Status Tracking, Reports (Sales / Order / Payment summary).
Extras: Users page (Admin), order details + receipt (double-click an order), CSV export.

## Roles
| | Admin | Staff | Viewer |
|---|---|---|---|
| View everything | yes | most (no Reports/Users) | yes (no Users) |
| Add/edit customers, create/edit/cancel orders, payments, status | yes | yes | no |
| Delete customers, manage services & prices, users | yes | no | no |

## Business rules
- An order can be edited or cancelled only while it is *Received* and has no payment.
- Status only moves forward (Received > Washing > Drying > Ready > Picked Up); *Picked Up* needs full payment.
- A payment cannot be more than the balance. Payment status (Unpaid/Partial/Paid) is computed automatically.
- Deleting a service hides it (old orders keep it). A customer with orders cannot be deleted.
- Every status change is logged in `order_status_log`.
