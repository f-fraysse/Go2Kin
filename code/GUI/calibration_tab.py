"""
Calibration tab for Go2Kin GUI.

Provides tkinter UI for charuco board config, intrinsic calibration,
extrinsic calibration, origin setting, and save/load.

Layout: vertical pipeline (collapsible sections) on the left,
3D camera position viewer on the right.
"""

from __future__ import annotations

import datetime
import logging
import shutil
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from GUI.components.collapsible_section import CollapsibleSection

logger = logging.getLogger(__name__)

# Config paths (charuco config stays global, not per-project)
CALIBRATION_DIR = Path("config/calibration")
CHARUCO_CONFIG_PATH = CALIBRATION_DIR / "charuco_config.json"


class CalibrationTab:
    """Calibration tab for the Go2Kin main window."""

    def __init__(self, notebook: ttk.Notebook, config: dict,
                 cameras=None, camera_status=None,
                 project_manager=None, get_current_project=None,
                 is_recording=None, run_rec_delay=None,
                 start_bar_timer=None, stop_bar_timer=None,
                 play_sync_sound=None,
                 app_config=None, save_app_config=None,
                 on_calibration_saved=None,
                 sync_method_var=None):
        self.notebook = notebook
        self.config = config
        self.frame = ttk.Frame(notebook)
        notebook.add(self.frame, text="Calibration")
        self.cameras = cameras if cameras is not None else {}
        self.camera_status = camera_status if camera_status is not None else {}
        self.project_manager = project_manager
        self.get_current_project = get_current_project or (lambda: None)
        self.is_recording = is_recording or (lambda: False)
        self.run_rec_delay = run_rec_delay or (lambda: None)
        self.start_bar_timer = start_bar_timer or (lambda: None)
        self.stop_bar_timer = stop_bar_timer or (lambda: None)
        self.play_sync_sound = play_sync_sound or (lambda: None)
        self.app_config = app_config or {}
        self._save_app_config = save_app_config or (lambda: None)
        self._on_calibration_saved = on_calibration_saved or (lambda: None)
        self.sync_method_var = sync_method_var or tk.StringVar(value="manual")

        # Lazy imports to avoid circular imports and slow startup
        self._charuco = None
        self._camera_array = None
        self._bundle = None
        self._intrinsic_results: dict[int, dict] = {}

        # Sound source position
        self._sound_source_pos = None

        # Recording state
        self._calib_recording = False
        self._calib_stop_event = threading.Event()

        self._create_widgets()
        self._load_charuco_config()
        self._update_charuco_status()

    # =================================================================
    # Widget creation
    # =================================================================

    def _create_widgets(self):
        # Two-column layout: left = scrollable controls, right = 3D viewer
        self.frame.columnconfigure(0, weight=3)
        self.frame.columnconfigure(1, weight=2)
        self.frame.rowconfigure(0, weight=1)

        left_frame = ttk.Frame(self.frame)
        left_frame.grid(row=0, column=0, sticky="nsew")

        right_frame = ttk.Frame(self.frame)
        right_frame.grid(row=0, column=1, sticky="nsew")

        # Scrollable canvas for the left panel
        canvas = tk.Canvas(left_frame)
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=canvas.yview)
        self._scroll_frame = ttk.Frame(canvas)

        self._scroll_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Bind mousewheel only when hovering over left panel
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        parent = self._scroll_frame

        # Load/Save bar at top
        self._create_load_bar(parent)

        # Charuco Board Config (collapsible)
        self._create_charuco_section(parent)

        # Intrinsic Calibration (collapsible)
        self._create_intrinsic_section(parent)

        # Extrinsic Calibration (always visible — primary daily action)
        self._create_extrinsic_section(parent)

        # Set Origin (always visible, disabled until extrinsics done)
        self._create_origin_section(parent)

        # Apply Calibration
        self._create_apply_section(parent)

        # 3D viewer in right panel
        self._create_3d_viewer(right_frame)

        # Initial pipeline state
        self._update_pipeline_state()

    def _create_load_bar(self, parent):
        """Load/Save bar at top of pipeline."""
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=10, pady=5)

        ttk.Button(bar, text="Load Calibration", command=self._load_calibration).pack(side="left", padx=2)
        ttk.Button(bar, text="Load Intrinsics", command=self._load_intrinsics).pack(side="left", padx=2)
        ttk.Button(bar, text="Delete Videos", command=self._delete_calib_videos).pack(side="right", padx=2)

        self._load_bar_status = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self._load_bar_status, foreground="#666666").pack(side="left", padx=10)

    def _create_charuco_section(self, parent):
        self._charuco_section = CollapsibleSection(parent, "Charuco Board Configuration")
        self._charuco_section.frame.pack(fill="x")

        content = self._charuco_section.content

        grid = ttk.Frame(content)
        grid.pack(fill="x")

        # Row 0: columns, rows
        ttk.Label(grid, text="Columns:").grid(row=0, column=0, sticky="e", padx=5, pady=2)
        self._charuco_cols = tk.IntVar(value=5)
        ttk.Spinbox(grid, from_=3, to=20, textvariable=self._charuco_cols, width=5).grid(row=0, column=1, padx=5)

        ttk.Label(grid, text="Rows:").grid(row=0, column=2, sticky="e", padx=5, pady=2)
        self._charuco_rows = tk.IntVar(value=7)
        ttk.Spinbox(grid, from_=3, to=20, textvariable=self._charuco_rows, width=5).grid(row=0, column=3, padx=5)

        # Row 1: square size, aruco scale
        ttk.Label(grid, text="Square size (cm):").grid(row=1, column=0, sticky="e", padx=5, pady=2)
        self._charuco_square_cm = tk.DoubleVar(value=11.70)
        ttk.Entry(grid, textvariable=self._charuco_square_cm, width=8).grid(row=1, column=1, padx=5)

        ttk.Label(grid, text="ArUco scale:").grid(row=1, column=2, sticky="e", padx=5, pady=2)
        self._charuco_aruco_scale = tk.DoubleVar(value=0.75)
        ttk.Entry(grid, textvariable=self._charuco_aruco_scale, width=8).grid(row=1, column=3, padx=5)

        # Row 2: dictionary, inverted
        ttk.Label(grid, text="Dictionary:").grid(row=2, column=0, sticky="e", padx=5, pady=2)
        self._charuco_dict = tk.StringVar(value="DICT_4X4_50")
        dict_options = [
            "DICT_4X4_50", "DICT_4X4_100", "DICT_4X4_250", "DICT_4X4_1000",
            "DICT_5X5_50", "DICT_5X5_100", "DICT_5X5_250", "DICT_5X5_1000",
            "DICT_6X6_50", "DICT_6X6_100", "DICT_6X6_250", "DICT_6X6_1000",
        ]
        ttk.Combobox(grid, textvariable=self._charuco_dict, values=dict_options, width=16, state="readonly").grid(
            row=2, column=1, padx=5
        )

        self._charuco_inverted = tk.BooleanVar(value=False)
        ttk.Checkbutton(grid, text="Inverted", variable=self._charuco_inverted).grid(row=2, column=2, columnspan=2, padx=5)

        # Buttons
        btn_frame = ttk.Frame(content)
        btn_frame.pack(fill="x", pady=5)
        ttk.Button(btn_frame, text="Save Board Image", command=self._save_board_image).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Save Config", command=self._save_charuco_config).pack(side="left", padx=5)

    def _create_intrinsic_section(self, parent):
        self._intrinsic_section = CollapsibleSection(parent, "Intrinsic Calibration")
        self._intrinsic_section.frame.pack(fill="x")

        content = self._intrinsic_section.content

        self._intrinsic_entries: dict[int, dict] = {}
        cam_nums = list(self.config.get("cameras", {}).keys())

        for cam_num in cam_nums:
            cam_num = int(cam_num)
            row_frame = ttk.Frame(content)
            row_frame.pack(fill="x", pady=2)

            ttk.Label(row_frame, text=f"Camera {cam_num}:", width=10).pack(side="left")

            record_btn = ttk.Button(
                row_frame, text="Record", width=7,
                command=lambda cn=cam_num: self._toggle_intrinsic_record(cn),
            )
            record_btn.pack(side="left", padx=2)

            path_var = tk.StringVar(value="No file selected")
            ttk.Label(row_frame, textvariable=path_var, width=40, relief="sunken").pack(side="left", padx=5)
            ttk.Button(
                row_frame, text="Browse",
                command=lambda cn=cam_num: self._browse_intrinsic_video(cn),
            ).pack(side="left", padx=2)
            ttk.Button(
                row_frame, text="Calibrate",
                command=lambda cn=cam_num: self._run_intrinsic(cn),
            ).pack(side="left", padx=2)

            status_var = tk.StringVar(value="Not calibrated")
            ttk.Label(row_frame, textvariable=status_var, width=20).pack(side="left", padx=5)

            self._intrinsic_entries[int(cam_num)] = {
                "path_var": path_var,
                "status_var": status_var,
                "video_path": None,
                "record_btn": record_btn,
            }

        # Progress
        self._intrinsic_progress = tk.StringVar(value="")
        ttk.Label(content, textvariable=self._intrinsic_progress).pack(fill="x", pady=2)

    def _create_extrinsic_section(self, parent):
        section = ttk.LabelFrame(parent, text="Extrinsic Calibration", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        # Sound source position (inline, centred)
        self._sound_x_var = tk.StringVar(value="")
        self._sound_y_var = tk.StringVar(value="")
        self._sound_z_var = tk.StringVar(value="")

        sound_frame = ttk.Frame(section)
        sound_frame.pack(pady=2)
        ttk.Label(sound_frame, text="Sound source:").pack(side="left")
        for label, var in [("X:", self._sound_x_var), ("Y:", self._sound_y_var), ("Z:", self._sound_z_var)]:
            ttk.Label(sound_frame, text=label).pack(side="left", padx=(8, 0))
            ttk.Entry(sound_frame, textvariable=var, width=7).pack(side="left", padx=2)
        ttk.Label(sound_frame, text="(m)", foreground="#666666").pack(side="left", padx=4)

        # Action button + countdown (centred)
        action_frame = ttk.Frame(section)
        action_frame.pack(pady=(5, 2))

        self._ext_auto_btn = tk.Button(
            action_frame, text="Calibrate", font=("TkDefaultFont", 10, "bold"),
            command=self._auto_calibrate_extrinsics, width=20, height=1,
        )
        self._ext_auto_btn.pack(side="left", padx=2)

        self._ext_countdown_var = tk.StringVar(value="")
        self._ext_countdown_label = ttk.Label(
            action_frame, textvariable=self._ext_countdown_var,
            font=("TkDefaultFont", 16, "bold"), foreground="#F44336",
        )
        self._ext_countdown_label.pack(side="left", padx=10)

        # Status row
        status_frame = ttk.Frame(section)
        status_frame.pack(fill="x", pady=2)

        self._ext_status_canvas = tk.Canvas(
            status_frame, width=14, height=14, highlightthickness=0, borderwidth=0,
        )
        self._ext_status_canvas.pack(side="left", padx=(0, 4))
        self._ext_status_circle = self._ext_status_canvas.create_oval(
            2, 2, 12, 12, fill="#9E9E9E", outline="",
        )

        self._extrinsic_status = tk.StringVar(value="")
        ttk.Label(status_frame, textvariable=self._extrinsic_status).pack(side="left")

    def _create_origin_section(self, parent):
        section = ttk.LabelFrame(parent, text="Set Origin", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        # Sound source display (same vars as extrinsic, centred)
        sound_frame = ttk.Frame(section)
        sound_frame.pack(pady=2)
        ttk.Label(sound_frame, text="Sound source:").pack(side="left")
        for label, var in [("X:", self._sound_x_var), ("Y:", self._sound_y_var), ("Z:", self._sound_z_var)]:
            ttk.Label(sound_frame, text=label).pack(side="left", padx=(8, 0))
            ttk.Entry(sound_frame, textvariable=var, width=7).pack(side="left", padx=2)
        ttk.Label(sound_frame, text="(m)", foreground="#666666").pack(side="left", padx=4)

        # Action button + countdown (centred)
        action_frame = ttk.Frame(section)
        action_frame.pack(pady=(5, 2))

        self._origin_auto_btn = tk.Button(
            action_frame, text="Set Origin", font=("TkDefaultFont", 10, "bold"),
            command=self._auto_set_origin, width=20, height=1,
        )
        self._origin_auto_btn.pack(side="left", padx=2)

        self._origin_countdown_var = tk.StringVar(value="")
        self._origin_countdown_label = ttk.Label(
            action_frame, textvariable=self._origin_countdown_var,
            font=("TkDefaultFont", 16, "bold"), foreground="#F44336",
        )
        self._origin_countdown_label.pack(side="left", padx=10)

        # Status row
        status_frame = ttk.Frame(section)
        status_frame.pack(fill="x", pady=2)

        self._origin_status_canvas = tk.Canvas(
            status_frame, width=14, height=14, highlightthickness=0, borderwidth=0,
        )
        self._origin_status_canvas.pack(side="left", padx=(0, 4))
        self._origin_status_circle = self._origin_status_canvas.create_oval(
            2, 2, 12, 12, fill="#9E9E9E", outline="",
        )

        self._origin_status = tk.StringVar(value="")
        ttk.Label(status_frame, textvariable=self._origin_status).pack(side="left")

    def _create_apply_section(self, parent):
        section = ttk.Frame(parent)
        section.pack(fill="x", padx=10, pady=10)

        self._apply_btn = tk.Button(
            section, text="Apply Calibration", font=("TkDefaultFont", 10, "bold"),
            command=self._apply_calibration, width=20, height=1, state="disabled",
        )
        self._apply_btn.pack(pady=2)

        self._apply_status = tk.StringVar(value="")
        ttk.Label(section, textvariable=self._apply_status).pack(pady=2)

    # =================================================================
    # Status updates
    # =================================================================

    def _update_charuco_status(self):
        """Update charuco CollapsibleSection status from current config values."""
        try:
            cols = self._charuco_cols.get()
            rows = self._charuco_rows.get()
            sq = self._charuco_square_cm.get()
            self._charuco_section.set_status("green", f"{rows}x{cols}, {sq}cm")
        except (tk.TclError, ValueError):
            self._charuco_section.set_status("grey", "Not configured")

    def _update_intrinsic_status(self):
        """Update intrinsic CollapsibleSection status from calibration results."""
        total = len(self._intrinsic_entries)
        calibrated = len(self._intrinsic_results)
        if calibrated == 0:
            self._intrinsic_section.set_status("grey", "Not calibrated")
        elif calibrated < total:
            self._intrinsic_section.set_status("amber", f"{calibrated}/{total} cameras")
        else:
            self._intrinsic_section.set_status("green", f"{calibrated}/{total} cameras")

    def _set_extrinsic_indicator(self, color):
        """Set extrinsic status circle color."""
        from GUI.components.collapsible_section import STATUS_COLORS
        fill = STATUS_COLORS.get(color, STATUS_COLORS["grey"])
        self._ext_status_canvas.itemconfig(self._ext_status_circle, fill=fill)

    def _set_origin_indicator(self, color):
        """Set origin status circle color."""
        from GUI.components.collapsible_section import STATUS_COLORS
        fill = STATUS_COLORS.get(color, STATUS_COLORS["grey"])
        self._origin_status_canvas.itemconfig(self._origin_status_circle, fill=fill)

    def _update_pipeline_state(self):
        """Enable/disable buttons based on current pipeline state."""
        has_intrinsics = bool(self._intrinsic_results)
        has_extrinsics = (self._camera_array is not None
                         and hasattr(self._camera_array, 'posed_cameras')
                         and self._camera_array.posed_cameras)

        # Extrinsic button: enabled when intrinsics exist
        ext_state = "normal" if has_intrinsics else "disabled"
        self._ext_auto_btn.config(state=ext_state)

        # Origin button: enabled when extrinsics done
        origin_state = "normal" if has_extrinsics else "disabled"
        self._origin_auto_btn.config(state=origin_state)

        # Apply button: enabled when extrinsics done
        apply_state = "normal" if has_extrinsics else "disabled"
        self._apply_btn.config(state=apply_state)

        self._update_intrinsic_status()

    # =================================================================
    # Sound source (inline — read silently before sync)
    # =================================================================

    def _read_sound_source_fields(self):
        """Read sound source X/Y/Z from inline fields. Sets self._sound_source_pos or None."""
        try:
            x = float(self._sound_x_var.get())
            y = float(self._sound_y_var.get())
            z = float(self._sound_z_var.get())
            self._sound_source_pos = [x, y, z]
        except (ValueError, TypeError):
            self._sound_source_pos = None

    # =================================================================
    # Countdown helper
    # =================================================================

    def _run_countdown(self, seconds, countdown_var, on_complete):
        """Run visual countdown, then call on_complete."""
        if seconds <= 0:
            countdown_var.set("")
            on_complete()
            return
        countdown_var.set(f"{seconds}...")
        self.frame.after(1000, lambda: self._run_countdown(seconds - 1, countdown_var, on_complete))

    # =================================================================
    # Automated extrinsic flow
    # =================================================================

    def _auto_calibrate_extrinsics(self):
        """One-button automated extrinsic calibration: countdown → record → sync → calibrate."""
        if not self._check_record_preconditions(need_multi=True):
            return
        if not self._intrinsic_results:
            messagebox.showwarning("Warning", "Run intrinsic calibration first")
            return

        self._read_sound_source_fields()

        # Disable button, show countdown
        self._ext_auto_btn.config(state="disabled", text="Starting...")
        self._extrinsic_status.set("Starting countdown...")
        self._set_extrinsic_indicator("grey")

        self._run_countdown(5, self._ext_countdown_var, self._ext_start_recording)

    def _ext_start_recording(self):
        """Start multi-camera recording for extrinsic calibration."""
        cam_list = self._get_connected_cameras()
        if not cam_list:
            self._ext_auto_btn.config(state="normal", text="Calibrate")
            self._extrinsic_status.set("No cameras connected")
            return

        video_dir = self._get_temp_video_dir()
        timestamp = self._make_timestamp()

        self._calib_recording = True
        self._calib_stop_event.clear()
        self._ext_auto_btn.config(
            text="STOP", bg="#dc3545", activebackground="#c82333",
            command=self._ext_stop_recording, state="normal",
        )
        self._extrinsic_status.set(f"Recording ({len(cam_list)} cameras)...")
        self._set_extrinsic_indicator("red")

        def worker():
            try:
                self._multi_record_worker(
                    cam_list, video_dir, "extrinsic", timestamp,
                    self._extrinsic_status,
                    on_synced=lambda synced_dir: self._ext_auto_run_calibration(synced_dir, video_dir, timestamp),
                )
            except Exception as e:
                self.frame.after(0, lambda: self._extrinsic_status.set(f"Error: {e}"))
                self.frame.after(0, lambda: self._set_extrinsic_indicator("red"))
                self.frame.after(0, lambda: messagebox.showerror("Recording Error", str(e)))
            finally:
                self._calib_recording = False
                self.frame.after(0, self.stop_bar_timer)
                self.frame.after(0, self._ext_reset_button)

        threading.Thread(target=worker, daemon=True).start()

    def _ext_stop_recording(self):
        """Stop the extrinsic recording."""
        self._calib_stop_event.set()
        self._ext_auto_btn.config(text="Stopping...", state="disabled")

    def _ext_reset_button(self):
        """Reset extrinsic button to idle state."""
        self._ext_auto_btn.config(
            text="Calibrate", bg="SystemButtonFace",
            activebackground="SystemButtonFace",
            command=self._auto_calibrate_extrinsics,
        )
        self._update_pipeline_state()

    def _ext_auto_run_calibration(self, synced_dir, video_dir, timestamp):
        """Chain extrinsic calibration after sync completes (called from worker thread)."""
        if synced_dir is None:
            self.frame.after(0, lambda: self._extrinsic_status.set("Sync failed — no synced folder"))
            self.frame.after(0, lambda: self._set_extrinsic_indicator("red"))
            return

        self.frame.after(0, lambda: self._extrinsic_status.set("Running extrinsic calibration..."))

        try:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from calibration.calibrate import run_extrinsic_calibration
            from calibration.data_types import CameraArray

            charuco = self._get_charuco()

            # Build CameraArray from intrinsic results
            cameras = {}
            for cam_num, result in self._intrinsic_results.items():
                cameras[cam_num] = result["camera"]

            camera_array = CameraArray(cameras=cameras)
            bundle = run_extrinsic_calibration(
                Path(synced_dir), charuco, camera_array,
            )

            self._camera_array = camera_array
            self._bundle = bundle

            self.frame.after(0, lambda: self._update_extrinsic_result(bundle))
            self.frame.after(0, lambda: self._update_pipeline_state())

            # Auto-delete temp videos on success
            self._cleanup_temp_videos(video_dir, "extrinsic", timestamp)

        except Exception as e:
            self.frame.after(0, lambda err=str(e): self._extrinsic_error(err))

    # =================================================================
    # Automated origin flow
    # =================================================================

    def _auto_set_origin(self):
        """One-button automated origin: countdown → record → sync → set origin."""
        if not self._check_record_preconditions(need_multi=True):
            return
        if self._camera_array is None:
            messagebox.showwarning("Warning", "Run extrinsic calibration first")
            return

        self._read_sound_source_fields()

        self._origin_auto_btn.config(state="disabled", text="Starting...")
        self._origin_status.set("Starting countdown...")
        self._set_origin_indicator("grey")

        self._run_countdown(5, self._origin_countdown_var, self._origin_start_recording)

    def _origin_start_recording(self):
        """Start multi-camera recording for origin."""
        cam_list = self._get_connected_cameras()
        if not cam_list:
            self._origin_auto_btn.config(state="normal", text="Set Origin")
            self._origin_status.set("No cameras connected")
            return

        video_dir = self._get_temp_video_dir()
        timestamp = self._make_timestamp()

        self._calib_recording = True
        self._calib_stop_event.clear()
        self._origin_auto_btn.config(
            text="STOP", bg="#dc3545", activebackground="#c82333",
            command=self._origin_stop_recording, state="normal",
        )
        self._origin_status.set(f"Recording ({len(cam_list)} cameras)...")
        self._set_origin_indicator("red")

        def worker():
            try:
                self._multi_record_worker(
                    cam_list, video_dir, "origin", timestamp,
                    self._origin_status,
                    on_synced=lambda synced_dir: self._origin_auto_run(synced_dir, video_dir, timestamp),
                )
            except Exception as e:
                self.frame.after(0, lambda: self._origin_status.set(f"Error: {e}"))
                self.frame.after(0, lambda: self._set_origin_indicator("red"))
                self.frame.after(0, lambda: messagebox.showerror("Recording Error", str(e)))
            finally:
                self._calib_recording = False
                self.frame.after(0, self.stop_bar_timer)
                self.frame.after(0, self._origin_reset_button)

        threading.Thread(target=worker, daemon=True).start()

    def _origin_stop_recording(self):
        """Stop the origin recording."""
        self._calib_stop_event.set()
        self._origin_auto_btn.config(text="Stopping...", state="disabled")

    def _origin_reset_button(self):
        """Reset origin button to idle state."""
        self._origin_auto_btn.config(
            text="Set Origin", bg="SystemButtonFace",
            activebackground="SystemButtonFace",
            command=self._auto_set_origin,
        )
        self._update_pipeline_state()

    def _origin_auto_run(self, synced_dir, video_dir, timestamp):
        """Chain set_origin after sync completes (called from worker thread)."""
        if synced_dir is None:
            self.frame.after(0, lambda: self._origin_status.set("Sync failed — no synced folder"))
            self.frame.after(0, lambda: self._set_origin_indicator("red"))
            return

        self.frame.after(0, lambda: self._origin_status.set("Setting origin..."))

        try:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

            charuco = self._get_charuco()

            if self._bundle is not None:
                from calibration.calibrate import set_origin
                aligned_bundle = set_origin(
                    Path(synced_dir), charuco, self._camera_array, self._bundle,
                )
                self._bundle = aligned_bundle
                self._camera_array = aligned_bundle.camera_array
            else:
                from calibration.calibrate import compute_origin_transform
                from calibration.alignment import apply_similarity_transform
                transform = compute_origin_transform(
                    Path(synced_dir), charuco, self._camera_array,
                )
                new_camera_array, _ = apply_similarity_transform(
                    self._camera_array, None, transform,
                )
                self._camera_array = new_camera_array

            self.frame.after(0, lambda: self._update_3d_viewer(self._camera_array))
            self.frame.after(0, lambda: self._origin_status.set("Origin set successfully"))
            self.frame.after(0, lambda: self._set_origin_indicator("green"))
            self.frame.after(0, lambda: self._update_pipeline_state())

            # Auto-delete temp videos on success
            self._cleanup_temp_videos(video_dir, "origin", timestamp)

        except Exception as e:
            self.frame.after(0, lambda err=str(e): self._origin_error(err))

    # =================================================================
    # Apply calibration
    # =================================================================

    def _apply_calibration(self):
        """Commit current calibration: auto-save with timestamp, update top bar."""
        if self._camera_array is None:
            messagebox.showwarning("Warning", "No calibration to apply")
            return

        calib_dir = self._get_calibrations_dir()
        if calib_dir is None:
            messagebox.showwarning("Warning", "No project selected")
            return

        self._read_sound_source_fields()

        today = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
        filename = f"calibration_{today}.json"
        filepath = calib_dir / filename

        try:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from calibration.persistence import save_calibration

            charuco = self._get_charuco()
            save_calibration(filepath, self._camera_array, charuco,
                             sound_source_position=self._sound_source_pos)

            # Persist to app config
            self.app_config["last_calibration"] = str(filepath)
            self._save_app_config()

            self._apply_status.set(f"Applied: {filename}")
            self._on_calibration_saved()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")

    # =================================================================
    # Browse fallback methods
    # =================================================================

    def _browse_and_run_extrinsic(self):
        """Browse for synced folder then run extrinsic calibration."""
        folder = filedialog.askdirectory(title="Select synced video folder")
        if not folder:
            return
        self._run_extrinsic_with_folder(folder)

    def _browse_and_run_origin(self):
        """Browse for origin folder then run set origin."""
        folder = filedialog.askdirectory(title="Select origin recording folder")
        if not folder:
            return
        self._run_set_origin_with_folder(folder)

    def _run_extrinsic_with_folder(self, folder):
        """Run extrinsic calibration with a specified folder."""
        if not self._intrinsic_results:
            messagebox.showwarning("Warning", "No cameras calibrated. Run intrinsic calibration first.")
            return

        self._extrinsic_status.set("Running extrinsic calibration...")
        self._set_extrinsic_indicator("grey")

        def worker():
            try:
                import sys
                sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                from calibration.calibrate import run_extrinsic_calibration
                from calibration.data_types import CameraArray

                charuco = self._get_charuco()

                cameras = {}
                for cam_num, result in self._intrinsic_results.items():
                    cameras[cam_num] = result["camera"]

                camera_array = CameraArray(cameras=cameras)
                bundle = run_extrinsic_calibration(
                    Path(folder), charuco, camera_array,
                )

                self._camera_array = camera_array
                self._bundle = bundle

                self.frame.after(0, lambda: self._update_extrinsic_result(bundle))
                self.frame.after(0, lambda: self._update_pipeline_state())
            except Exception as e:
                self.frame.after(0, lambda err=str(e): self._extrinsic_error(err))

        threading.Thread(target=worker, daemon=True).start()

    def _run_set_origin_with_folder(self, folder):
        """Run set origin with a specified folder."""
        if self._camera_array is None:
            messagebox.showwarning("Warning", "Load calibration or run extrinsic calibration first")
            return

        self._origin_status.set("Setting origin...")
        self._set_origin_indicator("grey")

        def worker():
            try:
                import sys
                sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

                charuco = self._get_charuco()

                if self._bundle is not None:
                    from calibration.calibrate import set_origin
                    aligned_bundle = set_origin(
                        Path(folder), charuco, self._camera_array, self._bundle,
                    )
                    self._bundle = aligned_bundle
                    self._camera_array = aligned_bundle.camera_array
                else:
                    from calibration.calibrate import compute_origin_transform
                    from calibration.alignment import apply_similarity_transform
                    transform = compute_origin_transform(
                        Path(folder), charuco, self._camera_array,
                    )
                    new_camera_array, _ = apply_similarity_transform(
                        self._camera_array, None, transform,
                    )
                    self._camera_array = new_camera_array

                self.frame.after(0, lambda: self._update_3d_viewer(self._camera_array))
                self.frame.after(0, lambda: self._origin_status.set("Origin set successfully"))
                self.frame.after(0, lambda: self._set_origin_indicator("green"))
                self.frame.after(0, lambda: self._update_pipeline_state())
            except Exception as e:
                self.frame.after(0, lambda err=str(e): self._origin_error(err))

        threading.Thread(target=worker, daemon=True).start()

    # =================================================================
    # Cleanup
    # =================================================================

    def _cleanup_temp_videos(self, video_dir, purpose, timestamp):
        """Auto-delete temp videos for a specific recording."""
        try:
            prefix = f"{purpose}_{timestamp}"
            for f in video_dir.iterdir():
                if f.is_file() and f.name.startswith(prefix):
                    f.unlink()
            sync_dir = video_dir / f"{prefix}_sync"
            if sync_dir.exists():
                shutil.rmtree(sync_dir)
        except Exception as e:
            logger.warning(f"Could not clean up temp videos: {e}")

    # =================================================================
    # Charuco operations
    # =================================================================

    def _get_charuco(self):
        """Create Charuco from current GUI values."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from calibration.charuco import Charuco

        return Charuco(
            columns=self._charuco_cols.get(),
            rows=self._charuco_rows.get(),
            square_size_overide_cm=self._charuco_square_cm.get(),
            dictionary=self._charuco_dict.get(),
            aruco_scale=self._charuco_aruco_scale.get(),
            inverted=self._charuco_inverted.get(),
        )

    def _save_board_image(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("All files", "*.*")],
            title="Save Charuco Board Image",
        )
        if not filepath:
            return
        try:
            charuco = self._get_charuco()
            charuco.save_image(Path(filepath))
            messagebox.showinfo("Success", f"Board image saved to {filepath}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save board image: {e}")

    def _save_charuco_config(self):
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from calibration.persistence import save_charuco_config

            charuco = self._get_charuco()
            save_charuco_config(CHARUCO_CONFIG_PATH, charuco)
            self._update_charuco_status()
            messagebox.showinfo("Success", f"Charuco config saved to {CHARUCO_CONFIG_PATH}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config: {e}")

    def _load_charuco_config(self):
        """Load charuco config from file if it exists."""
        if not CHARUCO_CONFIG_PATH.exists():
            return
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from calibration.persistence import load_charuco_config

            charuco = load_charuco_config(CHARUCO_CONFIG_PATH)
            self._charuco_cols.set(charuco.columns)
            self._charuco_rows.set(charuco.rows)
            if charuco.square_size_overide_cm:
                self._charuco_square_cm.set(charuco.square_size_overide_cm)
            self._charuco_dict.set(charuco.dictionary)
            self._charuco_aruco_scale.set(charuco.aruco_scale)
            self._charuco_inverted.set(charuco.inverted)
        except Exception as e:
            logger.warning(f"Could not load charuco config: {e}")

    # =================================================================
    # Recording helpers
    # =================================================================

    def update_camera_checkboxes(self, cam_num: int, connected: bool):
        """Called by main_window on connect/disconnect. No-op — we use all connected cameras."""
        pass

    def _get_connected_cameras(self):
        """Return list of (cam_num, GPcam) for all connected cameras."""
        result = []
        for cam_num, connected in self.camera_status.items():
            if connected and cam_num in self.cameras:
                result.append((cam_num, self.cameras[cam_num]))
        return result

    def _check_record_preconditions(self, need_multi=False):
        """Check common preconditions before recording. Returns True if OK."""
        if self._calib_recording:
            messagebox.showwarning("Warning", "A calibration recording is already in progress")
            return False
        if self.is_recording():
            messagebox.showwarning("Warning", "Recording tab is active — stop it first")
            return False
        project = self.get_current_project()
        if not project:
            messagebox.showwarning("Warning", "No project selected. Select a project first.")
            return False
        if need_multi:
            connected = self._get_connected_cameras()
            if not connected:
                messagebox.showwarning("Warning", "No cameras connected")
                return False
        return True

    def _make_timestamp(self):
        return datetime.datetime.now().strftime("%Y%m%d_%H%M")

    def _get_temp_video_dir(self):
        """Return and create [project]/calibrations/temp_videos/ directory."""
        project = self.get_current_project()
        temp_dir = self.project_manager.get_project_path(project) / "calibrations" / "temp_videos"
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir

    # --- Intrinsic recording ---

    def _toggle_intrinsic_record(self, cam_num: int):
        entry = self._intrinsic_entries[cam_num]
        if not self._calib_recording:
            # Start recording
            if not self._check_record_preconditions():
                return
            if not self.camera_status.get(cam_num, False) or cam_num not in self.cameras:
                messagebox.showwarning("Warning", f"Camera {cam_num} is not connected")
                return
            camera = self.cameras[cam_num]
            video_dir = self._get_temp_video_dir()
            timestamp = self._make_timestamp()

            self._calib_recording = True
            self._calib_stop_event.clear()
            entry["record_btn"].config(text="Stop")
            self._intrinsic_progress.set(f"Recording Camera {cam_num}...")

            def worker():
                try:
                    self.run_rec_delay()
                    camera.shutterStart()
                    self.frame.after(0, self.start_bar_timer)
                    self.play_sync_sound()
                    self._calib_stop_event.wait()
                    camera.shutterStop()
                    while camera.camBusy() or camera.encodingActive():
                        time.sleep(0.5)
                    self.frame.after(0, lambda: self._intrinsic_progress.set(
                        f"Downloading from Camera {cam_num}..."))
                    filename = video_dir / f"intrinsic_{timestamp}_GP{cam_num}.mp4"
                    camera.mediaDownloadLast(str(filename))
                    camera.deleteAllFiles()
                    self.frame.after(0, lambda: self._intrinsic_record_done(cam_num, filename))
                except Exception as e:
                    self.frame.after(0, lambda: self._intrinsic_record_error(cam_num, str(e)))
                finally:
                    self._calib_recording = False
                    self.frame.after(0, self.stop_bar_timer)
                    self.frame.after(0, lambda: entry["record_btn"].config(text="Record"))

            threading.Thread(target=worker, daemon=True).start()
        else:
            # Stop recording
            self._calib_stop_event.set()
            entry["record_btn"].config(text="Stopping...")

    def _intrinsic_record_done(self, cam_num, filepath):
        entry = self._intrinsic_entries[cam_num]
        entry["video_path"] = filepath
        entry["path_var"].set(filepath.name)
        self._intrinsic_progress.set(f"Camera {cam_num} recorded: {filepath.name}")

    def _intrinsic_record_error(self, cam_num, error_msg):
        self._intrinsic_progress.set(f"Camera {cam_num} recording error: {error_msg}")
        messagebox.showerror("Recording Error", f"Camera {cam_num}: {error_msg}")

    # --- Multi-camera recording (extrinsic / origin) ---

    def _multi_record_worker(self, cam_list, video_dir, purpose, timestamp, status_var,
                             on_synced=None):
        """Worker thread for multi-camera recording + auto-sync.

        If on_synced is provided, calls on_synced(synced_dir) after sync completes.
        """
        cam_nums = [num for num, cam in cam_list]
        print(f"Calibration: starting {purpose} recording on cameras: {cam_nums}")

        # Start all cameras
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(cam.shutterStart): (num, cam) for num, cam in cam_list}
            for f in futures:
                num, cam = futures[f]
                try:
                    f.result(timeout=15)
                    print(f"  GoPro {num} recording started")
                except Exception as e:
                    print(f"  Failed to start GoPro {num}: {e}")

        # Start bar timer after all cameras confirmed
        self.frame.after(0, self.start_bar_timer)

        # Play sync sound (1s delay + two claps) if enabled
        self.play_sync_sound()

        # Wait for user to click Stop
        self._calib_stop_event.wait()

        print(f"Calibration: stopping cameras and downloading...")
        self.frame.after(0, lambda: status_var.set("Stopping cameras and downloading..."))

        # Stop + download all cameras
        filenames = []
        def stop_and_download(cam_num, camera):
            camera.shutterStop()
            while camera.camBusy() or camera.encodingActive():
                time.sleep(0.5)
            filename = video_dir / f"{purpose}_{timestamp}_GP{cam_num}.mp4"
            camera.mediaDownloadLast(str(filename))
            camera.deleteAllFiles()
            return filename

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(stop_and_download, num, cam): num for num, cam in cam_list}
            for f in futures:
                num = futures[f]
                try:
                    result = f.result(timeout=300)
                    filenames.append(result)
                    print(f"  GoPro {num} file downloaded")
                except Exception as e:
                    print(f"  Error downloading GoPro {num}: {e}")

        # Auto-sync
        print("Calibration: starting audio sync...")
        self.frame.after(0, lambda: status_var.set("Running audio sync..."))
        synced_dir = self._run_calib_sync(video_dir, purpose, timestamp, status_var)

        if on_synced:
            on_synced(synced_dir)
        else:
            if synced_dir:
                n_synced = len([f for f in synced_dir.iterdir() if f.suffix.lower() == ".mp4"])
                self.frame.after(0, lambda: status_var.set(f"Synced {n_synced} files"))
            else:
                self.frame.after(0, lambda: status_var.set("Sync skipped (< 2 files)"))

    def _run_calib_sync(self, video_dir, purpose, timestamp, status_var):
        """Run audio sync on recorded calibration videos. Returns synced dir Path or None."""
        from audio_sync import (check_ffmpeg, check_audio_track, compute_sync_offsets,
                                trim_and_sync_videos, AudioSyncError)

        prefix = f"{purpose}_{timestamp}"
        video_paths = sorted([
            str(f) for f in video_dir.iterdir()
            if f.suffix.lower() == ".mp4" and f.is_file() and f.name.startswith(prefix)
        ])
        if len(video_paths) < 2:
            return None

        if not check_ffmpeg():
            self.frame.after(0, lambda: status_var.set("ffmpeg not found — sync skipped"))
            return None

        # Verify audio tracks
        for vp in video_paths:
            if not check_audio_track(vp):
                raise AudioSyncError(f"No audio track in: {Path(vp).name}")

        # Build camera positions for speed-of-sound compensation (if available)
        cam_positions, sound_pos = self._get_sync_compensation_data(video_paths)

        # Compute sync offsets
        offsets = compute_sync_offsets(video_paths, output_dir=str(video_dir),
                                       camera_positions=cam_positions,
                                       sound_source_position=sound_pos)

        # Log sync quality
        sync_msgs = []
        low_quality = False
        for path, info in offsets.items():
            name = Path(path).name
            ref = " (REF)" if info["is_reference"] else ""
            status = info.get("status", "")
            sync_msgs.append(f"{name}: {info['offset_seconds']:.4f}s {status}{ref}")
            if status == "WARN":
                low_quality = True

        detail = " | ".join(sync_msgs)
        if low_quality:
            detail += " | WARNING: Inconsistent clap offsets"
        self.frame.after(0, lambda: status_var.set(detail))

        # Trim and sync — trim_and_sync_videos creates a synced/ subfolder inside output_dir
        sync_parent = video_dir / f"{purpose}_{timestamp}_sync"
        sync_parent.mkdir(parents=True, exist_ok=True)
        trim_and_sync_videos(video_paths, offsets, str(sync_parent))

        synced_dir = sync_parent / "synced"
        return synced_dir

    def _get_sync_compensation_data(self, video_paths):
        """Build camera_positions dict and sound_source_position for sync compensation.

        Returns (camera_positions, sound_source_position) — either or both may be None.
        camera_positions maps filename (e.g. 'trial_GP1.mp4') to [x, y, z] world coords.
        """
        import numpy as np
        import re

        if (self._camera_array is None or not self._camera_array.posed_cameras
                or self._sound_source_pos is None):
            return None, None

        # Build cam_id -> world position
        cam_world_pos = {}
        for cam_id, cam in self._camera_array.posed_cameras.items():
            if cam.rotation is not None and cam.translation is not None:
                pos = -cam.rotation.T @ cam.translation
                cam_world_pos[cam_id] = pos.tolist()

        if not cam_world_pos:
            return None, None

        # Map filenames to camera positions via _GP{N} suffix
        camera_positions = {}
        for vp in video_paths:
            fname = Path(vp).name
            m = re.search(r"_GP(\d+)\.", fname)
            if m:
                cam_id = int(m.group(1))
                if cam_id in cam_world_pos:
                    camera_positions[fname] = cam_world_pos[cam_id]

        if not camera_positions:
            return None, None

        return camera_positions, self._sound_source_pos

    # =================================================================
    # Intrinsic calibration
    # =================================================================

    def _browse_intrinsic_video(self, cam_num: int):
        filepath = filedialog.askopenfilename(
            filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")],
            title=f"Select calibration video for Camera {cam_num}",
        )
        if filepath:
            entry = self._intrinsic_entries[cam_num]
            entry["video_path"] = Path(filepath)
            entry["path_var"].set(Path(filepath).name)

    def _run_intrinsic(self, cam_num: int):
        entry = self._intrinsic_entries[cam_num]
        video_path = entry.get("video_path")
        if video_path is None:
            messagebox.showwarning("Warning", f"No video selected for Camera {cam_num}")
            return

        entry["status_var"].set("Calibrating...")
        self._intrinsic_progress.set(f"Calibrating Camera {cam_num}...")

        def worker():
            try:
                import sys
                sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                from calibration.calibrate import run_intrinsic_calibration_from_video

                charuco = self._get_charuco()
                output = run_intrinsic_calibration_from_video(
                    video_path, cam_num, charuco,
                )

                self._intrinsic_results[cam_num] = {
                    "camera": output.camera,
                    "report": output.report,
                }

                self.frame.after(0, lambda: self._update_intrinsic_result(cam_num, output))
                self.frame.after(0, lambda: self._update_pipeline_state())
            except Exception as e:
                self.frame.after(0, lambda: self._intrinsic_error(cam_num, str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _update_intrinsic_result(self, cam_num: int, output):
        entry = self._intrinsic_entries[cam_num]
        rmse = output.report.rmse
        entry["status_var"].set(f"RMSE: {rmse:.3f}px")
        self._intrinsic_progress.set(
            f"Camera {cam_num}: RMSE={rmse:.3f}px, frames={output.report.frames_used}"
        )

    def _intrinsic_error(self, cam_num: int, error_msg: str):
        entry = self._intrinsic_entries[cam_num]
        entry["status_var"].set("Error")
        self._intrinsic_progress.set(f"Camera {cam_num} error: {error_msg}")
        messagebox.showerror("Intrinsic Calibration Error", f"Camera {cam_num}: {error_msg}")

    # =================================================================
    # Extrinsic calibration results
    # =================================================================

    def _update_extrinsic_result(self, bundle):
        report = bundle.reprojection_report
        rmse = report.overall_rmse
        status = f"RMSE: {rmse:.3f}px | {report.n_cameras} cameras | {report.n_points} points"
        self._extrinsic_status.set(status)

        # Color indicator based on RMSE quality
        if rmse < 1.0:
            self._set_extrinsic_indicator("green")
        elif rmse < 2.0:
            self._set_extrinsic_indicator("amber")
        else:
            self._set_extrinsic_indicator("red")

        self._update_3d_viewer(bundle.camera_array)

    def _extrinsic_error(self, error_msg: str):
        self._extrinsic_status.set(f"Error: {error_msg}")
        self._set_extrinsic_indicator("red")
        messagebox.showerror("Extrinsic Calibration Error", error_msg)

    # =================================================================
    # Origin results
    # =================================================================

    def _origin_error(self, error_msg: str):
        self._origin_status.set(f"Error: {error_msg}")
        self._set_origin_indicator("red")
        messagebox.showerror("Set Origin Error", error_msg)

    # =================================================================
    # 3D Viewer
    # =================================================================

    def _create_3d_viewer(self, parent):
        """Create persistent matplotlib 3D viewer in the right panel."""
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure

            self._viewer_fig = Figure(figsize=(5, 4), dpi=100)
            self._viewer_ax = self._viewer_fig.add_subplot(111, projection="3d")
            self._viewer_ax.set_xlabel("X")
            self._viewer_ax.set_ylabel("Y")
            self._viewer_ax.set_zlabel("Z")
            self._viewer_ax.set_title("Camera Positions")
            self._viewer_fig.tight_layout()

            self._viewer_canvas = FigureCanvasTkAgg(self._viewer_fig, master=parent)
            self._viewer_canvas.draw()
            self._viewer_canvas.get_tk_widget().pack(fill="both", expand=True)

        except ImportError:
            logger.info("matplotlib not available, 3D viewer disabled")
            self._viewer_fig = None
        except Exception as e:
            logger.warning(f"Could not create 3D viewer: {e}")
            self._viewer_fig = None

    def _update_3d_viewer(self, camera_array=None):
        """Clear and redraw 3D camera positions on the persistent viewer."""
        if self._viewer_fig is None:
            return

        import numpy as np
        ax = self._viewer_ax
        ax.cla()

        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_zlabel("Z")
        ax.set_title("Camera Positions")

        if camera_array is None or not camera_array.posed_cameras:
            self._viewer_canvas.draw_idle()
            return

        # Collect camera positions and look directions
        positions = {}
        look_dirs = {}
        for cam_id, cam in camera_array.posed_cameras.items():
            if cam.translation is not None and cam.rotation is not None:
                pos = -cam.rotation.T @ cam.translation
                positions[cam_id] = pos
                look_dirs[cam_id] = cam.rotation.T @ np.array([0, 0, 1])

        if not positions:
            self._viewer_canvas.draw_idle()
            return

        # Equal aspect ratio limits
        all_pos = np.array(list(positions.values()))
        mid = (all_pos.max(axis=0) + all_pos.min(axis=0)) / 2
        half_range = (all_pos.max(axis=0) - all_pos.min(axis=0)).max() / 2 * 1.1
        half_range = max(half_range, 0.5)  # minimum range for single-camera case
        ax.set_xlim(mid[0] - half_range, mid[0] + half_range)
        ax.set_ylim(mid[1] - half_range, mid[1] + half_range)
        z_lo = max(mid[2] - half_range, -0.2) if all_pos[:, 2].min() >= 0 else mid[2] - half_range
        ax.set_zlim(z_lo, mid[2] + half_range)

        arrow_len = half_range * 0.25

        for cam_id in sorted(positions):
            pos = positions[cam_id]
            look = look_dirs[cam_id]
            ax.scatter(*pos, s=80, zorder=5)
            ax.quiver(
                pos[0], pos[1], pos[2],
                look[0], look[1], look[2],
                length=arrow_len, arrow_length_ratio=0.15,
                color="red", linewidth=1.5,
            )
            ax.text(pos[0], pos[1], pos[2], f"  Cam {cam_id}", fontsize=9)

        # Floor plane at Z=0
        x_lo, x_hi = ax.get_xlim()
        y_lo, y_hi = ax.get_ylim()
        floor_x = np.array([[x_lo, x_hi], [x_lo, x_hi]])
        floor_y = np.array([[y_lo, y_lo], [y_hi, y_hi]])
        floor_z = np.zeros_like(floor_x)
        ax.plot_surface(floor_x, floor_y, floor_z, color="grey", alpha=0.4)

        # World coordinate system axes (RGB = XYZ, 1m arrows)
        ax.quiver(0, 0, 0, 1, 0, 0, length=1.0, arrow_length_ratio=0.1, color="red", linewidth=2)
        ax.quiver(0, 0, 0, 0, 1, 0, length=1.0, arrow_length_ratio=0.1, color="green", linewidth=2)
        ax.quiver(0, 0, 0, 0, 0, 1, length=1.0, arrow_length_ratio=0.1, color="blue", linewidth=2)

        # Sound source position marker
        if self._sound_source_pos is not None:
            sp = self._sound_source_pos
            ax.scatter(sp[0], sp[1], sp[2], marker="x", s=200, c="black",
                       linewidths=3, zorder=6)
            ax.text(sp[0], sp[1], sp[2], "  Speaker", fontsize=9, color="black")

        self._viewer_fig.tight_layout()
        self._viewer_canvas.draw_idle()

    # =================================================================
    # Save/Load
    # =================================================================

    def _get_calibrations_dir(self):
        """Return [project]/calibrations/ directory, or None if no project selected."""
        project = self.get_current_project()
        if not project:
            return None
        calib_dir = self.project_manager.get_project_path(project) / "calibrations"
        calib_dir.mkdir(parents=True, exist_ok=True)
        return calib_dir

    def load_calibration_file(self, filepath: Path, silent: bool = False) -> bool:
        """Load a calibration file and update GUI state.

        Returns True on success, False on failure.
        If silent=True, logs instead of showing messageboxes.
        """
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from calibration.persistence import load_calibration

            camera_array, charuco, sound_pos = load_calibration(filepath)
            self._camera_array = camera_array

            # Restore sound source position
            if sound_pos is not None:
                self._sound_source_pos = sound_pos
                self._sound_x_var.set(f"{sound_pos[0]:.3f}")
                self._sound_y_var.set(f"{sound_pos[1]:.3f}")
                self._sound_z_var.set(f"{sound_pos[2]:.3f}")
            else:
                self._sound_source_pos = None
                self._sound_x_var.set("")
                self._sound_y_var.set("")
                self._sound_z_var.set("")

            # Update charuco GUI
            self._charuco_cols.set(charuco.columns)
            self._charuco_rows.set(charuco.rows)
            if charuco.square_size_overide_cm:
                self._charuco_square_cm.set(charuco.square_size_overide_cm)
            self._charuco_dict.set(charuco.dictionary)
            self._charuco_aruco_scale.set(charuco.aruco_scale)
            self._charuco_inverted.set(charuco.inverted)
            self._update_charuco_status()
            self._charuco_section.collapse()

            # Update intrinsic status
            for cam_id, cam in camera_array.cameras.items():
                if cam_id in self._intrinsic_entries:
                    entry = self._intrinsic_entries[cam_id]
                    if cam.error is not None:
                        entry["status_var"].set(f"RMSE: {cam.error:.3f}px")
                        self._intrinsic_results[cam_id] = {"camera": cam, "report": None}
                    else:
                        entry["status_var"].set("No intrinsics")
            self._intrinsic_section.collapse()

            # Show 3D camera positions if extrinsics are available
            if camera_array.posed_cameras:
                self._update_3d_viewer(camera_array)
                self._set_extrinsic_indicator("green")
                self._extrinsic_status.set(f"Loaded ({len(camera_array.posed_cameras)} cameras)")
            else:
                self._set_extrinsic_indicator("grey")
                self._extrinsic_status.set("")

            self._load_bar_status.set(f"Loaded: {filepath.name}")

            # Persist to app config
            self.app_config["last_calibration"] = str(filepath)
            self._save_app_config()

            # Update pipeline state
            self._update_pipeline_state()

            if silent:
                logger.info("Auto-loaded calibration: %s", filepath.name)
            else:
                messagebox.showinfo("Success", f"Calibration loaded ({len(camera_array.cameras)} cameras)")
            self._on_calibration_saved()
            return True
        except Exception as e:
            if silent:
                logger.warning("Failed to auto-load calibration %s: %s", filepath.name, e)
            else:
                messagebox.showerror("Error", f"Failed to load: {e}")
            return False

    def auto_load_calibration(self):
        """Auto-load calibration on startup: prefer last_calibration, fall back to latest."""
        # Try last_calibration from config
        last_calib = self.app_config.get("last_calibration", "")
        if last_calib:
            calib_path = Path(last_calib)
            if calib_path.exists():
                self.load_calibration_file(calib_path, silent=True)
                return

        # Fall back to latest calibration in the current project
        project = self.get_current_project()
        if not project or not self.project_manager:
            return
        latest_name = self.project_manager.get_latest_calibration(project)
        if latest_name:
            calib_path = self.project_manager.get_calibration_path(project, latest_name, "json")
            if calib_path.exists():
                self.load_calibration_file(calib_path, silent=True)

    def _load_calibration(self):
        calib_dir = self._get_calibrations_dir()
        initialdir = str(calib_dir) if calib_dir else str(CALIBRATION_DIR)

        filepath = filedialog.askopenfilename(
            initialdir=initialdir,
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            title="Load Calibration",
        )
        if not filepath:
            return

        self.load_calibration_file(Path(filepath))

    def _load_intrinsics(self):
        """Load only intrinsic parameters from saved calibration file."""
        calib_dir = self._get_calibrations_dir()
        initialdir = str(calib_dir) if calib_dir else str(CALIBRATION_DIR)

        filepath = filedialog.askopenfilename(
            initialdir=initialdir,
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            title="Load Intrinsics Only",
        )
        if not filepath:
            return

        try:
            import sys
            from dataclasses import replace
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from calibration.persistence import load_calibration

            camera_array, charuco, _ = load_calibration(Path(filepath))

            # Update charuco GUI
            self._charuco_cols.set(charuco.columns)
            self._charuco_rows.set(charuco.rows)
            if charuco.square_size_overide_cm:
                self._charuco_square_cm.set(charuco.square_size_overide_cm)
            self._charuco_dict.set(charuco.dictionary)
            self._charuco_aruco_scale.set(charuco.aruco_scale)
            self._charuco_inverted.set(charuco.inverted)
            self._update_charuco_status()
            self._charuco_section.collapse()

            # Strip extrinsics and populate intrinsic results only
            self._intrinsic_results.clear()
            for cam_id, cam in camera_array.cameras.items():
                if cam_id in self._intrinsic_entries:
                    entry = self._intrinsic_entries[cam_id]
                    if cam.matrix is not None and cam.distortions is not None:
                        intrinsic_only = replace(cam, rotation=None, translation=None)
                        self._intrinsic_results[cam_id] = {"camera": intrinsic_only, "report": None}
                        error_str = f"RMSE: {cam.error:.3f}px" if cam.error is not None else "Loaded"
                        entry["status_var"].set(error_str)
                    else:
                        entry["status_var"].set("No intrinsics")

            # Clear extrinsic state so user must re-run extrinsics
            self._camera_array = None
            self._bundle = None
            self._extrinsic_status.set("")
            self._set_extrinsic_indicator("grey")
            self._update_3d_viewer(None)
            self._origin_status.set("")
            self._set_origin_indicator("grey")

            # Update pipeline state
            self._update_pipeline_state()

            self._load_bar_status.set(f"Intrinsics loaded: {Path(filepath).name}")
            messagebox.showinfo("Success", f"Intrinsics loaded for {len(self._intrinsic_results)} cameras")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load intrinsics: {e}")

    def _delete_calib_videos(self):
        """Delete all calibration temp videos for the current project."""
        project = self.get_current_project()
        if not project:
            messagebox.showwarning("Warning", "No project selected")
            return

        temp_dir = self.project_manager.get_project_path(project) / "calibrations" / "temp_videos"
        if not temp_dir.exists():
            messagebox.showinfo("Info", "No calibration videos to delete")
            return

        if messagebox.askyesno("Confirm Delete",
                               f"Delete all calibration videos?\n{temp_dir}"):
            shutil.rmtree(temp_dir)
            self._load_bar_status.set("Calibration videos deleted")
