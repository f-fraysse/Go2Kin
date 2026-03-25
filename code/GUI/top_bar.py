"""
Go2Kin - Top Bar
Persistent project/session/participant selection bar above the tab notebook.
"""

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox


class TopBar:
    """Persistent bar with project/session/participant dropdowns + calibration status."""

    def __init__(self, parent, project_manager, app_config, save_config_callback,
                 on_selection_changed=None):
        self.parent = parent
        self.pm = project_manager
        self.app_config = app_config
        self.save_config = save_config_callback
        self._on_selection_changed = on_selection_changed

        self._current_project = None
        self._current_session = None
        self._current_participant = None

        self._create_widgets()
        self._restore_last_selection()

    # -- Public API ----------------------------------------------------------

    def get_current_project(self):
        return self._current_project

    def get_current_session(self):
        return self._current_session

    def get_current_participant(self):
        return self._current_participant

    def refresh_calibration_status(self):
        """Update calibration indicator from ProjectManager."""
        self._update_calibration_indicator()

    def refresh_participants(self):
        """Re-populate participant dropdown from ProjectManager."""
        self._refresh_participants()

    # -- Widget creation -----------------------------------------------------

    def _create_widgets(self):
        self.frame = ttk.Frame(self.parent, padding=(8, 4))
        self.frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(5, 0))

        # --- Project ---
        ttk.Label(self.frame, text="Project:").pack(side=tk.LEFT, padx=(0, 3))
        self.project_combo = ttk.Combobox(self.frame, state="readonly", width=18)
        self.project_combo.pack(side=tk.LEFT, padx=(0, 2))
        self.project_combo.bind("<<ComboboxSelected>>", self._on_project_selected)
        ttk.Button(self.frame, text="+", width=2,
                   command=self._on_new_project).pack(side=tk.LEFT, padx=(0, 12))

        # --- Session ---
        ttk.Label(self.frame, text="Session:").pack(side=tk.LEFT, padx=(0, 3))
        self.session_combo = ttk.Combobox(self.frame, state="disabled", width=18)
        self.session_combo.pack(side=tk.LEFT, padx=(0, 2))
        self.session_combo.bind("<<ComboboxSelected>>", self._on_session_selected)
        self.session_add_btn = ttk.Button(self.frame, text="+", width=2,
                                          command=self._on_new_session, state="disabled")
        self.session_add_btn.pack(side=tk.LEFT, padx=(0, 12))

        # --- Calibration status ---
        ttk.Label(self.frame, text="Calib:").pack(side=tk.LEFT, padx=(0, 3))
        self.calib_status_canvas = tk.Canvas(self.frame, width=14, height=14,
                                             highlightthickness=0)
        self.calib_status_canvas.pack(side=tk.LEFT, padx=(0, 3))
        self.calib_status_circle = self.calib_status_canvas.create_oval(
            1, 1, 13, 13, fill="gray", outline="darkgray", width=1)
        self.calib_label = ttk.Label(self.frame, text="\u2014", width=20, anchor=tk.W)
        self.calib_label.pack(side=tk.LEFT, padx=(0, 12))

        # --- Participant ---
        ttk.Label(self.frame, text="Participant:").pack(side=tk.LEFT, padx=(0, 3))
        self.participant_combo = ttk.Combobox(self.frame, state="disabled", width=12)
        self.participant_combo.pack(side=tk.LEFT, padx=(0, 2))
        self.participant_combo.bind("<<ComboboxSelected>>", self._on_participant_selected)
        self.participant_add_btn = ttk.Button(self.frame, text="+", width=2,
                                              command=self._on_new_participant, state="disabled")
        self.participant_add_btn.pack(side=tk.LEFT, padx=(0, 12))

        # --- Manage button ---
        ttk.Button(self.frame, text="Manage", command=self._on_manage_clicked).pack(
            side=tk.RIGHT)

    # -- Cascading enablement ------------------------------------------------

    def _update_enablement(self):
        """Enable/disable dropdowns based on current selection."""
        has_project = self._current_project is not None
        session_state = "readonly" if has_project else "disabled"
        participant_state = "readonly" if has_project else "disabled"
        btn_state = "normal" if has_project else "disabled"

        self.session_combo.config(state=session_state)
        self.session_add_btn.config(state=btn_state)
        self.participant_combo.config(state=participant_state)
        self.participant_add_btn.config(state=btn_state)

    # -- Refresh helpers -----------------------------------------------------

    def _refresh_projects(self):
        projects = self.pm.list_projects() if self.pm else []
        self.project_combo["values"] = projects

    def _refresh_sessions(self):
        self.session_combo.set("")
        if not self._current_project or not self.pm:
            self.session_combo["values"] = []
            return
        sessions = self.pm.list_sessions(self._current_project)
        self.session_combo["values"] = sessions

    def _refresh_participants(self):
        self.participant_combo.set("")
        if not self._current_project or not self.pm:
            self.participant_combo["values"] = []
            return
        try:
            subjects = self.pm.list_subjects(self._current_project)
            ids = [s.get("subject_id", "") for s in subjects if s.get("subject_id")]
            self.participant_combo["values"] = ids
        except Exception:
            self.participant_combo["values"] = []

    def _update_calibration_indicator(self):
        """Query ProjectManager for latest calibration and update indicator."""
        if not self._current_project or not self.pm:
            self.calib_label.config(text="\u2014")
            self.calib_status_canvas.itemconfig(
                self.calib_status_circle, fill="gray", outline="darkgray")
            return

        try:
            latest = self.pm.get_latest_calibration(self._current_project)
        except Exception:
            latest = None

        if not latest:
            self.calib_label.config(text="none")
            self.calib_status_canvas.itemconfig(
                self.calib_status_circle, fill="red", outline="darkred")
            return

        try:
            days = self.pm.get_calibration_age_days(self._current_project, latest)
        except Exception:
            days = None

        if days is not None and days < 1:
            color, outline = "green", "darkgreen"
            age_text = "today"
        elif days is not None:
            color, outline = "orange", "#b8860b"
            age_text = f"{days}d ago"
        else:
            color, outline = "orange", "#b8860b"
            age_text = ""

        # Strip timestamp suffix for display (e.g. "initial_2026-03-25-14-00" → "initial")
        display_name = latest.rsplit("_", 1)[0] if "_" in latest else latest
        label_text = f"{display_name} \u2014 {age_text}" if age_text else display_name
        self.calib_label.config(text=label_text)
        self.calib_status_canvas.itemconfig(
            self.calib_status_circle, fill=color, outline=outline)

    # -- Selection handlers --------------------------------------------------

    def _select_project(self, name):
        self._current_project = name
        self._current_session = None
        self._current_participant = None
        self.project_combo.set(name)
        self.app_config["last_project"] = name
        self.app_config["last_session"] = ""
        self.app_config["last_participant"] = ""
        self.save_config()
        self._update_enablement()
        self._refresh_sessions()
        self._refresh_participants()
        self._update_calibration_indicator()
        if self._on_selection_changed:
            self._on_selection_changed()

    def _on_project_selected(self, _event=None):
        name = self.project_combo.get()
        if name:
            self._select_project(name)

    def _select_session(self, name):
        self._current_session = name
        self.session_combo.set(name)
        self.app_config["last_session"] = name
        self.save_config()
        if self._on_selection_changed:
            self._on_selection_changed()

    def _on_session_selected(self, _event=None):
        name = self.session_combo.get()
        if name:
            self._select_session(name)

    def _select_participant(self, name):
        self._current_participant = name
        self.participant_combo.set(name)
        self.app_config["last_participant"] = name
        self.save_config()

    def _on_participant_selected(self, _event=None):
        name = self.participant_combo.get()
        if name:
            self._select_participant(name)

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

    def _on_new_participant(self):
        if not self._current_project:
            messagebox.showwarning("No Project", "Select a project first.",
                                   parent=self.frame)
            return
        self._show_new_subject_dialog()

    def _show_new_subject_dialog(self):
        dlg = tk.Toplevel(self.frame)
        dlg.title("New Participant")
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
            self._refresh_participants()
            self._select_participant(subject_id)

        btn_row = row_sex + 1
        btn_frame = ttk.Frame(dlg)
        btn_frame.grid(row=btn_row, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side=tk.LEFT, padx=8)

        # Center dialog on parent
        dlg.update_idletasks()
        dlg.geometry(f"+{self.frame.winfo_rootx() + 50}+{self.frame.winfo_rooty() + 50}")

    # -- Manage dialog -------------------------------------------------------

    def _on_manage_clicked(self):
        """Open management dialog with subject table."""
        if not self._current_project:
            messagebox.showwarning("No Project", "Select a project first.",
                                   parent=self.frame)
            return

        dlg = tk.Toplevel(self.frame)
        dlg.title(f"Manage \u2014 {self._current_project}")
        dlg.geometry("600x400")
        dlg.grab_set()

        # Subject table
        subj_frame = ttk.LabelFrame(dlg, text="Subjects")
        subj_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        columns = ("subject_id", "initials", "age", "sex", "height_m", "mass_kg")
        tree = ttk.Treeview(subj_frame, columns=columns, show="headings", height=10)
        for col in columns:
            heading = col.replace("_", " ").title()
            tree.heading(col, text=heading)
            width = 60 if col in ("age", "sex") else 100
            tree.column(col, width=width, anchor=tk.CENTER)
        tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 2))

        def refresh_table():
            tree.delete(*tree.get_children())
            try:
                subjects = self.pm.list_subjects(self._current_project)
            except Exception:
                return
            for s in subjects:
                tree.insert("", tk.END, values=(
                    s.get("subject_id", ""),
                    s.get("initials", ""),
                    s.get("age", ""),
                    s.get("sex", ""),
                    s.get("height_m", ""),
                    s.get("mass_kg", ""),
                ))

        refresh_table()

        btn_frame = ttk.Frame(subj_frame)
        btn_frame.pack(padx=8, pady=(2, 6), anchor=tk.W)

        def add_subject():
            self._show_new_subject_dialog()
            refresh_table()

        ttk.Button(btn_frame, text="New Subject", command=add_subject).pack(side=tk.LEFT)

        # Close button
        ttk.Button(dlg, text="Close", command=dlg.destroy).pack(pady=(0, 10))

        dlg.update_idletasks()
        dlg.geometry(f"+{self.frame.winfo_rootx() + 50}+{self.frame.winfo_rooty() + 50}")

    # -- Restore last selection ----------------------------------------------

    def _restore_last_selection(self):
        self._refresh_projects()
        projects = list(self.project_combo["values"])

        last_project = self.app_config.get("last_project", "")
        if last_project and last_project in projects:
            self._current_project = last_project
            self.project_combo.set(last_project)
            self._update_enablement()
            self._refresh_sessions()
            self._refresh_participants()
            self._update_calibration_indicator()

            sessions = list(self.session_combo["values"])
            last_session = self.app_config.get("last_session", "")
            if last_session and last_session in sessions:
                self._current_session = last_session
                self.session_combo.set(last_session)

            participants = list(self.participant_combo["values"])
            last_participant = self.app_config.get("last_participant", "")
            if last_participant and last_participant in participants:
                self._current_participant = last_participant
                self.participant_combo.set(last_participant)
