"""
Pure-numpy DLT triangulation.

Adapted from caliscope/core/point_data.py (BSD-2-Clause, Lili Karashchuk / Anipose).
Numba JIT removed — pure numpy implementation. Interface is compatible so numba
can be added back later for performance if needed.
"""

from __future__ import annotations

import logging
from time import time

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from calibration.data_types import CameraArray, ImagePoints, WorldPoints

logger = logging.getLogger(__name__)


def triangulate_sync_index(
    projection_matrices: dict,
    current_camera_indices: np.ndarray,
    current_point_id: np.ndarray,
    current_img: np.ndarray,
) -> tuple[list, list]:
    """Triangulate points for a single sync_index using DLT (SVD).

    Pure numpy version of the numba-jitted caliscope function.

    Args:
        projection_matrices: dict mapping cam_id -> 3x4 projection matrix
        current_camera_indices: (N,) camera IDs for each observation
        current_point_id: (N,) point IDs for each observation
        current_img: (N, 2) undistorted image coordinates

    Returns:
        (point_ids, points_xyz): lists of triangulated point IDs and 3D coords
    """
    point_indices_xyz = []
    obj_xyz = []

    if len(current_point_id) < 2:
        return point_indices_xyz, obj_xyz

    # Sort by point_id to group observations of the same point
    sort_indices = np.argsort(current_point_id)
    sorted_points = current_point_id[sort_indices]
    sorted_cams = current_camera_indices[sort_indices]
    sorted_img = current_img[sort_indices]

    # Find group boundaries
    group_start = 0
    for i in range(1, len(sorted_points) + 1):
        # Process group when point_id changes or at end
        if i == len(sorted_points) or sorted_points[i] != sorted_points[group_start]:
            group_size = i - group_start
            if group_size > 1:
                point = sorted_points[group_start]
                points_xy = sorted_img[group_start:i]
                camera_ids = sorted_cams[group_start:i]
                num_cams = len(camera_ids)

                A = np.zeros((num_cams * 2, 4))
                for j in range(num_cams):
                    x, y = points_xy[j]
                    P = projection_matrices[camera_ids[j]]
                    A[j * 2] = x * P[2] - P[0]
                    A[j * 2 + 1] = y * P[2] - P[1]

                _, _, vh = np.linalg.svd(A, full_matrices=True)
                point_xyzw = vh[-1]
                point_xyz = point_xyzw[:3] / point_xyzw[3]
                point_indices_xyz.append(point)
                obj_xyz.append(point_xyz)

            if i < len(sorted_points):
                group_start = i

    return point_indices_xyz, obj_xyz


def _undistort_batch(xy_df: pd.DataFrame, camera_array: CameraArray) -> pd.DataFrame:
    """Undistort all image points in a DataFrame, grouped by camera."""
    undistorted_parts = []
    for cam_id, camera in camera_array.cameras.items():
        if camera.matrix is None:
            continue
        subset = xy_df.query(f"cam_id == {cam_id}").copy()
        if subset.empty:
            continue
        points = np.vstack([subset["img_loc_x"], subset["img_loc_y"]]).T
        undistorted_xy = camera.undistort_points(points, output="normalized")
        subset["img_loc_undistort_x"] = undistorted_xy[:, 0]
        subset["img_loc_undistort_y"] = undistorted_xy[:, 1]
        undistorted_parts.append(subset)

    if not undistorted_parts:
        return pd.DataFrame()
    return pd.concat(undistorted_parts)


def triangulate_image_points(
    image_points: ImagePoints,
    camera_array: CameraArray,
) -> WorldPoints:
    """Triangulate 2D image points to 3D world points.

    Undistorts points, then runs DLT triangulation per sync_index.

    Args:
        image_points: 2D point observations from multiple cameras
        camera_array: Camera array with intrinsic and extrinsic calibration

    Returns:
        WorldPoints with triangulated 3D coordinates
    """
    xy_df = image_points.df
    if xy_df.empty:
        return WorldPoints(pd.DataFrame(columns=["sync_index", "point_id", "x_coord", "y_coord", "z_coord"]))

    # Only process posed cameras
    posed_cam_ids = list(camera_array.posed_cam_id_to_index.keys())
    valid_cam_ids = [c for c in xy_df["cam_id"].unique() if c in posed_cam_ids]

    if not valid_cam_ids:
        logger.warning("No cameras in data have extrinsics for triangulation")
        return WorldPoints(pd.DataFrame(columns=["sync_index", "point_id", "x_coord", "y_coord", "z_coord"]))

    projection_matrices = camera_array.normalized_projection_matrices
    undistorted_xy = _undistort_batch(xy_df, camera_array)

    # Mean frame_time per sync_index
    frame_times = xy_df.groupby("sync_index")["frame_time"].mean()

    xyz_data: dict[str, list] = {
        "sync_index": [], "point_id": [],
        "x_coord": [], "y_coord": [], "z_coord": [],
        "frame_time": [],
    }

    valid_sync_indices = undistorted_xy[undistorted_xy["cam_id"].isin(valid_cam_ids)]["sync_index"].unique()

    start = time()
    last_log = int(start)
    total = len(valid_sync_indices)

    logger.info("Beginning triangulation...")

    for count, index in enumerate(valid_sync_indices, 1):
        active = undistorted_xy["sync_index"] == index
        index_data = undistorted_xy[active & undistorted_xy["cam_id"].isin(valid_cam_ids)]
        if index_data.empty:
            continue

        cam_id = index_data["cam_id"].to_numpy()
        point_ids = index_data["point_id"].to_numpy()
        raw_xy = np.vstack([
            index_data["img_loc_undistort_x"].to_numpy(),
            index_data["img_loc_undistort_y"].to_numpy(),
        ]).T

        point_id_xyz, points_xyz = triangulate_sync_index(projection_matrices, cam_id, point_ids, raw_xy)

        if len(point_id_xyz) > 0:
            xyz_data["sync_index"].extend([index] * len(point_id_xyz))
            xyz_data["point_id"].extend(point_id_xyz)
            pts = np.array(points_xyz)
            xyz_data["x_coord"].extend(pts[:, 0].tolist())
            xyz_data["y_coord"].extend(pts[:, 1].tolist())
            xyz_data["z_coord"].extend(pts[:, 2].tolist())
            ft = frame_times.get(index, np.nan)
            xyz_data["frame_time"].extend([ft] * len(point_id_xyz))

        now = int(time())
        if now - last_log >= 1:
            pct = int(100 * count / total)
            logger.info(f"Triangulation {pct}% complete")
            last_log = now

    return WorldPoints(pd.DataFrame(xyz_data))
