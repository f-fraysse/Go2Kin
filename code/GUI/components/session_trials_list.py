"""
Shared session trials list component.

Reusable scrollable list showing all trials for the current session with checkbox
selection, colored status indicators, and delete functionality. Used by RecordingTab,
ProcessingTab, and VisualisationTab.

Uses a Canvas+Frame approach instead of ttk.Treeview to allow per-cell colored
text (colored ● indicators for sync/calib/processed status).
"""

import tkinter as tk
from tkinter import ttk, messagebox


# Unicode characters
_UNCHECKED = "\u2610"  # ☐
_CHECKED = "\u2611"    # ☑
_CIRCLE = "\u25CF"     # ●

# Row colors
_BG_DEFAULT = "#ffffff"
_BG_ALT = "#f5f5f5"
_BG_CHECKED = "#d4edda"
_BG_HOVER = "#e8e8e8"

# Status colors
_GREEN = "#2e7d32"
_RED = "#c62828"
_GREY = "#9e9e9e"
_AMBER = "#f57f17"

# Column config: (key, heading, width, stretch, anchor)
# width in pixels; stretch=True means column expands with available space
_COLUMNS = [
    ("check",       "",           20,  False, "w"),
    ("trial",       "Trial",      200, True,  "w"),
    ("date",        "Date",       200, False, "w"),
    ("participant", "Participant", 80,  False, "w"),
    ("sync",        "Sync",       40,  False, "w"),
    ("calib",       "Cal",        40,  False, "w"),
    ("processed",   "Proc",       40,  False, "w"),
]


class SessionTrialsList:
    """Scrollable list of trials for the current session with checkboxes and status."""

    def __init__(self, parent, project_manager, get_current_project,
                 get_current_session, on_select=None, single_select=False):
        """
        Args:
            parent: tkinter parent widget
            project_manager: ProjectManager instance
            get_current_project: callable returning current project name or None
            get_current_session: callable returning current session name or None
            on_select: optional callback(trial_name) when a trial row is clicked
            single_select: if True, only one row can be checked at a time
        """
        self.pm = project_manager
        self.get_current_project = get_current_project
        self.get_current_session = get_current_session
        self.on_select = on_select
        self.single_select = single_select

        # State
        self._rows = []             # List of row dicts
        self._subject_cache = {}    # subject_id -> subject dict

        # Build widgets
        self.frame = ttk.LabelFrame(parent, text="Session Trials", padding=10)
        self._create_widgets()

    def _create_widgets(self):
        """Build the canvas-based list with buttons."""
        # Button row
        btn_row = ttk.Frame(self.frame)
        btn_row.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(btn_row, text="Select All", command=self._select_all).pack(
            side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="Deselect All", command=self._deselect_all).pack(
            side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="Delete Selected", command=self._delete_selected).pack(
            side=tk.RIGHT)

        # Scrollable canvas
        canvas_container = ttk.Frame(self.frame)
        canvas_container.pack(fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(canvas_container, highlightthickness=0,
                                 bg=_BG_DEFAULT)
        self._scrollbar = ttk.Scrollbar(canvas_container, orient="vertical",
                                        command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Interior frame inside canvas (header + data rows share same grid)
        self._interior = tk.Frame(self._canvas, bg=_BG_DEFAULT)
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._interior, anchor="nw")

        # Configure column layout on interior
        for i, (_, _, width, stretch, _) in enumerate(_COLUMNS):
            self._interior.columnconfigure(i, weight=1 if stretch else 0,
                                           minsize=width)

        # Header row (row 0 inside interior frame)
        self._create_header()

        # Resize bindings
        self._interior.bind("<Configure>", self._on_interior_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Mousewheel scrolling
        self._canvas.bind("<Enter>", self._bind_mousewheel)
        self._canvas.bind("<Leave>", self._unbind_mousewheel)

        # Keyboard delete
        self._canvas.bind("<Delete>", lambda e: self._delete_selected())

    def _create_header(self):
        """Create the column header row inside the interior frame (row 0)."""
        for i, (_, heading, _, _, _) in enumerate(_COLUMNS):
            lbl = tk.Label(self._interior, text=heading,
                           font=("Segoe UI", 9, "bold"),
                           bg="#e0e0e0", anchor="w", padx=4, pady=2)
            lbl.grid(row=0, column=i, sticky="ew")

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def refresh(self):
        """Rebuild list from current session's trials."""
        # Clear existing rows
        for row in self._rows:
            row["frame"].destroy()
        self._rows.clear()

        project = self.get_current_project()
        session = self.get_current_session()
        if not project or not session:
            return

        # Build subject cache
        self._subject_cache.clear()
        try:
            for subj in self.pm.list_subjects(project):
                sid = subj.get("subject_id", "")
                if sid:
                    self._subject_cache[sid] = subj
        except Exception:
            pass

        # Populate trials, sorted newest first by date field
        try:
            trial_names = self.pm.list_trials(project, session)
        except Exception:
            return

        trials_with_data = []
        for trial_name in trial_names:
            try:
                trial = self.pm.get_trial(project, session, trial_name)
            except Exception:
                trial = {}
            trials_with_data.append((trial_name, trial))

        trials_with_data.sort(
            key=lambda t: t[1].get("date", "") + " " + t[1].get("time", ""),
            reverse=True)

        for idx, (trial_name, trial) in enumerate(trials_with_data):
            self._create_row(idx, trial_name, trial)

    def get_checked_trials(self):
        """Return list of checked trial names."""
        return [row["trial_name"] for row in self._rows if row["checked"]]

    # -------------------------------------------------------------------------
    # Row creation
    # -------------------------------------------------------------------------

    def _create_row(self, idx, trial_name, trial):
        """Create a single row in the interior frame."""
        bg = _BG_ALT if idx % 2 else _BG_DEFAULT

        row_frame = tk.Frame(self._interior, bg=bg)
        row_frame.grid(row=idx + 1, column=0, columnspan=len(_COLUMNS), sticky="ew")

        # Match column layout
        for i, (_, _, width, stretch, _) in enumerate(_COLUMNS):
            row_frame.columnconfigure(i, weight=1 if stretch else 0,
                                      minsize=width)

        # Build cell data
        date_str = self._format_date(trial.get("date", ""), trial.get("time", ""))
        participant = self._format_participant(trial.get("subject_id", ""))
        sync_color, sync_text = self._format_sync(trial.get("synced", False))
        calib_color, calib_text = self._format_calib(trial.get("calibration_file", ""))
        proc_color, proc_text = self._format_processed(trial.get("processed", False))

        cells = [
            (_UNCHECKED, None),   # check
            (trial_name, None),   # trial
            (date_str, None),     # date
            (participant, None),  # participant
            (sync_text, sync_color),   # sync
            (calib_text, calib_color),  # calib
            (proc_text, proc_color),   # processed
        ]

        labels = {}
        for i, ((key, _, _, _, _), (text, fg)) in enumerate(zip(_COLUMNS, cells)):
            # Larger font for status circles, small for checkbox
            if key in ("sync", "calib", "processed"):
                font = ("Segoe UI", 16)
                pady = 0
            elif key == "check":
                font = ("Segoe UI", 11)
                pady = 1
            else:
                font = ("Segoe UI", 10)
                pady = 1
            lbl = tk.Label(row_frame, text=text, bg=bg, anchor="w",
                           padx=4, pady=pady, bd=0, font=font)
            if fg:
                lbl.configure(fg=fg)
            lbl.grid(row=0, column=i, sticky="ew")
            labels[key] = lbl

            # Bind click on each label
            lbl.bind("<ButtonRelease-1>",
                     lambda e, tn=trial_name: self._on_row_click(tn))

        # Bind click on row frame too
        row_frame.bind("<ButtonRelease-1>",
                       lambda e, tn=trial_name: self._on_row_click(tn))

        row_data = {
            "frame": row_frame,
            "labels": labels,
            "trial_name": trial_name,
            "checked": False,
            "bg": bg,
        }
        self._rows.append(row_data)

    # -------------------------------------------------------------------------
    # Status formatting
    # -------------------------------------------------------------------------

    def _format_date(self, date, time):
        """Format as 'YYYY-MM-DD HH:mm'."""
        if not date:
            return "--"
        # time is "HH:MM:SS", truncate to "HH:MM"
        hhmm = time[:5] if time else ""
        return f"{date} {hhmm}".strip()

    def _format_participant(self, subject_id):
        """Format as 'S01 (AB)' using subject cache."""
        if not subject_id:
            return "--"
        subj = self._subject_cache.get(subject_id)
        if subj and subj.get("initials"):
            return f"{subject_id} ({subj['initials']})"
        return subject_id

    def _format_sync(self, synced):
        """Return (color, display_text) for sync status."""
        if synced:
            return _GREEN, _CIRCLE
        return _RED, _CIRCLE

    def _format_calib(self, calib_file):
        """Return (color, display_text) for calibration status."""
        if calib_file and calib_file != "none":
            return _GREEN, _CIRCLE
        return _GREY, _CIRCLE

    def _format_processed(self, processed):
        """Return (color, display_text) for processed status."""
        if processed is True:
            return _GREEN, _CIRCLE
        elif processed == "failed":
            return _RED, _CIRCLE
        return _GREY, _CIRCLE

    # -------------------------------------------------------------------------
    # Row interaction
    # -------------------------------------------------------------------------

    def _on_row_click(self, trial_name):
        """Toggle checkbox on click, fire on_select callback."""
        row = self._find_row(trial_name)
        if not row:
            return

        if self.single_select:
            for r in self._rows:
                if r is not row and r["checked"]:
                    self._uncheck(r)
            self._check(row)
        elif row["checked"]:
            self._uncheck(row)
        else:
            self._check(row)

        if self.on_select:
            self.on_select(trial_name)

    def _check(self, row):
        """Mark a trial as checked."""
        row["checked"] = True
        row["labels"]["check"].configure(text=_CHECKED)
        self._set_row_bg(row, _BG_CHECKED)

    def _uncheck(self, row):
        """Unmark a trial."""
        row["checked"] = False
        row["labels"]["check"].configure(text=_UNCHECKED)
        self._set_row_bg(row, row["bg"])

    def _set_row_bg(self, row, bg):
        """Set background color on row frame and all labels."""
        row["frame"].configure(bg=bg)
        for lbl in row["labels"].values():
            lbl.configure(bg=bg)

    def _find_row(self, trial_name):
        """Find row dict by trial name."""
        for row in self._rows:
            if row["trial_name"] == trial_name:
                return row
        return None

    def _select_all(self):
        """Check all trials."""
        for row in self._rows:
            self._check(row)

    def _deselect_all(self):
        """Uncheck all trials."""
        for row in self._rows:
            self._uncheck(row)

    def _delete_selected(self):
        """Delete checked trials after confirmation."""
        checked = self.get_checked_trials()
        if not checked:
            return

        project = self.get_current_project()
        session = self.get_current_session()
        if not project or not session:
            return

        names = ", ".join(checked)
        if not messagebox.askyesno(
            "Delete Trials",
            f"Delete {len(checked)} trial(s)?\n\n{names}\n\nThis cannot be undone.",
        ):
            return

        for trial_name in checked:
            try:
                self.pm.delete_trial(project, session, trial_name)
                print(f"Deleted trial: {trial_name}")
            except Exception as e:
                print(f"Error deleting {trial_name}: {e}")

        self.refresh()

    # -------------------------------------------------------------------------
    # Canvas/scroll management
    # -------------------------------------------------------------------------

    def _on_interior_configure(self, event):
        """Update scrollregion when interior frame changes size."""
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        """Stretch interior frame to canvas width."""
        self._canvas.itemconfigure(self._canvas_window, width=event.width)

    def _bind_mousewheel(self, event):
        """Bind mousewheel when cursor enters canvas."""
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, event):
        """Unbind mousewheel when cursor leaves canvas."""
        self._canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        """Scroll canvas on mousewheel."""
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
