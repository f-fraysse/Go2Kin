"""Collapsible section widget for Go2Kin GUI."""

import tkinter as tk
from tkinter import ttk

# Status indicator colors
STATUS_COLORS = {
    "green": "#4CAF50",
    "amber": "#FF9800",
    "red": "#F44336",
    "grey": "#9E9E9E",
}


class CollapsibleSection:
    """A section with a clickable header that toggles content visibility.

    Header shows: arrow (▸/▾) + title + colored status circle + status text.
    Status line is always visible, even when collapsed.
    """

    def __init__(self, parent, title, initially_collapsed=True):
        self.parent = parent
        self._collapsed = initially_collapsed

        # Outer frame holds everything
        self.frame = ttk.Frame(parent)

        # Header frame — clickable
        self._header = ttk.Frame(self.frame)
        self._header.pack(fill="x", padx=10, pady=(5, 0))

        self._arrow_label = ttk.Label(
            self._header, text="\u25B8" if initially_collapsed else "\u25BE",
            font=("TkDefaultFont", 10),
        )
        self._arrow_label.pack(side="left", padx=(0, 4))

        self._title_label = ttk.Label(
            self._header, text=title,
            font=("TkDefaultFont", 10, "bold"),
        )
        self._title_label.pack(side="left")

        # Status indicator: canvas circle + text
        self._status_canvas = tk.Canvas(
            self._header, width=14, height=14,
            highlightthickness=0, borderwidth=0,
        )
        self._status_canvas.pack(side="left", padx=(12, 4))
        self._status_circle = self._status_canvas.create_oval(
            2, 2, 12, 12, fill=STATUS_COLORS["grey"], outline="",
        )

        self._status_label = ttk.Label(self._header, text="", foreground="#666666")
        self._status_label.pack(side="left")

        # Make header clickable
        for widget in (self._header, self._arrow_label, self._title_label):
            widget.bind("<Button-1>", lambda e: self.toggle())
            widget.configure(cursor="hand2")

        # Separator below header
        ttk.Separator(self.frame, orient="horizontal").pack(fill="x", padx=10, pady=(2, 0))

        # Content frame — shown/hidden
        self.content = ttk.Frame(self.frame, padding=(10, 5, 10, 5))
        if not initially_collapsed:
            self.content.pack(fill="x")

    def toggle(self):
        if self._collapsed:
            self.expand()
        else:
            self.collapse()

    def expand(self):
        self._collapsed = False
        self._arrow_label.config(text="\u25BE")
        self.content.pack(fill="x")

    def collapse(self):
        self._collapsed = True
        self._arrow_label.config(text="\u25B8")
        self.content.pack_forget()

    def set_status(self, color, text=""):
        """Update status indicator. color: 'green', 'amber', 'red', 'grey'."""
        fill = STATUS_COLORS.get(color, STATUS_COLORS["grey"])
        self._status_canvas.itemconfig(self._status_circle, fill=fill)
        self._status_label.config(text=text)

    @property
    def is_collapsed(self):
        return self._collapsed
