#!/usr/bin/env python3
"""
Go2Kin - Main GUI Window
Multi-Camera GoPro Control Application
"""

import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import threading
import time
import queue
import cv2
from pathlib import Path
from datetime import datetime
import concurrent.futures
from PIL import Image, ImageTk

# Add goproUSB to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'goproUSB'))
from goproUSB import GPcam

# Add code directory to path for camera_profiles
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from camera_profiles import get_profile_manager
import sounddevice as sd
import numpy as np

class LivePreviewCapture:
    """Simplified video capture class for live preview with threading optimization"""
    
    def __init__(self, stream_url):
        self.stream_url = stream_url
        self.cap = None
        self.running = False
        self.frame_queue = queue.Queue(maxsize=2)  # Small queue to prevent buildup
        self.capture_thread = None
        
    def start_capture(self):
        """Start the optimized video capture with threading"""
        if self.running:
            return False
            
        # Create optimized VideoCapture
        self.cap = cv2.VideoCapture()
        
        # Pre-configure properties for low latency
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimal buffer
        self.cap.set(cv2.CAP_PROP_FPS, 30)        # Match camera FPS
        
        # Open with optimized FFmpeg parameters
        stream_params = "?overrun_nonfatal=1&fifo_size=1000000&fflags=nobuffer&flags=low_delay"
        success = self.cap.open(self.stream_url + stream_params, cv2.CAP_FFMPEG)
        
        if not success:
            # Fallback to original parameters
            stream_params = "?overrun_nonfatal=1&fifo_size=50000000"
            success = self.cap.open(self.stream_url + stream_params, cv2.CAP_FFMPEG)
        
        if success:
            self.running = True
            self.capture_thread = threading.Thread(target=self._capture_frames, daemon=True)
            self.capture_thread.start()
            return True
        else:
            if self.cap:
                self.cap.release()
                self.cap = None
            return False
    
    def _capture_frames(self):
        """Background thread for continuous frame capture"""
        while self.running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                # Drop old frames if queue is full (prevents buildup)
                if self.frame_queue.full():
                    try:
                        self.frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                
                try:
                    self.frame_queue.put_nowait(frame)
                except queue.Full:
                    pass  # Drop frame if queue is full
            else:
                time.sleep(0.001)  # Brief pause on read failure
    
    def get_latest_frame(self):
        """Get the latest frame for display (BGR format)"""
        try:
            return self.frame_queue.get_nowait()
        except queue.Empty:
            return None
    
    def stop_capture(self):
        """Stop the video capture and cleanup"""
        self.running = False
        if self.capture_thread:
            self.capture_thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()
            self.cap = None
        
        # Clear remaining frames
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break

class Go2KinMainWindow:
    def __init__(self, root, project_manager=None, app_config=None, app_config_path=None):
        self.root = root
        self.root.title("Go2Kin - Multi-Camera GoPro Control")
        self.root.geometry("1400x900")

        # Project manager and app-level config
        self.project_manager = project_manager
        self.app_config = app_config or {}
        self.app_config_path = app_config_path

        # Camera configuration
        self.config_file = Path("config/cameras.json")
        self.config = self.load_config()
        
        # Camera instances
        self.cameras = {}
        self.camera_status = {}
        self.camera_references = {}  # Store settings reference per camera
        self.camera_profiles = {}     # Store profile per camera

        # Camera serial numbers from app config
        serials = self.app_config.get("gopro_serial_numbers", [])
        self.camera_serials = {}
        for i in range(min(4, len(serials))):
            self.camera_serials[i + 1] = serials[i]
        
        # Recording state
        self.recording = False
        self.recording_thread = None
        self.start_time = None
        self._bar_timer_running = False

        # Sync sound (generated on the fly — HDMI primer + two claps)
        self._sync_sound_sr = 44100
        self._sync_sound_data = self._generate_sync_sound()
        
        # Live preview state
        self.preview_active = False
        self.preview_capture = None
        self.preview_camera_num = None
        self.preview_update_job = None
        
        # Create GUI
        self.create_widgets()
        self.load_camera_settings()
        
        # Bind window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Start status monitoring
        self.start_status_monitoring()
    
    def load_config(self):
        """Load configuration from JSON file"""
        default_config = {
            "cameras": {
                "1": {"serial": "C3501326042700", "lens": "Linear", "resolution": "1080", "fps": 30},
                "2": {"serial": "C3501326054100", "lens": "Linear", "resolution": "1080", "fps": 30},
                "3": {"serial": "C3501326054460", "lens": "Linear", "resolution": "1080", "fps": 30},
                "4": {"serial": "C3501326062418", "lens": "Linear", "resolution": "1080", "fps": 30}
            },
            "recording": {
                "output_directory": str(Path.cwd() / "output"),
                "last_trial_name": "TEMP"
            }
        }
        
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            else:
                # Create config directory and file
                self.config_file.parent.mkdir(exist_ok=True)
                self.save_config(default_config)
                return default_config
        except Exception as e:
            print(f"Error loading config: {e}")
            return default_config
    
    def save_config(self, config=None):
        """Save configuration to JSON file"""
        if config is None:
            config = self.config
        
        try:
            self.config_file.parent.mkdir(exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def save_app_config(self):
        """Save the app-level config (go2kin_config.json)."""
        if not self.app_config_path:
            return
        try:
            with open(self.app_config_path, "w") as f:
                json.dump(self.app_config, f, indent=4)
        except Exception as e:
            print(f"Error saving app config: {e}")

    def get_current_project(self):
        """Return the currently selected project name, or None."""
        if hasattr(self, "project_tab"):
            return self.project_tab.get_current_project()
        return None

    def get_current_session(self):
        """Return the currently selected session name, or None."""
        if hasattr(self, "project_tab"):
            return self.project_tab.get_current_session()
        return None

    def create_widgets(self):
        """Create the main GUI widgets"""
        # Fixed bottom bar (packed first so it stays at the bottom)
        self.create_camera_bottom_bar()

        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        # Tab 0: Project
        self.create_project_tab()

        # Tab 1: Live Preview
        self.create_live_preview_tab()

        # Tab 2: Calibration
        self.create_calibration_tab()

        # Tab 3: Recording
        self.create_recording_tab()

        # Tab 4: Processing
        self.create_processing_tab()

        # Tab 5: Visualisation
        self.create_visualisation_tab()
    
    def create_camera_bottom_bar(self):
        """Create a fixed bottom panel with camera status, controls, and global settings"""
        bar_frame = ttk.LabelFrame(self.root, text="Cameras", padding=(8, 4))
        bar_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 5))

        self.camera_bar = {}

        # Per-camera controls (left side)
        cameras_frame = ttk.Frame(bar_frame)
        cameras_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        for i in range(1, 5):
            cam_frame = ttk.Frame(cameras_frame)
            cam_frame.pack(side=tk.LEFT, padx=(0, 12))

            # Status circle
            status_canvas = tk.Canvas(cam_frame, width=16, height=16,
                                      highlightthickness=0)
            status_canvas.pack(side=tk.LEFT, padx=(0, 3))
            status_circle = status_canvas.create_oval(2, 2, 14, 14,
                                                       fill="red", outline="darkred", width=2)

            # Camera label
            ttk.Label(cam_frame, text=f"GP{i}",
                      font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(0, 3))

            # Connect/Disconnect toggle button
            connect_btn = ttk.Button(cam_frame, text="Connect", width=10,
                                     command=lambda cn=i: self.toggle_camera_connection(cn))
            connect_btn.pack(side=tk.LEFT, padx=(0, 3))

            # Battery label
            battery_var = tk.StringVar(value="\u2014")
            battery_label = ttk.Label(cam_frame, textvariable=battery_var,
                                      font=("Arial", 9), width=5)
            battery_label.pack(side=tk.LEFT)

            self.camera_bar[i] = {
                'status_canvas': status_canvas,
                'status_circle': status_circle,
                'connect_btn': connect_btn,
                'battery_var': battery_var,
                'battery_label': battery_label,
            }

        # Resolution dropdown (left-aligned after camera controls)
        ttk.Label(cameras_frame, text="Res:").pack(side=tk.LEFT, padx=(20, 0))
        self.global_res_var = tk.StringVar()
        res_combo = ttk.Combobox(cameras_frame, textvariable=self.global_res_var,
                                 values=["1080", "2.7K", "4K"],
                                 state="readonly", width=5)
        res_combo.pack(side=tk.LEFT, padx=(3, 0))
        res_combo.bind('<<ComboboxSelected>>', self.on_global_resolution_change)

        # FPS dropdown
        ttk.Label(cameras_frame, text="FPS:").pack(side=tk.LEFT, padx=(8, 0))
        self.global_fps_var = tk.StringVar()
        fps_combo = ttk.Combobox(cameras_frame, textvariable=self.global_fps_var,
                                 values=["25", "50", "100", "200"],
                                 state="readonly", width=5)
        fps_combo.pack(side=tk.LEFT, padx=(3, 0))
        fps_combo.bind('<<ComboboxSelected>>', self.on_global_fps_change)

        # Recording delay controls (right side)
        settings_frame = ttk.Frame(bar_frame)
        settings_frame.pack(side=tk.RIGHT)

        self.sync_sound_enabled = tk.BooleanVar(value=False)
        self.sync_sound_checkbox = ttk.Checkbutton(settings_frame, text="Sync sound",
                        variable=self.sync_sound_enabled, state="disabled")
        self.sync_sound_checkbox.pack(side=tk.LEFT, padx=(0, 12))

        self.rec_delay_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, text="Rec. delay",
                        variable=self.rec_delay_enabled).pack(side=tk.LEFT, padx=(0, 0))
        self.rec_delay_seconds = tk.StringVar(value="3")
        ttk.Entry(settings_frame, textvariable=self.rec_delay_seconds,
                  width=3).pack(side=tk.LEFT, padx=(3, 0))
        ttk.Label(settings_frame, text="sec").pack(side=tk.LEFT, padx=(2, 0))
        self.rec_delay_countdown_label = tk.Label(
            settings_frame, text="", font=("Arial", 16, "bold"), fg="red")
        self.rec_delay_countdown_label.pack(side=tk.LEFT, padx=(6, 0))

    def toggle_camera_connection(self, camera_num):
        """Toggle connect/disconnect for a camera"""
        if self.camera_status.get(camera_num, False):
            self.disconnect_camera(camera_num)
        else:
            self.connect_camera(camera_num)
    
    def create_live_preview_tab(self):
        """Create the functional live preview tab with maximized video display"""
        self.preview_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.preview_frame, text="Live Preview")
        
        # Compact control bar - all controls on one line
        control_bar = ttk.Frame(self.preview_frame)
        control_bar.pack(fill=tk.X, padx=10, pady=5)
        
        # Left side: Preview controls
        preview_controls = ttk.Frame(control_bar)
        preview_controls.pack(side=tk.LEFT)
        
        ttk.Label(preview_controls, text="Camera:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 5))
        self.preview_camera_var = tk.StringVar()
        self.preview_combo = ttk.Combobox(preview_controls, textvariable=self.preview_camera_var,
                                         state="readonly", width=10)
        self.preview_combo.pack(side=tk.LEFT, padx=(0, 8))
        
        self.start_preview_btn = ttk.Button(preview_controls, text="▶ Start", 
                                          command=self.start_preview)
        self.start_preview_btn.pack(side=tk.LEFT, padx=(0, 4))
        
        self.stop_preview_btn = ttk.Button(preview_controls, text="⏹ Stop", 
                                         command=self.stop_preview, state="disabled")
        self.stop_preview_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Status indicator (compact)
        self.preview_status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(preview_controls, textvariable=self.preview_status_var, 
                               font=("Arial", 9), foreground="gray")
        status_label.pack(side=tk.LEFT)
        
        # Right side: Zoom controls
        zoom_controls = ttk.Frame(control_bar)
        zoom_controls.pack(side=tk.RIGHT)
        
        # Minus button
        self.zoom_minus_btn = ttk.Button(zoom_controls, text="−", width=2,
                                        command=self.zoom_decrement, state="disabled")
        self.zoom_minus_btn.pack(side=tk.LEFT, padx=(0, 3))
        
        # Slider (compact)
        self.zoom_slider = tk.Scale(zoom_controls, from_=0, to=100, orient=tk.HORIZONTAL,
                                   showvalue=False, state="disabled", length=150)
        self.zoom_slider.pack(side=tk.LEFT)
        self.zoom_slider.bind("<ButtonRelease-1>", self.on_zoom_slider_release)
        
        # Plus button
        self.zoom_plus_btn = ttk.Button(zoom_controls, text="+", width=2,
                                       command=self.zoom_increment, state="disabled")
        self.zoom_plus_btn.pack(side=tk.LEFT, padx=(3, 8))
        
        # Zoom label
        self.zoom_label_var = tk.StringVar(value="Zoom: 0%")
        zoom_label = ttk.Label(zoom_controls, textvariable=self.zoom_label_var,
                              font=("Arial", 9), width=10)
        zoom_label.pack(side=tk.LEFT, padx=(0, 5))
        
        # Direct input (compact)
        self.zoom_entry_var = tk.StringVar(value="0")
        self.zoom_entry = ttk.Entry(zoom_controls, textvariable=self.zoom_entry_var,
                                    width=4, state="disabled")
        self.zoom_entry.pack(side=tk.LEFT)
        self.zoom_entry.bind("<Return>", self.on_zoom_entry_enter)
        
        # Video display area - maximized with 16:9 aspect ratio
        video_container = ttk.Frame(self.preview_frame)
        video_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Video label for displaying frames (16:9 ratio maintained in update_video_display)
        self.video_label = tk.Label(video_container, text="Select a connected camera and click Start",
                                   bg="black", fg="white", font=("Arial", 12))
        self.video_label.pack(expand=True, fill=tk.BOTH)
        
        # Update camera dropdown initially
        self.update_preview_camera_dropdown()
    
    def create_project_tab(self):
        """Create the project management tab (first tab)"""
        from GUI.project_tab import ProjectTab
        self.project_tab = ProjectTab(
            self.notebook, self.project_manager,
            self.app_config, self.save_app_config
        )

    def create_calibration_tab(self):
        """Create the calibration tab"""
        from GUI.calibration_tab import CalibrationTab
        self.calibration_tab = CalibrationTab(
            self.notebook, self.config,
            cameras=self.cameras,
            camera_status=self.camera_status,
            project_manager=self.project_manager,
            get_current_project=lambda: self.project_tab.get_current_project(),
            is_recording=lambda: self.recording,
            run_rec_delay=self._run_rec_delay,
            start_bar_timer=self._start_bar_timer,
            stop_bar_timer=self._stop_bar_timer,
            play_sync_sound=self._play_sync_sound,
        )

    def create_processing_tab(self):
        """Create the Pose2Sim processing tab"""
        from GUI.processing_tab import ProcessingTab
        self.processing_tab = ProcessingTab(
            self.notebook, self.project_manager,
            get_current_project=lambda: self.project_tab.get_current_project(),
            get_current_session=lambda: self.project_tab.get_current_session(),
        )

    def create_visualisation_tab(self):
        """Create the visualisation/playback tab"""
        from GUI.visualisation_tab import VisualisationTab
        self.visualisation_tab = VisualisationTab(
            self.notebook, self.project_manager,
            get_current_project=lambda: self.project_tab.get_current_project(),
            get_current_session=lambda: self.project_tab.get_current_session(),
        )

    def create_recording_tab(self):
        """Create the recording tab"""
        self.recording_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.recording_frame, text="Recording")

        # Track current trial info for recording flow
        self._current_trial_info = None
        self._last_trial_video_dir = None

        # Title
        title_label = ttk.Label(self.recording_frame, text="Multi-Camera Recording",
                               font=("Arial", 16, "bold"))
        title_label.pack(pady=(15, 10))

        # --- Trial Setup section ---
        setup_frame = ttk.LabelFrame(self.recording_frame, text="Trial Setup", padding=10)
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
        selection_frame = ttk.LabelFrame(self.recording_frame, text="Camera Selection", padding=10)
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
        control_frame = ttk.Frame(self.recording_frame)
        control_frame.pack(pady=15)

        self.record_toggle_btn = ttk.Button(control_frame, text="START RECORDING",
                                            command=self.toggle_recording)
        self.record_toggle_btn.pack(side=tk.LEFT, padx=(0, 15))

        self.timer_var = tk.StringVar(value="Timer: 00:00:00")
        timer_label = ttk.Label(control_frame, textvariable=self.timer_var,
                               font=("Arial", 14, "bold"))
        timer_label.pack(side=tk.LEFT, padx=(15, 0))

        # --- Progress Log ---
        progress_frame = ttk.LabelFrame(self.recording_frame, text="Progress Log", padding=10)
        progress_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        text_frame = ttk.Frame(progress_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.progress_text = tk.Text(text_frame, height=8, state="disabled",
                                   font=("Consolas", 9), wrap=tk.WORD)
        self.progress_text.tag_configure("warning", foreground="red")
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.progress_text.yview)
        self.progress_text.configure(yscrollcommand=scrollbar.set)
        self.progress_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Session/Trial Tree View ---
        tree_frame = ttk.LabelFrame(self.recording_frame, text="Session Trials", padding=10)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        self.trial_tree = ttk.Treeview(tree_frame, height=5, show="tree")
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.trial_tree.yview)
        self.trial_tree.configure(yscrollcommand=tree_scroll.set)
        self.trial_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Open Trial Folder button ---
        self.open_folder_btn = ttk.Button(self.recording_frame, text="Open Trial Folder",
                                        command=self.open_trial_folder, state="disabled")
        self.open_folder_btn.pack(pady=8)

        # Bind tab change to refresh dropdowns
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
    
    def load_camera_settings(self):
        """Load last-used resolution/fps into global dropdowns"""
        if "1" in self.config["cameras"]:
            cam1 = self.config["cameras"]["1"]
            self.global_res_var.set(cam1.get("resolution", "4K"))
            self.global_fps_var.set(str(cam1.get("fps", 50)))

    def save_camera_settings(self):
        """Save current camera settings to config"""
        res = self.global_res_var.get()
        fps = int(self.global_fps_var.get()) if self.global_fps_var.get().isdigit() else 50
        for i in range(1, 5):
            self.config["cameras"][str(i)] = {
                "serial": self.camera_serials.get(i, ""),
                "lens": "Linear",
                "resolution": res,
                "fps": fps
            }

        self.config["recording"]["last_trial_name"] = self.trial_name_var.get()

        self.save_config()
    
    # -- Recording tab helpers ------------------------------------------------

    def _on_tab_changed(self, event):
        """Refresh tab contents when switching tabs."""
        try:
            selected = self.notebook.index(self.notebook.select())
            if selected == 2:  # Recording tab
                self.refresh_recording_dropdowns()
            elif selected == 4:  # Processing tab
                self.processing_tab.refresh_tree()
        except Exception:
            pass

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

    def connect_camera(self, camera_num):
        """Connect to a specific camera with profile management"""
        try:
            serial = self.camera_serials.get(camera_num, "")

            if not serial:
                messagebox.showerror("Error", f"No serial number configured for GoPro {camera_num} in go2kin_config.json")
                return
            
            self.log_progress(f"Connecting to GoPro {camera_num} ({serial})...")
            
            # Create camera instance
            camera = GPcam(serial)
            
            # Enable USB control
            response = camera.USBenable()
            if response.status_code != 200:
                raise Exception("Failed to enable USB control")
            
            time.sleep(1)
            
            # Verify connection
            response = camera.keepAlive()
            if response.status_code != 200:
                raise Exception("Camera not responding to keep-alive")
            
            self.log_progress(f"✓ Camera connected, querying camera info...")
            
            # Get camera info (model, firmware, serial)
            info_response = camera.getCameraInfo()
            if info_response.status_code != 200:
                raise Exception("Failed to get camera info")
            
            camera_info = info_response.json()
            model = camera_info['model_name']
            firmware = camera_info['firmware_version']
            
            self.log_progress(f"  Model: {model}, Firmware: {firmware}")
            
            # Get profile manager
            profile_mgr = get_profile_manager()
            
            # Load existing profile to check for saved zoom level
            existing_profile = profile_mgr.load_camera_profile(serial)
            saved_zoom = None
            if existing_profile and 'current_zoom' in existing_profile:
                saved_zoom = existing_profile.get('current_zoom', 0)
                if saved_zoom > 0:
                    self.log_progress(f"  Found saved zoom level: {saved_zoom}%")
            
            # Check if we have a settings reference for this model/firmware
            reference = profile_mgr.load_settings_reference(model, firmware)
            
            if reference is None:
                self.log_progress(f"⚠ No settings reference found for {model} {firmware}")
                self.log_progress(f"  Run: python tools/discover_camera_settings.py {serial}")
                messagebox.showwarning(
                    "Settings Reference Missing",
                    f"No settings reference found for {model} (firmware {firmware}).\n\n"
                    f"To enable full settings management, run:\n"
                    f"python tools/discover_camera_settings.py {serial}\n\n"
                    f"Camera will still connect, but settings display will be limited."
                )
                # Continue without reference - basic functionality still works
            else:
                self.log_progress(f"✓ Loaded settings reference for {model} {firmware}")
            
            # Force video mode to ensure video settings are available
            self.log_progress(f"  Setting camera to video mode...")
            camera.modeVideo()
            time.sleep(1)
            
            # Apply settings on connect (only if not already set)
            # These settings ensure consistent camera configuration for research use
            # Format: (setting_id, option_id, name, value_description)
            settings_on_connect = [
                (175, 1, "Control Mode", "Pro"),              # Pro control mode
                (121, 4, "Lens", "Linear"),                   # Linear lens mode
                (83, 0, "GPS", "Off"),                        # GPS off
                (167, 4, "Hindsight", "Off"),                 # Hindsight off
                (135, 0, "Hypersmooth", "Off"),               # Hypersmooth off
                (88, 30, "LCD Brightness", "30%"),            # LCD brightness 30%
                (134, 3, "Anti-Flicker", "50Hz"),             # 50Hz for Australia
                (182, 1, "Bit Rate", "High"),                 # High bitrate for better quality
                (183, 0, "Bit Depth", "8-Bit"),              # reduces processing
                (184, 0, "Profiles", "Standard"),             # Standard profile (no HDR processing)
                # Setting 180 (System Video Mode) removed - not supported on HERO12 Black
                (236, 0, "Auto WiFi AP", "Off"),              # Auto WiFi AP off
            ]
            
            state_check = camera.getState()
            if state_check.status_code == 200:
                current_settings = state_check.json()['settings']
                for setting_id, option_id, name, value_desc in settings_on_connect:
                    current_value = current_settings.get(str(setting_id), None)
                    if current_value != option_id:
                        self.log_progress(f"  Setting {name} to {value_desc}...")
                        camera.setSetting(setting_id, option_id)
                        time.sleep(0.3)
                    else:
                        self.log_progress(f"  {name} already {value_desc}")

            # Restore critical recording settings from saved profile
            # This ensures settings survive camera power-cycles between sessions
            if existing_profile and 'current_settings' in existing_profile:
                critical_settings = [
                    ('2', "Video Resolution"),
                    ('3', "Frames Per Second"),
                    ('121', "Video Lens"),
                ]
                for setting_id, name in critical_settings:
                    if setting_id in existing_profile['current_settings']:
                        saved = existing_profile['current_settings'][setting_id]
                        saved_value = saved['value']
                        current_value = current_settings.get(setting_id, None)
                        if current_value != saved_value:
                            self.log_progress(f"  Restoring {name} to {saved['value_name']}...")
                            camera.setSetting(int(setting_id), saved_value)
                            time.sleep(0.3)
                        else:
                            self.log_progress(f"  {name} already {saved['value_name']}")

            # Get current camera state
            state_response = camera.getState()
            if state_response.status_code != 200:
                raise Exception("Failed to get camera state")
            
            state = state_response.json()
            
            # Query current zoom level (status ID 75)
            current_zoom = state['status'].get('75', 0)  # Default to 0 if not found
            self.log_progress(f"  Current zoom: {current_zoom}%")
            
            # Restore saved zoom level if available and different from current
            if saved_zoom is not None and saved_zoom > 0 and saved_zoom != current_zoom:
                self.log_progress(f"  Restoring saved zoom level: {saved_zoom}%...")
                try:
                    response = camera.setDigitalZoom(saved_zoom)
                    if response.status_code == 200:
                        current_zoom = saved_zoom  # Update to restored value
                        self.log_progress(f"  ✓ Zoom restored to {saved_zoom}%")
                    else:
                        self.log_progress(f"  ⚠ Failed to restore zoom (status: {response.status_code})")
                except Exception as zoom_err:
                    self.log_progress(f"  ⚠ Failed to restore zoom: {zoom_err}")
            
            # Create or update camera profile
            profile = None
            if reference:
                profile = profile_mgr.create_or_update_profile(camera_info, state, reference)
                
                # Add zoom level to profile
                profile['current_zoom'] = current_zoom
                
                self.log_progress(f"✓ Camera profile updated")
                
                # Store reference and profile for this camera
                self.camera_references[camera_num] = reference
                self.camera_profiles[camera_num] = profile
                
                # Log some current settings
                if '2' in profile['current_settings']:  # Video Resolution
                    res_setting = profile['current_settings']['2']
                    self.log_progress(f"  Current resolution: {res_setting['value_name']}")
                if '3' in profile['current_settings']:  # FPS
                    fps_setting = profile['current_settings']['3']
                    self.log_progress(f"  Current FPS: {fps_setting['value_name']}")
                
                # Populate dropdowns from profile
                self.populate_dropdowns_from_profile(camera_num, profile)
                
                # Save profile with zoom level
                profile_mgr.save_camera_profile(serial, profile)
            
            # Store camera instance
            self.cameras[camera_num] = camera
            self.camera_status[camera_num] = True
            self.update_camera_status(camera_num, True)
            
            self.log_progress(f"✓ GoPro {camera_num} connected successfully")

            # Query initial battery level
            try:
                state_resp = camera.getState()
                if state_resp.status_code == 200:
                    state = state_resp.json()
                    battery_level = state.get('status', {}).get('2', None)
                    if battery_level is not None:
                        battery_level = int(battery_level)
                        self._update_battery(camera_num, str(battery_level), low=(battery_level == 0))
            except Exception:
                pass  # Non-critical

        except Exception as e:
            self.log_progress(f"✗ Failed to connect GoPro {camera_num}: {e}")
            messagebox.showerror("Connection Error", f"Failed to connect GoPro {camera_num}:\n{e}")
    
    def populate_dropdowns_from_profile(self, camera_num, profile):
        """Set global dropdown values from camera profile"""
        # Set current resolution from profile
        if '2' in profile['current_settings']:
            current_res = profile['current_settings']['2']['value_name']
            self.global_res_var.set(current_res)
            self.log_progress(f"  Resolution: {current_res}")

        # Set current FPS from profile
        if '3' in profile['current_settings']:
            current_fps = profile['current_settings']['3']['value_name']
            self.global_fps_var.set(current_fps)
            self.log_progress(f"  FPS: {current_fps}")

    def on_global_resolution_change(self, event=None):
        """Handle global resolution dropdown change — apply to all connected cameras"""
        new_value = self.global_res_var.get()
        self.log_progress(f"Applying resolution {new_value} to all cameras...")
        for camera_num in list(self.cameras.keys()):
            if camera_num in self.camera_references:
                self.apply_setting_to_camera(camera_num, 2, new_value, "Video Resolution")

    def on_global_fps_change(self, event=None):
        """Handle global FPS dropdown change — apply to all connected cameras"""
        new_value = self.global_fps_var.get()
        self.log_progress(f"Applying FPS {new_value} to all cameras...")
        for camera_num in list(self.cameras.keys()):
            if camera_num in self.camera_references:
                self.apply_setting_to_camera(camera_num, 3, new_value, "Frames Per Second")
    
    def apply_setting_to_camera(self, camera_num, setting_id, display_name, setting_name):
        """Apply a setting change to the camera with validation"""
        try:
            camera = self.cameras[camera_num]
            reference = self.camera_references[camera_num]
            
            # Find option_id for this display name (reverse lookup)
            setting_id_str = str(setting_id)
            if setting_id_str not in reference['settings']:
                raise Exception(f"Setting {setting_id} not found in reference")
            
            options = reference['settings'][setting_id_str]['available_options']
            option_id = None
            for opt_id, opt_name in options.items():
                if opt_name == display_name:
                    option_id = int(opt_id)
                    break
            
            if option_id is None:
                raise Exception(f"Option '{display_name}' not found for {setting_name}")
            
            # Apply setting to camera
            response = camera.setSetting(setting_id, option_id)
            
            if response.status_code == 200:
                # Success! Update profile
                self.update_camera_profile_setting(camera_num, setting_id, option_id, display_name)
                self.log_progress(f"✓ {setting_name} set to: {display_name}")

                # Re-apply zoom in case the setting change reset it
                if camera_num in self.camera_profiles:
                    saved_zoom = self.camera_profiles[camera_num].get('current_zoom', 0)
                    if saved_zoom > 0:
                        try:
                            camera.setDigitalZoom(saved_zoom)
                            time.sleep(0.2)
                        except Exception as e:
                            self.log_progress(f"  ⚠ Note: Zoom may have been reset by setting change")
                
            elif response.status_code == 403:
                # Invalid option - log details and show available options
                try:
                    error_data = response.json()
                    error_code = error_data.get('error', 'unknown')
                    self.log_progress(f"  Setting rejected (error code {error_code}): {error_data}")
                    available_options = error_data.get('supported_options', error_data.get('available_options', []))
                    self.show_invalid_setting_dialog(setting_name, available_options)
                except Exception as e:
                    self.log_progress(f"  Failed to parse 403 response: {e}")
                    messagebox.showerror("Setting Error",
                                       f"Cannot set {setting_name} to '{display_name}' with current camera state")
                
                # Revert dropdown to previous value
                if camera_num in self.camera_profiles:
                    profile = self.camera_profiles[camera_num]
                    if setting_id_str in profile['current_settings']:
                        old_value = profile['current_settings'][setting_id_str]['value_name']
                        if setting_id == 2:
                            self.global_res_var.set(old_value)
                        elif setting_id == 3:
                            self.global_fps_var.set(old_value)
                
            else:
                raise Exception(f"Unexpected response: {response.status_code}")
                
        except Exception as e:
            self.log_progress(f"✗ Failed to apply {setting_name}: {e}")
            messagebox.showerror("Setting Error", f"Failed to apply {setting_name}:\n{e}")
    
    def update_camera_profile_setting(self, camera_num, setting_id, option_id, display_name):
        """Update camera profile after successful setting change"""
        try:
            if camera_num not in self.camera_profiles:
                return
            
            profile = self.camera_profiles[camera_num]
            setting_id_str = str(setting_id)
            
            # Update in-memory profile
            if setting_id_str in profile['current_settings']:
                profile['current_settings'][setting_id_str]['value'] = option_id
                profile['current_settings'][setting_id_str]['value_name'] = display_name
            
            # Save profile to disk
            profile_mgr = get_profile_manager()
            serial = profile['serial_number']
            profile_mgr.save_camera_profile(serial, profile)
            
        except Exception as e:
            self.log_progress(f"⚠ Error updating profile: {e}")
    
    def show_invalid_setting_dialog(self, setting_name, available_options):
        """Show dialog with available options when setting is invalid"""
        if not available_options:
            messagebox.showerror("Invalid Setting", 
                               f"Cannot change {setting_name} with current camera state.\n\n"
                               f"No available options returned by camera.")
            return
        
        # Format available options
        options_text = "\n".join([f"  • {opt.get('display_name', 'Unknown')}" 
                                 for opt in available_options])
        
        messagebox.showwarning("Invalid Setting", 
                              f"Cannot set {setting_name} to the selected value.\n\n"
                              f"Available options with current camera state:\n{options_text}\n\n"
                              f"Try changing other settings first (e.g., aspect ratio, lens mode).")
    
    def disconnect_camera(self, camera_num):
        """Disconnect from a specific camera"""
        try:
            if camera_num in self.cameras:
                camera = self.cameras[camera_num]
                
                # Stop preview stream if this camera is currently streaming
                # This prevents 409 errors on next connection
                try:
                    camera.streamStop()
                except Exception:
                    pass  # Ignore errors - stream may not be active
                
                camera.USBdisable()
                del self.cameras[camera_num]
                self.camera_status[camera_num] = False
                self.update_camera_status(camera_num, False)
                
                # Clear stored reference and profile
                if camera_num in self.camera_references:
                    del self.camera_references[camera_num]
                if camera_num in self.camera_profiles:
                    del self.camera_profiles[camera_num]
                
                self.log_progress(f"✓ GoPro {camera_num} disconnected")
        except Exception as e:
            self.log_progress(f"✗ Error disconnecting GoPro {camera_num}: {e}")
    
    def update_camera_status(self, camera_num, connected):
        """Update the visual status indicator for a camera"""
        bar = self.camera_bar[camera_num]
        color = "green" if connected else "red"
        outline_color = "darkgreen" if connected else "darkred"
        bar['status_canvas'].itemconfig(bar['status_circle'], fill=color, outline=outline_color)
        bar['connect_btn'].config(text="Disconnect" if connected else "Connect")
        if not connected:
            bar['battery_var'].set("\u2014")

        # Enable/disable recording checkbox based on connection status
        if camera_num in self.camera_selection_checkboxes:
            if connected:
                self.camera_selection_checkboxes[camera_num].config(state="normal")
                self.camera_selection_vars[camera_num].set(True)
            else:
                self.camera_selection_checkboxes[camera_num].config(state="disabled")
                self.camera_selection_vars[camera_num].set(False)

        # Update calibration tab camera checkboxes
        if hasattr(self, 'calibration_tab'):
            self.calibration_tab.update_camera_checkboxes(camera_num, connected)

        # Update preview camera dropdown when camera status changes
        self.update_preview_camera_dropdown()
    
    def update_preview_camera_dropdown(self):
        """Update the preview camera dropdown to show only connected cameras"""
        connected_cameras = []
        for camera_num in range(1, 5):
            if camera_num in self.cameras and self.camera_status.get(camera_num, False):
                connected_cameras.append(f"GoPro {camera_num}")
        
        # Update dropdown values
        self.preview_combo['values'] = connected_cameras
        
        # Set default selection if cameras are available
        if connected_cameras:
            if not self.preview_camera_var.get() or self.preview_camera_var.get() not in connected_cameras:
                self.preview_camera_var.set(connected_cameras[0])
            self.start_preview_btn.config(state="normal")
        else:
            self.preview_camera_var.set("")
            self.start_preview_btn.config(state="disabled")
            self.preview_status_var.set("No cameras connected")
    
    def on_zoom_slider_release(self, event):
        """Apply zoom when user releases slider"""
        if not self.preview_active or self.preview_camera_num is None:
            return
        
        zoom_value = int(self.zoom_slider.get())
        self.apply_zoom_to_camera(zoom_value)
    
    def zoom_increment(self):
        """Increment zoom by 1%"""
        if not self.preview_active or self.preview_camera_num is None:
            return
        
        current = int(self.zoom_slider.get())
        new_value = min(100, current + 1)
        self.zoom_slider.set(new_value)
        self.apply_zoom_to_camera(new_value)
    
    def zoom_decrement(self):
        """Decrement zoom by 1%"""
        if not self.preview_active or self.preview_camera_num is None:
            return
        
        current = int(self.zoom_slider.get())
        new_value = max(0, current - 1)
        self.zoom_slider.set(new_value)
        self.apply_zoom_to_camera(new_value)
    
    def on_zoom_entry_enter(self, event):
        """Validate and apply zoom on Enter key"""
        if not self.preview_active or self.preview_camera_num is None:
            return
        
        value_str = self.zoom_entry_var.get()
        if self.validate_zoom_input(value_str):
            zoom_value = int(value_str)
            self.apply_zoom_to_camera(zoom_value)
        else:
            # Show error and revert to current camera zoom
            messagebox.showerror("Invalid Input", 
                               "Zoom must be a number between 0 and 100")
            self.sync_zoom_controls_from_camera()
    
    def validate_zoom_input(self, value_str):
        """Validate zoom input string"""
        try:
            value = int(value_str)
            return 0 <= value <= 100
        except ValueError:
            return False
    
    def apply_zoom_to_camera(self, zoom_value):
        """Apply zoom value to camera and update all controls"""
        if self.preview_camera_num is None or self.preview_camera_num not in self.cameras:
            return
        
        try:
            camera = self.cameras[self.preview_camera_num]
            response = camera.setDigitalZoom(zoom_value)
            
            if response.status_code == 200:
                # Success - update all controls
                self.update_zoom_display(zoom_value)
                
                # Update profile if available
                if self.preview_camera_num in self.camera_profiles:
                    profile = self.camera_profiles[self.preview_camera_num]
                    profile['current_zoom'] = zoom_value
                    
                    # Save profile to disk
                    profile_mgr = get_profile_manager()
                    serial = profile['serial_number']
                    profile_mgr.save_camera_profile(serial, profile)
            else:
                raise Exception(f"Camera returned status {response.status_code}")
                
        except Exception as e:
            messagebox.showerror("Zoom Error", f"Failed to set zoom:\n{e}")
            self.sync_zoom_controls_from_camera()
    
    def update_zoom_display(self, zoom_value):
        """Update all zoom controls to show the same value"""
        self.zoom_slider.set(zoom_value)
        self.zoom_entry_var.set(str(zoom_value))
        self.zoom_label_var.set(f"Zoom: {zoom_value}%")
    
    def sync_zoom_controls_from_camera(self):
        """Query camera and sync all zoom controls"""
        if self.preview_camera_num is None or self.preview_camera_num not in self.cameras:
            return
        
        try:
            camera = self.cameras[self.preview_camera_num]
            current_zoom = camera.getZoomLevel()
            
            if current_zoom is not None:
                self.update_zoom_display(current_zoom)
        except Exception as e:
            print(f"Error syncing zoom from camera: {e}")
    
    def enable_zoom_controls(self):
        """Enable zoom controls when preview is active"""
        self.zoom_slider.config(state="normal")
        self.zoom_minus_btn.config(state="normal")
        self.zoom_plus_btn.config(state="normal")
        self.zoom_entry.config(state="normal")
    
    def disable_zoom_controls(self):
        """Disable zoom controls when preview is not active"""
        self.zoom_slider.config(state="disabled")
        self.zoom_minus_btn.config(state="disabled")
        self.zoom_plus_btn.config(state="disabled")
        self.zoom_entry.config(state="disabled")
    
    def start_preview(self):
        """Start live preview for the selected camera"""
        if self.preview_active:
            return
        
        # Get selected camera
        selected_camera = self.preview_camera_var.get()
        if not selected_camera:
            messagebox.showerror("Error", "Please select a camera for preview")
            return
        
        # Extract camera number
        camera_num = int(selected_camera.split()[-1])
        
        if camera_num not in self.cameras or not self.camera_status.get(camera_num, False):
            messagebox.showerror("Error", f"GoPro {camera_num} is not connected")
            return
        
        try:
            self.preview_status_var.set("Starting preview...")
            camera = self.cameras[camera_num]
            
            # Apply fixed preview settings (Linear lens, 1080p, 30fps)
            camera.modeVideo()
            camera.setVideoLensesLinear()  # Always Linear
            camera.setVideoResolution1080()  # Always 1080p
            camera.setFPS30()  # Always 30fps
            
            # Apply saved zoom level from profile (after settings that might reset it)
            if camera_num in self.camera_profiles:
                saved_zoom = self.camera_profiles[camera_num].get('current_zoom', 0)
                if saved_zoom > 0:
                    camera.setDigitalZoom(saved_zoom)
                    time.sleep(0.3)
            
            # Start UDP stream
            response = camera.streamStart(port=8554)
            if response.status_code != 200:
                raise Exception(f"Failed to start preview stream (status: {response.status_code})")
            
            # Wait for stream to initialize
            time.sleep(2)
            
            # Create capture instance
            stream_url = "udp://0.0.0.0:8554"
            self.preview_capture = LivePreviewCapture(stream_url)
            
            if self.preview_capture.start_capture():
                self.preview_active = True
                self.preview_camera_num = camera_num
                
                # Initialize zoom controls from camera profile
                if camera_num in self.camera_profiles:
                    profile = self.camera_profiles[camera_num]
                    current_zoom = profile.get('current_zoom', 0)
                    self.update_zoom_display(current_zoom)
                else:
                    # No profile, query camera directly
                    self.sync_zoom_controls_from_camera()
                
                # Enable zoom controls
                self.enable_zoom_controls()
                
                # Update UI
                self.start_preview_btn.config(state="disabled")
                self.stop_preview_btn.config(state="normal")
                self.preview_combo.config(state="disabled")  # Disable camera selection during preview
                self.preview_status_var.set(f"Streaming from GoPro {camera_num}")
                
                # Start video display update loop
                self.update_video_display()
                
            else:
                raise Exception("Failed to start video capture")
                
        except Exception as e:
            self.preview_status_var.set(f"Error: {e}")
            messagebox.showerror("Preview Error", f"Failed to start preview:\n{e}")
            self.cleanup_preview()
    
    def stop_preview(self):
        """Stop live preview"""
        if not self.preview_active:
            return
        
        self.preview_status_var.set("Stopping preview...")
        self.cleanup_preview()
        self.preview_status_var.set("Ready")
    
    def cleanup_preview(self):
        """Clean up preview resources"""
        self.preview_active = False
        
        # Cancel video update job
        if self.preview_update_job:
            self.root.after_cancel(self.preview_update_job)
            self.preview_update_job = None
        
        # Stop capture
        if self.preview_capture:
            self.preview_capture.stop_capture()
            self.preview_capture = None
        
        # Stop camera stream
        if self.preview_camera_num and self.preview_camera_num in self.cameras:
            try:
                camera = self.cameras[self.preview_camera_num]
                camera.streamStop()
            except Exception as e:
                print(f"Error stopping camera stream: {e}")
        
        self.preview_camera_num = None
        
        # Disable zoom controls
        self.disable_zoom_controls()
        
        # Reset zoom display
        self.update_zoom_display(0)
        
        # Reset UI
        self.start_preview_btn.config(state="normal")
        self.stop_preview_btn.config(state="disabled")
        self.preview_combo.config(state="readonly")  # Re-enable camera selection
        
        # Clear video display
        self.video_label.config(image='', text="Select a connected camera and click Start Preview")
        
        # Update dropdown in case camera status changed
        self.update_preview_camera_dropdown()
    
    def update_video_display(self):
        """Update the video display with the latest frame (16:9 aspect ratio)"""
        if not self.preview_active or not self.preview_capture:
            return
        
        try:
            # Get latest frame
            frame = self.preview_capture.get_latest_frame()
            
            if frame is not None:
                # Convert BGR to RGB (OpenCV uses BGR, tkinter expects RGB)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Get available display area size
                self.video_label.update_idletasks()
                available_width = self.video_label.winfo_width()
                available_height = self.video_label.winfo_height()
                
                # Use minimum reasonable size if widget not yet sized
                if available_width < 100:
                    available_width = 800
                if available_height < 100:
                    available_height = 450
                
                # Calculate 16:9 display size that fits within available space
                target_ratio = 16 / 9
                
                # Try fitting by width first
                display_width = available_width
                display_height = int(display_width / target_ratio)
                
                # If too tall, fit by height instead
                if display_height > available_height:
                    display_height = available_height
                    display_width = int(display_height * target_ratio)
                
                # Ensure minimum size
                display_width = max(320, display_width)
                display_height = max(180, display_height)
                
                frame_resized = cv2.resize(frame_rgb, (display_width, display_height))
                
                # Convert to PIL Image and then to ImageTk
                pil_image = Image.fromarray(frame_resized)
                photo = ImageTk.PhotoImage(pil_image)
                
                # Update label
                self.video_label.config(image=photo, text="")
                self.video_label.image = photo  # Keep a reference to prevent garbage collection
            
        except Exception as e:
            print(f"Error updating video display: {e}")
        
        # Schedule next update (~30 FPS)
        if self.preview_active:
            self.preview_update_job = self.root.after(33, self.update_video_display)
    
    def start_status_monitoring(self):
        """Start background thread for status monitoring and battery queries"""
        def monitor_status():
            while True:
                for camera_num in list(self.cameras.keys()):
                    try:
                        camera = self.cameras[camera_num]
                        response = camera.keepAlive()
                        if response.status_code != 200:
                            self.camera_status[camera_num] = False
                            self.root.after(0, lambda cn=camera_num: self.update_camera_status(cn, False))
                            continue

                        # Query battery level
                        try:
                            state_resp = camera.getState()
                            if state_resp.status_code == 200:
                                state = state_resp.json()
                                battery_level = state.get('status', {}).get('2', None)
                                if battery_level is not None:
                                    battery_level = int(battery_level)
                                    text = str(battery_level)
                                    low = battery_level == 0
                                    self.root.after(0, lambda cn=camera_num, t=text, l=low:
                                                    self._update_battery(cn, t, l))
                        except Exception:
                            pass  # Battery query is non-critical

                    except Exception:
                        self.camera_status[camera_num] = False
                        self.root.after(0, lambda cn=camera_num: self.update_camera_status(cn, False))

                time.sleep(30)  # Check every 30 seconds

        monitor_thread = threading.Thread(target=monitor_status, daemon=True)
        monitor_thread.start()

    def _update_battery(self, camera_num, text, low=False):
        """Update battery display for a camera (must be called on main thread)"""
        if camera_num not in self.camera_bar:
            return
        bar = self.camera_bar[camera_num]
        bar['battery_var'].set(text)
        if low:
            bar['battery_label'].config(foreground="red", font=("Arial", 9, "bold"))
        else:
            bar['battery_label'].config(foreground="black", font=("Arial", 9))
    
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
        self.log_progress("Stopping recording...")

    def recording_worker(self, camera_list):
        """Background worker for recording process."""
        info = self._current_trial_info
        video_dir = info["video_dir"]
        trial_name = info["trial_name"]

        try:
            self.log_progress(f"Starting recording on cameras: {camera_list}")
            self.log_progress(f"Trial directory: {video_dir}")

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
                        self.log_progress(f"  GoPro {camera_num} recording started")
                    except Exception as e:
                        self.log_progress(f"  Failed to start GoPro {camera_num}: {e}")

            # Start timers after all cameras confirmed
            self.root.after(0, self.start_timer)
            self.root.after(0, self._start_bar_timer)

            # Play sync sound (1s delay + two claps) if enabled
            self._play_sync_sound()

            # Wait for stop signal
            while self.recording:
                time.sleep(0.5)

            # Stop recording and download files
            self.log_progress("Stopping cameras and downloading files...")

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
                        self.log_progress(f"  GoPro {camera_num} file downloaded")
                    except Exception as e:
                        self.log_progress(f"  Error downloading GoPro {camera_num}: {e}")

            self.log_progress("Recording complete. Starting audio synchronisation...")

            # Auto-sync
            self._auto_sync(info)

        except Exception as e:
            self.log_progress(f"Recording error: {e}")

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
            self.log_progress(f"Only {len(mp4_files)} video file(s) — skipping sync.")
            return

        try:
            # Check ffmpeg
            if not check_ffmpeg():
                self.log_progress("ffmpeg not found — skipping sync. Install with: conda install -c conda-forge ffmpeg")
                return

            video_paths = [str(f) for f in mp4_files]

            # Verify audio tracks
            for vp in video_paths:
                name = Path(vp).name
                if not check_audio_track(vp):
                    raise AudioSyncError(f"No audio track in: {name}")
                self.log_progress(f"  Audio confirmed: {name}")

            # Build camera positions for speed-of-sound compensation (if calibration loaded)
            cam_positions = None
            sound_pos = None
            if hasattr(self, 'calibration_tab'):
                cam_positions, sound_pos = self.calibration_tab._get_sync_compensation_data(video_paths)

            # Compute sync offsets (onset-based dual-clap detection)
            self.log_progress("Analysing audio for onset-based sync...")
            offsets = compute_sync_offsets(
                video_paths,
                output_dir=str(video_dir),
                progress_callback=lambda msg: self.log_progress(f"  {msg}"),
                camera_positions=cam_positions,
                sound_source_position=sound_pos,
            )

            # Check for warnings
            for path, info in offsets.items():
                if info.get("status") == "WARN":
                    name = Path(path).name
                    self.log_progress(
                        f"  WARNING: Inconsistent clap offsets for {name}. "
                        f"Consider re-recording with clearer claps.",
                        tag="warning")

            # Trim and sync videos
            self.log_progress("Trimming videos (stream copy, no re-encoding)...")
            output_files = trim_and_sync_videos(
                video_paths, offsets, str(video_dir),
                progress_callback=lambda msg: self.log_progress(f"  {msg}")
            )

            # Create stitched preview
            synced_dir = str(self.project_manager.get_trial_synced_path(project, session, trial_name))
            self.log_progress("Creating 2x2 stitched preview...")
            create_stitched_preview(
                synced_dir,
                progress_callback=lambda msg: self.log_progress(f"  {msg}")
            )

            # Update trial.json
            self.project_manager.update_trial(project, session, trial_name, synced=True)
            self.log_progress(
                f"Synchronisation complete! "
                f"{len(output_files)} synced files + stitched preview in synced/ folder")

        except Exception as e:
            self.log_progress(f"Sync error: {e}")
            try:
                self.project_manager.update_trial(project, session, trial_name, synced=False)
            except Exception:
                pass

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
        self.log_progress(f"Trial name updated to: {new_name}")

    def log_progress(self, message, tag=None):
        """Log a message to the progress text area (thread-safe)."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"

        def update_text():
            self.progress_text.config(state="normal")
            if tag:
                self.progress_text.insert(tk.END, log_message, tag)
            else:
                self.progress_text.insert(tk.END, log_message)
            self.progress_text.see(tk.END)
            self.progress_text.config(state="disabled")

        self.root.after(0, update_text)

    def on_closing(self):
        """Handle window close event with graceful cleanup"""
        
        # 1. Stop preview if active
        if self.preview_active:
            print("Closing window: Stopping active preview...")
            self.cleanup_preview()
        
        # 2. Stop recording if active (no user confirmation)
        if self.recording:
            print("Closing window: Stopping active recording...")
            self.recording = False
            # Wait briefly for recording thread to finish
            if self.recording_thread and self.recording_thread.is_alive():
                self.recording_thread.join(timeout=2.0)
        
        # 3. Disconnect all cameras
        if self.cameras:
            camera_list = list(self.cameras.keys())
            print(f"Closing window: Disconnecting cameras: {camera_list}")
            for camera_num in camera_list:
                self.disconnect_camera(camera_num)
        
        # 4. Save configuration
        self.save_camera_settings()
        
        # 5. Destroy window
        self.root.destroy()
