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
import concurrent.futures

# Add goproUSB to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'goproUSB'))
from goproUSB import GPcam

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
        
        # Recording state
        self.recording = False
        self.recording_thread = None
        self.start_time = None
        
        # Create GUI
        self.create_widgets()
        self.load_camera_settings()
        
        # Start status monitoring
        self.start_status_monitoring()
    
    def load_config(self):
        """Load configuration from JSON file"""
        default_config = {
            "cameras": {
                "1": {"serial": "C3501326042700", "lens": "Narrow", "resolution": "1080p", "fps": 30},
                "2": {"serial": "C3501326054100", "lens": "Narrow", "resolution": "1080p", "fps": 30},
                "3": {"serial": "C3501326054460", "lens": "Narrow", "resolution": "1080p", "fps": 30},
                "4": {"serial": "C3501326062418", "lens": "Narrow", "resolution": "1080p", "fps": 30}
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
        
        # Lens setting
        lens_frame = ttk.Frame(frame)
        lens_frame.pack(fill=tk.X, pady=3)
        ttk.Label(lens_frame, text="Lens:", width=10).pack(side=tk.LEFT)
        lens_var = tk.StringVar()
        lens_combo = ttk.Combobox(lens_frame, textvariable=lens_var, 
                                 values=["Narrow", "Linear", "Wide", "SuperView"], 
                                 state="readonly", width=15)
        lens_combo.pack(side=tk.RIGHT)
        frame.lens_var = lens_var
        
        # Resolution setting
        res_frame = ttk.Frame(frame)
        res_frame.pack(fill=tk.X, pady=3)
        ttk.Label(res_frame, text="Resolution:", width=10).pack(side=tk.LEFT)
        res_var = tk.StringVar()
        res_combo = ttk.Combobox(res_frame, textvariable=res_var,
                                values=["1080p", "1440p", "2.7K", "4K", "5K"],
                                state="readonly", width=15)
        res_combo.pack(side=tk.RIGHT)
        frame.res_var = res_var
        
        # FPS setting
        fps_frame = ttk.Frame(frame)
        fps_frame.pack(fill=tk.X, pady=3)
        ttk.Label(fps_frame, text="FPS:", width=10).pack(side=tk.LEFT)
        fps_var = tk.StringVar()
        fps_combo = ttk.Combobox(fps_frame, textvariable=fps_var,
                                values=["24", "25", "30", "50", "60", "120", "240"],
                                state="readonly", width=15)
        fps_combo.pack(side=tk.RIGHT)
        frame.fps_var = fps_var
        
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
        """Create the live preview tab (placeholder)"""
        self.preview_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.preview_frame, text="Live Preview")
        
        # Placeholder content
        placeholder_frame = ttk.Frame(self.preview_frame)
        placeholder_frame.pack(expand=True, fill=tk.BOTH)
        
        title_label = ttk.Label(placeholder_frame, text="Live Preview", 
                               font=("Arial", 16, "bold"))
        title_label.pack(pady=30)
        
        info_label = ttk.Label(placeholder_frame, 
                              text="Live preview functionality is currently unavailable\n"
                                   "due to network firewall constraints.\n\n"
                                   "Camera streaming has been confirmed (3.6 Mbps data flow),\n"
                                   "but UDP port access is blocked by corporate firewall.\n\n"
                                   "This feature will be implemented when\n"
                                   "streaming connectivity is resolved.",
                              justify=tk.CENTER,
                              font=("Arial", 11))
        info_label.pack(pady=20)
        
        # Camera selector (for future use)
        selector_frame = ttk.Frame(placeholder_frame)
        selector_frame.pack(pady=30)
        
        ttk.Label(selector_frame, text="Camera:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(0, 10))
        self.preview_camera_var = tk.StringVar(value="GoPro 1")
        preview_combo = ttk.Combobox(selector_frame, textvariable=self.preview_camera_var,
                                   values=["GoPro 1", "GoPro 2", "GoPro 3", "GoPro 4"],
                                   state="readonly", width=12)
        preview_combo.pack(side=tk.LEFT, padx=(0, 15))
        
        start_preview_btn = ttk.Button(selector_frame, text="▶ Start Preview", state="disabled")
        start_preview_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        stop_preview_btn = ttk.Button(selector_frame, text="⏹ Stop Preview", state="disabled")
        stop_preview_btn.pack(side=tk.LEFT)
        
        # Placeholder video area
        video_frame = ttk.LabelFrame(placeholder_frame, text="Video Display", padding=20)
        video_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=20)
        
        video_placeholder = tk.Label(video_frame, text="Preview video will appear here\nwhen streaming is available",
                                    bg="black", fg="white", font=("Arial", 12),
                                    width=60, height=20)
        video_placeholder.pack(expand=True, fill=tk.BOTH)
    
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
        """Connect to a specific camera"""
        try:
            panel = self.camera_panels[camera_num]
            serial = panel.serial_var.get()
            
            if not serial:
                messagebox.showerror("Error", f"Please enter serial number for GoPro {camera_num}")
                return
            
            self.log_progress(f"Connecting to GoPro {camera_num} ({serial})...")
            
            # Create camera instance
            camera = GPcam(serial)
            
            # Test connection
            response = camera.USBenable()
            if response.status_code == 200:
                time.sleep(1)
                response = camera.keepAlive()
                if response.status_code == 200:
                    self.cameras[camera_num] = camera
                    self.camera_status[camera_num] = True
                    self.update_camera_status(camera_num, True)
                    self.log_progress(f"✓ GoPro {camera_num} connected successfully")
                else:
                    raise Exception("Camera not responding to keep-alive")
            else:
                raise Exception("Failed to enable USB control")
                
        except Exception as e:
            self.log_progress(f"✗ Failed to connect GoPro {camera_num}: {e}")
            messagebox.showerror("Connection Error", f"Failed to connect GoPro {camera_num}:\n{e}")
    
    def disconnect_camera(self, camera_num):
        """Disconnect from a specific camera"""
        try:
            if camera_num in self.cameras:
                camera = self.cameras[camera_num]
                camera.USBdisable()
                del self.cameras[camera_num]
                self.camera_status[camera_num] = False
                self.update_camera_status(camera_num, False)
                self.log_progress(f"✓ GoPro {camera_num} disconnected")
        except Exception as e:
            self.log_progress(f"✗ Error disconnecting GoPro {camera_num}: {e}")
    
    def update_camera_status(self, camera_num, connected):
        """Update the visual status indicator for a camera"""
        panel = self.camera_panels[camera_num]
        color = "green" if connected else "red"
        outline_color = "darkgreen" if connected else "darkred"
        panel.status_canvas.itemconfig(panel.status_circle, fill=color, outline=outline_color)
    
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
        """Start recording on a single camera"""
        # Apply settings
        panel = self.camera_panels[camera_num]
        
        # Set video mode
        camera.modeVideo()
        time.sleep(1)
        
        # Apply lens setting
        lens = panel.lens_var.get()
        if lens == "Narrow":
            camera.setVideoLensesNarrow()
        elif lens == "Linear":
            camera.setVideoLensesLinear()
        elif lens == "Wide":
            camera.setVideoLensesWide()
        elif lens == "SuperView":
            camera.setVideoLensesSuperview()
        
        time.sleep(0.5)
        
        # Apply resolution
        resolution = panel.res_var.get()
        if resolution == "1080p":
            camera.setVideoResolution1080()
        elif resolution == "1440p":
            camera.setVideoResolution1440()
        elif resolution == "2.7K":
            camera.setVideoResolution2p7k()
        elif resolution == "4K":
            camera.setVideoResolution4k()
        elif resolution == "5K":
            camera.setVideoResolution5k()
        
        time.sleep(0.5)
        
        # Apply FPS
        fps = int(panel.fps_var.get())
        if fps == 24:
            camera.setFPS24()
        elif fps == 25:
            camera.setFPS25()
        elif fps == 30:
            camera.setFPS30()
        elif fps == 50:
            camera.setFPS50()
        elif fps == 60:
            camera.setFPS60()
        elif fps == 120:
            camera.setFPS120()
        elif fps == 240:
            camera.setFPS240()
        
        time.sleep(1)
        
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
