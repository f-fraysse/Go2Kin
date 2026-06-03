"""
Post-triangulation participant filter.

Deletes per-participant TRC files in `<processed>/pose-3d/` whose Hip keypoint
spends less than `percent_time_inside_volume` of the trial inside a cylindrical
inclusion volume centred on the world origin. Radius is sized from the mean
horizontal camera-to-origin distance in the calibration JSON.
"""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


percent_time_inside_volume = 0.02   # min fraction of frames Hip must be inside cylinder
inclusion_radius_factor = 0.5       # R = inclusion_radius_factor * D


def _mean_horizontal_camera_distance(calib_json_path: Path) -> tuple[float, int]:
    """Compute mean horizontal distance from world origin to each camera."""
    with open(calib_json_path) as f:
        data = json.load(f)

    cameras = data.get("cameras", {})
    if not cameras:
        raise ValueError(f"No cameras in calibration JSON: {calib_json_path}")

    distances = []
    for cam in cameras.values():
        R_mat = np.asarray(cam["rotation"], dtype=float)
        t_vec = np.asarray(cam["translation"], dtype=float).reshape(3)
        pos = -R_mat.T @ t_vec
        distances.append(float(np.hypot(pos[0], pos[1])))

    return float(np.mean(distances)), len(distances)


def _find_hip_marker_index(trc_path: Path) -> int:
    """Return the 0-indexed position of the Hip marker in the TRC file."""
    with open(trc_path) as f:
        for _ in range(3):
            f.readline()
        marker_line = f.readline()

    tokens = marker_line.rstrip("\n").split("\t")
    markers = [t for t in tokens[2:] if t]
    try:
        return markers.index("Hip")
    except ValueError:
        raise ValueError(f"'Hip' marker not found in {trc_path.name}")


def filter_participants_by_volume(processed_path: Path, calib_json_path: Path) -> None:
    """Delete TRC files whose Hip spends too little time inside the inclusion cylinder."""
    processed_path = Path(processed_path)
    calib_json_path = Path(calib_json_path)

    D, n_cams = _mean_horizontal_camera_distance(calib_json_path)
    R = inclusion_radius_factor * D
    print(f"[Participant Filter] Mean horizontal camera-origin distance "
          f"D = {D:.3f} m (over {n_cams} cameras)")
    print(f"[Participant Filter] Cylinder radius R = {R:.3f} m")

    pose3d_dir = processed_path / "pose-3d"
    if not pose3d_dir.exists():
        print(f"[Participant Filter] No pose-3d folder at {pose3d_dir}, skipping")
        return

    trc_files = sorted(p for p in pose3d_dir.glob("*.trc") if "filt" not in p.name)
    if not trc_files:
        print("[Participant Filter] No participant TRC files to evaluate")
        return

    kept = 0
    discarded = 0

    for trc in trc_files:
        try:
            k = _find_hip_marker_index(trc)
        except ValueError as e:
            print(f"[Participant Filter] Skipping {trc.name}: {e}")
            continue

        df = pd.read_csv(trc, sep="\t", skiprows=5, header=None)
        total = len(df)
        if total == 0:
            print(f"[Participant Filter] Discarding {trc.name} (empty TRC)")
            trc.unlink()
            discarded += 1
            continue

        hip_x = df.iloc[:, 2 + 3 * k].to_numpy(dtype=float)
        hip_z = df.iloc[:, 4 + 3 * k].to_numpy(dtype=float)
        r = np.hypot(hip_x, hip_z)
        inside = np.where(np.isnan(r), False, r <= R)
        inside_count = int(inside.sum())

        threshold = max(1, math.floor(total * percent_time_inside_volume))

        if inside_count < threshold:
            print(f"[Participant Filter] Discarding {trc.name} "
                  f"({inside_count}/{total} frames inside, threshold {threshold})")
            trc.unlink()
            discarded += 1
        else:
            print(f"[Participant Filter] Keeping {trc.name} "
                  f"({inside_count}/{total} frames inside)")
            kept += 1

    print(f"[Participant Filter] Kept {kept}, discarded {discarded} "
          f"participant TRC files.")
