"""
Re-run sync (audio or light) on an already-recorded trial and store the offsets.

The GUI only syncs automatically straight after recording, so this CLI lets you
re-sync an existing trial with the current audio_sync / light_sync code. It
imports and calls the real sync functions rather than reimplementing them.
Nothing is trimmed or re-encoded: the per-camera frame offsets are written to
trial.json["sync"] (see audio_sync.offsets_to_trial_sync) and the sync plot to
processed/videos/.

Usage:
    python tools/resync_trial.py "<project>/sessions/<session>/<trial>" [audio|light]

The method defaults to trial.json["sync_method"]. Light sync takes the LED ROIs
from the trial's calibration JSON (<project>/calibrations/<calibration_file>.json).

Note: no speed-of-sound compensation is applied for audio (the standalone tool
has no sound-source context). Use the Recording tab for compensated sync.
"""

import json
import sys
from pathlib import Path

# Import the real sync modules from code/ (matches repo import style)
CODE_DIR = Path(__file__).resolve().parent.parent / "code"
sys.path.insert(0, str(CODE_DIR))

from audio_sync import (  # noqa: E402
    compute_sync_offsets,
    evaluate_sync_acceptance,
    offsets_to_trial_sync,
    GP_CAM_RE,
    AudioSyncError,
)
from light_sync import (  # noqa: E402
    compute_light_sync_offsets,
    evaluate_light_sync_acceptance,
    resolve_rois_for_videos,
)


def _load_rois_from_calib(path):
    with open(path) as f:
        data = json.load(f)
    rois = {}
    for cam_id, cam in data["cameras"].items():
        if cam.get("led_roi"):
            rois[int(cam_id)] = {"roi": tuple(cam["led_roi"]), "size": tuple(cam["size"])}
    return rois


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    trial_dir = Path(sys.argv[1])
    trial_json = trial_dir / "trial.json"
    if not trial_json.is_file():
        print(f"ERROR: no trial.json in {trial_dir}")
        sys.exit(1)
    trial = json.loads(trial_json.read_text())
    method = sys.argv[2] if len(sys.argv) > 2 else trial.get("sync_method", "audio")

    video_dir = trial_dir / "processed" / "videos"
    video_paths = sorted(str(p) for p in video_dir.glob("*.mp4") if GP_CAM_RE.search(p.name))
    if len(video_paths) < 2:
        print(f"ERROR: need at least 2 *_GP<N>.mp4 files in {video_dir}, found {len(video_paths)}")
        sys.exit(1)

    print(f"Re-syncing ({method}) {len(video_paths)} videos in {video_dir}")
    for vp in video_paths:
        print(f"  {Path(vp).name}")

    log = lambda msg: print(f"  {msg}")  # noqa: E731

    try:
        if method == "light":
            project_dir = trial_dir.parents[2]
            calib = project_dir / "calibrations" / f"{trial['calibration_file']}.json"
            rois = resolve_rois_for_videos(video_paths, _load_rois_from_calib(calib))
            offsets = compute_light_sync_offsets(
                video_paths, rois, output_dir=str(video_dir), progress_callback=log)
            ok, reasons = evaluate_light_sync_acceptance(offsets, max_offset_ms=200.0)
        else:
            offsets = compute_sync_offsets(
                video_paths, output_dir=str(video_dir), progress_callback=log)
            ok, reasons = evaluate_sync_acceptance(offsets, max_offset_ms=200.0)
    except AudioSyncError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    print(f"\nAcceptance: {'PASS' if ok else 'FAIL'}")
    for r in reasons:
        print(f"  - {r}")
    if not ok:
        print("trial.json not changed.")
        sys.exit(1)

    sync = offsets_to_trial_sync(offsets)
    trial.update(synced=True, sync_method=method, sync=sync)
    trial_json.write_text(json.dumps(trial, indent=2))
    print(f"\nWrote trial.json sync: {sync}")


if __name__ == "__main__":
    main()
