"""
Extrinsic calibration: PnP pose estimation and pose network construction.

Adapted from caliscope/core/bootstrap_pose/pose_network_builder.py (BSD-2-Clause, Mac Prible).
"""

from __future__ import annotations

import logging
import time
from itertools import combinations

import cv2
import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.spatial.transform import Rotation

from calibration.data_types import CameraArray, ImagePoints, StereoPair
from calibration.paired_pose_network import PairedPoseNetwork

logger = logging.getLogger(__name__)

DEFAULT_MIN_PNP_POINTS = 4
DEFAULT_OUTLIER_THRESHOLD = 1.5


class PoseNetworkBuilder:
    """Fluent builder for creating PairedPoseNetwork from camera array and point data.

    Pipeline:
    1. estimate_camera_to_object_poses() — per-camera PnP
    2. estimate_relative_poses() — pairwise relative transforms
    3. filter_outliers() — IQR rejection
    4. build() — aggregate + create network

    Example:
        network = (
            PoseNetworkBuilder(camera_array, image_points)
            .estimate_camera_to_object_poses()
            .estimate_relative_poses()
            .filter_outliers()
            .build()
        )
        network.apply_to(camera_array)
    """

    def __init__(self, camera_array: CameraArray, image_points: ImagePoints):
        self.camera_array = camera_array
        self._image_points = image_points

        self._camera_to_object_poses: dict | None = None
        self._relative_poses: dict | None = None
        self._filtered_poses: dict | None = None
        self._aggregated_poses: dict | None = None

    def estimate_camera_to_object_poses(
        self,
        min_points: int = DEFAULT_MIN_PNP_POINTS,
        pnp_flags: int = cv2.SOLVEPNP_IPPE,
        fallback_flags: int = cv2.SOLVEPNP_ITERATIVE,
    ) -> PoseNetworkBuilder:
        """Step 1a: Estimate per-camera poses via PnP."""
        logger.info("Step 1a: Camera-to-Object Poses")
        self._camera_to_object_poses = None
        self._relative_poses = None
        self._filtered_poses = None
        self._aggregated_poses = None

        self._camera_to_object_poses = _compute_camera_to_object_poses_pnp(
            self._image_points, self.camera_array,
            min_points=min_points, pnp_flags=pnp_flags, fallback_flags=fallback_flags,
        )
        return self

    def estimate_relative_poses(self) -> PoseNetworkBuilder:
        """Step 1b: Compute relative poses between camera pairs."""
        logger.info("Step 1b: Relative Poses")
        if self._camera_to_object_poses is None:
            raise RuntimeError("Must call estimate_camera_to_object_poses() first")
        self._relative_poses = _compute_relative_poses(self._camera_to_object_poses, self.camera_array)
        return self

    def filter_outliers(self, threshold: float = DEFAULT_OUTLIER_THRESHOLD) -> PoseNetworkBuilder:
        """Step 2: Apply IQR-based outlier rejection."""
        logger.info("Step 2: Outlier Filtering")
        if self._relative_poses is None:
            raise RuntimeError("Must call estimate_relative_poses() first")
        self._filtered_poses = _reject_outliers(self._relative_poses, threshold=threshold)
        return self

    def build(self) -> PairedPoseNetwork:
        """Step 3: Aggregate poses and create PairedPoseNetwork."""
        logger.info("Step 3: Build PairedPoseNetwork")
        if self._filtered_poses is None:
            raise RuntimeError("Must call filter_outliers() first")

        self._aggregated_poses = _aggregate_poses(self._filtered_poses)
        network = _estimate_pnp_paired_pose_network(
            self._aggregated_poses, self.camera_array, self._image_points,
        )
        logger.info(f"Built PairedPoseNetwork with {len(network._pairs)} pairs")
        return network


# =============================================================================
# Internal functions
# =============================================================================

def _compute_camera_to_object_poses_pnp(
    image_points: ImagePoints,
    camera_array: CameraArray,
    min_points: int = DEFAULT_MIN_PNP_POINTS,
    pnp_flags: int = cv2.SOLVEPNP_IPPE,
    fallback_flags: int = cv2.SOLVEPNP_ITERATIVE,
) -> dict[tuple[int, int], tuple[NDArray, NDArray, float]]:
    """Compute per-camera poses relative to object frame for each sync_index."""
    logger.info(f"Computing per-frame camera poses with PnP (min_points={min_points})...")

    # Pre-undistort all points per camera
    undistorted_data = []
    for cam_id, camera in camera_array.cameras.items():
        if camera.matrix is None:
            logger.warning(f"Camera {cam_id} missing intrinsics, skipping")
            continue
        cam_data = image_points.df[image_points.df["cam_id"] == cam_id].copy()
        if cam_data.empty:
            continue
        img_pts = cam_data[["img_loc_x", "img_loc_y"]].to_numpy(dtype=np.float32)
        undistorted_xy = camera.undistort_points(img_pts, output="normalized")
        cam_data[["undistort_x", "undistort_y"]] = undistorted_xy
        undistorted_data.append(cam_data)

    if not undistorted_data:
        raise ValueError("No valid camera data found for PnP")

    all_undistorted = pd.concat(undistorted_data)
    grouped = all_undistorted.groupby(["cam_id", "sync_index"])

    poses = {}
    success_count = 0
    failure_count = 0
    start_time = time.time()

    K_perfect = np.identity(3)
    D_perfect = np.zeros(5)

    for (cam_id, sync_index), group in grouped:
        if len(group) < min_points:
            failure_count += 1
            continue

        img_pts = group[["undistort_x", "undistort_y"]].to_numpy(dtype=np.float32)
        obj_pts = group[["obj_loc_x", "obj_loc_y"]].to_numpy()
        obj_pts = np.hstack([obj_pts, np.zeros((len(obj_pts), 1))]).astype(np.float32)

        success, rvec, tvec = cv2.solvePnP(
            obj_pts, img_pts, cameraMatrix=K_perfect, distCoeffs=D_perfect, flags=pnp_flags,
        )
        if not success:
            success, rvec, tvec = cv2.solvePnP(
                obj_pts, img_pts, cameraMatrix=K_perfect, distCoeffs=D_perfect, flags=fallback_flags,
            )
        if success:
            R, _ = cv2.Rodrigues(rvec)
            t = tvec.flatten()
            projected, _ = cv2.projectPoints(obj_pts, rvec, tvec, K_perfect, D_perfect)
            rmse = np.sqrt(np.mean(np.sum((img_pts - projected.reshape(-1, 2)) ** 2, axis=1)))
            poses[(cam_id, sync_index)] = (R, t, rmse)
            success_count += 1
        else:
            failure_count += 1

    elapsed = time.time() - start_time
    logger.info(f"PnP: {success_count} successes, {failure_count} failures in {elapsed:.2f}s")
    return poses


def _compute_relative_poses(
    camera_to_object_poses: dict[tuple[int, int], tuple[NDArray, NDArray, float]],
    camera_array: CameraArray,
) -> dict[tuple[tuple[int, int], int], StereoPair]:
    """Compute relative poses between camera pairs at each sync_index."""
    logger.info("Computing relative poses between camera pairs...")
    relative_poses: dict[tuple[tuple[int, int], int], StereoPair] = {}

    cam_ids = [c for c, cam in camera_array.cameras.items() if not cam.ignore]
    pairs = [(i, j) for i, j in combinations(cam_ids, 2) if i < j]

    for cam_a, cam_b in pairs:
        sync_a = {s for c, s in camera_to_object_poses.keys() if c == cam_a}
        sync_b = {s for c, s in camera_to_object_poses.keys() if c == cam_b}
        common = sync_a & sync_b

        for sync_index in common:
            R_a, t_a, _ = camera_to_object_poses[(cam_a, sync_index)]
            R_b, t_b, _ = camera_to_object_poses[(cam_b, sync_index)]

            R_a_inv = R_a.T
            t_a_inv = -R_a_inv @ t_a
            R_rel = R_b @ R_a_inv
            t_rel = R_b @ t_a_inv + t_b

            relative_poses[((cam_a, cam_b), sync_index)] = StereoPair(
                primary_cam_id=cam_a,
                secondary_cam_id=cam_b,
                error_score=float("nan"),
                translation=t_rel,
                rotation=R_rel,
            )

    logger.info(f"Computed {len(relative_poses)} relative poses across {len(pairs)} pairs")
    return relative_poses


def _quaternion_average(quaternions: NDArray[np.float64]) -> np.ndarray:
    """Average quaternions via eigen decomposition of Q @ Q^T."""
    if len(quaternions) == 0:
        raise ValueError("Cannot average empty quaternion array")
    if len(quaternions) == 1:
        return quaternions[0]

    Q = quaternions.T
    M = Q @ Q.T
    eigenvals, eigenvecs = np.linalg.eigh(M)
    avg = eigenvecs[:, -1]
    if avg[0] < 0:
        avg = -avg

    norm = np.linalg.norm(avg)
    if norm < 1e-10:
        logger.warning("Quaternion average failed, returning first quaternion")
        return quaternions[0]
    return avg / norm


def _rotation_error(R1: NDArray, R2: NDArray) -> float:
    """Geodesic rotation error in degrees."""
    R_rel = R1 @ R2.T
    trace = np.clip(np.trace(R_rel), -1.0, 3.0)
    angle = np.arccos((trace - 1) / 2)
    return float(np.degrees(angle))


def _reject_outliers(
    relative_poses: dict[tuple[tuple[int, int], int], StereoPair],
    threshold: float = DEFAULT_OUTLIER_THRESHOLD,
) -> dict[tuple[int, int], list[StereoPair]]:
    """Apply IQR-based outlier rejection to relative poses."""
    logger.info(f"Applying outlier rejection (threshold={threshold})...")

    poses_by_pair: dict[tuple[int, int], list[StereoPair]] = {}
    for (pair, _), sp in relative_poses.items():
        poses_by_pair.setdefault(pair, []).append(sp)

    filtered_poses = {}
    for pair, stereo_pairs in poses_by_pair.items():
        valid = [sp for sp in stereo_pairs
                 if not (np.any(np.isnan(sp.rotation)) or np.any(np.isnan(sp.translation)))]

        if len(valid) < 5:
            logger.warning(f"Pair {pair}: only {len(valid)} samples, skipping outlier rejection")
            filtered_poses[pair] = valid
            continue

        # Quaternion and translation magnitude arrays
        quats = []
        t_mags = []
        for sp in valid:
            quat = Rotation.from_matrix(sp.rotation).as_quat()  # (x,y,z,w)
            quats.append(np.roll(quat, 1))  # -> (w,x,y,z)
            t_mags.append(np.linalg.norm(sp.translation))

        quats_arr = np.array(quats)
        t_mags_arr = np.array(t_mags)

        # Translation IQR filter
        t_q1, t_q3 = np.percentile(t_mags_arr, [25, 75])
        t_iqr = t_q3 - t_q1
        t_lower = t_q1 - threshold * t_iqr
        t_upper = t_q3 + threshold * t_iqr

        # Rotation angle IQR filter
        median_quat = _quaternion_average(quats_arr)
        R_median = Rotation.from_quat(np.roll(median_quat, -1)).as_matrix()
        rot_angles = np.array([_rotation_error(sp.rotation, R_median) for sp in valid])

        rot_q1, rot_q3 = np.percentile(rot_angles, [25, 75])
        rot_iqr = rot_q3 - rot_q1
        rot_upper = rot_q3 + threshold * rot_iqr

        filtered = []
        outlier_count = 0
        for i, sp in enumerate(valid):
            is_t_outlier = t_mags_arr[i] < t_lower or t_mags_arr[i] > t_upper
            is_rot_outlier = rot_angles[i] > rot_upper
            if not (is_t_outlier or is_rot_outlier):
                filtered.append(sp)
            else:
                outlier_count += 1

        logger.info(f"Pair {pair}: {outlier_count}/{len(valid)} outliers rejected")
        filtered_poses[pair] = filtered

    return filtered_poses


def _aggregate_poses(
    filtered_poses: dict[tuple[int, int], list[StereoPair]],
) -> dict[tuple[int, int], StereoPair]:
    """Aggregate per-sync poses into single estimate per pair."""
    logger.info("Aggregating poses...")
    aggregated = {}

    for pair, stereo_pairs in filtered_poses.items():
        if not stereo_pairs:
            logger.warning(f"No valid poses for pair {pair} after outlier rejection")
            continue
        if len(stereo_pairs) == 1:
            aggregated[pair] = stereo_pairs[0]
            continue

        quats = [np.roll(Rotation.from_matrix(sp.rotation).as_quat(), 1) for sp in stereo_pairs]
        avg_quat = _quaternion_average(np.array(quats))
        avg_R = Rotation.from_quat(np.roll(avg_quat, -1)).as_matrix()
        avg_t = np.mean([sp.translation for sp in stereo_pairs], axis=0)

        aggregated[pair] = StereoPair(
            primary_cam_id=pair[0],
            secondary_cam_id=pair[1],
            error_score=float("nan"),
            rotation=avg_R,
            translation=avg_t,
        )

    logger.info(f"Aggregated poses for {len(aggregated)} pairs")
    return aggregated


def _estimate_pnp_paired_pose_network(
    aggregated_pairs: dict[tuple[int, int], StereoPair],
    camera_array: CameraArray,
    image_points: ImagePoints,
) -> PairedPoseNetwork:
    """Create PairedPoseNetwork with RMSE scores computed via stereo triangulation."""
    logger.info("Creating PairedPoseNetwork...")

    common_obs = _precompute_common_observations(image_points, camera_array)

    pairs_with_rmse = {}
    for pair, sp in aggregated_pairs.items():
        rmse = _calculate_stereo_rmse(sp, camera_array, common_obs)
        if rmse is None:
            logger.warning(f"Could not compute RMSE for pair {pair}, skipping")
            continue
        pairs_with_rmse[pair] = StereoPair(
            primary_cam_id=sp.primary_cam_id,
            secondary_cam_id=sp.secondary_cam_id,
            error_score=rmse,
            rotation=sp.rotation,
            translation=sp.translation,
        )
        logger.info(f"Pair {pair}: RMSE = {rmse:.6f}")

    return PairedPoseNetwork.from_raw_estimates(pairs_with_rmse)


def _precompute_common_observations(
    image_points: ImagePoints, camera_array: CameraArray,
) -> dict[tuple[int, int], pd.DataFrame]:
    """Pre-compute merged observations for all camera pairs."""
    df = image_points.df
    cam_ids = [c for c, cam in camera_array.cameras.items() if not cam.ignore]

    common_obs = {}
    for cam_a, cam_b in combinations(cam_ids, 2):
        data_a = df[df["cam_id"] == cam_a]
        data_b = df[df["cam_id"] == cam_b]
        common = pd.merge(data_a, data_b, on=["sync_index", "point_id"], suffixes=("_a", "_b"))
        if len(common) >= DEFAULT_MIN_PNP_POINTS:
            common_obs[(cam_a, cam_b)] = common

    logger.info(f"Pre-computed common observations for {len(common_obs)} pairs")
    return common_obs


def _calculate_stereo_rmse(
    stereo_pair: StereoPair,
    camera_array: CameraArray,
    common_observations: dict[tuple[int, int], pd.DataFrame],
) -> float | None:
    """Calculate stereo RMSE via triangulation/reprojection."""
    cam_a, cam_b = stereo_pair.pair
    common = common_observations.get((cam_a, cam_b))
    if common is None or len(common) < DEFAULT_MIN_PNP_POINTS:
        return None

    cam_data_a = camera_array.cameras[cam_a]
    cam_data_b = camera_array.cameras[cam_b]

    pts_a = common[["img_loc_x_a", "img_loc_y_a"]].to_numpy(dtype=np.float32)
    pts_b = common[["img_loc_x_b", "img_loc_y_b"]].to_numpy(dtype=np.float32)
    norm_a = cam_data_a.undistort_points(pts_a, output="normalized")
    norm_b = cam_data_b.undistort_points(pts_b, output="normalized")

    P1 = np.eye(3, 4)
    P2 = np.hstack((stereo_pair.rotation, stereo_pair.translation.reshape(3, 1)))

    points_4d = cv2.triangulatePoints(P1, P2, norm_a.T, norm_b.T)
    points_3d = points_4d[:3] / points_4d[3]

    proj_a, _ = cv2.projectPoints(points_3d.T, np.zeros(3), np.zeros(3), np.eye(3), np.zeros(5))
    proj_b, _ = cv2.projectPoints(
        points_3d.T, cv2.Rodrigues(stereo_pair.rotation)[0], stereo_pair.translation, np.eye(3), np.zeros(5),
    )

    errors = np.vstack([norm_a - proj_a.reshape(-1, 2), norm_b - proj_b.reshape(-1, 2)])
    rmse = np.sqrt(np.mean(np.sum(errors ** 2, axis=1)))
    return float(rmse)
