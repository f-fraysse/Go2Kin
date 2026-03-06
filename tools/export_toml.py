"""Convert calibration.json to Caliscope/Pose2Sim camera_array.toml format.

Usage:
    python tools/export_toml.py [input.json] [output.toml]

Defaults:
    input:  config/calibration/calibration.json
    output: config/calibration/camera_array_go2kin.toml
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np


def main():
    root = Path(__file__).resolve().parent.parent
    default_in = root / "config" / "calibration" / "calibration.json"
    default_out = root / "config" / "calibration" / "camera_array_go2kin.toml"

    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_in
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else default_out

    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    with open(input_path) as f:
        data = json.load(f)

    lines = []
    for cam_id_str, cam in data["cameras"].items():
        R = np.array(cam["rotation"])
        rvec = cv2.Rodrigues(R)[0].flatten()
        t = cam["translation"]

        lines.append(f"[cam_{cam_id_str}]")
        lines.append(f"cam_id = {cam_id_str}")
        lines.append(f"rotation_count = {cam.get('rotation_count', 0)}")
        lines.append(f"error = {cam['error']}")
        lines.append(f"grid_count = {cam.get('grid_count', 0)}")
        lines.append(f"fisheye = {'true' if cam.get('fisheye') else 'false'}")
        lines.append(f"size = {cam['size']}")
        lines.append(f"matrix = {cam['matrix']}")
        lines.append(f"distortions = {cam['distortions']}")
        lines.append(f"translation = {list(t)}")
        lines.append(f"rotation = {rvec.tolist()}")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    print(f"Exported {len(data['cameras'])} cameras to {output_path}")


if __name__ == "__main__":
    main()
