"""
Go2Kin - Project Tab
Manages project, session, and subject selection.
"""

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox


class ProjectTab:
    """First tab in the GUI — project/session/subject management."""

    def __init__(self, notebook, project_manager, app_config, save_config_callback):
        self.notebook = notebook
        self.pm = project_manager
        self.app_config = app_config
        self.save_config = save_config_callback

        self._current_project = None
        self._current_session = None

        self.frame = ttk.Frame(notebook)
        notebook.add(self.frame, text="Project")

        self._create_widgets()
        self._restore_last_selection()

    # -- Public API ----------------------------------------------------------

    def get_current_project(self):
        """Return the currently selected project name, or None."""
        return self._current_project

    def get_current_session(self):
        """Return the currently selected session name, or None."""
        return self._current_session

    # -- Widget creation -----------------------------------------------------

    def _create_widgets(self):
        # Outer padding
        pad = {"padx": 10, "pady": 5}

        # --- Project section ---
        proj_frame = ttk.LabelFrame(self.frame, text="Project")
        proj_frame.pack(fill=tk.X, **pad)

        row = ttk.Frame(proj_frame)
        row.pack(fill=tk.X, padx=8, pady=6)

        self.project_combo = ttk.Combobox(row, state="readonly", width=40)
        self.project_combo.pack(side=tk.LEFT, padx=(0, 8))
        self.project_combo.bind("<<ComboboxSelected>>", self._on_project_selected)

        ttk.Button(row, text="New Project", command=self._on_new_project).pack(side=tk.LEFT)

        # --- Session section ---
        sess_frame = ttk.LabelFrame(self.frame, text="Session")
        sess_frame.pack(fill=tk.X, **pad)

        row2 = ttk.Frame(sess_frame)
        row2.pack(fill=tk.X, padx=8, pady=6)

        self.session_combo = ttk.Combobox(row2, state="readonly", width=40)
        self.session_combo.pack(side=tk.LEFT, padx=(0, 8))
        self.session_combo.bind("<<ComboboxSelected>>", self._on_session_selected)

        ttk.Button(row2, text="New Session", command=self._on_new_session).pack(side=tk.LEFT)

        # --- Subjects section ---
        subj_frame = ttk.LabelFrame(self.frame, text="Subjects")
        subj_frame.pack(fill=tk.BOTH, expand=True, **pad)

        columns = ("subject_id", "initials", "age", "sex", "height_m", "mass_kg")
        self.subject_tree = ttk.Treeview(
            subj_frame, columns=columns, show="headings", height=8
        )
        for col in columns:
            heading = col.replace("_", " ").title()
            self.subject_tree.heading(col, text=heading)
            width = 60 if col in ("age", "sex") else 100
            self.subject_tree.column(col, width=width, anchor=tk.CENTER)

        self.subject_tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 2))

        ttk.Button(subj_frame, text="New Subject", command=self._on_new_subject).pack(
            padx=8, pady=(2, 6), anchor=tk.W
        )

        # --- Status label (shown when nothing is available) ---
        self.status_label = ttk.Label(self.frame, text="", foreground="gray")
        self.status_label.pack(padx=10, pady=(0, 5))

    # -- Refresh helpers -----------------------------------------------------

    def _refresh_projects(self):
        projects = self.pm.list_projects() if self.pm else []
        self.project_combo["values"] = projects
        if not projects:
            self.status_label.config(text="Create a project to get started")
        else:
            self.status_label.config(text="")

    def _refresh_sessions(self):
        self.session_combo.set("")
        if not self._current_project or not self.pm:
            self.session_combo["values"] = []
            return
        sessions = self.pm.list_sessions(self._current_project)
        self.session_combo["values"] = sessions

    def _refresh_subjects(self):
        self.subject_tree.delete(*self.subject_tree.get_children())
        if not self._current_project or not self.pm:
            return
        try:
            subjects = self.pm.list_subjects(self._current_project)
        except Exception:
            return
        for s in subjects:
            self.subject_tree.insert("", tk.END, values=(
                s.get("subject_id", ""),
                s.get("initials", ""),
                s.get("age", ""),
                s.get("sex", ""),
                s.get("height_m", ""),
                s.get("mass_kg", ""),
            ))

    # -- Selection handlers --------------------------------------------------

    def _select_project(self, name):
        """Programmatically select a project and update state."""
        self._current_project = name
        self._current_session = None
        self.project_combo.set(name)
        self.app_config["last_project"] = name
        self.app_config["last_session"] = ""
        self.save_config()
        self._refresh_sessions()
        self._refresh_subjects()

    def _on_project_selected(self, _event=None):
        name = self.project_combo.get()
        if name:
            self._select_project(name)

    def _select_session(self, name):
        """Programmatically select a session and update state."""
        self._current_session = name
        self.session_combo.set(name)
        self.app_config["last_session"] = name
        self.save_config()

    def _on_session_selected(self, _event=None):
        name = self.session_combo.get()
        if name:
            self._select_session(name)

    # -- "New" dialogs -------------------------------------------------------

    def _on_new_project(self):
        name = simpledialog.askstring("New Project", "Project name:",
                                      parent=self.frame)
        if not name:
            return
        try:
            self.pm.create_project(name.strip())
        except ValueError as e:
            messagebox.showerror("Error", str(e), parent=self.frame)
            return
        self._refresh_projects()
        self._select_project(name.strip())

    def _on_new_session(self):
        if not self._current_project:
            messagebox.showwarning("No Project", "Select a project first.",
                                   parent=self.frame)
            return
        name = simpledialog.askstring("New Session", "Session name:",
                                      parent=self.frame)
        if not name:
            return
        try:
            self.pm.create_session(self._current_project, name.strip())
        except ValueError as e:
            messagebox.showerror("Error", str(e), parent=self.frame)
            return
        self._refresh_sessions()
        self._select_session(name.strip())

    def _on_new_subject(self):
        if not self._current_project:
            messagebox.showwarning("No Project", "Select a project first.",
                                   parent=self.frame)
            return
        self._show_new_subject_dialog()

    def _show_new_subject_dialog(self):
        dlg = tk.Toplevel(self.frame)
        dlg.title("New Subject")
        dlg.resizable(False, False)
        dlg.grab_set()

        fields = {}
        labels = [
            ("Subject ID", "subject_id"),
            ("Initials", "initials"),
            ("Age", "age"),
            ("Height (m)", "height_m"),
            ("Mass (kg)", "mass_kg"),
        ]

        for i, (label, key) in enumerate(labels):
            ttk.Label(dlg, text=label).grid(row=i, column=0, padx=8, pady=4, sticky=tk.W)
            entry = ttk.Entry(dlg, width=20)
            entry.grid(row=i, column=1, padx=8, pady=4)
            fields[key] = entry

        # Sex dropdown
        row_sex = len(labels)
        ttk.Label(dlg, text="Sex").grid(row=row_sex, column=0, padx=8, pady=4, sticky=tk.W)
        sex_var = tk.StringVar(value="M")
        sex_combo = ttk.Combobox(dlg, textvariable=sex_var, values=["M", "F", "Other"],
                                 state="readonly", width=17)
        sex_combo.grid(row=row_sex, column=1, padx=8, pady=4)

        def on_ok():
            try:
                subject_id = fields["subject_id"].get().strip()
                initials = fields["initials"].get().strip()
                age = int(fields["age"].get().strip())
                height_m = float(fields["height_m"].get().strip())
                mass_kg = float(fields["mass_kg"].get().strip())
                sex = sex_var.get()
            except ValueError:
                messagebox.showerror("Invalid Input",
                                     "Age must be a whole number.\n"
                                     "Height and Mass must be numbers.",
                                     parent=dlg)
                return

            if not subject_id or not initials:
                messagebox.showerror("Missing Fields",
                                     "Subject ID and Initials are required.",
                                     parent=dlg)
                return

            try:
                self.pm.create_subject(
                    self._current_project, subject_id, initials,
                    age, sex, height_m, mass_kg
                )
            except ValueError as e:
                messagebox.showerror("Error", str(e), parent=dlg)
                return

            dlg.destroy()
            self._refresh_subjects()

        btn_row = row_sex + 1
        btn_frame = ttk.Frame(dlg)
        btn_frame.grid(row=btn_row, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side=tk.LEFT, padx=8)

        # Center dialog on parent
        dlg.update_idletasks()
        dlg.geometry(f"+{self.frame.winfo_rootx() + 50}+{self.frame.winfo_rooty() + 50}")

    # -- Restore last selection ----------------------------------------------

    def _restore_last_selection(self):
        self._refresh_projects()
        projects = list(self.project_combo["values"])

        last_project = self.app_config.get("last_project", "")
        if last_project and last_project in projects:
            # Set project state without clearing last_session
            # (_select_project would clear it and save to disk)
            self._current_project = last_project
            self.project_combo.set(last_project)
            self._refresh_sessions()
            self._refresh_subjects()

            sessions = list(self.session_combo["values"])
            last_session = self.app_config.get("last_session", "")
            if last_session and last_session in sessions:
                self._current_session = last_session
                self.session_combo.set(last_session)
