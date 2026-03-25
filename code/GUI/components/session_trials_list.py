"""
Shared session trials list component.

Reusable treeview showing all trials for the current session with checkbox
selection, status columns, and delete functionality. Used by RecordingTab,
ProcessingTab, and VisualisationTab.
"""

import tkinter as tk
from tkinter import ttk, messagebox


# Unicode checkbox characters (same pattern as ProcessingTab)
_UNCHECKED = "\u2610"  # ☐
_CHECKED = "\u2611"    # ☑


class SessionTrialsList:
    """Treeview list of trials for the current session with checkboxes and status."""

    def __init__(self, parent, project_manager, get_current_project,
                 get_current_session, on_select=None):
        """
        Args:
            parent: tkinter parent widget
            project_manager: ProjectManager instance
            get_current_project: callable returning current project name or None
            get_current_session: callable returning current session name or None
            on_select: optional callback(trial_name) when a trial row is clicked
        """
        self.pm = project_manager
        self.get_current_project = get_current_project
        self.get_current_session = get_current_session
        self.on_select = on_select

        # State
        self._checked = set()       # Set of checked treeview item IDs
        self._trial_map = {}        # iid -> trial_name
        self._subject_cache = {}    # subject_id -> subject dict

        # Build widgets
        self.frame = ttk.LabelFrame(parent, text="Session Trials", padding=10)
        self._create_widgets()

    def _create_widgets(self):
        """Build the treeview with buttons."""
        # Button row
        btn_row = ttk.Frame(self.frame)
        btn_row.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(btn_row, text="Select All", command=self._select_all).pack(
            side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="Deselect All", command=self._deselect_all).pack(
            side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="Delete Selected", command=self._delete_selected).pack(
            side=tk.RIGHT)

        # Treeview
        tree_container = ttk.Frame(self.frame)
        tree_container.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(
            tree_container, height=6, show="tree headings",
            columns=("participant", "sync", "calib", "processed"),
        )
        self.tree.heading("#0", text="Trial")
        self.tree.heading("participant", text="Participant")
        self.tree.heading("sync", text="Sync")
        self.tree.heading("calib", text="Calib")
        self.tree.heading("processed", text="Processed")

        self.tree.column("#0", width=180, minwidth=120)
        self.tree.column("participant", width=100, minwidth=70)
        self.tree.column("sync", width=80, minwidth=60)
        self.tree.column("calib", width=120, minwidth=80)
        self.tree.column("processed", width=80, minwidth=60)

        tree_scroll = ttk.Scrollbar(tree_container, orient="vertical",
                                    command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Tags
        self.tree.tag_configure("checked", background="#d4edda")

        # Click handler
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
        self.tree.bind("<Delete>", lambda e: self._delete_selected())

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def refresh(self):
        """Rebuild tree from current session's trials."""
        # Clear
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._checked.clear()
        self._trial_map.clear()

        project = self.get_current_project()
        session = self.get_current_session()
        if not project or not session:
            return

        # Build subject cache for participant display
        self._subject_cache.clear()
        try:
            for subj in self.pm.list_subjects(project):
                sid = subj.get("subject_id", "")
                if sid:
                    self._subject_cache[sid] = subj
        except Exception:
            pass

        # Populate trials
        try:
            trials = self.pm.list_trials(project, session)
        except Exception:
            return

        for trial_name in trials:
            try:
                trial = self.pm.get_trial(project, session, trial_name)
            except Exception:
                trial = {}

            participant = self._format_participant(trial.get("subject_id", ""))
            sync = "Synced" if trial.get("synced", False) else "Not synced"
            calib = trial.get("calibration_file", "") or "--"
            if calib == "none":
                calib = "--"
            processed = self._format_processed(trial.get("processed", False))

            display = f"{_UNCHECKED} {trial_name}"
            iid = self.tree.insert(
                "", tk.END, text=display,
                values=(participant, sync, calib, processed),
            )
            self._trial_map[iid] = trial_name

    def get_checked_trials(self):
        """Return list of checked trial names."""
        return [self._trial_map[iid] for iid in self._checked
                if iid in self._trial_map]

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    def _format_participant(self, subject_id):
        """Format as 'S01 (AB)' using subject cache, or just subject_id."""
        if not subject_id:
            return "--"
        subj = self._subject_cache.get(subject_id)
        if subj and subj.get("initials"):
            return f"{subject_id} ({subj['initials']})"
        return subject_id

    def _format_processed(self, processed):
        """Format processed status."""
        if processed is True:
            return "Done"
        elif processed == "failed":
            return "Failed"
        return "--"

    def _on_tree_click(self, event):
        """Toggle checkbox on click, fire on_select callback."""
        iid = self.tree.identify_row(event.y)
        if not iid or iid not in self._trial_map:
            return

        # Toggle check
        if iid in self._checked:
            self._uncheck(iid)
        else:
            self._check(iid)

        # Fire callback
        if self.on_select:
            self.on_select(self._trial_map[iid])

    def _check(self, iid):
        """Mark a trial as checked."""
        self._checked.add(iid)
        current_text = self.tree.item(iid, "text")
        new_text = current_text.replace(_UNCHECKED, _CHECKED, 1)
        self.tree.item(iid, text=new_text, tags=("checked",))

    def _uncheck(self, iid):
        """Unmark a trial."""
        self._checked.discard(iid)
        current_text = self.tree.item(iid, "text")
        new_text = current_text.replace(_CHECKED, _UNCHECKED, 1)
        self.tree.item(iid, text=new_text, tags=())

    def _select_all(self):
        """Check all trials."""
        for iid in self._trial_map:
            self._check(iid)

    def _deselect_all(self):
        """Uncheck all trials."""
        for iid in list(self._checked):
            self._uncheck(iid)

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
