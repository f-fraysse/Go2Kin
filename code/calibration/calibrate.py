"""
High-level calibration orchestrator for Go2Kin.

Provides run_intrinsic_calibration(), run_extrinsic_calibration(), and set_origin()
as the main entry points for the calibration pipeline.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from calibration.alignment import estimate_similarity_transform, apply_similarity_transform
from calibration.bundle_adjustment import PointDataBundle
from calibration.charuco import Charuco
from calibration.data_types import CameraArray, CameraData, ImagePoints
from calibration.extrinsic import PoseNetworkBuilder
from calibration.intrinsic import IntrinsicCalibrationOutput, run_intrinsic_calibration as _run_intrinsic
from calibration.triangulation import triangulate_image_points
from calibration.video_processor import (
    discover_synced_videos,
    extract_charuco_points_from_video,
    extract_charuco_points_from_videos,
    get_video_image_size,
)

logger = logging.getLogger(__name__)


def run_intrinsic_calibration_from_video(
    video_path: Path,
    cam_id: int,
    charuco: Charuco,
    *,
    fisheye: bool = False,
    sample_fps: float = 5.0,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> IntrinsicCalibrationOutput:
    """Run intrinsic calibration from a single video file.

    Pipeline:
    1. Extract charuco corners from video
    2. Select best calibration frames (orientation diversity + spatial coverage)
    3. Run cv2.calibrateCamera
    4. Return calibrated CameraData + report

    Args:
        video_path: Path to calibration video (charuco board in view)
        cam_id: Camera identifier
        charuco: Charuco board definition
        fisheye: Use fisheye model (4 distortion coeffs) instead of standard (5)
        sample_fps: Frame sampling rate
        progress_callback: Optional fn(cam_id, frame_idx, total_frames)

    Returns:
        IntrinsicCalibrationOutput with calibrated camera and report
    """
    logger.info(f"Intrinsic calibration for camera {cam_id} from {video_path.name}")

    # Extract corners
    image_points = extract_charuco_points_from_video(
        video_path, cam_id, charuco, sample_fps, progress_callback,
    )

    if image_points.df.empty:
        raise ValueError(f"No charuco corners detected in {video_path}")

    # Get video resolution
    image_size = get_video_image_size(video_path)

    # Create uncalibrated CameraData
    camera = CameraData(cam_id=cam_id, size=image_size, fisheye=fisheye)

    # Run calibration (frame selection + cv2.calibrateCamera)
    output = _run_intrinsic(camera, image_points)

    logger.info(
        f"Camera {cam_id} intrinsic calibration: "
        f"RMSE={output.report.rmse:.3f}px, frames={output.report.frames_used}"
    )
    return output


def run_extrinsic_calibration(
    synced_folder: Path,
    charuco: Charuco,
    camera_array: CameraArray,
    *,
    sample_fps: float = 5.0,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> PointDataBundle:
    """Run extrinsic calibration from synchronized multi-camera videos.

    Pipeline:
    1. Discover synced MP4 files in folder
    2. Extract charuco corners from all cameras
    3. PnP per camera per frame -> relative poses
    4. IQR outlier rejection -> quaternion averaging
    5. Stereo pair network with bridging -> global camera poses
    6. DLT triangulation -> 3D world points
    7. Bundle adjustment (scipy least_squares)

    Requires: all cameras in camera_array must be intrinsically calibrated.

    Args:
        synced_folder: Path to synced/ subfolder containing per-camera MP4s
        charuco: Charuco board definition
        camera_array: CameraArray with intrinsic calibration (will be mutated)
        sample_fps: Frame sampling rate for corner extraction
        progress_callback: Optional fn(cam_id, frame_idx, total_frames)

    Returns:
        PointDataBundle with optimized camera poses and world points
    """
    logger.info(f"Extrinsic calibration from {synced_folder}")

    # 1. Discover videos
    video_map = discover_synced_videos(synced_folder)
    logger.info(f"Found {len(video_map)} cameras")

    # 2. Extract charuco corners
    image_points = extract_charuco_points_from_videos(
        video_map, charuco, sample_fps, progress_callback,
    )
    logger.info(f"Extracted {len(image_points.df)} observations")

    # 3-4. PnP + outlier rejection + aggregation -> pose network
    network = (
        PoseNetworkBuilder(camera_array, image_points)
        .estimate_camera_to_object_poses()
        .estimate_relative_poses()
        .filter_outliers()
        .build()
    )

    # 5. Apply network to get global camera poses
    network.apply_to(camera_array)
    logger.info("Camera poses computed")

    # 6. Triangulate
    world_points = triangulate_image_points(image_points, camera_array)
    logger.info(f"Triangulated {len(world_points.df)} 3D points")

    # 7. Bundle adjustment
    bundle = PointDataBundle(
        camera_array=camera_array,
        image_points=image_points,
        world_points=world_points,
    )

    optimized_bundle = bundle.optimize(verbose=0)
    logger.info(
        f"Bundle adjustment: converged={optimized_bundle.optimization_status.converged}, "
        f"RMSE={optimized_bundle.reprojection_report.overall_rmse:.3f}px"
    )

    return optimized_bundle


def set_origin(
    origin_folder: Path,
    charuco: Charuco,
    camera_array: CameraArray,
    bundle: PointDataBundle,
    *,
    sample_fps: float = 5.0,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> PointDataBundle:
    """Set the coordinate origin using a charuco board at the lab origin.

    Pipeline:
    1. Extract charuco corners from origin videos
    2. Triangulate board corners
    3. Umeyama similarity transform to align to board's known 3D coordinates

    Args:
        origin_folder: Folder with short recordings of board at lab origin
        charuco: Charuco board definition
        camera_array: CameraArray with extrinsic calibration
        bundle: Existing PointDataBundle to align
        sample_fps: Frame sampling rate
        progress_callback: Optional fn(cam_id, frame_idx, total_frames)

    Returns:
        New PointDataBundle aligned to real-world coordinates
    """
    logger.info(f"Setting origin from {origin_folder}")

    # Discover and extract corners from origin videos
    video_map = discover_synced_videos(origin_folder)
    origin_points = extract_charuco_points_from_videos(
        video_map, charuco, sample_fps, progress_callback,
    )

    if origin_points.df.empty:
        raise ValueError("No charuco corners detected in origin videos")

    # Triangulate origin corners
    origin_world = triangulate_image_points(origin_points, camera_array)
    if origin_world.df.empty:
        raise ValueError("Could not triangulate any origin board corners")

    # Create temporary bundle for alignment
    origin_bundle = PointDataBundle(
        camera_array=camera_array,
        image_points=origin_points,
        world_points=origin_world,
    )

    # Find the sync_index with most triangulated corners
    sync_counts = origin_world.df.groupby("sync_index").size()
    best_sync = int(sync_counts.idxmax())
    logger.info(f"Using sync_index {best_sync} with {sync_counts[best_sync]} corners for alignment")

    # Align using object coordinates from that frame
    aligned_bundle = origin_bundle.align_to_object(best_sync)

    # Apply the same transform to the main bundle
    # We need to recompute the transform and apply it to the main bundle's data
    img_df = origin_points.df
    world_df = origin_world.df

    img_sub = img_df[img_df["sync_index"] == best_sync]
    world_sub = world_df[world_df["sync_index"] == best_sync]

    import pandas as pd
    merged = pd.merge(
        world_sub[["point_id", "x_coord", "y_coord", "z_coord"]],
        img_sub[["point_id", "obj_loc_x", "obj_loc_y", "obj_loc_z"]],
        on="point_id", how="inner",
    )

    if merged["obj_loc_z"].isna().all():
        merged = merged.copy()
        merged["obj_loc_z"] = 0.0

    obj_cols = ["obj_loc_x", "obj_loc_y", "obj_loc_z"]
    valid = ~merged[obj_cols].isna().any(axis=1)
    merged = merged[valid]

    source = merged[["x_coord", "y_coord", "z_coord"]].values.astype(np.float64)
    target = merged[obj_cols].values.astype(np.float64)
    target[:, 2] *= -1  # Flip Z axis to point upward

    transform = estimate_similarity_transform(source, target)
    logger.info(f"Origin alignment: scale={transform.scale:.6f}")

    # Apply transform to the main bundle's camera array and world points
    new_cam, new_world = apply_similarity_transform(
        bundle.camera_array, bundle.world_points, transform,
    )

    return PointDataBundle(
        camera_array=new_cam,
        image_points=bundle.image_points,
        world_points=new_world,
        _optimization_status=bundle.optimization_status,
    )
