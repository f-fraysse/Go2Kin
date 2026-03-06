"""
Calibration tab for Go2Kin GUI.

Provides tkinter UI for charuco board config, intrinsic calibration,
extrinsic calibration, origin setting, and save/load.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

logger = logging.getLogger(__name__)

# Config paths
CALIBRATION_DIR = Path("config/calibration")
CHARUCO_CONFIG_PATH = CALIBRATION_DIR / "charuco_config.json"
CALIBRATION_PATH = CALIBRATION_DIR / "calibration.json"


class CalibrationTab:
    """Calibration tab for the Go2Kin main window."""

    def __init__(self, notebook: ttk.Notebook, config: dict):
        self.notebook = notebook
        self.config = config
        self.frame = ttk.Frame(notebook)
        notebook.add(self.frame, text="Calibration")

        # Lazy imports to avoid circular imports and slow startup
        self._charuco = None
        self._camera_array = None
        self._bundle = None
        self._intrinsic_results: dict[int, dict] = {}

        self._create_widgets()
        self._load_charuco_config()

    # =================================================================
    # Widget creation
    # =================================================================

    def _create_widgets(self):
        # Scrollable canvas for the tab content
        canvas = tk.Canvas(self.frame)
        scrollbar = ttk.Scrollbar(self.frame, orient="vertical", command=canvas.yview)
        self._scroll_frame = ttk.Frame(canvas)

        self._scroll_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Bind mousewheel
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        parent = self._scroll_frame

        # Section 1: Charuco Board Config
        self._create_charuco_section(parent)

        # Section 2: Intrinsic Calibration
        self._create_intrinsic_section(parent)

        # Section 3: Extrinsic Calibration
        self._create_extrinsic_section(parent)

        # Section 4: Set Origin
        self._create_origin_section(parent)

        # Section 5: Save/Load
        self._create_save_load_section(parent)

    def _create_charuco_section(self, parent):
        section = ttk.LabelFrame(parent, text="Charuco Board Configuration", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        grid = ttk.Frame(section)
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
        btn_frame = ttk.Frame(section)
        btn_frame.pack(fill="x", pady=5)
        ttk.Button(btn_frame, text="Save Board Image", command=self._save_board_image).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Save Config", command=self._save_charuco_config).pack(side="left", padx=5)

    def _create_intrinsic_section(self, parent):
        section = ttk.LabelFrame(parent, text="Intrinsic Calibration", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        self._intrinsic_entries: dict[int, dict] = {}
        cam_nums = list(self.config.get("cameras", {}).keys())

        for cam_num in cam_nums:
            cam_num = int(cam_num)
            row_frame = ttk.Frame(section)
            row_frame.pack(fill="x", pady=2)

            ttk.Label(row_frame, text=f"Camera {cam_num}:", width=10).pack(side="left")

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
            }

        # Progress
        self._intrinsic_progress = tk.StringVar(value="")
        ttk.Label(section, textvariable=self._intrinsic_progress).pack(fill="x", pady=2)

    def _create_extrinsic_section(self, parent):
        section = ttk.LabelFrame(parent, text="Extrinsic Calibration", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        folder_frame = ttk.Frame(section)
        folder_frame.pack(fill="x", pady=2)

        ttk.Label(folder_frame, text="Synced folder:").pack(side="left")
        self._extrinsic_folder_var = tk.StringVar(value="No folder selected")
        ttk.Label(folder_frame, textvariable=self._extrinsic_folder_var, width=50, relief="sunken").pack(side="left", padx=5)
        ttk.Button(folder_frame, text="Browse", command=self._browse_extrinsic_folder).pack(side="left", padx=2)

        btn_frame = ttk.Frame(section)
        btn_frame.pack(fill="x", pady=5)
        ttk.Button(btn_frame, text="Calibrate Extrinsics", command=self._run_extrinsic).pack(side="left", padx=5)

        self._extrinsic_status = tk.StringVar(value="")
        ttk.Label(section, textvariable=self._extrinsic_status).pack(fill="x", pady=2)

        # Results frame (for camera positions display)
        self._extrinsic_results_frame = ttk.Frame(section)
        self._extrinsic_results_frame.pack(fill="x", pady=5)

    def _create_origin_section(self, parent):
        section = ttk.LabelFrame(parent, text="Set Origin", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        folder_frame = ttk.Frame(section)
        folder_frame.pack(fill="x", pady=2)

        ttk.Label(folder_frame, text="Origin folder:").pack(side="left")
        self._origin_folder_var = tk.StringVar(value="No folder selected")
        ttk.Label(folder_frame, textvariable=self._origin_folder_var, width=50, relief="sunken").pack(side="left", padx=5)
        ttk.Button(folder_frame, text="Browse", command=self._browse_origin_folder).pack(side="left", padx=2)

        btn_frame = ttk.Frame(section)
        btn_frame.pack(fill="x", pady=5)
        ttk.Button(btn_frame, text="Set Origin", command=self._run_set_origin).pack(side="left", padx=5)

        self._origin_status = tk.StringVar(value="")
        ttk.Label(section, textvariable=self._origin_status).pack(fill="x", pady=2)

    def _create_save_load_section(self, parent):
        section = ttk.LabelFrame(parent, text="Save / Load Calibration", padding=10)
        section.pack(fill="x", padx=10, pady=5)

        btn_frame = ttk.Frame(section)
        btn_frame.pack(fill="x", pady=5)
        ttk.Button(btn_frame, text="Save Calibration", command=self._save_calibration).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Load Calibration", command=self._load_calibration).pack(side="left", padx=5)

        self._save_load_status = tk.StringVar(value="")
        ttk.Label(section, textvariable=self._save_load_status).pack(fill="x", pady=2)

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
    # Extrinsic calibration
    # =================================================================

    def _browse_extrinsic_folder(self):
        folder = filedialog.askdirectory(title="Select synced video folder")
        if folder:
            self._extrinsic_folder_var.set(folder)

    def _run_extrinsic(self):
        folder = self._extrinsic_folder_var.get()
        if folder == "No folder selected":
            messagebox.showwarning("Warning", "No synced folder selected")
            return

        # Check all cameras are intrinsically calibrated
        if not self._intrinsic_results:
            messagebox.showwarning("Warning", "No cameras calibrated. Run intrinsic calibration first.")
            return

        self._extrinsic_status.set("Running extrinsic calibration...")

        def worker():
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
                    Path(folder), charuco, camera_array,
                )

                self._camera_array = camera_array
                self._bundle = bundle

                self.frame.after(0, lambda: self._update_extrinsic_result(bundle))
            except Exception as e:
                self.frame.after(0, lambda err=str(e): self._extrinsic_error(err))

        threading.Thread(target=worker, daemon=True).start()

    def _update_extrinsic_result(self, bundle):
        report = bundle.reprojection_report
        status = f"RMSE: {report.overall_rmse:.3f}px | {report.n_cameras} cameras | {report.n_points} points"
        self._extrinsic_status.set(status)

        # Show per-camera info
        for widget in self._extrinsic_results_frame.winfo_children():
            widget.destroy()

        for cam_id, rmse in report.by_camera.items():
            cam = bundle.camera_array.cameras[cam_id]
            if cam.translation is not None:
                pos = cam.translation
                ttk.Label(
                    self._extrinsic_results_frame,
                    text=f"  Camera {cam_id}: RMSE={rmse:.3f}px, pos=[{pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}]",
                ).pack(anchor="w")

        # Try to show 3D plot
        self._show_camera_positions(bundle.camera_array)

    def _extrinsic_error(self, error_msg: str):
        self._extrinsic_status.set(f"Error: {error_msg}")
        messagebox.showerror("Extrinsic Calibration Error", error_msg)

    def _show_camera_positions(self, camera_array):
        """Show matplotlib 3D scatter plot of camera positions."""
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
            import numpy as np

            fig = Figure(figsize=(4, 3), dpi=100)
            ax = fig.add_subplot(111, projection="3d")

            for cam_id, cam in camera_array.posed_cameras.items():
                if cam.translation is not None and cam.rotation is not None:
                    # Camera position in world: C = -R^T @ t
                    pos = -cam.rotation.T @ cam.translation
                    ax.scatter(*pos, s=50, label=f"Cam {cam_id}")
                    ax.text(pos[0], pos[1], pos[2], f" {cam_id}", fontsize=8)

            ax.set_xlabel("X")
            ax.set_ylabel("Y")
            ax.set_zlabel("Z")
            ax.set_aspect("equal")
            ax.set_title("Camera Positions")
            fig.tight_layout()

            canvas = FigureCanvasTkAgg(fig, master=self._extrinsic_results_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="x", pady=5)

        except ImportError:
            logger.info("matplotlib not available, skipping 3D camera view")
        except Exception as e:
            logger.warning(f"Could not display camera positions: {e}")

    # =================================================================
    # Origin setting
    # =================================================================

    def _browse_origin_folder(self):
        folder = filedialog.askdirectory(title="Select origin recording folder")
        if folder:
            self._origin_folder_var.set(folder)

    def _run_set_origin(self):
        folder = self._origin_folder_var.get()
        if folder == "No folder selected":
            messagebox.showwarning("Warning", "No origin folder selected")
            return

        if self._camera_array is None:
            messagebox.showwarning("Warning", "Load calibration or run extrinsic calibration first")
            return

        self._origin_status.set("Setting origin...")

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

                self.frame.after(0, lambda: self._show_camera_positions(self._camera_array))

                self.frame.after(0, lambda: self._origin_status.set("Origin set successfully"))
            except Exception as e:
                self.frame.after(0, lambda err=str(e): self._origin_error(err))

        threading.Thread(target=worker, daemon=True).start()

    def _origin_error(self, error_msg: str):
        self._origin_status.set(f"Error: {error_msg}")
        messagebox.showerror("Set Origin Error", error_msg)

    # =================================================================
    # Save/Load
    # =================================================================

    def _save_calibration(self):
        if self._camera_array is None:
            messagebox.showwarning("Warning", "No calibration to save")
            return

        try:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from calibration.persistence import save_calibration

            charuco = self._get_charuco()
            save_calibration(CALIBRATION_PATH, self._camera_array, charuco)
            self._save_load_status.set(f"Saved to {CALIBRATION_PATH}")
            messagebox.showinfo("Success", f"Calibration saved to {CALIBRATION_PATH}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")

    def _load_calibration(self):
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from calibration.persistence import load_calibration

            if not CALIBRATION_PATH.exists():
                messagebox.showwarning("Warning", f"No calibration file found at {CALIBRATION_PATH}")
                return

            camera_array, charuco = load_calibration(CALIBRATION_PATH)
            self._camera_array = camera_array

            # Update charuco GUI
            self._charuco_cols.set(charuco.columns)
            self._charuco_rows.set(charuco.rows)
            if charuco.square_size_overide_cm:
                self._charuco_square_cm.set(charuco.square_size_overide_cm)
            self._charuco_dict.set(charuco.dictionary)
            self._charuco_aruco_scale.set(charuco.aruco_scale)
            self._charuco_inverted.set(charuco.inverted)

            # Update intrinsic status
            for cam_id, cam in camera_array.cameras.items():
                if cam_id in self._intrinsic_entries:
                    entry = self._intrinsic_entries[cam_id]
                    if cam.error is not None:
                        entry["status_var"].set(f"RMSE: {cam.error:.3f}px")
                        self._intrinsic_results[cam_id] = {"camera": cam, "report": None}
                    else:
                        entry["status_var"].set("No intrinsics")

            self._save_load_status.set(f"Loaded from {CALIBRATION_PATH}")
            messagebox.showinfo("Success", f"Calibration loaded ({len(camera_array.cameras)} cameras)")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load: {e}")
