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
                 get_current_participant,
                 save_camera_settings, save_app_config,
                 get_calibration_tab,
                 rec_delay_enabled, rec_delay_seconds, rec_delay_countdown_label,
                 sync_method_var):
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
        self.get_current_participant = get_current_participant
        self.save_camera_settings = save_camera_settings
        self.save_app_config = save_app_config
        self._get_calibration_tab = get_calibration_tab

        # Bottom bar widget references (owned by main_window, shared)
        self.rec_delay_enabled = rec_delay_enabled
        self.rec_delay_seconds = rec_delay_seconds
        self.rec_delay_countdown_label = rec_delay_countdown_label
        self.sync_method_var = sync_method_var

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
        """Create the recording tab UI — cockpit layout."""
        from GUI.components.session_trials_list import SessionTrialsList

        # --- Session Trials List (top, expandable) ---
        self.trials_list = SessionTrialsList(
            self.frame, self.project_manager,
            self.get_current_project, self.get_current_session,
        )
        self.trials_list.frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(10, 5))

        # --- Trial Setup section ---
        setup_frame = ttk.LabelFrame(self.frame, text="Trial Setup", padding=10)
        setup_frame.pack(fill=tk.X, padx=20, pady=5)

        # Trial name row (big, prominent)
        trial_frame = ttk.Frame(setup_frame)
        trial_frame.pack(fill=tk.X, pady=3)
        ttk.Label(trial_frame, text="Trial Name:", font=("Arial", 11)).pack(side=tk.LEFT)
        self.trial_name_var = tk.StringVar(value=self.config["recording"]["last_trial_name"])
        self.trial_name_entry = ttk.Entry(trial_frame, textvariable=self.trial_name_var,
                                          width=30, font=("Arial", 14))
        self.trial_name_entry.pack(side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True)

        # Camera selection row
        cam_frame = ttk.Frame(setup_frame)
        cam_frame.pack(fill=tk.X, pady=3)
        ttk.Label(cam_frame, text="Cameras:").pack(side=tk.LEFT)

        self.camera_selection_vars = {}
        self.camera_selection_checkboxes = {}
        for i in range(1, 5):
            var = tk.BooleanVar(value=False)
            checkbox = ttk.Checkbutton(cam_frame, text=f"GoPro {i}", variable=var,
                                       state="disabled")
            checkbox.pack(side=tk.LEFT, padx=10)
            self.camera_selection_vars[i] = var
            self.camera_selection_checkboxes[i] = checkbox

        # Sound source row (always visible — manual mode assumed for now)
        self.sound_source_frame = ttk.Frame(setup_frame)
        self.sound_source_frame.pack(fill=tk.X, pady=3)
        ttk.Label(self.sound_source_frame, text="Sound source:").pack(side=tk.LEFT)

        # Load defaults from app_config
        sound_defaults = self.app_config.get("sound_source", {})
        self.sound_x_var = tk.StringVar(value=sound_defaults.get("x", "0.0"))
        self.sound_y_var = tk.StringVar(value=sound_defaults.get("y", "0.0"))
        self.sound_z_var = tk.StringVar(value=sound_defaults.get("z", "0.0"))

        for label, var in [("X", self.sound_x_var), ("Y", self.sound_y_var),
                           ("Z", self.sound_z_var)]:
            ttk.Label(self.sound_source_frame, text=f"  {label}:").pack(side=tk.LEFT)
            ttk.Entry(self.sound_source_frame, textvariable=var, width=7).pack(side=tk.LEFT)

        # --- Record Button + Timer ---
        control_frame = ttk.Frame(self.frame)
        control_frame.pack(pady=15)

        self.record_btn = tk.Button(
            control_frame, text="RECORD",
            font=("Arial", 18, "bold"),
            bg="#28a745", fg="white",
            activebackground="#218838", activeforeground="white",
            width=20, height=2,
            command=self.toggle_recording,
            relief="raised", bd=3,
        )
        self.record_btn.pack(side=tk.LEFT, padx=(0, 20))

        self.timer_var = tk.StringVar(value="00:00:00")
        self.timer_label = tk.Label(control_frame, textvariable=self.timer_var,
                                    font=("Arial", 24, "bold"), fg="#333333")
        self.timer_label.pack(side=tk.LEFT)

    # -- Refresh (backward-compatible alias) -----------------------------------

    def refresh_recording_dropdowns(self):
        """Refresh the session trials list. Called by main_window on tab switch."""
        self.trials_list.refresh()

    # -- Recording logic -------------------------------------------------------

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
            messagebox.showerror("Error", "No project selected. Use the top bar to create one.")
            return
        if not session:
            messagebox.showerror("Error", "No session selected. Use the top bar to create one.")
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

        # Participant from top bar, calibration = latest
        subject_id = self.get_current_participant() or ""
        calibration_name = self.project_manager.get_latest_calibration(project) or "none"
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

        # Save sound source position to app_config for persistence
        self.app_config["sound_source"] = {
            "x": self.sound_x_var.get(),
            "y": self.sound_y_var.get(),
            "z": self.sound_z_var.get(),
        }

        # Save settings and start
        self.save_camera_settings()
        self.recording = True
        self.recording_thread = threading.Thread(
            target=self.recording_worker, args=(available_cameras,), daemon=True
        )
        self.recording_thread.start()

        # Update UI — dramatic state change
        self.record_btn.config(text="STOP", bg="#dc3545", activebackground="#c82333")
        self.timer_label.config(fg="#dc3545")
        self.trial_name_entry.config(state="disabled")

    def _stop_recording(self):
        """Signal the recording worker to stop."""
        self.recording = False
        self._stop_bar_timer()
        self.record_btn.config(text="Stopping...", bg="#6c757d",
                               activebackground="#5a6268", state="disabled")
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

            # Build camera positions from calibration tab (if available)
            cam_positions = None
            calibration_tab = self._get_calibration_tab()
            if calibration_tab is not None:
                cam_positions, _ = calibration_tab._get_sync_compensation_data(video_paths)

            # Sound source position from recording tab UI
            sound_pos = self._get_sound_source_position()

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

    def _get_sound_source_position(self):
        """Read sound source X/Y/Z from UI fields. Returns [x, y, z] or None."""
        try:
            x = float(self.sound_x_var.get())
            y = float(self.sound_y_var.get())
            z = float(self.sound_z_var.get())
            return [x, y, z]
        except (ValueError, TypeError):
            return None

    # -- Recording delay / sync sound / bar timer ------------------------------

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
        if self.sync_method_var.get() != "speaker":
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

    # -- Camera recording helpers ----------------------------------------------

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
            self.timer_var.set(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            self.root.after(1000, self.update_timer)
        else:
            self.timer_var.set("00:00:00")

    def reset_recording_ui(self):
        """Reset recording UI after completion."""
        self.record_btn.config(text="RECORD", bg="#28a745",
                               activebackground="#218838", state="normal")
        self.timer_label.config(fg="#333333")
        self.trial_name_entry.config(state="normal")
        self.timer_var.set("00:00:00")
        self._stop_bar_timer()

        self.increment_trial_name()
        self.trials_list.refresh()

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
