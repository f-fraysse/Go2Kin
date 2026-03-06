"""Pure functions for intrinsic camera calibration.

Stateless functions for calibrating camera intrinsic parameters (camera matrix
and distortion coefficients) from charuco corner observations. Returns immutable
results; mutation handled by caller.

Adapted from caliscope/core/calibrate_intrinsics.py (BSD-2-Clause, Mac Prible).
"""

from dataclasses import dataclass, replace
import logging

import cv2
import numpy as np
from numpy.typing import NDArray

from calibration.data_types import CameraData, ImagePoints
from calibration.frame_selector import IntrinsicCoverageReport, select_calibration_frames

logger = logging.getLogger(__name__)

MIN_CORNERS_PER_FRAME = 4


@dataclass(frozen=True)
class IntrinsicCalibrationResult:
    camera_matrix: NDArray[np.float64]
    distortions: NDArray[np.float64]
    reprojection_error: float
    frames_used: int


@dataclass(frozen=True)
class IntrinsicCalibrationReport:
    rmse: float
    frames_used: int
    coverage_fraction: float
    edge_coverage_fraction: float
    corner_coverage_fraction: float
    orientation_sufficient: bool
    orientation_count: int
    selected_frames: tuple[int, ...]


@dataclass(frozen=True)
class IntrinsicCalibrationOutput:
    camera: CameraData
    report: IntrinsicCalibrationReport


def calibrate_intrinsics(
    image_points: ImagePoints,
    cam_id: int,
    image_size: tuple[int, int],
    selected_frames: list[int],
    *,
    fisheye: bool = False,
) -> IntrinsicCalibrationResult:
    obj_points_list, img_points_list = _extract_calibration_arrays(image_points, cam_id, selected_frames)

    if len(obj_points_list) == 0:
        raise ValueError(
            f"No valid calibration frames found for cam_id {cam_id}. "
            f"Ensure frames have at least {MIN_CORNERS_PER_FRAME} corners each."
        )

    width, height = image_size

    if fisheye:
        obj_pts = [p.reshape(-1, 1, 3).astype(np.float32) for p in obj_points_list]
        img_pts = [p.reshape(-1, 1, 2).astype(np.float32) for p in img_points_list]
        camera_matrix = np.zeros((3, 3), dtype=np.float64)
        dist_coeffs = np.zeros(4, dtype=np.float64)
        error, mtx, dist, rvecs, tvecs = cv2.fisheye.calibrate(
            obj_pts, img_pts, (width, height), camera_matrix, dist_coeffs,
            flags=cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC,
        )
        dist = dist.ravel()
    else:
        obj_pts = [p.astype(np.float32) for p in obj_points_list]
        img_pts = [p.astype(np.float32) for p in img_points_list]
        camera_matrix = np.zeros((3, 3), dtype=np.float64)
        dist_coeffs = np.zeros(5, dtype=np.float64)
        error, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
            obj_pts, img_pts, (width, height), camera_matrix, dist_coeffs,
        )
        dist = dist.ravel()

    logger.info(f"Calibration complete for cam_id {cam_id}: error={error:.4f}px, frames={len(obj_points_list)}")

    return IntrinsicCalibrationResult(
        camera_matrix=np.asarray(mtx, dtype=np.float64),
        distortions=np.asarray(dist, dtype=np.float64),
        reprojection_error=float(error),
        frames_used=len(obj_points_list),
    )


def _extract_calibration_arrays(
    image_points: ImagePoints, cam_id: int, frames: list[int],
) -> tuple[list[NDArray], list[NDArray]]:
    df = image_points.df
    mask = (df["cam_id"] == cam_id) & (df["sync_index"].isin(frames))
    cam_df = df[mask]

    obj_points_list: list[NDArray] = []
    img_points_list: list[NDArray] = []

    for sync_index in frames:
        frame_df = cam_df[cam_df["sync_index"] == sync_index]
        if len(frame_df) < MIN_CORNERS_PER_FRAME:
            continue

        img_loc: NDArray = np.asarray(frame_df[["img_loc_x", "img_loc_y"]])
        obj_loc: NDArray = np.asarray(frame_df[["obj_loc_x", "obj_loc_y", "obj_loc_z"]])
        obj_loc = np.nan_to_num(obj_loc, nan=0.0)

        obj_points_list.append(obj_loc)
        img_points_list.append(img_loc)

    return obj_points_list, img_points_list


def run_intrinsic_calibration(
    camera: CameraData,
    image_points: ImagePoints,
    selection_result: IntrinsicCoverageReport | None = None,
) -> IntrinsicCalibrationOutput:
    """Execute complete intrinsic calibration workflow."""
    cam_id = camera.cam_id
    image_size = camera.size
    fisheye = camera.fisheye

    if selection_result is None:
        selection_result = select_calibration_frames(image_points, cam_id, image_size)

    if not selection_result.selected_frames:
        raise ValueError(f"No frames selected for calibration on cam_id {cam_id}")

    selected_frames = selection_result.selected_frames

    calibration_result = calibrate_intrinsics(
        image_points, cam_id, image_size, selected_frames, fisheye=fisheye,
    )

    calibrated_camera = replace(
        camera,
        matrix=calibration_result.camera_matrix,
        distortions=calibration_result.distortions,
        error=calibration_result.reprojection_error,
        grid_count=calibration_result.frames_used,
    )

    report = IntrinsicCalibrationReport(
        rmse=calibration_result.reprojection_error,
        frames_used=calibration_result.frames_used,
        coverage_fraction=selection_result.coverage_fraction,
        edge_coverage_fraction=selection_result.edge_coverage_fraction,
        corner_coverage_fraction=selection_result.corner_coverage_fraction,
        orientation_sufficient=selection_result.orientation_sufficient,
        orientation_count=selection_result.orientation_count,
        selected_frames=tuple(selected_frames),
    )

    logger.info(
        f"Calibration complete for cam_id {cam_id}: "
        f"rmse={report.rmse:.3f}px, frames={report.frames_used}, "
        f"coverage={report.coverage_fraction:.0%}"
    )

    return IntrinsicCalibrationOutput(camera=calibrated_camera, report=report)
