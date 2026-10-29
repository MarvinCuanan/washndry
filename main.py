"""Wash 'n Dry - Laundry Shop Management System

The application is split into core services, reusable widgets, and screens.
Run with: python main.py
"""
import tkinter as tk
from tkinter import messagebox

from app import LaundryManagementApp
from core import Error, initialize_database


def main():
    try:
        initialize_database()
    except Error as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "MySQL connection failed",
            "Could not connect to MySQL.\n\n"
            "Check that MySQL is running in XAMPP and that DB_PASSWORD in core.py "
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
