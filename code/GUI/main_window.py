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
    def __init__(self, root):
        self.root = root
        self.root.title("Go2Kin - Multi-Camera GoPro Control")
        self.root.geometry("900x700")
        
        # Configuration
        self.config_file = Path("config/cameras.json")
        self.config = self.load_config()
        
        # Camera instances
        self.cameras = {}
        self.camera_status = {}
        self.camera_references = {}  # Store settings reference per camera
        self.camera_profiles = {}     # Store profile per camera
        
        # Recording state
        self.recording = False
        self.recording_thread = None
        self.start_time = None
        
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
    
    def create_widgets(self):
        """Create the main GUI widgets"""
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Tab 1: Camera Settings
        self.create_camera_settings_tab()
        
        # Tab 2: Live Preview (placeholder)
        self.create_live_preview_tab()
        
        # Tab 3: Recording
        self.create_recording_tab()
    
    def create_camera_settings_tab(self):
        """Create the camera settings tab"""
        self.camera_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.camera_frame, text="Camera Settings")
        
        # Title
        title_label = ttk.Label(self.camera_frame, text="Camera Configuration", 
                               font=("Arial", 16, "bold"))
        title_label.pack(pady=15)
        
        # Camera grid frame
        grid_frame = ttk.Frame(self.camera_frame)
        grid_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Configure grid weights
        for i in range(2):
            grid_frame.columnconfigure(i, weight=1)
        for i in range(2):
            grid_frame.rowconfigure(i, weight=1)
        
        # Camera panels
        self.camera_panels = {}
        positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
        
        for i, (row, col) in enumerate(positions, 1):
            panel = self.create_camera_panel(grid_frame, i)
            panel.grid(row=row, column=col, padx=15, pady=15, sticky="nsew")
            self.camera_panels[i] = panel
    
    def create_camera_panel(self, parent, camera_num):
        """Create a single camera configuration panel"""
        # Main frame with border
        frame = ttk.LabelFrame(parent, text=f"GoPro {camera_num}", padding=15)
        
        # Status indicator
        status_frame = ttk.Frame(frame)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        status_label = ttk.Label(status_frame, text="Status:", font=("Arial", 10, "bold"))
        status_label.pack(side=tk.LEFT)
        
        # Status indicator (circle)
        status_canvas = tk.Canvas(status_frame, width=24, height=24)
        status_canvas.pack(side=tk.LEFT, padx=(8, 0))
        status_circle = status_canvas.create_oval(2, 2, 22, 22, fill="red", outline="darkred", width=2)
        
        # Store references
        frame.status_canvas = status_canvas
        frame.status_circle = status_circle
        
        # Serial number
        serial_frame = ttk.Frame(frame)
        serial_frame.pack(fill=tk.X, pady=3)
        ttk.Label(serial_frame, text="Serial:", width=10).pack(side=tk.LEFT)
        serial_var = tk.StringVar()
        serial_entry = ttk.Entry(serial_frame, textvariable=serial_var, width=18)
        serial_entry.pack(side=tk.RIGHT)
        frame.serial_var = serial_var
        
        # Lens setting (fixed to Linear)
        lens_frame = ttk.Frame(frame)
        lens_frame.pack(fill=tk.X, pady=3)
        ttk.Label(lens_frame, text="Lens:", width=10).pack(side=tk.LEFT)
        lens_var = tk.StringVar(value="Linear")
        lens_combo = ttk.Combobox(lens_frame, textvariable=lens_var, 
                                 values=["Linear"], 
                                 state="disabled", width=15)
        lens_combo.pack(side=tk.RIGHT)
        frame.lens_var = lens_var
        
        # Resolution setting
        res_frame = ttk.Frame(frame)
        res_frame.pack(fill=tk.X, pady=3)
        ttk.Label(res_frame, text="Resolution:", width=10).pack(side=tk.LEFT)
        res_var = tk.StringVar()
        res_combo = ttk.Combobox(res_frame, textvariable=res_var,
                                values=["1080", "2.7K", "4K"],
                                state="readonly", width=15)
        res_combo.pack(side=tk.RIGHT)
        frame.res_var = res_var
        frame.res_combo = res_combo  # Store reference to combobox
        
        # FPS setting
        fps_frame = ttk.Frame(frame)
        fps_frame.pack(fill=tk.X, pady=3)
        ttk.Label(fps_frame, text="FPS:", width=10).pack(side=tk.LEFT)
        fps_var = tk.StringVar()
        fps_combo = ttk.Combobox(fps_frame, textvariable=fps_var,
                                values=["25", "50", "100", "200"],
                                state="readonly", width=15)
        fps_combo.pack(side=tk.RIGHT)
        frame.fps_var = fps_var
        frame.fps_combo = fps_combo  # Store reference to combobox
        
        # Connect/Disconnect buttons
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=(15, 0))
        
        connect_btn = ttk.Button(button_frame, text="Connect",
                               command=lambda: self.connect_camera(camera_num))
        connect_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        disconnect_btn = ttk.Button(button_frame, text="Disconnect",
                                  command=lambda: self.disconnect_camera(camera_num))
        disconnect_btn.pack(side=tk.LEFT)
        
        frame.connect_btn = connect_btn
        frame.disconnect_btn = disconnect_btn
        
        return frame
    
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
    
    def create_recording_tab(self):
        """Create the recording tab"""
        self.recording_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.recording_frame, text="Recording")
        
        # Title
        title_label = ttk.Label(self.recording_frame, text="Multi-Camera Recording", 
                               font=("Arial", 16, "bold"))
        title_label.pack(pady=15)
        
        # Configuration section
        config_frame = ttk.LabelFrame(self.recording_frame, text="Recording Configuration", padding=15)
        config_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # Output directory
        dir_frame = ttk.Frame(config_frame)
        dir_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(dir_frame, text="Output Directory:", width=15).pack(side=tk.LEFT)
        self.output_dir_var = tk.StringVar(value=self.config["recording"]["output_directory"])
        dir_entry = ttk.Entry(dir_frame, textvariable=self.output_dir_var, width=50)
        dir_entry.pack(side=tk.LEFT, padx=(10, 8), fill=tk.X, expand=True)
        
        browse_btn = ttk.Button(dir_frame, text="📁 Browse", command=self.browse_output_dir)
        browse_btn.pack(side=tk.RIGHT)
        
        # Trial name
        trial_frame = ttk.Frame(config_frame)
        trial_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(trial_frame, text="Trial Name:", width=15).pack(side=tk.LEFT)
        self.trial_name_var = tk.StringVar(value=self.config["recording"]["last_trial_name"])
        trial_entry = ttk.Entry(trial_frame, textvariable=self.trial_name_var, width=30)
        trial_entry.pack(side=tk.LEFT, padx=(10, 0))
        
        # Camera selection
        selection_frame = ttk.LabelFrame(self.recording_frame, text="Camera Selection", padding=15)
        selection_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.camera_selection_vars = {}
        for i in range(1, 5):
            var = tk.BooleanVar(value=True)
            checkbox = ttk.Checkbutton(selection_frame, text=f"GoPro {i}", variable=var)
            checkbox.pack(side=tk.LEFT, padx=15)
            self.camera_selection_vars[i] = var
        
        # Recording controls
        control_frame = ttk.Frame(self.recording_frame)
        control_frame.pack(pady=25)
        
        self.start_recording_btn = ttk.Button(control_frame, text="🔴 START RECORDING",
                                            command=self.start_recording)
        self.start_recording_btn.pack(side=tk.LEFT, padx=(0, 15))
        
        self.stop_recording_btn = ttk.Button(control_frame, text="⏹ STOP",
                                           command=self.stop_recording,
                                           state="disabled")
        self.stop_recording_btn.pack(side=tk.LEFT, padx=(0, 15))
        
        # Timer display
        self.timer_var = tk.StringVar(value="Timer: 00:00:00")
        timer_label = ttk.Label(control_frame, textvariable=self.timer_var, 
                               font=("Arial", 14, "bold"))
        timer_label.pack(side=tk.LEFT, padx=(15, 0))
        
        # Progress area
        progress_frame = ttk.LabelFrame(self.recording_frame, text="Progress Log", padding=10)
        progress_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Create text widget with scrollbar
        text_frame = ttk.Frame(progress_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.progress_text = tk.Text(text_frame, height=10, state="disabled", 
                                   font=("Consolas", 9), wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.progress_text.yview)
        self.progress_text.configure(yscrollcommand=scrollbar.set)
        
        self.progress_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Open folder button
        self.open_folder_btn = ttk.Button(self.recording_frame, text="📁 Open Output Folder",
                                        command=self.open_output_folder, state="disabled")
        self.open_folder_btn.pack(pady=15)
    
    def load_camera_settings(self):
        """Load camera settings from config into GUI"""
        for i in range(1, 5):
            if str(i) in self.config["cameras"]:
                camera_config = self.config["cameras"][str(i)]
                panel = self.camera_panels[i]
                
                panel.serial_var.set(camera_config["serial"])
                panel.lens_var.set(camera_config["lens"])
                panel.res_var.set(camera_config["resolution"])
                panel.fps_var.set(str(camera_config["fps"]))
    
    def save_camera_settings(self):
        """Save current camera settings to config"""
        for i in range(1, 5):
            panel = self.camera_panels[i]
            self.config["cameras"][str(i)] = {
                "serial": panel.serial_var.get(),
                "lens": panel.lens_var.get(),
                "resolution": panel.res_var.get(),
                "fps": int(panel.fps_var.get()) if panel.fps_var.get().isdigit() else 30
            }
        
        self.config["recording"]["output_directory"] = self.output_dir_var.get()
        self.config["recording"]["last_trial_name"] = self.trial_name_var.get()
        
        self.save_config()
    
    def connect_camera(self, camera_num):
        """Connect to a specific camera with profile management"""
        try:
            panel = self.camera_panels[camera_num]
            serial = panel.serial_var.get()
            
            if not serial:
                messagebox.showerror("Error", f"Please enter serial number for GoPro {camera_num}")
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
                
        except Exception as e:
            self.log_progress(f"✗ Failed to connect GoPro {camera_num}: {e}")
            messagebox.showerror("Connection Error", f"Failed to connect GoPro {camera_num}:\n{e}")
    
    def populate_dropdowns_from_profile(self, camera_num, profile):
        """Set dropdown current values from camera profile and bind change handlers"""
        panel = self.camera_panels[camera_num]

        # Set current resolution from profile
        if '2' in profile['current_settings']:
            current_res = profile['current_settings']['2']['value_name']
            panel.res_var.set(current_res)
            self.log_progress(f"  Resolution: {current_res}")

        # Set current FPS from profile
        if '3' in profile['current_settings']:
            current_fps = profile['current_settings']['3']['value_name']
            panel.fps_var.set(current_fps)
            self.log_progress(f"  FPS: {current_fps}")

        # Bind change handlers
        panel.res_combo.bind('<<ComboboxSelected>>',
                            lambda e, cn=camera_num: self.on_resolution_change(cn))
        panel.fps_combo.bind('<<ComboboxSelected>>',
                            lambda e, cn=camera_num: self.on_fps_change(cn))
    
    def on_resolution_change(self, camera_num):
        """Handle resolution dropdown change"""
        if camera_num not in self.cameras or camera_num not in self.camera_references:
            return
        
        panel = self.camera_panels[camera_num]
        new_value = panel.res_var.get()
        
        self.log_progress(f"Applying resolution change: {new_value}")
        self.apply_setting_to_camera(camera_num, 2, new_value, "Video Resolution")
    
    def on_fps_change(self, camera_num):
        """Handle FPS dropdown change"""
        if camera_num not in self.cameras or camera_num not in self.camera_references:
            return
        
        panel = self.camera_panels[camera_num]
        new_value = panel.fps_var.get()
        
        self.log_progress(f"Applying FPS change: {new_value}")
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
                        panel = self.camera_panels[camera_num]
                        if setting_id == 2:
                            panel.res_var.set(old_value)
                        elif setting_id == 3:
                            panel.fps_var.set(old_value)
                
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
        panel = self.camera_panels[camera_num]
        color = "green" if connected else "red"
        outline_color = "darkgreen" if connected else "darkred"
        panel.status_canvas.itemconfig(panel.status_circle, fill=color, outline=outline_color)
        
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
        """Start background thread for status monitoring"""
        def monitor_status():
            while True:
                for camera_num in list(self.cameras.keys()):
                    try:
                        camera = self.cameras[camera_num]
                        response = camera.keepAlive()
                        if response.status_code != 200:
                            self.camera_status[camera_num] = False
                            self.root.after(0, lambda cn=camera_num: self.update_camera_status(cn, False))
                    except:
                        self.camera_status[camera_num] = False
                        self.root.after(0, lambda cn=camera_num: self.update_camera_status(cn, False))
                
                time.sleep(30)  # Check every 30 seconds
        
        monitor_thread = threading.Thread(target=monitor_status, daemon=True)
        monitor_thread.start()
    
    def browse_output_dir(self):
        """Browse for output directory"""
        directory = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if directory:
            self.output_dir_var.set(directory)
    
    def start_recording(self):
        """Start multi-camera recording"""
        if self.recording:
            return
        
        # Get selected cameras
        selected_cameras = [i for i in range(1, 5) if self.camera_selection_vars[i].get()]
        available_cameras = [i for i in selected_cameras if i in self.cameras and self.camera_status.get(i, False)]
        
        if not available_cameras:
            messagebox.showerror("Error", "No cameras are connected and selected for recording")
            return
        
        # Save settings
        self.save_camera_settings()
        
        # Start recording in background thread
        self.recording = True
        self.recording_thread = threading.Thread(target=self.recording_worker, args=(available_cameras,))
        self.recording_thread.start()
        
        # Update UI
        self.start_recording_btn.config(state="disabled")
        self.stop_recording_btn.config(state="normal")
        self.start_timer()
    
    def stop_recording(self):
        """Stop multi-camera recording"""
        self.recording = False
        self.stop_recording_btn.config(state="disabled")
        self.log_progress("🛑 Stopping recording...")
    
    def recording_worker(self, camera_list):
        """Background worker for recording process"""
        try:
            self.log_progress(f"🎬 Starting recording on cameras: {camera_list}")
            
            # Create trial directory using exact name from text box (no auto-increment)
            trial_name = self.trial_name_var.get()
            output_dir = Path(self.output_dir_var.get())
            trial_dir = output_dir / trial_name
            
            # Create the trial directory (overwrite if exists)
            trial_dir.mkdir(parents=True, exist_ok=True)
            
            self.log_progress(f"📁 Using trial directory: {trial_dir}")
            
            # Apply settings and start recording
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                # Start recording on all cameras
                futures = []
                for camera_num in camera_list:
                    camera = self.cameras[camera_num]
                    future = executor.submit(self.start_camera_recording, camera_num, camera)
                    futures.append((camera_num, future))
                
                # Wait for all to start
                for camera_num, future in futures:
                    try:
                        future.result(timeout=15)
                        self.log_progress(f"✓ GoPro {camera_num} recording started")
                    except Exception as e:
                        self.log_progress(f"✗ Failed to start recording on GoPro {camera_num}: {e}")
            
            # Wait for stop signal
            while self.recording:
                time.sleep(0.5)
            
            # Stop recording and download files
            self.log_progress("⏬ Stopping cameras and downloading files...")
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = []
                for camera_num in camera_list:
                    if camera_num in self.cameras:
                        camera = self.cameras[camera_num]
                        future = executor.submit(self.stop_and_download, camera_num, camera, trial_dir, trial_name)
                        futures.append((camera_num, future))
                
                # Wait for all downloads
                for camera_num, future in futures:
                    try:
                        future.result(timeout=300)  # 5 minute timeout for download
                        self.log_progress(f"✓ GoPro {camera_num} file downloaded successfully")
                    except Exception as e:
                        self.log_progress(f"✗ Error downloading from GoPro {camera_num}: {e}")
            
            self.log_progress("🎉 Recording session completed!")
            
        except Exception as e:
            self.log_progress(f"✗ Recording error: {e}")
        
        finally:
            # Reset UI
            self.root.after(0, self.reset_recording_ui)
    
    def start_camera_recording(self, camera_num, camera):
        """Start recording on a single camera with settings from profile"""
        
        # Get camera profile
        if camera_num not in self.camera_profiles:
            # No profile - just start recording with current settings
            camera.shutterStart()
            return
        
        profile = self.camera_profiles[camera_num]
        
        # Ensure video mode
        camera.modeVideo()
        time.sleep(0.5)
        
        # Apply resolution from profile (setting ID 2)
        if '2' in profile['current_settings']:
            res_setting = profile['current_settings']['2']
            camera.setSetting(2, res_setting['value'])
            time.sleep(0.3)
        
        # Apply FPS from profile (setting ID 3)
        if '3' in profile['current_settings']:
            fps_setting = profile['current_settings']['3']
            camera.setSetting(3, fps_setting['value'])
            time.sleep(0.3)
        
        # Apply lens from profile (setting ID 121 for video)
        if '121' in profile['current_settings']:
            lens_setting = profile['current_settings']['121']
            camera.setSetting(121, lens_setting['value'])
            time.sleep(0.3)
        
        # Apply zoom from profile
        saved_zoom = profile.get('current_zoom', 0)
        camera.setDigitalZoom(saved_zoom)
        time.sleep(0.3)
        
        # Start recording
        camera.shutterStart()
    
    def stop_and_download(self, camera_num, camera, trial_dir, trial_name):
        """Stop recording and download file from a single camera"""
        # Stop recording
        camera.shutterStop()
        
        # Wait for encoding to finish
        while camera.camBusy() or camera.encodingActive():
            time.sleep(0.5)

        # Download file to the shared trial directory
        filename = trial_dir / f"{trial_name}_GP{camera_num}.mp4"
        camera.mediaDownloadLast(str(filename))
        
        # Delete files from camera
        camera.deleteAllFiles()
    
    def start_timer(self):
        """Start the recording timer"""
        self.start_time = time.time()
        self.update_timer()
    
    def update_timer(self):
        """Update the recording timer display"""
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
        """Reset recording UI after completion"""
        self.start_recording_btn.config(state="normal")
        self.stop_recording_btn.config(state="disabled")
        self.open_folder_btn.config(state="normal")
        self.timer_var.set("Timer: 00:00:00")
        
        # Auto-increment trial name for next recording
        self.increment_trial_name()
    
    def increment_trial_name(self):
        """Auto-increment trial name for next recording"""
        current_name = self.trial_name_var.get()
        
        # Check if name already has a suffix (e.g., "walking_001")
        if '_' in current_name and current_name.split('_')[-1].isdigit():
            # Extract base name and current number
            parts = current_name.rsplit('_', 1)
            base_name = parts[0]
            current_num = int(parts[1])
            new_name = f"{base_name}_{current_num + 1:03d}"
        else:
            # No suffix yet, add _001
            new_name = f"{current_name}_001"
        
        # Update the trial name text box
        self.trial_name_var.set(new_name)
        self.log_progress(f"ℹ️ Trial name updated to: {new_name}")
    
    def log_progress(self, message):
        """Log a message to the progress text area"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        
        def update_text():
            self.progress_text.config(state="normal")
            self.progress_text.insert(tk.END, log_message)
            self.progress_text.see(tk.END)
            self.progress_text.config(state="disabled")
        
        self.root.after(0, update_text)
    
    def open_output_folder(self):
        """Open the output folder in file explorer"""
        import subprocess
        import os
        
        output_dir = self.output_dir_var.get()
        if os.path.exists(output_dir):
            subprocess.Popen(f'explorer "{output_dir}"')
        else:
            messagebox.showerror("Error", "Output directory does not exist")
    
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
