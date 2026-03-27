"""
Visualisation tab for reviewing trial videos with optional pose overlay.

Read-only tab that plays back synced trial video from a selected camera,
with optional 2D pose estimation keypoints and skeleton overlay,
and optional 3D keypoint reprojection from triangulated TRC data.
"""

import json
import logging
import sys
import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageTk

logger = logging.getLogger(__name__)


class VisualisationTab:
    """Video playback tab with pose overlay for reviewing trial recordings."""

    def __init__(self, notebook, project_manager, get_current_project,
                 get_current_session):
        self.notebook = notebook
        self.pm = project_manager
        self.get_current_project = get_current_project
        self.get_current_session = get_current_session
        self.root = notebook.winfo_toplevel()

        # Selection state
        self._current_trial = None
        self._active_camera = None
        self._available_cameras = []

        # Video state
        self._cap = None
        self._fps = 50.0
        self._total_frames = 0
        self._current_frame_idx = -1
        self._playing = False
        self._play_job = None
        self._loop_enabled = True
        self._photo = None  # prevent GC of displayed image

        # 2D pose overlay state
        self._pose_overlay = tk.BooleanVar(value=False)
        self._pose_json_dir = None
        self._pose_model = None
        self._draw_funcs_loaded = False
        self._draw_skel = None
        self._draw_keypts = None

        # 3D TRC overlay state
        self._trc_overlay = tk.BooleanVar(value=False)
        self._trc_data = None       # np.ndarray (n_frames, n_markers, 3) or None
        self._trc_keypoint_ids = None  # list mapping TRC col index → skeleton node ID
        self._cam_K = None           # 3x3 intrinsic matrix
        self._cam_dist = None        # distortion coefficients
        self._cam_rvec = None        # Rodrigues rotation vector
        self._cam_tvec = None        # translation vector

        # IK joint centres overlay state
        self._kin_overlay = tk.BooleanVar(value=False)
        self._kin_body_positions = None  # np.ndarray (n_frames, n_bodies, 3) or None
        self._kin_times = None           # np.ndarray of motion timestamps

        # Build UI
        self.frame = ttk.Frame(notebook)
        notebook.add(self.frame, text="Visualisation")
        self._build_ui()

    # =========================================================================
    # UI construction
    # =========================================================================

    def _build_ui(self):
        """Create the tab layout with left panel and right video display."""
        paned = ttk.PanedWindow(self.frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # --- Left panel ---
        left = ttk.Frame(paned, width=250)
        paned.add(left, weight=0)

        # Trial selection (shared SessionTrialsList component)
        from GUI.components.session_trials_list import SessionTrialsList
        self.trial_list = SessionTrialsList(
            left, self.pm,
            self.get_current_project, self.get_current_session,
            on_select=self._on_trial_selected_from_list,
            single_select=True,
        )
        self.trial_list.frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 2))

        # Camera selection
        cam_frame = ttk.LabelFrame(left, text="Camera", padding=8)
        cam_frame.pack(fill=tk.X, padx=5, pady=2)

        cam_btn_row = ttk.Frame(cam_frame)
        cam_btn_row.pack()
        self._cam_buttons = {}
        for n in range(1, 5):
            btn = tk.Button(cam_btn_row, text=f"GP{n}", width=5,
                            state=tk.DISABLED, relief=tk.RAISED,
                            command=lambda cam=n: self._on_camera_selected(cam))
            btn.pack(side=tk.LEFT, padx=2)
            self._cam_buttons[n] = btn

        # Overlay controls
        overlay_frame = ttk.LabelFrame(left, text="Overlay", padding=8)
        overlay_frame.pack(fill=tk.X, padx=5, pady=2)

        self._pose_check = ttk.Checkbutton(
            overlay_frame, text="2D kpts", variable=self._pose_overlay,
            command=self._on_overlay_toggle)
        self._pose_check.pack(anchor=tk.W)

        self._trc_check = ttk.Checkbutton(
            overlay_frame, text="3D kpts", variable=self._trc_overlay,
            command=self._on_overlay_toggle)
        self._trc_check.pack(anchor=tk.W)

        self._kin_check = ttk.Checkbutton(
            overlay_frame, text="IK joint centres", variable=self._kin_overlay,
            command=self._on_overlay_toggle)
        self._kin_check.pack(anchor=tk.W)

        # OpenSim viewer button
        self._osim_viewer_btn = ttk.Button(
            overlay_frame, text="View in OpenSim",
            command=self._launch_opensim_viewer, state=tk.DISABLED)
        self._osim_viewer_btn.pack(anchor=tk.W, pady=(6, 0))

        # Info
        info_frame = ttk.LabelFrame(left, text="Info", padding=8)
        info_frame.pack(fill=tk.X, padx=5, pady=(2, 5))
        self._info_label = ttk.Label(info_frame, text="No trial loaded",
                                     wraplength=220, justify=tk.LEFT)
        self._info_label.pack(anchor=tk.W)

        # --- Right panel ---
        right = ttk.Frame(paned)
        paned.add(right, weight=1)

        # Video canvas
        self.canvas = tk.Canvas(right, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # Playback controls
        controls = ttk.Frame(right)
        controls.pack(fill=tk.X, padx=5, pady=5)

        self.rewind_btn = ttk.Button(controls, text="<<", width=3,
                                     command=self._rewind, state=tk.DISABLED)
        self.rewind_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.step_back_btn = ttk.Button(controls, text="-1", width=3,
                                       command=self._step_back, state=tk.DISABLED)
        self.step_back_btn.pack(side=tk.LEFT, padx=(0, 2))

        self.play_btn = ttk.Button(controls, text="Play", width=5,
                                   command=self._toggle_play, state=tk.DISABLED)
        self.play_btn.pack(side=tk.LEFT, padx=(0, 2))

        self.step_fwd_btn = ttk.Button(controls, text="+1", width=3,
                                       command=self._step_forward, state=tk.DISABLED)
        self.step_fwd_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.loop_btn = tk.Button(controls, text="Loop", width=5,
                                  command=self._toggle_loop, relief=tk.SUNKEN)
        self.loop_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.scrubber = ttk.Scale(controls, from_=0, to=0,
                                  orient=tk.HORIZONTAL,
                                  command=self._on_scrub)
        self.scrubber.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        # Frame entry box
        ttk.Label(controls, text="Go to:").pack(side=tk.LEFT)
        self.frame_entry = ttk.Entry(controls, width=7)
        self.frame_entry.pack(side=tk.LEFT, padx=(2, 8))
        self.frame_entry.bind("<Return>", self._on_frame_entry)

        self._frame_label = ttk.Label(controls, text="Frame: - / -")
        self._frame_label.pack(side=tk.LEFT)

        # Initial populate
        self.trial_list.refresh()

    # =========================================================================
    # Selection
    # =========================================================================

    def refresh(self):
        """Refresh trial list from current session (called by main_window)."""
        self._current_trial = None
        self._clear_video()
        self.trial_list.refresh()

    def _on_trial_selected_from_list(self, trial_name):
        """Handle trial selection from SessionTrialsList."""
        if trial_name == self._current_trial:
            return
        self._current_trial = trial_name
        self._scan_cameras()
        if self._available_cameras:
            self._on_camera_selected(self._available_cameras[0])
        else:
            self._clear_video()
            self._show_placeholder("No synced video available")

    def _scan_cameras(self):
        """Detect which cameras (GP1-GP4) have synced video files."""
        self._available_cameras = []
        for n in range(1, 5):
            self._cam_buttons[n].configure(state=tk.DISABLED, relief=tk.RAISED,
                                           bg="SystemButtonFace")
        if not self.get_current_project() or not self.get_current_session() or not self._current_trial:
            return

        synced = self.pm.get_trial_synced_path(
            self.get_current_project(), self.get_current_session(), self._current_trial)
        if not synced.exists():
            return

        for n in range(1, 5):
            matches = list(synced.glob(f"*_GP{n}.mp4"))
            if matches:
                self._available_cameras.append(n)
                self._cam_buttons[n].configure(state=tk.NORMAL)

    def _on_camera_selected(self, cam_num):
        """Switch to the selected camera view."""
        if cam_num == self._active_camera:
            return
        saved_frame = max(self._current_frame_idx, 0)
        self._active_camera = cam_num
        # Update button appearance
        for n, btn in self._cam_buttons.items():
            if n == cam_num:
                btn.configure(relief=tk.SUNKEN, bg="#4CAF50")
            elif n in self._available_cameras:
                btn.configure(relief=tk.RAISED, bg="SystemButtonFace")
        self._load_video()
        # Restore frame position (clamped to new video length)
        if self._cap and self._total_frames > 0:
            target = min(saved_frame, self._total_frames - 1)
            self._display_frame(target)

    # =========================================================================
    # Video loading and display
    # =========================================================================

    def _load_video(self):
        """Open VideoCapture for the active camera's synced MP4."""
        self._stop_playback()
        if self._cap:
            self._cap.release()
            self._cap = None

        if not all([self.get_current_project(), self.get_current_session(),
                    self._current_trial, self._active_camera]):
            return

        synced = self.pm.get_trial_synced_path(
            self.get_current_project(), self.get_current_session(), self._current_trial)
        files = list(synced.glob(f"*_GP{self._active_camera}.mp4"))
        if not files:
            self._show_placeholder("Video file not found")
            return

        self._cap = cv2.VideoCapture(str(files[0]))
        if not self._cap.isOpened():
            self._cap = None
            self._show_placeholder("Failed to open video")
            return

        self._fps = self._cap.get(cv2.CAP_PROP_FPS) or 50.0
        self._total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._current_frame_idx = -1  # force seek on first display

        # Update scrubber
        self.scrubber.configure(to=max(0, self._total_frames - 1))
        self.play_btn.configure(state=tk.NORMAL)
        self.rewind_btn.configure(state=tk.NORMAL)
        self.step_back_btn.configure(state=tk.NORMAL)
        self.step_fwd_btn.configure(state=tk.NORMAL)

        # Detect pose data (2D and 3D) and kinematics
        self._detect_pose_data()
        self._detect_trc_data()
        self._detect_kinematics_data()

        # Update info
        self._update_info()

        # Display first frame
        self._display_frame(0)

    def _clear_video(self):
        """Release video and reset display."""
        self._stop_playback()
        if self._cap:
            self._cap.release()
            self._cap = None
        self._active_camera = None
        self._total_frames = 0
        self._current_frame_idx = -1
        self._pose_json_dir = None
        self._pose_model = None
        self._trc_data = None
        self._trc_keypoint_ids = None
        self._cam_K = None
        self._cam_dist = None
        self._cam_rvec = None
        self._cam_tvec = None
        self._kin_osim_path = None
        self._kin_mot_path = None
        self._kin_body_positions = None
        self._kin_times = None
        self._osim_viewer_btn.configure(state=tk.DISABLED, text="View in OpenSim")
        self.play_btn.configure(state=tk.DISABLED)
        self.rewind_btn.configure(state=tk.DISABLED)
        self.step_back_btn.configure(state=tk.DISABLED)
        self.step_fwd_btn.configure(state=tk.DISABLED)
        self.scrubber.configure(to=0)
        self._frame_label.configure(text="Frame: - / -")
        self._info_label.configure(text="No trial loaded")
        self.canvas.delete("all")
        self._photo = None
        for n, btn in self._cam_buttons.items():
            btn.configure(relief=tk.RAISED, bg="SystemButtonFace")

    def _show_placeholder(self, text):
        """Show a text message on the canvas."""
        self.canvas.delete("all")
        self._photo = None
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        self.canvas.create_text(w // 2, h // 2, text=text,
                                fill="gray", font=("Arial", 14))

    def _display_frame(self, frame_idx):
        """Read and display a specific frame, with optional pose overlay."""
        if not self._cap:
            return

        frame_idx = max(0, min(frame_idx, self._total_frames - 1))
        frame = self._read_frame(frame_idx)
        if frame is None:
            return

        self._current_frame_idx = frame_idx

        # 2D pose overlay
        if self._pose_overlay.get() and self._pose_json_dir:
            frame = self._overlay_pose(frame, frame_idx)

        # 3D TRC overlay
        if self._trc_overlay.get() and self._trc_data is not None:
            frame = self._overlay_trc(frame, frame_idx)

        # IK joint centres overlay
        if self._kin_overlay.get() and self._kin_body_positions is not None:
            frame = self._overlay_kin(frame, frame_idx)

        # BGR -> RGB, resize with OpenCV (much faster than PIL LANCZOS), then to PhotoImage
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w > 1 and canvas_h > 1:
            h, w = frame_rgb.shape[:2]
            scale = min(canvas_w / w, canvas_h / h)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            frame_rgb = cv2.resize(frame_rgb, (new_w, new_h),
                                   interpolation=cv2.INTER_LINEAR)

        pil_img = Image.fromarray(frame_rgb)
        self._photo = ImageTk.PhotoImage(pil_img)
        self.canvas.delete("all")
        self.canvas.create_image(canvas_w // 2, canvas_h // 2,
                                 anchor=tk.CENTER, image=self._photo)

        # Update controls (without triggering scrubber callback)
        self.scrubber.set(frame_idx)
        self._update_frame_label(frame_idx)

    def _read_frame(self, frame_idx):
        """Read a frame, using sequential read when possible to avoid slow seeks."""
        if frame_idx != self._current_frame_idx + 1:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = self._cap.read()
        return frame if ret else None

    def _fit_image(self, pil_img, canvas_w, canvas_h):
        """Resize PIL image to fit canvas while preserving aspect ratio."""
        img_w, img_h = pil_img.size
        if img_w == 0 or img_h == 0:
            return pil_img
        scale = min(canvas_w / img_w, canvas_h / img_h)
        new_w = max(1, int(img_w * scale))
        new_h = max(1, int(img_h * scale))
        return pil_img.resize((new_w, new_h), Image.LANCZOS)

    def _update_frame_label(self, frame_idx):
        """Update the frame counter label."""
        total = self._total_frames
        t_sec = frame_idx / self._fps if self._fps > 0 else 0
        minutes = int(t_sec // 60)
        seconds = t_sec % 60
        self._frame_label.configure(
            text=f"Frame: {frame_idx + 1} / {total}  |  {minutes}:{seconds:05.2f}")

    def _update_info(self):
        """Update info label with trial metadata."""
        if not self._current_trial:
            self._info_label.configure(text="No trial loaded")
            return
        try:
            trial = self.pm.get_trial(
                self.get_current_project(), self.get_current_session(), self._current_trial)
            subject = trial.get("subject_id", "?")
            fps = f"{self._fps:.0f}" if self._fps else "?"
            w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if self._cap else 0
            h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if self._cap else 0
            pose_2d = str(len(list(self._pose_json_dir.glob("*.json")))) if self._pose_json_dir else "no"
            pose_3d = str(self._trc_data.shape[0]) if self._trc_data is not None else "no"
            self._info_label.configure(
                text=f"Subject: {subject}\n"
                     f"FPS: {fps}  |  {w}x{h}\n"
                     f"Frames: {self._total_frames}\n"
                     f"2D kpts: {pose_2d}  |  3D kpts: {pose_3d}")
        except Exception:
            self._info_label.configure(text="Could not load trial info")

    # =========================================================================
    # Playback
    # =========================================================================

    def _toggle_play(self):
        if self._playing:
            self._stop_playback()
        else:
            self._start_playback()

    def _step_forward(self):
        self._stop_playback()
        if self._cap and self._current_frame_idx < self._total_frames - 1:
            self._display_frame(self._current_frame_idx + 1)

    def _step_back(self):
        self._stop_playback()
        if self._cap and self._current_frame_idx > 0:
            self._display_frame(self._current_frame_idx - 1)

    def _rewind(self):
        self._stop_playback()
        if self._cap:
            self._display_frame(0)

    def _toggle_loop(self):
        self._loop_enabled = not self._loop_enabled
        self.loop_btn.configure(relief=tk.SUNKEN if self._loop_enabled else tk.RAISED)

    def _start_playback(self):
        if not self._cap:
            return
        self._playing = True
        self.play_btn.configure(text="Pause")
        self._schedule_next_frame()

    def _stop_playback(self):
        self._playing = False
        self.play_btn.configure(text="Play")
        if self._play_job:
            self.root.after_cancel(self._play_job)
            self._play_job = None

    def _schedule_next_frame(self):
        if not self._playing or not self._cap:
            return

        next_idx = self._current_frame_idx + 1
        if next_idx >= self._total_frames:
            if self._loop_enabled:
                next_idx = 0
            else:
                self._stop_playback()
                return

        t_start = time.perf_counter()
        self._display_frame(next_idx)
        elapsed_ms = (time.perf_counter() - t_start) * 1000

        target_ms = 1000.0 / self._fps
        delay = max(1, int(target_ms - elapsed_ms))
        self._play_job = self.root.after(delay, self._schedule_next_frame)

    def _on_scrub(self, value):
        """Called when user drags the slider."""
        frame_idx = int(float(value))
        if frame_idx != self._current_frame_idx and self._cap:
            # Don't seek during playback (scrubber updates from display_frame)
            if not self._playing:
                self._display_frame(frame_idx)

    def _on_frame_entry(self, _event=None):
        """Jump to the frame number typed in the entry box."""
        text = self.frame_entry.get().strip()
        if not text or not self._cap:
            return
        try:
            frame_idx = int(text)
        except ValueError:
            return
        frame_idx = max(0, min(frame_idx, self._total_frames - 1))
        self._stop_playback()
        self._display_frame(frame_idx)

    def _on_canvas_resize(self, _event=None):
        """Redraw current frame when canvas resizes."""
        if self._cap and not self._playing and self._current_frame_idx >= 0:
            self._display_frame(self._current_frame_idx)

    def _on_overlay_toggle(self):
        """Redraw current frame when any overlay is toggled."""
        if self._cap and not self._playing and self._current_frame_idx >= 0:
            self._display_frame(self._current_frame_idx)

    # =========================================================================
    # Pose overlay
    # =========================================================================

    def _detect_pose_data(self):
        """Check if pose JSON directory exists for the active camera."""
        self._pose_json_dir = None
        self._pose_model = None

        if not all([self.get_current_project(), self.get_current_session(),
                    self._current_trial, self._active_camera]):
            return

        processed = self.pm.get_trial_processed_path(
            self.get_current_project(), self.get_current_session(), self._current_trial)
        pose_dir = processed / "pose"
        if not pose_dir.exists():
            return

        # Find the json dir matching this camera
        cam_name = f"{self._current_trial}_GP{self._active_camera}"
        json_dir = pose_dir / f"{cam_name}_json"
        if json_dir.exists() and any(json_dir.glob("*.json")):
            self._pose_json_dir = json_dir
            self._load_pose_model(processed)
            self._ensure_draw_funcs()

    def _load_pose_model(self, processed_path):
        """Load skeleton model from Config.toml or default to HALPE_26."""
        try:
            # Try reading pose_model from the trial's Config.toml
            import toml
            config = toml.load(processed_path / "Config.toml")
            model_name = config.get("pose", {}).get("pose_model", "Body_with_feet")
        except Exception:
            model_name = "Body_with_feet"

        mapping = {
            'body_with_feet': 'HALPE_26',
            'whole_body_wrist': 'COCO_133_WRIST',
            'whole_body': 'COCO_133',
            'body': 'COCO_17',
        }
        skel_name = mapping.get(model_name.lower(), model_name.upper())

        try:
            self._ensure_pose2sim_path()
            import Pose2Sim.skeletons as skeletons
            self._pose_model = getattr(skeletons, skel_name, skeletons.HALPE_26)
        except Exception:
            logger.warning("Could not load skeleton model, pose overlay may not work")
            self._pose_model = None

    def _ensure_pose2sim_path(self):
        """Add pose2sim submodule to sys.path if needed."""
        pose2sim_path = str(Path(__file__).resolve().parents[1] / "pose2sim")
        if pose2sim_path not in sys.path:
            sys.path.insert(0, pose2sim_path)

    def _ensure_draw_funcs(self):
        """Lazy-load drawing functions from Pose2Sim.common."""
        if self._draw_funcs_loaded:
            return
        try:
            self._ensure_pose2sim_path()
            from Pose2Sim.common import draw_skel, draw_keypts
            self._draw_skel = draw_skel
            self._draw_keypts = draw_keypts
            self._draw_funcs_loaded = True
        except Exception:
            logger.warning("Could not import Pose2Sim drawing functions")

    def _overlay_pose(self, frame, frame_idx):
        """Draw 2D pose keypoints and skeleton on the frame if JSON exists."""
        cam_name = f"{self._current_trial}_GP{self._active_camera}"
        json_file = self._pose_json_dir / f"{cam_name}_{frame_idx:06d}.json"

        if not json_file.exists():
            return frame

        try:
            with open(json_file) as f:
                data = json.load(f)

            X_all, Y_all, S_all = [], [], []
            for person in data.get("people", []):
                kpts = person.get("pose_keypoints_2d", [])
                if len(kpts) < 3:
                    continue
                x = kpts[0::3]
                y = kpts[1::3]
                s = kpts[2::3]
                X_all.append(x)
                Y_all.append(y)
                S_all.append(s)

            if X_all and self._draw_funcs_loaded:
                X = [np.array(x) for x in X_all]
                Y = [np.array(y) for y in Y_all]
                S = [np.array(s) for s in S_all]

                if self._pose_model and self._draw_skel:
                    frame = self._draw_skel(frame, X, Y, self._pose_model)
                if self._draw_keypts:
                    frame = self._draw_keypts(frame, X, Y, S)
        except Exception:
            pass  # Silently skip malformed JSON

        return frame

    # =========================================================================
    # 3D TRC overlay
    # =========================================================================

    def _detect_trc_data(self):
        """Load TRC 3D marker data and camera calibration for reprojection."""
        self._trc_data = None
        self._cam_K = None
        self._cam_dist = None
        self._cam_rvec = None
        self._cam_tvec = None

        if not all([self.get_current_project(), self.get_current_session(),
                    self._current_trial, self._active_camera]):
            return

        processed = self.pm.get_trial_processed_path(
            self.get_current_project(), self.get_current_session(), self._current_trial)
        pose3d_dir = processed / "pose-3d"
        if not pose3d_dir.exists():
            return

        # Find .trc file
        trc_files = list(pose3d_dir.glob("*.trc"))
        if not trc_files:
            return

        try:
            self._trc_data = self._parse_trc(trc_files[0])
        except Exception:
            logger.warning(f"Could not parse TRC file: {trc_files[0]}")
            self._trc_data = None
            return

        # Load calibration for this camera
        self._load_camera_calibration()

        # Ensure skeleton model is loaded (needed for draw_skel)
        if self._pose_model is None:
            self._load_pose_model(processed)
        self._ensure_draw_funcs()

        # Compute TRC column → skeleton ID mapping (same traversal as triangulation.py:734)
        if self._pose_model is not None:
            try:
                from anytree import RenderTree
                self._trc_keypoint_ids = [
                    node.id for _, _, node in RenderTree(self._pose_model)
                    if node.id is not None
                ]
            except Exception:
                self._trc_keypoint_ids = None

    def _parse_trc(self, trc_path):
        """Parse a TRC file into a numpy array of shape (n_frames, n_markers, 3).

        TRC format:
          Line 1: PathFileType header
          Line 2: DataRate CameraRate NumFrames NumMarkers Units ...
          Line 3: values for above
          Line 4: marker names (tab-separated, every 3rd column after Frame#, Time)
          Line 5: X1 Y1 Z1 X2 Y2 Z2 ... (sub-headers)
          Line 6+: data rows: frame time x1 y1 z1 x2 y2 z2 ...
        """
        import pandas as pd

        # Read header to get marker count
        header_df = pd.read_csv(trc_path, sep="\t", skiprows=1, header=None,
                                nrows=2, encoding="ISO-8859-1")
        n_markers = int(header_df.iloc[1, 3])  # NumMarkers column

        # Read marker names from line 4
        labels_df = pd.read_csv(trc_path, sep="\t", skiprows=3, nrows=1)
        marker_names = labels_df.columns.tolist()[2::3][:n_markers]

        # Build column names
        labels_xyz = []
        for name in marker_names:
            labels_xyz.extend([f"{name}_X", f"{name}_Y", f"{name}_Z"])
        all_cols = ["Frame", "Time"] + labels_xyz

        # Read data
        data = pd.read_csv(trc_path, sep="\t", skiprows=5, index_col=False,
                           header=None, names=all_cols)

        # Extract coordinates as numpy array (n_frames, n_markers*3)
        coords = data.iloc[:, 2:].values.astype(np.float64)

        # Reshape to (n_frames, n_markers, 3)
        n_frames = coords.shape[0]
        trc_data = coords.reshape(n_frames, n_markers, 3)

        # Convert OpenSim coords (X,Y,Z) to Go2Kin coords (Z_osim, X_osim, Y_osim)
        trc_data = trc_data[:, :, [2, 0, 1]]
        return trc_data

    def _load_camera_calibration(self):
        """Load camera intrinsics/extrinsics from the Pose2Sim TOML calibration."""
        try:
            trial = self.pm.get_trial(
                self.get_current_project(), self.get_current_session(), self._current_trial)
            calib_name = trial.get("calibration_file", "")
            if not calib_name or calib_name == "none":
                return

            toml_path = self.pm.get_calibration_path(
                self.get_current_project(), calib_name, fmt="toml")
            if not toml_path.exists():
                logger.warning(f"Calibration TOML not found: {toml_path}")
                return

            import toml
            calib = toml.load(toml_path)

            # Map active camera (1-4) to TOML section (cam_1, cam_2, ...)
            cam_key = f"cam_{self._active_camera}"
            if cam_key not in calib:
                logger.warning(f"Camera {cam_key} not found in calibration TOML")
                return

            cam_data = calib[cam_key]
            self._cam_K = np.array(cam_data["matrix"], dtype=np.float64)
            self._cam_dist = np.array(cam_data["distortions"], dtype=np.float64)

            # TOML stores rotation as Rodrigues vector
            rvec = np.array(cam_data["rotation"], dtype=np.float64)
            self._cam_rvec = rvec.reshape(3, 1)
            tvec = np.array(cam_data["translation"], dtype=np.float64)
            self._cam_tvec = tvec.reshape(3, 1)

        except Exception:
            logger.warning("Could not load camera calibration for TRC overlay")
            self._cam_K = None

    def _overlay_trc(self, frame, frame_idx):
        """Project 3D TRC markers onto the frame using camera calibration."""
        if (self._trc_data is None or self._cam_K is None
                or frame_idx >= len(self._trc_data)):
            return frame

        try:
            markers_3d = self._trc_data[frame_idx]  # (n_markers, 3)

            # Build full arrays, keeping NaN markers as NaN in output
            n_markers = markers_3d.shape[0]
            x_2d = np.full(n_markers, np.nan)
            y_2d = np.full(n_markers, np.nan)

            # Find valid (non-NaN) markers
            valid = ~np.isnan(markers_3d).any(axis=1)
            if not valid.any():
                return frame

            pts_3d = markers_3d[valid].reshape(-1, 1, 3)
            pts_2d, _ = cv2.projectPoints(
                pts_3d, self._cam_rvec, self._cam_tvec,
                self._cam_K, self._cam_dist)
            pts_2d = pts_2d.reshape(-1, 2)

            x_2d[valid] = pts_2d[:, 0]
            y_2d[valid] = pts_2d[:, 1]

            # Reorder from TRC traversal order → skeleton ID order
            # TRC col i has skeleton ID self._trc_keypoint_ids[i]
            if self._trc_keypoint_ids:
                max_id = max(self._trc_keypoint_ids) + 1
                x_by_id = np.full(max_id, np.nan)
                y_by_id = np.full(max_id, np.nan)
                s_by_id = np.full(max_id, np.nan)
                for trc_idx, skel_id in enumerate(self._trc_keypoint_ids):
                    if trc_idx < n_markers:
                        x_by_id[skel_id] = x_2d[trc_idx]
                        y_by_id[skel_id] = y_2d[trc_idx]
                        s_by_id[skel_id] = 1.0 if not np.isnan(x_2d[trc_idx]) else np.nan

                X = [x_by_id]
                Y = [y_by_id]
                S = [s_by_id]

                if self._pose_model:
                    frame = self._draw_skel_3d(frame, X, Y, self._pose_model)
                frame = self._draw_keypts_3d(frame, X, Y, S)
        except Exception:
            pass  # Silently skip on error

        return frame

    @staticmethod
    def _draw_skel_3d(img, X, Y, model, line_thickness=4):
        """Draw skeleton lines for 3D keypoints with configurable thickness."""
        from anytree import PreOrderIter

        # Get bone pairs from skeleton tree
        id_pairs, name_pairs = [], []
        for leaf in PreOrderIter(model.root, filter_=lambda node: node.is_leaf):
            branch_ids = [n.id for n in leaf.path]
            branch_names = [n.name for n in leaf.path]
            id_pairs += [[branch_ids[i], branch_ids[i + 1]]
                         for i in range(len(branch_ids) - 1)]
            name_pairs += [[branch_names[i], branch_names[i + 1]]
                           for i in range(len(branch_names) - 1)]
        node_pairs = {tuple(np): ip for np, ip in zip(name_pairs, id_pairs)}

        for (x, y) in zip(X, Y):
            if np.isnan(x).all():
                continue
            for names, ids in node_pairs.items():
                if None in ids:
                    continue
                if (np.isnan(x[ids[0]]) or np.isnan(y[ids[0]])
                        or np.isnan(x[ids[1]]) or np.isnan(y[ids[1]])):
                    continue
                # Color: right=orange, left=green, center=blue
                if any(n.startswith('R') for n in names) and not any(n.startswith('L') for n in names):
                    c = (255, 128, 0)
                elif any(n.startswith('L') for n in names) and not any(n.startswith('R') for n in names):
                    c = (0, 255, 0)
                else:
                    c = (51, 153, 255)
                cv2.line(img,
                         (int(x[ids[0]]), int(y[ids[0]])),
                         (int(x[ids[1]]), int(y[ids[1]])),
                         c, line_thickness)
        return img

    @staticmethod
    def _draw_keypts_3d(img, X, Y, scores, radius=12, cmap_str='RdYlGn'):
        """Draw keypoint circles for 3D keypoints with configurable radius."""
        import matplotlib.pyplot as plt

        scores = np.where(np.isnan(scores), 0, scores)
        scores = np.clip(scores, 0, 0.99)

        cmap = plt.get_cmap(cmap_str)
        for (x, y, s) in zip(X, Y, scores):
            colors = np.array(cmap(s))[:, :-1] * 255
            for i in range(len(x)):
                if not (np.isnan(x[i]) or np.isnan(y[i])):
                    cv2.circle(img, (int(x[i]), int(y[i])),
                               radius, colors[i][::-1].tolist(), -1)
        return img

    # =========================================================================
    # OpenSim kinematics viewer
    # =========================================================================

    def _detect_kinematics_data(self):
        """Check if kinematics output (.osim + .mot) exists for the current trial."""
        self._kin_osim_path = None
        self._kin_mot_path = None
        self._kin_body_positions = None
        self._kin_times = None
        self._osim_viewer_btn.configure(state=tk.DISABLED)

        if not all([self.get_current_project(), self.get_current_session(),
                    self._current_trial]):
            return

        processed = self.pm.get_trial_processed_path(
            self.get_current_project(), self.get_current_session(),
            self._current_trial)
        kin_dir = processed / "kinematics"
        if not kin_dir.exists():
            return

        osim_files = sorted(kin_dir.glob("*.osim"))
        mot_files = sorted(kin_dir.glob("*.mot"))
        if osim_files and mot_files:
            self._kin_osim_path = osim_files[0]
            self._kin_mot_path = mot_files[0]
            self._osim_viewer_btn.configure(state=tk.NORMAL)
            self._precompute_kin_data(osim_files[0], mot_files[0])

    def _launch_opensim_viewer(self):
        """Launch OpenSim simbody-visualizer in a separate window (background thread)."""
        import threading

        if not self._kin_osim_path or not self._kin_mot_path:
            logger.warning("No kinematics files found for this trial")
            return

        try:
            import opensim
        except ImportError:
            logger.error("OpenSim Python package not installed")
            return

        osim_path = str(self._kin_osim_path)
        mot_path = str(self._kin_mot_path)

        self._osim_viewer_btn.configure(state=tk.DISABLED, text="Visualizer Open...")

        def run():
            try:
                # Add geometry search path
                osim_setup_dir = Path(sys.modules['Pose2Sim'].__file__).resolve().parent / 'OpenSim_Setup'
                opensim.ModelVisualizer.addDirToGeometrySearchPaths(str(osim_setup_dir / 'Geometry'))

                model = opensim.Model(osim_path)
                model.initSystem()
                motion = opensim.TimeSeriesTable(mot_path)
                opensim.VisualizerUtilities.showMotion(model, motion)
            except Exception as e:
                logger.error(f"OpenSim visualizer error: {e}")
            finally:
                self.root.after(0, lambda: self._osim_viewer_btn.configure(
                    state=tk.NORMAL, text="View in OpenSim"))

        threading.Thread(target=run, daemon=True).start()

    def _precompute_kin_data(self, osim_path, mot_path):
        """Pre-compute body centre positions from .osim + .mot for overlay.

        Extracts each body's ground-frame position at every motion frame
        using the OpenSim API, following the pattern from bodykin_from_mot_osim.py.
        Runs in a background thread to avoid blocking the GUI.
        """
        import threading

        try:
            import opensim
        except ImportError:
            logger.warning("OpenSim not available, IK overlay disabled")
            return

        osim_str = str(osim_path)
        mot_str = str(mot_path)

        def run():
            try:
                model = opensim.Model(osim_str)
                motion_data = opensim.TimeSeriesTable(mot_str)

                # Coordinate names and data
                coord_names = list(motion_data.getColumnLabels())
                times = np.array(motion_data.getIndependentColumn())
                motion_np = motion_data.getMatrix().to_numpy()

                # Convert degrees to radians for rotational coordinates
                model_coord_set = model.getCoordinateSet()
                in_degrees = motion_data.getTableMetaDataAsString('inDegrees') == 'yes'
                if in_degrees:
                    for i, name in enumerate(coord_names):
                        if model_coord_set.get(name).getMotionType() == 1:  # rotation
                            motion_np[:, i] = np.deg2rad(motion_np[:, i])

                # Get body list
                body_set = model.getBodySet()
                bodies = [body_set.get(i) for i in range(body_set.getSize())]

                # Extract positions per frame
                state = model.initSystem()
                n_frames = motion_data.getNumRows()
                n_bodies = len(bodies)
                positions = np.zeros((n_frames, n_bodies, 3))

                for n in range(n_frames):
                    for c, coord in enumerate(coord_names):
                        try:
                            model.getCoordinateSet().get(coord).setValue(
                                state, motion_np[n, c], enforceContraints=False)
                        except Exception:
                            pass
                    model.realizePosition(state)

                    for b_idx, body in enumerate(bodies):
                        positions[n, b_idx] = body.getTransformInGround(state).T().to_numpy()

                # Convert Y-up (OpenSim) → Z-up (Go2Kin) — same as TRC overlay
                positions = positions[:, :, [2, 0, 1]]

                self._kin_body_positions = positions
                self._kin_times = times
                logger.info(f"IK overlay: pre-computed {n_frames} frames, {n_bodies} bodies")
            except Exception as e:
                logger.error(f"IK overlay pre-computation failed: {e}")
                self._kin_body_positions = None
                self._kin_times = None

        threading.Thread(target=run, daemon=True).start()

    def _overlay_kin(self, frame, frame_idx):
        """Project IK body centres onto the frame using camera calibration."""
        if (self._kin_body_positions is None or self._cam_K is None
                or self._kin_times is None):
            return frame

        try:
            # Map video frame to motion frame via timestamp
            video_time = frame_idx / self._fps
            mot_idx = int(np.searchsorted(self._kin_times, video_time, side='right') - 1)
            mot_idx = max(0, min(mot_idx, len(self._kin_body_positions) - 1))

            bodies_3d = self._kin_body_positions[mot_idx]  # (n_bodies, 3)

            # Project to 2D
            pts_3d = bodies_3d.reshape(-1, 1, 3)
            pts_2d, _ = cv2.projectPoints(
                pts_3d, self._cam_rvec, self._cam_tvec,
                self._cam_K, self._cam_dist)
            pts_2d = pts_2d.reshape(-1, 2)

            # Draw filled circles at each body centre — bone color (227, 218, 201) as BGR
            color = (201, 218, 227)
            for pt in pts_2d:
                if not (np.isnan(pt[0]) or np.isnan(pt[1])):
                    cv2.circle(frame, (int(pt[0]), int(pt[1])), 12, color, -1)
        except Exception:
            pass

        return frame
