"""
Reprojection error computation for bundle adjustment.

Adapted from caliscope/core/reprojection.py (BSD-2-Clause, Mac Prible).
"""

import cv2
import numpy as np
from numpy.typing import NDArray

from calibration.data_types import CameraArray

# Type aliases
CameraIndices = NDArray[np.int16]
ImageCoords = NDArray[np.float64]
WorldCoords = NDArray[np.float64]
ErrorsXY = NDArray[np.float64]


def reprojection_errors(
    camera_array: CameraArray,
    camera_indices: CameraIndices,
    image_coords: ImageCoords,
    world_coords: WorldCoords,
    use_normalized: bool = False,
    extrinsics_override: NDArray[np.float64] | None = None,
) -> ErrorsXY:
    """Compute reprojection errors for observations.

    Two modes:
    - normalized: Undistorts observations, projects with identity K (for optimization)
    - pixels: Projects with full camera model (for reporting)

    Args:
        camera_array: CameraArray with posed cameras
        camera_indices: (n_obs,) mapping each observation to a camera index
        image_coords: (n_obs, 2) observed 2D image coordinates
        world_coords: (n_obs, 3) 3D world coordinates
        use_normalized: If True, work in normalized coordinates
        extrinsics_override: (n_cams, 6) rvec+tvec per camera (for optimization)

    Returns:
        (n_obs, 2) array of x,y reprojection errors
    """
    errors_xy = np.zeros_like(image_coords)

    for cam_id, camera_data in camera_array.posed_cameras.items():
        camera_index = camera_array.posed_cam_id_to_index[cam_id]
        cam_mask = camera_indices == camera_index
        if not cam_mask.any():
            continue

        cam_world_coords = world_coords[cam_mask]
        cam_observed = image_coords[cam_mask]

        if use_normalized:
            cam_observed = camera_data.undistort_points(cam_observed, output="normalized")
            cam_matrix = np.identity(3)
            dist_coeffs = np.zeros(5)
        else:
            if camera_data.matrix is None or camera_data.distortions is None:
                raise ValueError(f"Camera {cam_id} missing intrinsics for pixel-mode reprojection")
            cam_matrix = camera_data.matrix
            dist_coeffs = camera_data.distortions

        if extrinsics_override is not None:
            rvec = extrinsics_override[camera_index, :3]
            tvec = extrinsics_override[camera_index, 3:6]
        else:
            if camera_data.rotation is None or camera_data.translation is None:
                raise ValueError(f"Camera {cam_id} missing extrinsics")
            rvec, _ = cv2.Rodrigues(camera_data.rotation)
            rvec = rvec.ravel()
            tvec = camera_data.translation

        projected, _ = cv2.projectPoints(
            cam_world_coords.reshape(-1, 1, 3), rvec, tvec, cam_matrix, dist_coeffs,
        )
        projected = projected.reshape(-1, 2)
        errors_xy[cam_mask] = projected - cam_observed

    return errors_xy


def bundle_residuals(
    params: NDArray[np.float64],
    camera_array: CameraArray,
    camera_indices: CameraIndices,
    image_coords: ImageCoords,
    obj_indices: NDArray[np.int32],
    use_normalized: bool = True,
) -> NDArray[np.float64]:
    """Callback for scipy.optimize.least_squares.

    Does NOT mutate camera_array — extrinsics are passed via override.

    Args:
        params: Flattened [camera_params, point_coords]
        camera_array: READ-ONLY, used for intrinsics
        camera_indices: (n_obs,) observation-to-camera mapping
        image_coords: (n_obs, 2) observed 2D coordinates
        obj_indices: (n_obs,) observation-to-3D-point mapping
        use_normalized: If True, use undistorted coordinates

    Returns:
        (n_obs*2,) flattened residuals
    """
    n_cams = len(camera_array.posed_cameras)
    n_cam_params = 6

    extrinsics = params[:n_cams * n_cam_params].reshape((n_cams, n_cam_params))
    points_3d = params[n_cams * n_cam_params:].reshape((-1, 3))
    world_coords = points_3d[obj_indices]

    errors_xy = reprojection_errors(
        camera_array, camera_indices, image_coords, world_coords,
        use_normalized, extrinsics_override=extrinsics,
    )
    return errors_xy.ravel()
