#!/usr/bin/env python3
"""
Go2Kin - Live Preview Tab
Camera live preview with zoom controls
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import queue
import cv2
from pathlib import Path
from PIL import Image, ImageTk

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


class LivePreviewTab:
    """Live Preview tab — camera streaming with zoom controls."""

    def __init__(self, notebook, cameras, camera_status, camera_profiles):
        self.notebook = notebook
        self.root = notebook.winfo_toplevel()
        self.cameras = cameras
        self.camera_status = camera_status
        self.camera_profiles = camera_profiles

        # Preview state
        self.preview_active = False
        self.preview_capture = None
        self.preview_camera_num = None
        self.preview_update_job = None

        # Build UI
        self.frame = ttk.Frame(notebook)
        notebook.add(self.frame, text="Live Preview")
        self._create_widgets()
        self.update_preview_camera_dropdown()

    def _create_widgets(self):
        """Create the live preview tab UI"""
        # Compact control bar - all controls on one line
        control_bar = ttk.Frame(self.frame)
        control_bar.pack(fill=tk.X, padx=10, pady=5)

        # Left side: Preview controls
        preview_controls = ttk.Frame(control_bar)
        preview_controls.pack(side=tk.LEFT)

        ttk.Label(preview_controls, text="Camera:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 5))
        self.preview_camera_var = tk.StringVar()
        self.preview_combo = ttk.Combobox(preview_controls, textvariable=self.preview_camera_var,
                                         state="readonly", width=10)
        self.preview_combo.pack(side=tk.LEFT, padx=(0, 8))

        self.start_preview_btn = ttk.Button(preview_controls, text="\u25b6 Start",
                                          command=self.start_preview)
        self.start_preview_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.stop_preview_btn = ttk.Button(preview_controls, text="\u23f9 Stop",
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
        self.zoom_minus_btn = ttk.Button(zoom_controls, text="\u2212", width=2,
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

        # Zoom recalibration warning
        zoom_warning = tk.Label(
            self.frame, text="\u26a0 Changing zoom requires recalibrating intrinsics",
            font=("Arial", 10, "bold"), fg="#e67700",
        )
        zoom_warning.pack(fill=tk.X, padx=10, pady=(0, 2))

        # Video display area - maximized with 16:9 aspect ratio
        video_container = ttk.Frame(self.frame)
        video_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Video label for displaying frames (16:9 ratio maintained in update_video_display)
        self.video_label = tk.Label(video_container, text="Select a connected camera and click Start",
                                   bg="black", fg="white", font=("Arial", 12))
        self.video_label.pack(expand=True, fill=tk.BOTH)

    # -- Camera dropdown ---------------------------------------------------

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

    # -- Zoom controls -----------------------------------------------------

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

    # -- Preview start/stop ------------------------------------------------

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

    # -- Video display loop ------------------------------------------------

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
