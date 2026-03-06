"""Video file to ImagePoints bridge.

Processes MP4 video files to extract charuco corner observations,
producing ImagePoints DataFrames for the calibration pipelines.
"""

import logging
import re
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
import pandas as pd

from calibration.charuco import Charuco
from calibration.charuco_tracker import CharucoTracker
from calibration.data_types import ImagePoints

logger = logging.getLogger(__name__)

# Files to skip when scanning a synced folder
SKIP_FILES = {"stitched_videos.mp4", "timestamps.csv"}

# Pattern for Go2Kin filename convention: {trial}_GP{N}.mp4
GP_PATTERN = re.compile(r"_GP(\d+)\.mp4$", re.IGNORECASE)


def extract_charuco_points_from_video(
    video_path: Path,
    cam_id: int,
    charuco: Charuco,
    sample_fps: float = 5.0,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> ImagePoints:
    """Extract charuco corners from a single video file.

    Args:
        video_path: Path to MP4 file.
        cam_id: Camera identifier for this video.
        charuco: Charuco board definition.
        sample_fps: Frames per second to sample (not every frame).
        progress_callback: Optional fn(cam_id, frame_idx, total_frames).

    Returns:
        ImagePoints with corners detected in sampled frames.
    """
    tracker = CharucoTracker(charuco)
    all_rows = []

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, int(fps / sample_fps))

    sync_index = 0
    for frame_idx in range(0, total_frames, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        point_packet = tracker.get_points(frame, cam_id=cam_id)
        if len(point_packet.point_id) > 0:
            for i in range(len(point_packet.point_id)):
                row = {
                    "sync_index": sync_index,
                    "cam_id": cam_id,
                    "point_id": int(point_packet.point_id[i]),
                    "img_loc_x": float(point_packet.img_loc[i, 0]),
                    "img_loc_y": float(point_packet.img_loc[i, 1]),
                    "obj_loc_x": float(point_packet.obj_loc[i, 0]),
                    "obj_loc_y": float(point_packet.obj_loc[i, 1]),
                    "obj_loc_z": float(point_packet.obj_loc[i, 2]),
                }
                all_rows.append(row)

        sync_index += 1

        if progress_callback:
            progress_callback(cam_id, frame_idx, total_frames)

    cap.release()

    if not all_rows:
        logger.warning(f"No charuco corners detected in {video_path}")

    return ImagePoints(pd.DataFrame(all_rows) if all_rows else pd.DataFrame(
        columns=["sync_index", "cam_id", "point_id", "img_loc_x", "img_loc_y",
                 "obj_loc_x", "obj_loc_y", "obj_loc_z"]
    ))


def extract_charuco_points_from_videos(
    video_paths: dict[int, Path],
    charuco: Charuco,
    sample_fps: float = 5.0,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> ImagePoints:
    """Extract charuco corners from multiple synchronized video files.

    For extrinsic calibration, the same sync_index across cameras represents
    the same moment in time (videos must be pre-synchronized).

    Args:
        video_paths: Mapping of cam_id -> video file path.
        charuco: Charuco board definition.
        sample_fps: Frames per second to sample.
        progress_callback: Optional fn(cam_id, frame_idx, total_frames).

    Returns:
        Combined ImagePoints from all cameras.
    """
    all_dfs = []

    for cam_id, video_path in sorted(video_paths.items()):
        logger.info(f"Processing camera {cam_id}: {video_path.name}")
        ip = extract_charuco_points_from_video(
            video_path, cam_id, charuco, sample_fps, progress_callback,
        )
        all_dfs.append(ip.df)

    if not all_dfs:
        raise ValueError("No video files provided")

    combined = pd.concat(all_dfs, ignore_index=True)
    return ImagePoints(combined)


def get_video_image_size(video_path: Path) -> tuple[int, int]:
    """Get (width, height) from a video file."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return (w, h)


def discover_synced_videos(synced_folder: Path) -> dict[int, Path]:
    """Discover MP4 files in a synced folder and map to camera numbers.

    Uses Go2Kin naming convention: {trial}_GP{N}.mp4
    Skips stitched_videos.mp4 and timestamps.csv.

    Args:
        synced_folder: Path to synced/ subfolder.

    Returns:
        Dict mapping camera number (int) -> video file path.

    Raises:
        ValueError: If no valid MP4 files found or camera numbers can't be parsed.
    """
    mp4_files = [
        f for f in synced_folder.glob("*.mp4")
        if f.name.lower() not in SKIP_FILES
    ]

    if not mp4_files:
        raise ValueError(f"No MP4 files found in {synced_folder} (excluding {SKIP_FILES})")

    video_map: dict[int, Path] = {}
    unmatched: list[Path] = []

    for f in sorted(mp4_files):
        match = GP_PATTERN.search(f.name)
        if match:
            cam_num = int(match.group(1))
            video_map[cam_num] = f
        else:
            unmatched.append(f)

    if unmatched and not video_map:
        raise ValueError(
            f"Could not parse camera numbers from filenames: {[f.name for f in unmatched]}. "
            f"Expected Go2Kin naming convention: {{trial}}_GP{{N}}.mp4"
        )

    if unmatched:
        logger.warning(f"Skipping files with unrecognized names: {[f.name for f in unmatched]}")

    logger.info(f"Discovered {len(video_map)} camera videos: {dict((k, v.name) for k, v in video_map.items())}")
    return video_map
