"""
Save/load calibration data as JSON.

Provides serialization for CameraArray, Charuco config, and calibration results.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

import numpy as np

from calibration.charuco import Charuco
from calibration.data_types import CameraArray, CameraData

logger = logging.getLogger(__name__)


def save_calibration(
    filepath: Path,
    camera_array: CameraArray,
    charuco: Charuco,
) -> None:
    """Save calibration to JSON file.

    Args:
        filepath: Path to output JSON file
        camera_array: Calibrated camera array
        charuco: Charuco board configuration
    """
    data = {
        "charuco": _charuco_to_dict(charuco),
        "cameras": {
            str(cam_id): _camera_data_to_dict(cam)
            for cam_id, cam in camera_array.cameras.items()
        },
    }

    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"Calibration saved to {filepath}")

    # Auto-export TOML for Pose2Sim compatibility
    try:
        toml_script = Path(__file__).resolve().parents[2] / "tools" / "export_toml.py"
        if toml_script.exists():
            subprocess.run([sys.executable, str(toml_script), str(filepath)], check=False)
    except Exception as e:
        logger.warning(f"TOML export failed: {e}")


def load_calibration(filepath: Path) -> tuple[CameraArray, Charuco]:
    """Load calibration from JSON file.

    Args:
        filepath: Path to JSON file

    Returns:
        (CameraArray, Charuco)
    """
    with open(filepath) as f:
        data = json.load(f)

    charuco = _dict_to_charuco(data["charuco"])
    cameras = {
        int(cam_id): _dict_to_camera_data(int(cam_id), cam_dict)
        for cam_id, cam_dict in data["cameras"].items()
    }
    camera_array = CameraArray(cameras=cameras)

    logger.info(f"Calibration loaded from {filepath}")
    return camera_array, charuco


def save_charuco_config(filepath: Path, charuco: Charuco) -> None:
    """Save charuco board config to JSON."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(_charuco_to_dict(charuco), f, indent=2)
    logger.info(f"Charuco config saved to {filepath}")


def load_charuco_config(filepath: Path) -> Charuco:
    """Load charuco board config from JSON."""
    with open(filepath) as f:
        data = json.load(f)
    return _dict_to_charuco(data)


# =============================================================================
# Internal serialization helpers
# =============================================================================

def _charuco_to_dict(charuco: Charuco) -> dict:
    return {
        "columns": charuco.columns,
        "rows": charuco.rows,
        "board_height": charuco.board_height,
        "board_width": charuco.board_width,
        "dictionary": charuco.dictionary,
        "aruco_scale": charuco.aruco_scale,
        "inverted": charuco.inverted,
        "square_size_overide_cm": charuco.square_size_overide_cm,
    }


def _dict_to_charuco(d: dict) -> Charuco:
    return Charuco(
        columns=d["columns"],
        rows=d["rows"],
        board_height=d["board_height"],
        board_width=d["board_width"],
        dictionary=d["dictionary"],
        aruco_scale=d["aruco_scale"],
        inverted=d["inverted"],
        square_size_overide_cm=d.get("square_size_overide_cm"),
    )


def _camera_data_to_dict(cam: CameraData) -> dict:
    d: dict = {
        "size": list(cam.size),
        "rotation_count": cam.rotation_count,
        "error": cam.error,
        "fisheye": cam.fisheye,
        "ignore": cam.ignore,
    }

    if cam.matrix is not None:
        d["matrix"] = cam.matrix.tolist()
    if cam.distortions is not None:
        d["distortions"] = cam.distortions.tolist()
    if cam.rotation is not None:
        d["rotation"] = cam.rotation.tolist()
    if cam.translation is not None:
        d["translation"] = cam.translation.tolist()
    if cam.grid_count is not None:
        d["grid_count"] = cam.grid_count
    if cam.exposure is not None:
        d["exposure"] = cam.exposure

    return d


def _dict_to_camera_data(cam_id: int, d: dict) -> CameraData:
    cam = CameraData(
        cam_id=cam_id,
        size=tuple(d["size"]),
        rotation_count=d.get("rotation_count", 0),
        error=d.get("error"),
        fisheye=d.get("fisheye", False),
        ignore=d.get("ignore", False),
        grid_count=d.get("grid_count"),
        exposure=d.get("exposure"),
    )

    if "matrix" in d:
        cam.matrix = np.array(d["matrix"], dtype=np.float64)
    if "distortions" in d:
        cam.distortions = np.array(d["distortions"], dtype=np.float64)
    if "rotation" in d:
        cam.rotation = np.array(d["rotation"], dtype=np.float64)
    if "translation" in d:
        cam.translation = np.array(d["translation"], dtype=np.float64)

    return cam
