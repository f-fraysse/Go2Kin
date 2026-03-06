"""
Umeyama similarity transform for coordinate alignment.

Adapted from caliscope/core/alignment.py (BSD-2-Clause, Mac Prible).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from calibration.data_types import CameraArray, CameraData, WorldPoints

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SimilarityTransform:
    """Immutable similarity transform: target = s * (R @ source) + t"""

    rotation: NDArray[np.float64]
    translation: NDArray[np.float64]
    scale: float

    def __post_init__(self):
        if self.rotation.shape != (3, 3):
            raise ValueError(f"Rotation must be 3x3, got {self.rotation.shape}")
        det = np.linalg.det(self.rotation)
        if not np.isclose(det, 1.0, atol=1e-6):
            raise ValueError(f"Rotation must be proper (det=+1), got det={det:.6f}")
        if not np.allclose(self.rotation @ self.rotation.T, np.eye(3), atol=1e-6):
            raise ValueError("Rotation matrix must be orthogonal")
        if self.translation.shape != (3,):
            raise ValueError(f"Translation must be 3-vector, got {self.translation.shape}")
        if self.scale <= 0:
            raise ValueError(f"Scale must be positive, got {self.scale}")

    def apply(self, points: NDArray[np.float64]) -> NDArray[np.float64]:
        """Apply transform to Nx3 points: target = s * (R @ points) + t"""
        if points.ndim != 2 or points.shape[1] != 3:
            raise ValueError(f"Points must be Nx3 array, got shape {points.shape}")
        return self.scale * (self.rotation @ points.T).T + self.translation

    @property
    def inverse(self) -> SimilarityTransform:
        inv_rotation = self.rotation.T
        inv_scale = 1.0 / self.scale
        inv_translation = -inv_scale * (inv_rotation @ self.translation)
        return SimilarityTransform(inv_rotation, inv_translation, inv_scale)

    @property
    def matrix(self) -> NDArray[np.float64]:
        """4x4 homogeneous transformation matrix [[s*R, t], [0, 1]]."""
        m = np.eye(4, dtype=np.float64)
        m[:3, :3] = self.scale * self.rotation
        m[:3, 3] = self.translation
        return m


def estimate_similarity_transform(
    source_points: NDArray[np.float64],
    target_points: NDArray[np.float64],
) -> SimilarityTransform:
    """Estimate optimal similarity transform using Umeyama's algorithm.

    Finds s, R, t that minimize ||target - (s * (R @ source) + t)||^2

    Args:
        source_points: Nx3 points in source frame
        target_points: Nx3 points in target frame

    Returns:
        SimilarityTransform

    Raises:
        ValueError: If arrays invalid or < 3 points
    """
    if source_points.shape != target_points.shape:
        raise ValueError(f"Shape mismatch: {source_points.shape} vs {target_points.shape}")
    if source_points.shape[0] < 3:
        raise ValueError(f"Need >= 3 points, got {source_points.shape[0]}")
    if source_points.shape[1] != 3:
        raise ValueError(f"Points must be 3D (Nx3), got {source_points.shape}")
    if np.any(np.isnan(source_points)) or np.any(np.isnan(target_points)):
        raise ValueError("Input points cannot contain NaN values")

    source_centroid = np.mean(source_points, axis=0)
    target_centroid = np.mean(target_points, axis=0)
    source_centered = source_points - source_centroid
    target_centered = target_points - target_centroid

    H = source_centered.T @ target_centered
    U, S, Vt = np.linalg.svd(H)

    if np.linalg.det(Vt.T @ U.T) < 0:
        Vt[-1, :] *= -1

    rotation = Vt.T @ U.T
    source_variance = np.sum(source_centered ** 2)
    scale = np.sum(target_centered * (rotation @ source_centered.T).T) / source_variance
    translation = target_centroid - scale * (rotation @ source_centroid)

    try:
        return SimilarityTransform(rotation, translation, float(scale))
    except ValueError as e:
        raise RuntimeError(f"Estimated transform is invalid: {e}")


def apply_similarity_transform(
    camera_array: CameraArray,
    world_points: WorldPoints,
    transform: SimilarityTransform,
) -> tuple[CameraArray, WorldPoints]:
    """Apply similarity transform to camera array and world points.

    Returns new instances (immutable pattern).

    Camera extrinsics are transformed correctly:
    1. Extract camera position: C_old = -R_cam^T @ t_cam
    2. Transform position: C_new = scale * (R_world @ C_old) + t_world
    3. Rotate orientation: R_cam_new = R_cam @ R_world^T
    4. New translation: t_cam_new = -R_cam_new @ C_new
    """
    # Transform world points
    points_3d = world_points.points
    transformed_points = transform.apply(points_3d)

    world_df = world_points.df.copy()
    world_df[["x_coord", "y_coord", "z_coord"]] = transformed_points
    new_world_points = WorldPoints(world_df)

    # Transform camera extrinsics
    new_cameras = {}
    for cam_id, camera_data in camera_array.cameras.items():
        new_cam = CameraData(
            cam_id=camera_data.cam_id,
            size=camera_data.size,
            rotation_count=camera_data.rotation_count,
            error=camera_data.error,
            matrix=camera_data.matrix,
            distortions=camera_data.distortions,
            exposure=camera_data.exposure,
            grid_count=camera_data.grid_count,
            ignore=camera_data.ignore,
            fisheye=camera_data.fisheye,
        )

        if camera_data.rotation is not None and camera_data.translation is not None:
            R_cam = camera_data.rotation
            t_cam = camera_data.translation

            cam_position_old = -R_cam.T @ t_cam
            cam_position_new = transform.scale * (transform.rotation @ cam_position_old) + transform.translation
            R_cam_new = R_cam @ transform.rotation.T
            t_cam_new = -R_cam_new @ cam_position_new

            new_cam.rotation = R_cam_new
            new_cam.translation = t_cam_new

        new_cameras[cam_id] = new_cam

    new_camera_array = CameraArray(cameras=new_cameras)
    return new_camera_array, new_world_points
