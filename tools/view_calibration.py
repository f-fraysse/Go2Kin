"""Standalone 3D viewer for calibration camera positions.

Usage:
    python tools/view_calibration.py [path_to_calibration.json]

Defaults to config/calibration/calibration.json if no path given.
"""

import json
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt


def load_cameras(filepath: Path):
    with open(filepath) as f:
        data = json.load(f)

    cameras = {}
    for cam_id_str, cam_dict in data["cameras"].items():
        cam_id = int(cam_id_str)
        if "rotation" in cam_dict and "translation" in cam_dict:
            R = np.array(cam_dict["rotation"])
            t = np.array(cam_dict["translation"])
            # Camera position in world: C = -R^T @ t
            pos = -R.T @ t
            cameras[cam_id] = {"pos": pos, "R": R, "t": t}
    return cameras


def main():
    default_path = Path(__file__).resolve().parent.parent / "config" / "calibration" / "calibration.json"
    filepath = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path

    if not filepath.exists():
        print(f"File not found: {filepath}")
        sys.exit(1)

    cameras = load_cameras(filepath)
    if not cameras:
        print("No cameras with extrinsic data found in calibration file.")
        sys.exit(1)

    fig = plt.figure(figsize=(8, 6))
    ax = fig.add_subplot(111, projection="3d")

    # Equal aspect ratio on all axes
    all_pos = np.array([cam["pos"] for cam in cameras.values()])
    mid = (all_pos.max(axis=0) + all_pos.min(axis=0)) / 2
    half_range = (all_pos.max(axis=0) - all_pos.min(axis=0)).max() / 2 * 1.1
    ax.set_xlim(mid[0] - half_range, mid[0] + half_range)
    ax.set_ylim(mid[1] - half_range, mid[1] + half_range)
    ax.set_zlim(mid[2] - half_range, mid[2] + half_range)

    arrow_len = half_range * 0.25

    for cam_id, cam in sorted(cameras.items()):
        pos = cam["pos"]
        R = cam["R"]
        # Principal axis is camera Z axis in world coords
        look_dir = R.T @ np.array([0, 0, 1])
        ax.scatter(*pos, s=100, zorder=5)
        ax.quiver(pos[0], pos[1], pos[2],
                  look_dir[0], look_dir[1], look_dir[2],
                  length=arrow_len, arrow_length_ratio=0.15, color="red", linewidth=1.5)
        ax.text(pos[0], pos[1], pos[2], f"  Cam {cam_id}", fontsize=10)
        print(f"Camera {cam_id}: pos = [{pos[0]:.4f}, {pos[1]:.4f}, {pos[2]:.4f}]")

    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_zlabel("Z")
    ax.set_title("Camera Positions")

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
