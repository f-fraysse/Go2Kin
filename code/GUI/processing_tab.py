"""
Processing tab for running the Pose2Sim pipeline on recorded trials.

Uses the shared SessionTrialsList component for trial selection and displays
pipeline step progress with colored indicators.
"""

import logging
import threading
import tkinter as tk
from tkinter import ttk


logger = logging.getLogger(__name__)

# Pipeline steps (must match run_pose2sim_pipeline step order)
_PIPELINE_STEPS = [
    "Calibration",
    "Pose Estimation",
    "Triangulation",
    "Filtering",
    "Kinematics",
]

# Pipeline step status emoji
_ICON_PENDING = "\u26AB"       # ⚫
_ICON_PROCESSING = "\U0001F504"  # 🔄
_ICON_COMPLETE = "\U0001F7E2"   # 🟢
_ICON_FAILED = "\U0001F534"     # 🔴


class ProcessingTab:
    """Pose2Sim processing tab with shared trial list and pipeline progress."""

    def __init__(self, notebook, project_manager, get_current_project,
                 get_current_session):
        self.notebook = notebook
        self.pm = project_manager
        self.get_current_project = get_current_project
        self.get_current_session = get_current_session
        self.root = notebook.winfo_toplevel()

        # State
        self._processing = False
        self._stop_event = threading.Event()

        # Build UI
        self.frame = ttk.Frame(notebook)
        notebook.add(self.frame, text="Processing")
        self._build_ui()

    def _build_ui(self):
        """Create the tab layout."""
        from GUI.components.session_trials_list import SessionTrialsList

        # --- Session Trials List (top, expandable) ---
        self.trials_list = SessionTrialsList(
            self.frame, self.pm,
            self.get_current_project, self.get_current_session,
        )
        self.trials_list.frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(10, 5))

        # --- Pipeline Progress ---
        progress_frame = ttk.LabelFrame(self.frame, text="Pipeline Progress", padding=10)
        progress_frame.pack(fill=tk.X, padx=20, pady=5)

        # Context label (e.g. "Processing trial_003 (2/5)")
        self.context_var = tk.StringVar(value="Ready")
        self.context_label = ttk.Label(progress_frame, textvariable=self.context_var,
                                       font=("Arial", 10))
        self.context_label.pack(anchor=tk.W, pady=(0, 5))

        # Step indicators — horizontal row of circles + labels
        steps_frame = ttk.Frame(progress_frame)
        steps_frame.pack(fill=tk.X)

        self._step_circles = []
        for step_name in _PIPELINE_STEPS:
            circle = tk.Label(steps_frame, text=_ICON_PENDING, font=("Segoe UI Emoji", 14))
            circle.pack(side=tk.LEFT)
            label = ttk.Label(steps_frame, text=step_name, font=("Arial", 9))
            label.pack(side=tk.LEFT, padx=(2, 12))
            self._step_circles.append(circle)

        # --- Process Button ---
        control_frame = ttk.Frame(self.frame)
        control_frame.pack(pady=15)

        self.process_btn = tk.Button(
            control_frame, text="PROCESS SELECTED",
            font=("Arial", 18, "bold"),
            bg="#4CAF50", fg="white",
            activebackground="#388E3C", activeforeground="white",
            width=20, height=2,
            command=self._toggle_process,
            relief="raised", bd=3,
        )
        self.process_btn.pack()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def refresh(self):
        """Refresh the trials list."""
        self.trials_list.refresh()

    # -------------------------------------------------------------------------
    # Pipeline progress helpers
    # -------------------------------------------------------------------------

    def _reset_steps(self):
        """Reset all step circles to ⚫ Pending."""
        for circle in self._step_circles:
            circle.config(text=_ICON_PENDING)

    def _set_step_state(self, index, icon):
        """Set a step circle emoji (called via root.after from worker)."""
        if 0 <= index < len(self._step_circles):
            self._step_circles[index].config(text=icon)

    def _set_context(self, text):
        """Update context label (called via root.after from worker)."""
        self.context_var.set(text)

    # -------------------------------------------------------------------------
    # Processing controls
    # -------------------------------------------------------------------------

    def _toggle_process(self):
        """Toggle between start processing and cancel."""
        if self._processing:
            self._on_cancel()
        else:
            self._on_process()

    def _on_process(self):
        """Start processing selected trials."""
        selected = self.trials_list.get_checked_trials()
        if not selected:
            print("No trials selected")
            return

        project = self.get_current_project()
        session = self.get_current_session()
        if not project or not session:
            print("No project/session selected")
            return

        self._processing = True
        self._stop_event.clear()
        self._reset_steps()
        self.process_btn.config(text="CANCEL", bg="#f44336",
                                activebackground="#d32f2f")

        thread = threading.Thread(
            target=self._processing_worker,
            args=(project, session, selected),
            daemon=True,
        )
        thread.start()

    def _on_cancel(self):
        """Request pipeline stop after current step."""
        self._stop_event.set()
        print("Cancel requested — will stop after current step completes")

    def _processing_worker(self, project, session, trial_names):
        """Background thread: process selected trials sequentially."""
        from pose2sim_builder import build_pose2sim_project

        total = len(trial_names)
        success_count = 0

        print(f"Starting processing of {total} trial(s)")

        for i, trial_name in enumerate(trial_names, 1):
            if self._stop_event.is_set():
                print("Cancelled by user")
                break

            self.root.after(0, self._reset_steps)
            self.root.after(0, self._set_context,
                            f"Processing {trial_name} ({i}/{total})")

            print(f"\n{'='*50}")
            print(f"[{i}/{total}] Setting up {session}/{trial_name}...")

            # Build
            try:
                processed_path = build_pose2sim_project(
                    self.pm, project, session, trial_name,
                )
            except (ValueError, FileNotFoundError) as e:
                print(f"SKIPPED {trial_name}: {e}")
                continue
            except Exception as e:
                print(f"SKIPPED {trial_name}: unexpected error: {e}")
                logger.exception(f"Build failed for {trial_name}")
                continue

            # Run pipeline with step-by-step progress
            print(f"Processing {session}/{trial_name}...")
            ok = self._run_pipeline_with_progress(processed_path)

            if ok:
                success_count += 1
                try:
                    self.pm.update_trial(project, session, trial_name, processed=True)
                except Exception as e:
                    print(f"Warning: could not update trial.json: {e}")
                print(f"Completed {trial_name} successfully")
            else:
                print(f"Failed processing {trial_name}")

        # Summary
        summary = f"Complete: {success_count}/{total} trials successful"
        print(f"\n{'='*50}")
        print(f"Processing {summary.lower()}")

        # Re-enable UI on main thread
        def finish():
            self._processing = False
            self.process_btn.config(text="PROCESS SELECTED", bg="#4CAF50",
                                    activebackground="#388E3C")
            self._set_context(summary)
            self.trials_list.refresh()

        self.root.after(0, finish)

    def _run_pipeline_with_progress(self, processed_path):
        """Run Pose2Sim pipeline, updating step circles after each step.

        Returns True on success, False on failure or cancel.
        """
        import os
        import sys

        original_cwd = os.getcwd()

        try:
            os.chdir(str(processed_path))

            # Import Pose2Sim (submodule at code/pose2sim/)
            from pathlib import Path
            pose2sim_path = str(Path(__file__).resolve().parent.parent / "pose2sim")
            if pose2sim_path not in sys.path:
                sys.path.insert(0, pose2sim_path)

            from Pose2Sim import Pose2Sim as P2S

            steps = [
                ("Calibration", P2S.calibration),
                ("Pose Estimation", P2S.poseEstimation),
                ("Triangulation", P2S.triangulation),
                ("Filtering", P2S.filtering),
                ("Kinematics", P2S.kinematics),
            ]

            for step_idx, (step_name, step_fn) in enumerate(steps):
                if self._stop_event.is_set():
                    print(f"Pipeline stopped before {step_name}")
                    return False

                # Mark current step as 🔄 Processing
                self.root.after(0, self._set_step_state, step_idx, _ICON_PROCESSING)

                print(f"--- Starting {step_name} ---")
                try:
                    step_fn()
                except Exception as e:
                    print(f"ERROR in {step_name}: {e}")
                    logger.exception(f"Pose2Sim {step_name} failed")
                    # Mark failed step as 🔴 Failed
                    self.root.after(0, self._set_step_state, step_idx, _ICON_FAILED)
                    return False

                # Mark completed step as 🟢 Complete
                self.root.after(0, self._set_step_state, step_idx, _ICON_COMPLETE)

            print("Pipeline completed successfully")
            return True

        except Exception as e:
            print(f"Pipeline error: {e}")
            logger.exception("Pose2Sim pipeline failed")
            return False

        finally:
            os.chdir(original_cwd)
