#!/usr/bin/env python3
"""
LED ROI picker dialog.

Shows one reduced-size frame per camera (2x2 grid) with a shared time slider
over the sampled frames. Clicking the LED in a view places a fixed-size square
ROI centred on the click; a magnified crop of the ROI is shown in the corner of
the cell for confirmation. Returns full-resolution ROIs.
"""

import tkinter as tk
from tkinter import ttk

import cv2
from PIL import Image, ImageTk

_ROI_COLOR = "#F44336"
_MAG_SIZE = 120  # px, magnified crop shown in the cell corner


def show_led_roi_dialog(parent, frames_by_cam, frame_scale, initial_rois=None,
                        default_size=80, sample_fps=4.0):
    """Open the modal ROI picker and return {cam_id: (x, y, w, h)} in full-res
    pixels, or None if cancelled.

    Args:
        parent: Tk/Toplevel to attach the dialog to.
        frames_by_cam: {cam_id: [RGB ndarray, ...]} sampled frames (same count per cam).
        frame_scale: full_width / sampled_width — a float, or {cam_id: float}.
        initial_rois: {cam_id: (x, y, w, h)} full-res ROIs to prefill.
        default_size: initial ROI side length (full-res px).
        sample_fps: sampling rate of the frames (for the time label only).
    """
    dlg = _LedRoiDialog(parent, frames_by_cam, frame_scale, initial_rois or {},
                        default_size, sample_fps)
    parent.wait_window(dlg.top)
    return dlg.result


class _LedRoiDialog:

    def __init__(self, parent, frames_by_cam, frame_scale, initial_rois,
                 default_size, sample_fps):
        self.frames_by_cam = frames_by_cam
        self.cams = sorted(frames_by_cam)
        self._scales = (frame_scale if isinstance(frame_scale, dict)
                        else {c: float(frame_scale) for c in self.cams})
        self.sample_fps = sample_fps
        self.n_samples = min(len(f) for f in frames_by_cam.values())
        self.rois = {c: tuple(r) for c, r in initial_rois.items() if c in frames_by_cam}
        self.result = None

        self._photos = {}      # cam -> (frame PhotoImage, magnifier PhotoImage)
        self._geom = {}        # cam -> (scale, ox, oy, disp_w, disp_h)

        self.top = tk.Toplevel(parent)
        self.top.title("Set LED ROI — click the LED in each view")
        # A transient of a withdrawn master is never mapped (e.g. the CLI tool's
        # hidden root), so only attach to a visible parent.
        if parent.winfo_viewable():
            self.top.transient(parent)
        self.top.minsize(900, 600)

        # ── Controls row ──
        ctrl = ttk.Frame(self.top, padding=(10, 8))
        ctrl.pack(fill="x")
        ttk.Label(ctrl, text="Time:").pack(side="left")
        self._idx = tk.IntVar(value=self.n_samples // 2)
        self._time_label = ttk.Label(ctrl, text="", width=8)
        self._slider = ttk.Scale(ctrl, from_=0, to=max(0, self.n_samples - 1),
                                 orient="horizontal", length=320,
                                 command=self._on_slider)
        self._slider.set(self._idx.get())
        self._slider.pack(side="left", padx=(4, 4))
        self._time_label.pack(side="left")

        ttk.Label(ctrl, text="ROI size (px):").pack(side="left", padx=(20, 4))
        self._size = tk.IntVar(value=int(default_size))
        spin = ttk.Spinbox(ctrl, from_=20, to=400, increment=10, width=5,
                           textvariable=self._size, command=self._on_size_change)
        spin.pack(side="left")
        spin.bind("<Return>", lambda e: self._on_size_change())
        ttk.Label(ctrl, text="Drag the slider until the LED is on, then click it in every view.",
                  foreground="#666666").pack(side="left", padx=(20, 0))

        # ── 2x2 grid ──
        grid = ttk.Frame(self.top)
        grid.pack(fill="both", expand=True, padx=10)
        cols = 2
        rows = (len(self.cams) + cols - 1) // cols
        for r in range(rows):
            grid.rowconfigure(r, weight=1)
        for c in range(cols):
            grid.columnconfigure(c, weight=1)

        self._canvases = {}
        self._status = {}
        for i, cam in enumerate(self.cams):
            cell = ttk.Frame(grid)
            cell.grid(row=i // cols, column=i % cols, sticky="nsew", padx=4, pady=4)
            cell.rowconfigure(0, weight=1)
            cell.columnconfigure(0, weight=1)
            canvas = tk.Canvas(cell, bg="black", width=440, height=248,
                               highlightthickness=1, highlightbackground="#999999",
                               cursor="crosshair")
            canvas.grid(row=0, column=0, sticky="nsew")
            canvas.bind("<Button-1>", lambda e, c=cam: self._on_click(c, e))
            canvas.bind("<Configure>", lambda e, c=cam: self._redraw(c))
            status = tk.StringVar()
            ttk.Label(cell, textvariable=status).grid(row=1, column=0, sticky="w")
            self._canvases[cam] = canvas
            self._status[cam] = status
            self._update_status(cam)

        # ── Buttons ──
        btns = ttk.Frame(self.top, padding=10)
        btns.pack(fill="x")
        self._ok_btn = ttk.Button(btns, text="OK", command=self._ok, width=12)
        self._ok_btn.pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="Cancel", command=self._cancel, width=12).pack(side="right")
        self._update_ok()

        self.top.protocol("WM_DELETE_WINDOW", self._cancel)
        self._update_time_label()
        self.top.grab_set()
        self.top.focus_set()

    # ── geometry helpers ──

    def _full_size(self, cam):
        h, w = self.frames_by_cam[cam][0].shape[:2]
        s = self._scales[cam]
        return int(round(w * s)), int(round(h * s))

    def _redraw(self, cam):
        canvas = self._canvases[cam]
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        if cw < 2 or ch < 2:
            return
        frame = self.frames_by_cam[cam][min(self._idx.get(), len(self.frames_by_cam[cam]) - 1)]
        h, w = frame.shape[:2]
        scale = min(cw / w, ch / h)
        dw, dh = max(1, int(w * scale)), max(1, int(h * scale))
        ox, oy = (cw - dw) // 2, (ch - dh) // 2
        self._geom[cam] = (scale, ox, oy, dw, dh)

        disp = cv2.resize(frame, (dw, dh), interpolation=cv2.INTER_AREA)
        photo = ImageTk.PhotoImage(Image.fromarray(disp))
        canvas.delete("all")
        canvas.create_image(ox, oy, anchor=tk.NW, image=photo)
        mag_photo = None

        roi = self.rois.get(cam)
        if roi:
            fs = self._scales[cam]
            x, y, rw, rh = roi
            # full-res -> sampled -> display
            sx0, sy0 = x / fs, y / fs
            sx1, sy1 = (x + rw) / fs, (y + rh) / fs
            canvas.create_rectangle(ox + sx0 * scale, oy + sy0 * scale,
                                    ox + sx1 * scale, oy + sy1 * scale,
                                    outline=_ROI_COLOR, width=2)
            # magnified crop (from the sampled frame) in the top-right corner
            cx0, cy0 = max(0, int(sx0)), max(0, int(sy0))
            cx1, cy1 = min(w, max(cx0 + 1, int(round(sx1)))), min(h, max(cy0 + 1, int(round(sy1))))
            crop = frame[cy0:cy1, cx0:cx1]
            if crop.size:
                mag = cv2.resize(crop, (_MAG_SIZE, _MAG_SIZE), interpolation=cv2.INTER_NEAREST)
                mag_photo = ImageTk.PhotoImage(Image.fromarray(mag))
                mx, my = cw - _MAG_SIZE - 6, 6
                canvas.create_image(mx, my, anchor=tk.NW, image=mag_photo)
                canvas.create_rectangle(mx, my, mx + _MAG_SIZE, my + _MAG_SIZE,
                                        outline=_ROI_COLOR, width=2)
        self._photos[cam] = (photo, mag_photo)

    def _redraw_all(self):
        for cam in self.cams:
            self._redraw(cam)

    # ── events ──

    def _on_slider(self, value):
        idx = int(round(float(value)))
        if idx != self._idx.get():
            self._idx.set(idx)
            self._update_time_label()
            self._redraw_all()

    def _update_time_label(self):
        self._time_label.config(text=f"{self._idx.get() / self.sample_fps:.2f} s")

    def _on_size_change(self):
        try:
            size = max(4, int(self._size.get()))
        except (tk.TclError, ValueError):
            return
        for cam, (x, y, w, h) in list(self.rois.items()):
            cx, cy = x + w / 2, y + h / 2
            self.rois[cam] = self._make_roi(cam, cx, cy, size)
            self._update_status(cam)
        self._redraw_all()

    def _make_roi(self, cam, cx, cy, size):
        fw, fh = self._full_size(cam)
        size = int(min(size, fw, fh))
        x = int(round(cx - size / 2))
        y = int(round(cy - size / 2))
        x = max(0, min(x, fw - size))
        y = max(0, min(y, fh - size))
        return (x, y, size, size)

    def _on_click(self, cam, event):
        geom = self._geom.get(cam)
        if geom is None:
            return
        scale, ox, oy, dw, dh = geom
        if not (ox <= event.x < ox + dw and oy <= event.y < oy + dh):
            return
        fs = self._scales[cam]
        cx = (event.x - ox) / scale * fs
        cy = (event.y - oy) / scale * fs
        try:
            size = max(4, int(self._size.get()))
        except (tk.TclError, ValueError):
            size = 80
        self.rois[cam] = self._make_roi(cam, cx, cy, size)
        self._update_status(cam)
        self._redraw(cam)
        self._update_ok()

    def _update_status(self, cam):
        roi = self.rois.get(cam)
        if roi:
            self._status[cam].set(f"GP{cam}: ROI (x={roi[0]}, y={roi[1]}, {roi[2]}x{roi[3]} px)")
        else:
            self._status[cam].set(f"GP{cam}: click the LED")

    def _update_ok(self):
        complete = all(c in self.rois for c in self.cams)
        self._ok_btn.config(state="normal" if complete else "disabled")

    def _ok(self):
        self.result = {c: tuple(self.rois[c]) for c in self.cams}
        self.top.destroy()

    def _cancel(self):
        self.result = None
        self.top.destroy()
