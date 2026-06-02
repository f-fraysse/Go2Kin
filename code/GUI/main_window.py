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
from pathlib import Path
from datetime import datetime

# Add goproUSB to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'goproUSB'))
from goproUSB import GPcam

# Add code directory to path for camera_profiles
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from camera_profiles import get_profile_manager

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
        
        # Create GUI
        self.create_widgets()
        self.load_camera_settings()

        # Auto-load last calibration and refresh top bar status
        self.calibration_tab.auto_load_calibration()
        self.top_bar.refresh_calibration_status()

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
        if hasattr(self, "top_bar"):
            return self.top_bar.get_current_project()
        return None

    def get_current_session(self):
        """Return the currently selected session name, or None."""
        if hasattr(self, "top_bar"):
            return self.top_bar.get_current_session()
        return None

    def get_current_participant(self):
        """Return the currently selected participant ID, or None."""
        if hasattr(self, "top_bar"):
            return self.top_bar.get_current_participant()
        return None

    def create_widgets(self):
        """Create the main GUI widgets"""
        # Fixed bottom bar (packed first so it stays at the bottom)
        self.create_camera_bottom_bar()

        # Log placeholder panel (above camera bar)
        self.create_log_panel()

        # Persistent top bar (project/session/participant selection)
        self.create_top_bar()

        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        # Tab 0: Live Preview
        self.create_live_preview_tab()

        # Tab 1: Calibration
        self.create_calibration_tab()

        # Tab 2: Recording
        self.create_recording_tab()

        # Tab 3: Processing
        self.create_processing_tab()

        # Tab 4: Visualisation
        self.create_visualisation_tab()

        # Start on Calibration tab
        self.notebook.select(1)

        # Bind tab change to refresh tabs
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
    
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

        self.sync_method_var = tk.StringVar(value="manual")
        ttk.Label(settings_frame, text="Sync:").pack(side=tk.LEFT, padx=(0, 3))
        ttk.Radiobutton(settings_frame, text="Manual", variable=self.sync_method_var,
                         value="manual").pack(side=tk.LEFT, padx=(0, 3))
        ttk.Radiobutton(settings_frame, text="Speaker", variable=self.sync_method_var,
                         value="speaker").pack(side=tk.LEFT, padx=(0, 12))

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

    def create_log_panel(self):
        """Create a placeholder log panel above the camera bar"""
        log_frame = ttk.LabelFrame(self.root, text="Log", padding=(8, 4))
        log_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 2))

        # Filter labels (visual only — no functionality yet)
        header = ttk.Frame(log_frame)
        header.pack(fill=tk.X, pady=(0, 2))
        for label_text in ["Cal", "Rec", "Proc"]:
            btn = ttk.Label(header, text=f"[{label_text}]", font=("Arial", 8),
                            foreground="grey")
            btn.pack(side=tk.LEFT, padx=(0, 4))

        # Placeholder text area
        self.log_text = tk.Text(log_frame, height=3, state="disabled",
                                bg="#f0f0f0", fg="#888888", relief="flat",
                                font=("Consolas", 9))
        self.log_text.configure(state="normal")
        self.log_text.insert("1.0", "Output is shown in the terminal")
        self.log_text.configure(state="disabled")

    def toggle_camera_connection(self, camera_num):
        """Toggle connect/disconnect for a camera"""
        if self.camera_status.get(camera_num, False):
            self.disconnect_camera(camera_num)
        else:
            self.connect_camera(camera_num)
    
    def create_live_preview_tab(self):
        """Create the live preview tab (delegated to LivePreviewTab)"""
        from GUI.live_preview_tab import LivePreviewTab
        self.live_preview_tab = LivePreviewTab(
            self.notebook, self.cameras, self.camera_status, self.camera_profiles
        )
    
    def create_top_bar(self):
        """Create the persistent top bar with project/session/participant selection."""
        from GUI.top_bar import TopBar
        self.top_bar = TopBar(
            self.root, self.project_manager,
            self.app_config, self.save_app_config,
            on_selection_changed=self._on_top_bar_changed,
        )

    def create_calibration_tab(self):
        """Create the calibration tab"""
        from GUI.calibration_tab import CalibrationTab
        self.calibration_tab = CalibrationTab(
            self.notebook, self.config,
            cameras=self.cameras,
            camera_status=self.camera_status,
            project_manager=self.project_manager,
            get_current_project=lambda: self.top_bar.get_current_project(),
            is_recording=lambda: self.recording_tab.recording,
            run_rec_delay=lambda: self.recording_tab._run_rec_delay(),
            start_bar_timer=lambda: self.recording_tab._start_bar_timer(),
            stop_bar_timer=lambda: self.recording_tab._stop_bar_timer(),
            play_sync_sound=lambda: self.recording_tab._play_sync_sound(),
            app_config=self.app_config,
            save_app_config=self.save_app_config,
            on_calibration_saved=lambda: self.top_bar.refresh_calibration_status(),
            sync_method_var=self.sync_method_var,
        )

    def create_processing_tab(self):
        """Create the Pose2Sim processing tab"""
        from GUI.processing_tab import ProcessingTab
        self.processing_tab = ProcessingTab(
            self.notebook, self.project_manager,
            get_current_project=lambda: self.top_bar.get_current_project(),
            get_current_session=lambda: self.top_bar.get_current_session(),
        )

    def create_visualisation_tab(self):
        """Create the visualisation/playback tab"""
        from GUI.visualisation_tab import VisualisationTab
        self.visualisation_tab = VisualisationTab(
            self.notebook, self.project_manager,
            get_current_project=lambda: self.top_bar.get_current_project(),
            get_current_session=lambda: self.top_bar.get_current_session(),
        )

    def create_recording_tab(self):
        """Create the recording tab (delegated to RecordingTab)"""
        from GUI.recording_tab import RecordingTab
        self.recording_tab = RecordingTab(
            self.notebook, self.config,
            self.cameras, self.camera_status, self.camera_serials,
            self.project_manager, self.app_config,
            get_current_project=lambda: self.top_bar.get_current_project(),
            get_current_session=lambda: self.top_bar.get_current_session(),
            get_current_participant=lambda: self.top_bar.get_current_participant(),
            save_camera_settings=self.save_camera_settings,
            save_app_config=self.save_app_config,
            get_calibration_tab=lambda: self.calibration_tab if hasattr(self, 'calibration_tab') else None,
            rec_delay_enabled=self.rec_delay_enabled,
            rec_delay_seconds=self.rec_delay_seconds,
            rec_delay_countdown_label=self.rec_delay_countdown_label,
            sync_method_var=self.sync_method_var,
        )
    
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

        if hasattr(self, 'recording_tab'):
            self.config["recording"]["last_trial_name"] = self.recording_tab.trial_name_var.get()

        self.save_config()
    
    def _on_tab_changed(self, event):
        """Refresh tab contents when switching tabs."""
        self._refresh_active_tab()

    def _on_top_bar_changed(self):
        """Called when project or session changes in the top bar."""
        self._refresh_active_tab()

    def _refresh_active_tab(self):
        """Refresh the currently visible tab's data."""
        try:
            tab_id = self.notebook.select()
            if hasattr(self, 'recording_tab') and tab_id == str(self.recording_tab.frame):
                self.recording_tab.refresh_recording_dropdowns()
            elif hasattr(self, 'processing_tab') and tab_id == str(self.processing_tab.frame):
                self.processing_tab.refresh()
            elif hasattr(self, 'visualisation_tab') and tab_id == str(self.visualisation_tab.frame):
                self.visualisation_tab.refresh()
        except Exception:
            pass

    def connect_camera(self, camera_num):
        """Connect to a specific camera with profile management"""
        try:
            serial = self.camera_serials.get(camera_num, "")

            if not serial:
                messagebox.showerror("Error", f"No serial number configured for GoPro {camera_num} in go2kin_config.json")
                return
            
            print(f"Connecting to GoPro {camera_num} ({serial})...")
            
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
            
            print(f"✓ Camera connected, querying camera info...")
            
            # Get camera info (model, firmware, serial)
            info_response = camera.getCameraInfo()
            if info_response.status_code != 200:
                raise Exception("Failed to get camera info")
            
            camera_info = info_response.json()
            model = camera_info['model_name']
            firmware = camera_info['firmware_version']
            
            print(f"  Model: {model}, Firmware: {firmware}")
            
            # Get profile manager
            profile_mgr = get_profile_manager()
            
            # Load existing profile to check for saved zoom level
            existing_profile = profile_mgr.load_camera_profile(serial)
            saved_zoom = None
            if existing_profile and 'current_zoom' in existing_profile:
                saved_zoom = existing_profile.get('current_zoom', 0)
                if saved_zoom > 0:
                    print(f"  Found saved zoom level: {saved_zoom}%")
            
            # Check if we have a settings reference for this model/firmware
            reference = profile_mgr.load_settings_reference(model, firmware)
            
            if reference is None:
                print(f"⚠ No settings reference found for {model} {firmware}")
                print(f"  Run: python tools/discover_camera_settings.py {serial}")
                messagebox.showwarning(
                    "Settings Reference Missing",
                    f"No settings reference found for {model} (firmware {firmware}).\n\n"
                    f"To enable full settings management, run:\n"
                    f"python tools/discover_camera_settings.py {serial}\n\n"
                    f"Camera will still connect, but settings display will be limited."
                )
                # Continue without reference - basic functionality still works
            else:
                print(f"✓ Loaded settings reference for {model} {firmware}")
            
            # Force video mode to ensure video settings are available
            print(f"  Setting camera to video mode...")
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
                        print(f"  Setting {name} to {value_desc}...")
                        camera.setSetting(setting_id, option_id)
                        time.sleep(0.3)
                    else:
                        print(f"  {name} already {value_desc}")

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
                            print(f"  Restoring {name} to {saved['value_name']}...")
                            camera.setSetting(int(setting_id), saved_value)
                            time.sleep(0.3)
                        else:
                            print(f"  {name} already {saved['value_name']}")

            # Get current camera state
            state_response = camera.getState()
            if state_response.status_code != 200:
                raise Exception("Failed to get camera state")
            
            state = state_response.json()
            
            # Query current zoom level (status ID 75)
            current_zoom = state['status'].get('75', 0)  # Default to 0 if not found
            print(f"  Current zoom: {current_zoom}%")
            
            # Restore saved zoom level if available and different from current
            if saved_zoom is not None and saved_zoom > 0 and saved_zoom != current_zoom:
                print(f"  Restoring saved zoom level: {saved_zoom}%...")
                try:
                    response = camera.setDigitalZoom(saved_zoom)
                    if response.status_code == 200:
                        current_zoom = saved_zoom  # Update to restored value
                        print(f"  ✓ Zoom restored to {saved_zoom}%")
                    else:
                        print(f"  ⚠ Failed to restore zoom (status: {response.status_code})")
                except Exception as zoom_err:
                    print(f"  ⚠ Failed to restore zoom: {zoom_err}")
            
            # Create or update camera profile
            profile = None
            if reference:
                profile = profile_mgr.create_or_update_profile(camera_info, state, reference)
                
                # Add zoom level to profile
                profile['current_zoom'] = current_zoom
                
                print(f"✓ Camera profile updated")
                
                # Store reference and profile for this camera
                self.camera_references[camera_num] = reference
                self.camera_profiles[camera_num] = profile
                
                # Log some current settings
                if '2' in profile['current_settings']:  # Video Resolution
                    res_setting = profile['current_settings']['2']
                    print(f"  Current resolution: {res_setting['value_name']}")
                if '3' in profile['current_settings']:  # FPS
                    fps_setting = profile['current_settings']['3']
                    print(f"  Current FPS: {fps_setting['value_name']}")
                
                # Populate dropdowns from profile
                self.populate_dropdowns_from_profile(camera_num, profile)
                
                # Save profile with zoom level
                profile_mgr.save_camera_profile(serial, profile)
            
            # Store camera instance
            self.cameras[camera_num] = camera
            self.camera_status[camera_num] = True
            self.update_camera_status(camera_num, True)
            
            print(f"✓ GoPro {camera_num} connected successfully")

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
            print(f"✗ Failed to connect GoPro {camera_num}: {e}")
            messagebox.showerror("Connection Error", f"Failed to connect GoPro {camera_num}:\n{e}")
    
    def populate_dropdowns_from_profile(self, camera_num, profile):
        """Set global dropdown values from camera profile"""
        # Set current resolution from profile
        if '2' in profile['current_settings']:
            current_res = profile['current_settings']['2']['value_name']
            self.global_res_var.set(current_res)
            print(f"  Resolution: {current_res}")

        # Set current FPS from profile
        if '3' in profile['current_settings']:
            current_fps = profile['current_settings']['3']['value_name']
            self.global_fps_var.set(current_fps)
            print(f"  FPS: {current_fps}")

    def on_global_resolution_change(self, event=None):
        """Handle global resolution dropdown change — apply to all connected cameras"""
        new_value = self.global_res_var.get()
        print(f"Applying resolution {new_value} to all cameras...")
        for camera_num in list(self.cameras.keys()):
            if camera_num in self.camera_references:
                self.apply_setting_to_camera(camera_num, 2, new_value, "Video Resolution")

    def on_global_fps_change(self, event=None):
        """Handle global FPS dropdown change — apply to all connected cameras"""
        new_value = self.global_fps_var.get()
        print(f"Applying FPS {new_value} to all cameras...")
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
                print(f"✓ {setting_name} set to: {display_name}")

                # Re-apply zoom in case the setting change reset it
                if camera_num in self.camera_profiles:
                    saved_zoom = self.camera_profiles[camera_num].get('current_zoom', 0)
                    if saved_zoom > 0:
                        try:
                            camera.setDigitalZoom(saved_zoom)
                            time.sleep(0.2)
                        except Exception as e:
                            print(f"  ⚠ Note: Zoom may have been reset by setting change")
                
            elif response.status_code == 403:
                # Invalid option - log details and show available options
                try:
                    error_data = response.json()
                    error_code = error_data.get('error', 'unknown')
                    print(f"  Setting rejected (error code {error_code}): {error_data}")
                    available_options = error_data.get('supported_options', error_data.get('available_options', []))
                    self.show_invalid_setting_dialog(setting_name, available_options)
                except Exception as e:
                    print(f"  Failed to parse 403 response: {e}")
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
            print(f"✗ Failed to apply {setting_name}: {e}")
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
            print(f"⚠ Error updating profile: {e}")
    
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
                
                print(f"✓ GoPro {camera_num} disconnected")
        except Exception as e:
            print(f"✗ Error disconnecting GoPro {camera_num}: {e}")
    
    def update_camera_status(self, camera_num, connected):
        """Update the visual status indicator for a camera"""
        bar = self.camera_bar[camera_num]
        color = "green" if connected else "red"
        outline_color = "darkgreen" if connected else "darkred"
        bar['status_canvas'].itemconfig(bar['status_circle'], fill=color, outline=outline_color)
        bar['connect_btn'].config(text="Disconnect" if connected else "Connect")
        if not connected:
            bar['battery_var'].set("\u2014")

        # Update calibration tab camera checkboxes
        if hasattr(self, 'calibration_tab'):
            self.calibration_tab.update_camera_checkboxes(camera_num, connected)

        # Update preview camera dropdown when camera status changes
        if hasattr(self, 'live_preview_tab'):
            self.live_preview_tab.update_preview_camera_dropdown()

    
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
    
    def on_closing(self):
        """Handle window close event with graceful cleanup"""
        
        # 1. Stop preview if active
        if hasattr(self, 'live_preview_tab') and self.live_preview_tab.preview_active:
            print("Closing window: Stopping active preview...")
            self.live_preview_tab.cleanup_preview()
        
        # 2. Stop recording if active (no user confirmation)
        if hasattr(self, 'recording_tab') and self.recording_tab.recording:
            print("Closing window: Stopping active recording...")
            self.recording_tab.recording = False
            # Wait briefly for recording thread to finish
            if self.recording_tab.recording_thread and self.recording_tab.recording_thread.is_alive():
                self.recording_tab.recording_thread.join(timeout=2.0)
        
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
