#!/usr/bin/env python3
"""
Shared red "sync issue" popup.

Shown when an automatic audio sync is unacceptable — used by the Recording tab
(trial discarded) and the Calibration tab (extrinsic calibration aborted). Displays
the failure reasons and the sync table; a single OK button (and the window close
button) runs the caller-supplied ``on_ok`` cleanup.
"""

import tkinter as tk

_RED = "#c62828"


def show_sync_discard_dialog(parent, table_text, reasons, *,
                             heading, subtext, on_ok=None):
    """Build and show the modal red sync-issue dialog.

    Args:
        parent: parent window (a Tk/Toplevel) to attach the dialog to.
        table_text: the formatted audio sync table, or None if unavailable.
        reasons: list of human-readable failure reasons.
        heading: bold white text in the red header band.
        subtext: one-line message under the header.
        on_ok: callable invoked after the dialog is closed (OK or window close).
    """
    dlg = tk.Toplevel(parent)
    dlg.title("Sync Issue")
    dlg.transient(parent)
    dlg.configure(bg="white")
    dlg.resizable(False, False)

    # Red header band
    header = tk.Frame(dlg, bg=_RED)
    header.pack(fill="x")
    tk.Label(
        header, text=heading,
        bg=_RED, fg="white", font=("Segoe UI", 14, "bold"),
        padx=20, pady=12,
    ).pack(fill="x")

    body = tk.Frame(dlg, bg="white", padx=20, pady=15)
    body.pack(fill="both", expand=True)

    tk.Label(
        body, text=subtext,
        bg="white", fg="#333333", font=("Segoe UI", 10), anchor="w",
    ).pack(fill="x", pady=(0, 8))

    # Failure reasons
    for r in reasons:
        tk.Label(
            body, text=f"•  {r}", bg="white", fg=_RED,
            font=("Segoe UI", 9), anchor="w", justify="left", wraplength=760,
        ).pack(fill="x")

    # Sync table (monospace)
    tk.Label(
        body, text="Audio sync table:", bg="white", fg="#333333",
        font=("Segoe UI", 9, "bold"), anchor="w",
    ).pack(fill="x", pady=(12, 4))

    if table_text:
        txt = tk.Text(body, height=min(len(table_text.splitlines()) + 1, 14),
                      width=118, font=("Courier New", 9),
                      bg="#f5f5f5", fg="#222222", relief="solid", borderwidth=1,
                      wrap="none")
        txt.insert("1.0", table_text)
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)
    else:
        tk.Label(
            body, text="No sync table available.", bg="white", fg="#777777",
            font=("Courier New", 9), anchor="w",
        ).pack(fill="x")

    def _ok():
        dlg.destroy()
        if on_ok:
            on_ok()

    btn_row = tk.Frame(dlg, bg="white", pady=12)
    btn_row.pack(fill="x")
    tk.Button(
        btn_row, text="OK", command=_ok, width=12,
        bg=_RED, fg="white", activebackground="#a31515", activeforeground="white",
        font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
    ).pack()

    dlg.protocol("WM_DELETE_WINDOW", _ok)
    dlg.grab_set()
    dlg.focus_set()
    return dlg
