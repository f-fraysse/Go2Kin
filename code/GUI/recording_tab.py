#!/usr/bin/env python3
"""
Go2Kin - Recording Tab
Multi-camera recording with trial management
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import concurrent.futures
from pathlib import Path
import sounddevice as sd
import numpy as np


class RecordingTab:
    """Recording tab — multi-camera recording with trial setup and sync."""

    def __init__(self, notebook, config, cameras, camera_status, camera_serials,
                 project_manager, app_config,
                 get_current_project, get_current_session,
                 save_camera_settings, save_app_config,
                 get_calibration_tab,
                 rec_delay_enabled, rec_delay_seconds, rec_delay_countdown_label,
                 sync_sound_enabled):
        self.notebook = notebook
        self.root = notebook.winfo_toplevel()
        self.config = config
        self.cameras = cameras
        self.camera_status = camera_status
        self.camera_serials = camera_serials
        self.project_manager = project_manager
        self.app_config = app_config
        self.get_current_project = get_current_project
        self.get_current_session = get_current_session
        self.save_camera_settings = save_camera_settings
        self.save_app_config = save_app_config
        self._get_calibration_tab = get_calibration_tab

        # Bottom bar widget references (owned by main_window, shared)
        self.rec_delay_enabled = rec_delay_enabled
        self.rec_delay_seconds = rec_delay_seconds
        self.rec_delay_countdown_label = rec_delay_countdown_label
        self.sync_sound_enabled = sync_sound_enabled

        # Recording state
        self.recording = False
        self.recording_thread = None
        self.start_time = None
        self._current_trial_info = None
        self._last_trial_video_dir = None
        self._bar_timer_running = False
        self._bar_timer_start = None

        # Sync sound (generated on the fly — HDMI primer + two claps)
        self._sync_sound_sr = 44100
        self._sync_sound_data = self._generate_sync_sound()

        # Build UI
        self.frame = ttk.Frame(notebook)
        notebook.add(self.frame, text="Recording")
        self._create_widgets()

    def _create_widgets(self):
        """Create the recording tab UI"""
        # Title
        title_label = ttk.Label(self.frame, text="Multi-Camera Recording",
                               font=("Arial", 16, "bold"))
        title_label.pack(pady=(15, 10))

        # --- Trial Setup section ---
        setup_frame = ttk.LabelFrame(self.frame, text="Trial Setup", padding=10)
        setup_frame.pack(fill=tk.X, padx=20, pady=(0, 5))

        # Participant row
        part_frame = ttk.Frame(setup_frame)
        part_frame.pack(fill=tk.X, pady=3)
        ttk.Label(part_frame, text="Participant:", width=12).pack(side=tk.LEFT)
        self.participant_var = tk.StringVar()
        self.participant_combo = ttk.Combobox(part_frame, textvariable=self.participant_var,
                                              state="readonly", width=25)
        self.participant_combo.pack(side=tk.LEFT, padx=(5, 8))
        self.new_participant_btn = ttk.Button(part_frame, text="New Participant",
                                              command=self._on_new_participant)
        self.new_participant_btn.pack(side=tk.LEFT)

        # Calibration row
        cal_frame = ttk.Frame(setup_frame)
        cal_frame.pack(fill=tk.X, pady=3)
        ttk.Label(cal_frame, text="Calibration:", width=12).pack(side=tk.LEFT)
        self.calibration_var = tk.StringVar()
        self.calibration_combo = ttk.Combobox(cal_frame, textvariable=self.calibration_var,
                                              state="readonly", width=25)
        self.calibration_combo.pack(side=tk.LEFT, padx=(5, 8))
        self.calibration_combo.bind("<<ComboboxSelected>>", self._on_calibration_selected)
        self.calibration_age_label = ttk.Label(cal_frame, text="", foreground="gray")
        self.calibration_age_label.pack(side=tk.LEFT, padx=5)

        # Trial name row
        trial_frame = ttk.Frame(setup_frame)
        trial_frame.pack(fill=tk.X, pady=3)
        ttk.Label(trial_frame, text="Trial Name:", width=12).pack(side=tk.LEFT)
        self.trial_name_var = tk.StringVar(value=self.config["recording"]["last_trial_name"])
        self.trial_name_entry = ttk.Entry(trial_frame, textvariable=self.trial_name_var, width=28)
        self.trial_name_entry.pack(side=tk.LEFT, padx=(5, 0))

        # --- Camera Selection ---
        selection_frame = ttk.LabelFrame(self.frame, text="Camera Selection", padding=10)
        selection_frame.pack(fill=tk.X, padx=20, pady=5)

        self.camera_selection_vars = {}
        self.camera_selection_checkboxes = {}
        for i in range(1, 5):
            var = tk.BooleanVar(value=False)
            checkbox = ttk.Checkbutton(selection_frame, text=f"GoPro {i}", variable=var, state="disabled")
            checkbox.pack(side=tk.LEFT, padx=15)
            self.camera_selection_vars[i] = var
            self.camera_selection_checkboxes[i] = checkbox

        # --- Recording Controls ---
        control_frame = ttk.Frame(self.frame)
        control_frame.pack(pady=15)

        self.record_toggle_btn = ttk.Button(control_frame, text="START RECORDING",
                                            command=self.toggle_recording)
        self.record_toggle_btn.pack(side=tk.LEFT, padx=(0, 15))

        self.timer_var = tk.StringVar(value="Timer: 00:00:00")
        timer_label = ttk.Label(control_frame, textvariable=self.timer_var,
                               font=("Arial", 14, "bold"))
        timer_label.pack(side=tk.LEFT, padx=(15, 0))

        # --- Session/Trial Tree View ---
        tree_frame = ttk.LabelFrame(self.frame, text="Session Trials", padding=10)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        self.trial_tree = ttk.Treeview(tree_frame, height=5, show="tree")
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.trial_tree.yview)
        self.trial_tree.configure(yscrollcommand=tree_scroll.set)
        self.trial_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Open Trial Folder button ---
        self.open_folder_btn = ttk.Button(self.frame, text="Open Trial Folder",
                                        command=self.open_trial_folder, state="disabled")
        self.open_folder_btn.pack(pady=8)

    # -- Recording tab helpers ------------------------------------------------

    def refresh_recording_dropdowns(self):
        """Populate participant, calibration dropdowns and trial tree from ProjectManager."""
        project = self.get_current_project()

        if not project:
            self.participant_combo["values"] = []
            self.participant_var.set("")
            self.calibration_combo["values"] = []
            self.calibration_var.set("")
            self.calibration_age_label.config(text="Select a project first")
            self._clear_trial_tree()
            return

        # Participant dropdown
        try:
            subjects = self.project_manager.list_subjects(project)
            subject_ids = [s["subject_id"] for s in subjects]
        except Exception:
            subject_ids = []
        prev = self.participant_var.get()
        self.participant_combo["values"] = subject_ids
        if prev in subject_ids:
            self.participant_var.set(prev)
        elif subject_ids:
            self.participant_var.set(subject_ids[0])
        else:
            self.participant_var.set("")

        # Calibration dropdown
        try:
            calibrations = self.project_manager.list_calibrations(project)
        except Exception:
            calibrations = []
        self.calibration_combo["values"] = calibrations
        if calibrations:
            latest = self.project_manager.get_latest_calibration(project)
            self.calibration_var.set(latest if latest else calibrations[0])
            self._update_calibration_age_label()
        else:
            self.calibration_var.set("")
            self.calibration_age_label.config(text="No calibration found", foreground="orange")

        # Trial tree
        self.refresh_trial_tree()

    def _update_calibration_age_label(self):
        """Update the calibration age display."""
        project = self.get_current_project()
        name = self.calibration_var.get()
        if project and name:
            try:
                days = self.project_manager.get_calibration_age_days(project, name)
                self.calibration_age_label.config(
                    text=f"{days} day{'s' if days != 1 else ''} old",
                    foreground="gray" if days < 14 else "orange"
                )
            except Exception:
                self.calibration_age_label.config(text="", foreground="gray")
        else:
            self.calibration_age_label.config(text="", foreground="gray")

    def _on_calibration_selected(self, event=None):
        """Handle calibration dropdown selection."""
        self._update_calibration_age_label()

    def refresh_trial_tree(self):
        """Refresh the session/trial tree view from ProjectManager."""
        self._clear_trial_tree()
        project = self.get_current_project()
        if not project:
            return
        try:
            tree_data = self.project_manager.get_project_tree(project)
        except Exception:
            return
        for session_name, session_info in tree_data.get("sessions", {}).items():
            session_id = self.trial_tree.insert("", tk.END, text=session_name, open=True)
            for trial_name in session_info.get("trials", []):
                self.trial_tree.insert(session_id, tk.END, text=trial_name)

    def _clear_trial_tree(self):
        """Remove all items from the trial tree view."""
        for item in self.trial_tree.get_children():
            self.trial_tree.delete(item)

    def _on_new_participant(self):
        """Show dialog to create a new participant/subject."""
        project = self.get_current_project()
        if not project:
            messagebox.showwarning("No Project", "Select a project first.")
            return

        dlg = tk.Toplevel(self.root)
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
                self.project_manager.create_subject(
                    project, subject_id, initials, age, sex, height_m, mass_kg
                )
            except ValueError as e:
                messagebox.showerror("Error", str(e), parent=dlg)
                return

            dlg.destroy()
            self.refresh_recording_dropdowns()
            self.participant_var.set(subject_id)

        btn_row = row_sex + 1
        btn_frame = ttk.Frame(dlg)
        btn_frame.grid(row=btn_row, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side=tk.LEFT, padx=8)

        dlg.update_idletasks()
        dlg.geometry(f"+{self.root.winfo_rootx() + 100}+{self.root.winfo_rooty() + 100}")

    def open_trial_folder(self):
        """Open the most recent trial's video folder in file explorer."""
        import subprocess
        import os

        folder = self._last_trial_video_dir
        if folder and os.path.exists(str(folder)):
            subprocess.Popen(f'explorer "{folder}"')
        else:
            messagebox.showinfo("No Trial", "No trial folder available yet.")

    # -- Recording logic ------------------------------------------------------

    def toggle_recording(self):
        """Toggle recording start/stop."""
        if not self.recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        """Validate and start multi-camera recording."""
        # Validate project and session
        project = self.get_current_project()
        session = self.get_current_session()
        if not project:
            messagebox.showerror("Error", "No project selected. Go to the Project tab first.")
            return
        if not session:
            messagebox.showerror("Error", "No session selected. Go to the Project tab first.")
            return

        trial_name = self.trial_name_var.get().strip()
        if not trial_name:
            messagebox.showerror("Error", "Trial name cannot be empty.")
            return

        # Get selected & connected cameras
        selected_cameras = [i for i in range(1, 5) if self.camera_selection_vars[i].get()]
        available_cameras = [i for i in selected_cameras
                             if i in self.cameras and self.camera_status.get(i, False)]
        if not available_cameras:
            messagebox.showerror("Error", "No cameras are connected and selected for recording.")
            return

        # Participant and calibration (optional)
        subject_id = self.participant_var.get() or ""
        calibration_name = self.calibration_var.get() or "none"
        cameras_used = [self.camera_serials.get(i, f"cam{i}") for i in available_cameras]

        # Create trial via ProjectManager
        try:
            self.project_manager.create_trial(
                project, session, trial_name,
                subject_id=subject_id,
                calibration_file=calibration_name,
                cameras_used=cameras_used,
            )
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return

        video_dir = self.project_manager.get_trial_video_path(project, session, trial_name)
        video_dir.mkdir(parents=True, exist_ok=True)

        self._current_trial_info = {
            "project": project,
            "session": session,
            "trial_name": trial_name,
            "video_dir": video_dir,
        }
        self._last_trial_video_dir = video_dir

        # Save settings and start
        self.save_camera_settings()
        self.recording = True
        self.recording_thread = threading.Thread(
            target=self.recording_worker, args=(available_cameras,), daemon=True
        )
        self.recording_thread.start()

        # Update UI
        self.record_toggle_btn.config(text="STOP RECORDING")
        self.trial_name_entry.config(state="disabled")
        self.participant_combo.config(state="disabled")
        self.calibration_combo.config(state="disabled")
        self.new_participant_btn.config(state="disabled")

    def _stop_recording(self):
        """Signal the recording worker to stop."""
        self.recording = False
        self._stop_bar_timer()
        self.record_toggle_btn.config(text="Stopping...", state="disabled")
        print("Stopping recording...")

    def recording_worker(self, camera_list):
        """Background worker for recording process."""
        info = self._current_trial_info
        video_dir = info["video_dir"]
        trial_name = info["trial_name"]

        try:
            print(f"Starting recording on cameras: {camera_list}")
            print(f"Trial directory: {video_dir}")

            # Run recording delay countdown if enabled
            self._run_rec_delay()

            # Start recording on all cameras
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = []
                for camera_num in camera_list:
                    camera = self.cameras[camera_num]
                    future = executor.submit(self.start_camera_recording, camera_num, camera)
                    futures.append((camera_num, future))

                for camera_num, future in futures:
                    try:
                        future.result(timeout=15)
                        print(f"  GoPro {camera_num} recording started")
                    except Exception as e:
                        print(f"  Failed to start GoPro {camera_num}: {e}")

            # Start timers after all cameras confirmed
            self.root.after(0, self.start_timer)
            self.root.after(0, self._start_bar_timer)

            # Play sync sound (1s delay + two claps) if enabled
            self._play_sync_sound()

            # Wait for stop signal
            while self.recording:
                time.sleep(0.5)

            # Stop recording and download files
            print("Stopping cameras and downloading files...")

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = []
                for camera_num in camera_list:
                    if camera_num in self.cameras:
                        camera = self.cameras[camera_num]
                        future = executor.submit(
                            self.stop_and_download, camera_num, camera, video_dir, trial_name
                        )
                        futures.append((camera_num, future))

                for camera_num, future in futures:
                    try:
                        future.result(timeout=300)
                        print(f"  GoPro {camera_num} file downloaded")
                    except Exception as e:
                        print(f"  Error downloading GoPro {camera_num}: {e}")

            print("Recording complete. Starting audio synchronisation...")

            # Auto-sync
            self._auto_sync(info)

        except Exception as e:
            print(f"Recording error: {e}")

        finally:
            self.root.after(0, self.reset_recording_ui)

    def _auto_sync(self, trial_info):
        """Automatically synchronise downloaded video files after recording."""
        from audio_sync import (check_ffmpeg, check_audio_track, compute_sync_offsets,
                                trim_and_sync_videos, create_stitched_preview,
                                AudioSyncError)

        project = trial_info["project"]
        session = trial_info["session"]
        trial_name = trial_info["trial_name"]
        video_dir = trial_info["video_dir"]

        mp4_files = sorted([
            f for f in video_dir.iterdir()
            if f.suffix.lower() == ".mp4" and f.is_file()
        ])

        if len(mp4_files) < 2:
            print(f"Only {len(mp4_files)} video file(s) — skipping sync.")
            return

        try:
            # Check ffmpeg
            if not check_ffmpeg():
                print("ffmpeg not found — skipping sync. Install with: conda install -c conda-forge ffmpeg")
                return

            video_paths = [str(f) for f in mp4_files]

            # Verify audio tracks
            for vp in video_paths:
                name = Path(vp).name
                if not check_audio_track(vp):
                    raise AudioSyncError(f"No audio track in: {name}")
                print(f"  Audio confirmed: {name}")

            # Build camera positions for speed-of-sound compensation (if calibration loaded)
            cam_positions = None
            sound_pos = None
            calibration_tab = self._get_calibration_tab()
            if calibration_tab is not None:
                cam_positions, sound_pos = calibration_tab._get_sync_compensation_data(video_paths)

            # Compute sync offsets (onset-based dual-clap detection)
            print("Analysing audio for onset-based sync...")
            offsets = compute_sync_offsets(
                video_paths,
                output_dir=str(video_dir),
                progress_callback=lambda msg: print(f"  {msg}"),
                camera_positions=cam_positions,
                sound_source_position=sound_pos,
            )

            # Check for warnings
            for path, info in offsets.items():
                if info.get("status") == "WARN":
                    name = Path(path).name
                    print(
                        f"  WARNING: Inconsistent clap offsets for {name}. "
                        f"Consider re-recording with clearer claps.")

            # Trim and sync videos
            print("Trimming videos (stream copy, no re-encoding)...")
            output_files = trim_and_sync_videos(
                video_paths, offsets, str(video_dir),
                progress_callback=lambda msg: print(f"  {msg}")
            )

            # Create stitched preview
            synced_dir = str(self.project_manager.get_trial_synced_path(project, session, trial_name))
            print("Creating 2x2 stitched preview...")
            create_stitched_preview(
                synced_dir,
                progress_callback=lambda msg: print(f"  {msg}")
            )

            # Update trial.json
            self.project_manager.update_trial(project, session, trial_name, synced=True)
            print(
                f"Synchronisation complete! "
                f"{len(output_files)} synced files + stitched preview in synced/ folder")

        except Exception as e:
            print(f"Sync error: {e}")
            try:
                self.project_manager.update_trial(project, session, trial_name, synced=False)
            except Exception:
                pass

    # -- Recording delay / sync sound / bar timer -----------------------------

    def _run_rec_delay(self):
        """Run recording delay countdown if enabled. Called from background threads."""
        if not self.rec_delay_enabled.get():
            return
        try:
            delay = int(self.rec_delay_seconds.get())
        except (ValueError, TypeError):
            return
        if delay <= 0:
            return
        for remaining in range(delay, 0, -1):
            self.root.after(0, lambda r=remaining:
                            self.rec_delay_countdown_label.config(text=str(r)))
            time.sleep(1)
        self.root.after(0, lambda: self.rec_delay_countdown_label.config(text=""))

    def _generate_sync_sound(self):
        """Generate sync sound: 1.5s HDMI primer + two 10ms clap impulses."""
        sr = self._sync_sound_sr
        # 1.5s near-silent primer to wake HDMI audio devices
        primer = (np.random.randn(int(sr * 1.5)) * 0.001).astype(np.float32)
        # 10ms 1kHz sine burst
        t = np.arange(int(sr * 0.01)) / sr
        impulse = (np.sin(2 * np.pi * 1000 * t) * 0.98).astype(np.float32)
        # Gaps
        gap = np.zeros(int(sr * 0.5), dtype=np.float32)
        tail = np.zeros(int(sr * 0.5), dtype=np.float32)
        return np.concatenate([primer, impulse, gap, impulse, tail])

    def _play_sync_sound(self):
        """Play sync sound (primer + two claps). Call from background thread."""
        if not self.sync_sound_enabled.get():
            return
        if self._sync_sound_data is None:
            return
        try:
            print("Sync sound: playing...")
            sd.play(self._sync_sound_data, self._sync_sound_sr)
            sd.wait()
            print("Sync sound: playback complete")
        except Exception as e:
            print(f"Sync sound playback failed: {e}")

    def _start_bar_timer(self):
        """Start the bottom bar mm:ss timer (red label). Called from GUI thread."""
        self._bar_timer_start = time.time()
        self._bar_timer_running = True
        self._update_bar_timer()

    def _update_bar_timer(self):
        """Update the bottom bar timer display every second."""
        if self._bar_timer_running:
            elapsed = int(time.time() - self._bar_timer_start)
            minutes = elapsed // 60
            seconds = elapsed % 60
            self.rec_delay_countdown_label.config(text=f"{minutes:02d}:{seconds:02d}")
            self.root.after(1000, self._update_bar_timer)

    def _stop_bar_timer(self):
        """Stop the bottom bar timer and clear the label."""
        self._bar_timer_running = False
        self.rec_delay_countdown_label.config(text="")

    # -- Camera recording helpers ---------------------------------------------

    def start_camera_recording(self, camera_num, camera):
        """Start recording on a single camera (settings already applied via GUI)."""
        camera.shutterStart()

    def stop_and_download(self, camera_num, camera, video_dir, trial_name):
        """Stop recording and download file from a single camera."""
        camera.shutterStop()

        while camera.camBusy() or camera.encodingActive():
            time.sleep(0.5)

        filename = video_dir / f"{trial_name}_GP{camera_num}.mp4"
        camera.mediaDownloadLast(str(filename))

        camera.deleteAllFiles()

    def start_timer(self):
        """Start the recording timer."""
        self.start_time = time.time()
        self.update_timer()

    def update_timer(self):
        """Update the recording timer display."""
        if self.recording:
            elapsed = int(time.time() - self.start_time)
            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            seconds = elapsed % 60
            self.timer_var.set(f"Timer: {hours:02d}:{minutes:02d}:{seconds:02d}")
            self.root.after(1000, self.update_timer)
        else:
            self.timer_var.set("Timer: 00:00:00")

    def reset_recording_ui(self):
        """Reset recording UI after completion."""
        self.record_toggle_btn.config(text="START RECORDING", state="normal")
        self.trial_name_entry.config(state="normal")
        self.participant_combo.config(state="readonly")
        self.calibration_combo.config(state="readonly")
        self.new_participant_btn.config(state="normal")
        self.open_folder_btn.config(state="normal")
        self.timer_var.set("Timer: 00:00:00")
        self._stop_bar_timer()

        self.increment_trial_name()
        self.refresh_trial_tree()

    def increment_trial_name(self):
        """Auto-increment trial name for next recording."""
        current_name = self.trial_name_var.get()

        if '_' in current_name and current_name.split('_')[-1].isdigit():
            parts = current_name.rsplit('_', 1)
            base_name = parts[0]
            current_num = int(parts[1])
            new_name = f"{base_name}_{current_num + 1:03d}"
        else:
            new_name = f"{current_name}_001"

        self.trial_name_var.set(new_name)
        print(f"Trial name updated to: {new_name}")
