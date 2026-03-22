"""
Processing tab for running the Pose2Sim pipeline on recorded trials.

Displays a tree of sessions/trials with checkboxes for selection,
a log output area, and controls to run/stop the pipeline.
"""

import logging
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime

logger = logging.getLogger(__name__)

# Unicode checkbox characters
_UNCHECKED = "\u2610"  # ☐
_CHECKED = "\u2611"    # ☑


class ProcessingTab:
    """Pose2Sim processing tab with trial selection, log output, and pipeline controls."""

    def __init__(self, notebook, project_manager, get_current_project,
                 get_current_session):
        self.notebook = notebook
        self.pm = project_manager
        self.get_current_project = get_current_project
        self.get_current_session = get_current_session
        self.root = notebook.winfo_toplevel()

        # State
        self._checked = set()         # Set of treeview item IDs that are checked
        self._trial_map = {}          # iid -> (session, trial_name)
        self._processing = False
        self._stop_event = threading.Event()
        self._progress_marks = {}     # key -> tk.Text mark name (for tqdm bars)

        # Build UI
        self.frame = ttk.Frame(notebook)
        notebook.add(self.frame, text="Processing")
        self._build_ui()

    def _build_ui(self):
        """Create the tab layout."""
        # Title
        title = ttk.Label(self.frame, text="Pose2Sim Processing",
                          font=("Arial", 16, "bold"))
        title.pack(pady=(15, 10))

        # --- Trial Selection ---
        select_frame = ttk.LabelFrame(self.frame, text="Select Trials", padding=10)
        select_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        # Button row
        btn_row = ttk.Frame(select_frame)
        btn_row.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(btn_row, text="Select All", command=self._select_all).pack(
            side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="Deselect All", command=self._deselect_all).pack(
            side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="Refresh", command=self.refresh_tree).pack(
            side=tk.LEFT)

        # Treeview
        tree_container = ttk.Frame(select_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(
            tree_container, height=8, show="tree headings",
            columns=("subject", "calibration", "status"),
        )
        self.tree.heading("#0", text="Session / Trial")
        self.tree.heading("subject", text="Subject")
        self.tree.heading("calibration", text="Calibration")
        self.tree.heading("status", text="Status")

        self.tree.column("#0", width=250, minwidth=150)
        self.tree.column("subject", width=100, minwidth=80)
        self.tree.column("calibration", width=150, minwidth=100)
        self.tree.column("status", width=100, minwidth=80)

        tree_scroll = ttk.Scrollbar(tree_container, orient="vertical",
                                    command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Tag for checked items
        self.tree.tag_configure("checked", background="#d4edda")
        self.tree.tag_configure("session", font=("Arial", 10, "bold"))

        # Click to toggle
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)

        # --- Log Output ---
        log_frame = ttk.LabelFrame(self.frame, text="Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        log_btn_row = ttk.Frame(log_frame)
        log_btn_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(log_btn_row, text="Clear Log", command=self._clear_log).pack(
            side=tk.LEFT)

        text_container = ttk.Frame(log_frame)
        text_container.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(text_container, height=10, state="disabled",
                                font=("Consolas", 9), wrap=tk.WORD)
        log_scroll = ttk.Scrollbar(text_container, orient="vertical",
                                   command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Controls ---
        control_frame = ttk.Frame(self.frame)
        control_frame.pack(fill=tk.X, padx=20, pady=(5, 15))

        self.process_btn = ttk.Button(control_frame, text="Process Selected",
                                      command=self._on_process)
        self.process_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_btn = ttk.Button(control_frame, text="Stop",
                                   command=self._on_stop, state="disabled")
        self.stop_btn.pack(side=tk.LEFT)

    # -------------------------------------------------------------------------
    # Tree management
    # -------------------------------------------------------------------------

    def refresh_tree(self):
        """Rebuild the treeview from the current project's data."""
        # Clear existing
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._checked.clear()
        self._trial_map.clear()

        project = self.get_current_project()
        if not project:
            return

        try:
            tree_data = self.pm.get_project_tree(project)
        except Exception:
            return

        for session_name, session_info in tree_data.get("sessions", {}).items():
            session_id = self.tree.insert(
                "", tk.END, text=session_name, open=True,
                tags=("session",)
            )

            for trial_name in session_info.get("trials", []):
                # Load trial metadata
                try:
                    trial = self.pm.get_trial(project, session_name, trial_name)
                except Exception:
                    trial = {}

                subject = trial.get("subject_id", "")
                calib = trial.get("calibration_file", "")
                synced = trial.get("synced", False)
                processed = trial.get("processed", False)

                if processed:
                    status = "Processed"
                elif synced:
                    status = "Ready"
                else:
                    status = "Not synced"

                display = f"{_UNCHECKED} {trial_name}"
                iid = self.tree.insert(
                    session_id, tk.END, text=display,
                    values=(subject, calib, status),
                )
                self._trial_map[iid] = (session_name, trial_name)

    def _on_tree_click(self, event):
        """Toggle checkbox on trial click."""
        iid = self.tree.identify_row(event.y)
        if not iid or iid not in self._trial_map:
            return  # Clicked on session header or empty space

        if iid in self._checked:
            self._uncheck(iid)
        else:
            self._check(iid)

    def _check(self, iid):
        """Mark a trial as checked."""
        self._checked.add(iid)
        session, trial_name = self._trial_map[iid]
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

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------

    def log(self, message):
        """Thread-safe log message to the text widget."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"

        def update_text():
            self.log_text.config(state="normal")
            self.log_text.insert(tk.END, log_message)
            self.log_text.see(tk.END)
            self.log_text.config(state="disabled")

        self.root.after(0, update_text)

    def log_progress(self, key, message):
        """Thread-safe progress update — each key gets its own updating line."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        # Sanitize key for use as a tk.Text mark name
        mark_name = f"prog_{hash(key) & 0xFFFFFFFF}"

        def update_text():
            self.log_text.config(state="normal")
            if mark_name in self._progress_marks:
                # Replace existing progress line at mark position
                try:
                    mark_pos = self.log_text.index(mark_name)
                    line_end = f"{mark_pos} lineend +1c"
                    self.log_text.delete(mark_pos, line_end)
                    self.log_text.insert(mark_name, log_message)
                except tk.TclError:
                    # Mark was lost — fall back to append
                    self.log_text.insert(tk.END, log_message)
            else:
                # Append new progress line and set a mark at its start
                insert_pos = self.log_text.index("end -1c")
                self.log_text.insert(tk.END, log_message)
                self.log_text.mark_set(mark_name, insert_pos)
                self.log_text.mark_gravity(mark_name, "left")
                self._progress_marks[mark_name] = True
            self.log_text.see(tk.END)
            self.log_text.config(state="disabled")

        self.root.after(0, update_text)

    def _clear_log(self):
        """Clear the log text widget."""
        self._progress_marks.clear()
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")

    # -------------------------------------------------------------------------
    # Processing controls
    # -------------------------------------------------------------------------

    def _on_process(self):
        """Start processing selected trials."""
        if self._processing:
            return

        selected = [(iid, *self._trial_map[iid]) for iid in self._checked
                     if iid in self._trial_map]
        if not selected:
            self.log("No trials selected")
            return

        project = self.get_current_project()
        if not project:
            self.log("No project selected")
            return

        self._processing = True
        self._stop_event.clear()
        self.process_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        thread = threading.Thread(
            target=self._processing_worker,
            args=(project, selected),
            daemon=True,
        )
        thread.start()

    def _on_stop(self):
        """Request pipeline stop after current step."""
        self._stop_event.set()
        self.log("Stop requested — will stop after current step completes")

    def _processing_worker(self, project, selected_trials):
        """Background thread: process selected trials sequentially."""
        from pose2sim_builder import build_pose2sim_project, run_pose2sim_pipeline

        total = len(selected_trials)
        success_count = 0

        self.log(f"Starting processing of {total} trial(s)")

        for i, (iid, session, trial_name) in enumerate(selected_trials, 1):
            if self._stop_event.is_set():
                self.log("Stopped by user")
                break

            self.log(f"\n{'='*50}")
            self.log(f"[{i}/{total}] Setting up {session}/{trial_name}...")

            # Build
            try:
                processed_path = build_pose2sim_project(
                    self.pm, project, session, trial_name,
                    log_callback=self.log,
                )
            except (ValueError, FileNotFoundError) as e:
                self.log(f"SKIPPED {trial_name}: {e}")
                continue
            except Exception as e:
                self.log(f"SKIPPED {trial_name}: unexpected error: {e}")
                logger.exception(f"Build failed for {trial_name}")
                continue

            # Run pipeline
            self._progress_marks.clear()
            self.log(f"Processing {session}/{trial_name}...")
            ok = run_pose2sim_pipeline(
                processed_path,
                log_callback=self.log,
                progress_callback=self.log_progress,
                stop_event=self._stop_event,
            )

            if ok:
                success_count += 1
                try:
                    self.pm.update_trial(project, session, trial_name, processed=True)
                except Exception as e:
                    self.log(f"Warning: could not update trial.json: {e}")
                self.log(f"Completed {trial_name} successfully")
            else:
                self.log(f"Failed processing {trial_name}")

        # Summary
        self.log(f"\n{'='*50}")
        self.log(f"Processing complete: {success_count}/{total} trials successful")

        # Re-enable UI on main thread
        def finish():
            self._processing = False
            self.process_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.refresh_tree()

        self.root.after(0, finish)
