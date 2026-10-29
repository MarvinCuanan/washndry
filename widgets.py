"""Reusable Tkinter widgets and table helpers."""
import tkinter as tk
from tkinter import ttk

from core import *

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


