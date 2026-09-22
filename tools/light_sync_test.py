"""
Light (LED flash) sync test script.

Runs the real light_sync detector on a folder of raw *_GP{N}.mp4 recordings and
prints the summary table, acceptance verdict and step timing; saves
synced/sync_led_signal.png next to the videos. Set USE_DIALOG to open the ROI
picker on the folder instead (prints the chosen ROIs to paste into ROIS).

Usage:
    python tools/light_sync_test.py ["<...>/<trial>/video"]

If no path is given, VIDEO_DIR below is used. See docs/light_sync_spec.md.
"""

import sys
from pathlib import Path

# Import the real light_sync module from code/ (matches repo import style)
CODE_DIR = Path(__file__).resolve().parent.parent / "code"
sys.path.insert(0, str(CODE_DIR))

from audio_sync import StepTimer, AudioSyncError  # noqa: E402
from light_sync import (  # noqa: E402
    compute_light_sync_offsets,
    evaluate_light_sync_acceptance,
    resolve_rois_for_videos,
    sample_frames_for_roi,
    cam_id_from_filename,
    LIGHT_SEARCH_SECONDS,
)

# === CONFIGURE THESE ===
VIDEO_DIR = Path(r"D:\Markerless_Projects\tests_Francois\sessions\Charlotte_Pilot2\LED_loc\video")
# Full-resolution (x, y, w, h) ROI around the LED, per camera number. Used when
# CALIB_FILE is None. Get them from USE_DIALOG = True.
ROIS = {
    1: (764, 750, 80, 80),
    2: (806, 714, 80, 80),
    3: (936, 758, 80, 80),
    4: (1006, 782, 80, 80),
}
# Frame size the ROIS above were defined on (None = same as the videos).
ROI_SIZE = (1920, 1080)
# Optional calibration JSON with per-camera "led_roi" (overrides ROIS).
CALIB_FILE = None
SEARCH_SECONDS = LIGHT_SEARCH_SECONDS
USE_DIALOG = False


def _load_rois_from_calib(path):
    import json
    with open(path) as f:
        data = json.load(f)
    rois = {}
    for cam_id, cam in data["cameras"].items():
        if cam.get("led_roi"):
            rois[int(cam_id)] = {"roi": tuple(cam["led_roi"]), "size": tuple(cam["size"])}
    return rois


def main():
    video_dir = Path(sys.argv[1] if len(sys.argv) > 1 else VIDEO_DIR)
    if not video_dir.is_dir():
        print(f"ERROR: not a directory: {video_dir}")
        sys.exit(1)

    video_paths = sorted(
        str(p) for p in video_dir.iterdir()
        if p.suffix.lower() == ".mp4" and cam_id_from_filename(p.name) is not None
    )
    if len(video_paths) < 2:
        print(f"ERROR: need at least 2 *_GP{{N}}.mp4 files in {video_dir}, found {len(video_paths)}")
        sys.exit(1)

    print(f"Light sync on {len(video_paths)} videos in {video_dir}")
    for vp in video_paths:
        print(f"  {Path(vp).name}")

    if USE_DIALOG:
        import tkinter as tk
        from GUI.components.led_roi_dialog import show_led_roi_dialog

        frames_by_cam = {}
        frame_scale = 1.0
        for vp in video_paths:
            cam_id = cam_id_from_filename(vp)
            print(f"  Decoding preview frames for GP{cam_id}...")
            frames, frame_scale = sample_frames_for_roi(vp, seconds=SEARCH_SECONDS)
            frames_by_cam[cam_id] = frames
        root = tk.Tk()
        root.withdraw()
        result = show_led_roi_dialog(root, frames_by_cam, frame_scale,
                                     initial_rois={k: v for k, v in ROIS.items()})
        root.destroy()
        if result is None:
            print("Cancelled.")
            return
        print("\nROIS = {")
        for cam_id in sorted(result):
            print(f"    {cam_id}: {tuple(result[cam_id])},")
        print("}")
        return

    if CALIB_FILE:
        rois_by_cam = _load_rois_from_calib(CALIB_FILE)
    else:
        rois_by_cam = {k: {"roi": v, "size": ROI_SIZE} for k, v in ROIS.items()}

    log = lambda msg: print(f"  {msg}")  # noqa: E731
    timer = StepTimer()
    try:
        rois = resolve_rois_for_videos(video_paths, rois_by_cam)
        results = compute_light_sync_offsets(
            video_paths, rois, output_dir=str(video_dir),
            progress_callback=log, timer=timer, seconds=SEARCH_SECONDS,
        )
    except AudioSyncError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
    timer.stop()

    ok, reasons = evaluate_light_sync_acceptance(results, max_offset_ms=200.0)
    print(f"\nAcceptance: {'PASS' if ok else 'FAIL'}")
    for r in reasons:
        print(f"  - {r}")
    print()
    print(timer.format_table())


if __name__ == "__main__":
    main()
