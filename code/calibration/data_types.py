"""
Core data types for camera calibration.

Consolidated from multiple Caliscope modules:
- PointPacket (caliscope/packets.py)
- CameraData, CameraArray (caliscope/cameras/camera_array.py)
- ImagePoints, WorldPoints (caliscope/core/point_data.py)
- StereoPair (caliscope/core/bootstrap_pose/stereopairs.py)

Adapted for Go2Kin: removed pandera schema validation (replaced with simple
column checks), removed numba (replaced NumbaDict with plain dict).

Original code licensed under BSD-2-Clause by Mac Prible (Caliscope)
and Lili Karashchuk (Anipose triangulation).
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Literal, Tuple, cast

import cv2
import numpy as np
import pandas as pd
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

CAMERA_PARAM_COUNT = 6


# =============================================================================
# PointPacket
# =============================================================================

@dataclass(frozen=True, slots=True)
class PointPacket:
    """Return value from CharucoTracker.get_points().

    obj_loc contains 3D coordinates in the board's frame of reference,
    used for calibration. It is None for non-calibration trackers.
    """

    point_id: NDArray[Any]
    img_loc: NDArray[Any]
    obj_loc: NDArray[Any] | None = None
    confidence: NDArray[Any] | None = None

    @property
    def obj_loc_list(self) -> list[list[float | None]]:
        if self.obj_loc is not None:
            obj_loc_x = self.obj_loc[:, 0].tolist()
            obj_loc_y = self.obj_loc[:, 1].tolist()
            obj_loc_z = self.obj_loc[:, 2].tolist()
        else:
            length = len(self.point_id) if self.point_id is not None else 0
            obj_loc_x = [None] * length
            obj_loc_y = [None] * length
            obj_loc_z = [None] * length
        return cast(list[list[float | None]], [obj_loc_x, obj_loc_y, obj_loc_z])


# =============================================================================
# CameraData
# =============================================================================

@dataclass
class CameraData:
    """Intrinsic and extrinsic calibration state for a single camera.

    Provides undistort_points() as a unified interface for both standard
    and fisheye camera models.
    """

    cam_id: int
    size: tuple[int, int]
    rotation_count: int = 0
    error: float | None = None
    matrix: np.ndarray | None = None
    distortions: np.ndarray | None = None
    exposure: int | None = None
    grid_count: int | None = None
    ignore: bool = False
    translation: np.ndarray | None = None  # camera relative to world
    rotation: np.ndarray | None = None  # camera relative to world
    fisheye: bool = False

    @property
    def transformation(self):
        assert self.rotation is not None and self.translation is not None
        t = np.hstack([self.rotation, np.expand_dims(self.translation, 1)])
        t = np.vstack([t, np.array([0, 0, 0, 1], np.float32)])
        return t

    @transformation.setter
    def transformation(self, t: np.ndarray):
        self.rotation = t[0:3, 0:3]
        self.translation = t[0:3, 3]

    @property
    def normalized_projection_matrix(self):
        assert self.matrix is not None and self.transformation is not None
        return self.transformation[0:3, :]

    def extrinsics_to_vector(self):
        assert self.rotation is not None and self.translation is not None
        rotation_rodrigues = cv2.Rodrigues(self.rotation)[0]
        cam_param = np.hstack([rotation_rodrigues[:, 0], self.translation])
        return cam_param

    def extrinsics_from_vector(self, row):
        self.rotation = cv2.Rodrigues(row[0:3])[0]
        self.translation = np.array([row[3:6]], dtype=np.float64)[0]

    def undistort_points(self, points: NDArray, *, output: Literal["normalized", "pixels"]) -> NDArray:
        """Remove lens distortion from 2D image points.

        Args:
            points: (N, 2) array of distorted points in pixel coordinates
            output: 'normalized' for triangulation/optimization, 'pixels' for display
        """
        if self.matrix is None or self.distortions is None:
            raise ValueError(f"Camera {self.cam_id} lacks intrinsic calibration; cannot undistort points.")

        points_reshaped = np.ascontiguousarray(points, dtype=np.float32).reshape(-1, 1, 2)

        if output == "normalized":
            projection_matrix = np.identity(3)
        else:
            projection_matrix = self.matrix

        if self.fisheye:
            undistorted_points = cv2.fisheye.undistortPoints(
                points_reshaped, self.matrix, self.distortions, P=projection_matrix
            )
        else:
            undistorted_points = cv2.undistortPoints(
                points_reshaped, self.matrix, self.distortions, P=projection_matrix
            )
        return undistorted_points.reshape(-1, 2)

    def undistort_frame(self, frame: NDArray) -> NDArray:
        """Undistort a frame using cached remap tables."""
        if self.matrix is None or self.distortions is None:
            raise ValueError(f"Camera {self.cam_id} lacks intrinsic calibration; cannot undistort frame.")

        h, w = frame.shape[:2]
        frame_size = (w, h)

        if not hasattr(self, "_remap_cache") or self._remap_cache.get("size") != frame_size:
            if self.fisheye:
                map1, map2 = cv2.fisheye.initUndistortRectifyMap(
                    self.matrix, self.distortions, np.eye(3), self.matrix, frame_size, cv2.CV_16SC2
                )
            else:
                map1, map2 = cv2.initUndistortRectifyMap(
                    self.matrix, self.distortions, np.eye(3), self.matrix, frame_size, cv2.CV_16SC2
                )
            self._remap_cache = {"size": frame_size, "map1": map1, "map2": map2}

        return cv2.remap(frame, self._remap_cache["map1"], self._remap_cache["map2"], cv2.INTER_LINEAR)

    def get_display_data(self) -> OrderedDict:
        if self.matrix is not None:
            fx, fy = self.matrix[0, 0], self.matrix[1, 1]
            cx, cy = self.matrix[0, 2], self.matrix[1, 2]
        else:
            fx, fy = None, None
            cx, cy = None, None

        def round_or_none(value, places):
            return round(value, places) if value is not None else None

        distortion_coeffs_dict = OrderedDict()
        if self.distortions is not None:
            coeffs = self.distortions.ravel().tolist()
            if self.fisheye:
                k1, k2, k3, k4 = coeffs
                distortion_coeffs_dict["radial_k1"] = round_or_none(k1, 2)
                distortion_coeffs_dict["radial_k2"] = round_or_none(k2, 2)
                distortion_coeffs_dict["radial_k3"] = round_or_none(k3, 2)
                distortion_coeffs_dict["radial_k4"] = round_or_none(k4, 2)
            else:
                k1, k2, p1, p2, k3 = coeffs
                distortion_coeffs_dict["radial_k1"] = round_or_none(k1, 2)
                distortion_coeffs_dict["radial_k2"] = round_or_none(k2, 2)
                distortion_coeffs_dict["radial_k3"] = round_or_none(k3, 2)
                distortion_coeffs_dict["tangential_p1"] = round_or_none(p1, 2)
                distortion_coeffs_dict["tangential_p2"] = round_or_none(p2, 2)
        else:
            if self.fisheye:
                distortion_coeffs_dict = OrderedDict(
                    [("radial_k1", None), ("radial_k2", None), ("radial_k3", None), ("radial_k4", None)]
                )
            else:
                distortion_coeffs_dict = OrderedDict(
                    [("radial_k1", None), ("radial_k2", None), ("radial_k3", None),
                     ("tangential_p1", None), ("tangential_p2", None)]
                )

        return OrderedDict([
            ("size", self.size),
            ("RMSE", self.error),
            ("Grid_Count", self.grid_count),
            ("rotation_count", self.rotation_count),
            ("fisheye", self.fisheye),
            ("intrinsic_parameters", OrderedDict([
                ("focal_length_x", round_or_none(fx, 2)),
                ("focal_length_y", round_or_none(fy, 2)),
                ("optical_center_x", round_or_none(cx, 2)),
                ("optical_center_y", round_or_none(cy, 2)),
            ])),
            ("distortion_coefficients", distortion_coeffs_dict),
        ])

    def erase_calibration_data(self):
        self.error = None
        self.matrix = None
        self.distortions = None
        self.grid_count = None
        self.translation = None
        self.rotation = None


# =============================================================================
# CameraArray
# =============================================================================

@dataclass
class CameraArray:
    """Container for multiple CameraData objects."""

    cameras: Dict[int, CameraData]

    @property
    def posed_cameras(self) -> Dict[int, CameraData]:
        return {
            cam_id: cam for cam_id, cam in self.cameras.items()
            if cam.rotation is not None and cam.translation is not None
        }

    @property
    def unposed_cameras(self) -> Dict[int, CameraData]:
        return {
            cam_id: cam for cam_id, cam in self.cameras.items()
            if cam.rotation is None or cam.translation is None
        }

    @property
    def posed_cam_id_to_index(self) -> Dict[int, int]:
        eligible_cam_ids = [cam_id for cam_id, cam in self.posed_cameras.items() if not cam.ignore]
        eligible_cam_ids.sort()
        return {cam_id: i for i, cam_id in enumerate(eligible_cam_ids)}

    @property
    def posed_index_to_cam_id(self) -> Dict[int, int]:
        return {value: key for key, value in self.posed_cam_id_to_index.items()}

    def get_extrinsic_params(self) -> NDArray | None:
        ordered_cam_ids = self.posed_index_to_cam_id.keys()
        if not ordered_cam_ids:
            return None
        params_list = []
        for index in sorted(ordered_cam_ids):
            cam_id = self.posed_index_to_cam_id[index]
            cam = self.cameras[cam_id]
            params_list.append(cam.extrinsics_to_vector())
        return np.vstack(params_list)

    def update_extrinsic_params(self, least_sq_result_x: NDArray) -> None:
        indices_to_update = self.posed_index_to_cam_id
        n_cameras = len(indices_to_update)
        if n_cameras == 0:
            return
        n_cam_param = 6
        flat_camera_params = least_sq_result_x[0: n_cameras * n_cam_param]
        new_camera_params = flat_camera_params.reshape(n_cameras, n_cam_param)
        for index, cam_vec in enumerate(new_camera_params):
            cam_id = indices_to_update[index]
            self.cameras[cam_id].extrinsics_from_vector(cam_vec)

    def all_extrinsics_calibrated(self) -> bool:
        if not self.cameras:
            return True
        return not self.unposed_cameras

    def all_intrinsics_calibrated(self) -> bool:
        return all(cam.matrix is not None and cam.distortions is not None for cam in self.cameras.values())

    @property
    def normalized_projection_matrices(self):
        """Projection matrices for posed, non-ignored cameras (plain dict)."""
        proj_mat = {}
        for cam_id in self.posed_cam_id_to_index.keys():
            proj_mat[cam_id] = self.cameras[cam_id].normalized_projection_matrix
        return proj_mat


# =============================================================================
# ImagePoints
# =============================================================================

IMAGEPOINTS_REQUIRED = ["sync_index", "cam_id", "point_id", "img_loc_x", "img_loc_y"]
IMAGEPOINTS_OPTIONAL = ["obj_loc_x", "obj_loc_y", "obj_loc_z", "frame_time"]


class ImagePoints:
    """Validated container for 2D (x,y) point observations."""

    _df: pd.DataFrame

    @property
    def df(self) -> pd.DataFrame:
        return self._df.copy()

    def __init__(self, df: pd.DataFrame):
        df = df.copy()
        for col in IMAGEPOINTS_OPTIONAL:
            if col not in df.columns:
                df[col] = np.nan

        missing = [c for c in IMAGEPOINTS_REQUIRED if c not in df.columns]
        if missing:
            raise ValueError(f"ImagePoints missing required columns: {missing}")

        # Coerce types
        for col in ["sync_index", "cam_id", "point_id"]:
            df[col] = df[col].astype(int)
        for col in ["img_loc_x", "img_loc_y", "obj_loc_x", "obj_loc_y", "obj_loc_z"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        self._df = df

    @classmethod
    def from_csv(cls, path: str | Path) -> ImagePoints:
        df = pd.read_csv(path)
        return cls(df)

    def fill_gaps(self, max_gap_size: int = 3) -> ImagePoints:
        xy_filled = pd.DataFrame()
        index_key = "sync_index"
        base_df = self.df
        for (cam_id, point_id), group in base_df.groupby(["cam_id", "point_id"]):
            group = group.sort_values(index_key)
            all_frames = pd.DataFrame({index_key: np.arange(group[index_key].min(), group[index_key].max() + 1)})
            all_frames["cam_id"] = int(cam_id)
            all_frames["point_id"] = int(point_id)
            merged = pd.merge(all_frames, group, on=["cam_id", "point_id", index_key], how="left")
            merged["gap_size"] = (
                merged["img_loc_x"].isnull().astype(int).groupby((merged["img_loc_x"].notnull()).cumsum()).cumsum()
            )
            merged = merged[merged["gap_size"] <= max_gap_size]
            for col in ["img_loc_x", "img_loc_y", "frame_time"]:
                if col in merged.columns:
                    merged[col] = merged[col].interpolate(method="linear", limit=max_gap_size)
            xy_filled = pd.concat([xy_filled, merged])
        return ImagePoints(xy_filled.dropna(subset=["img_loc_x"]))


# =============================================================================
# WorldPoints
# =============================================================================

WORLDPOINTS_REQUIRED = ["sync_index", "point_id", "x_coord", "y_coord", "z_coord"]


@dataclass(frozen=True)
class WorldPoints:
    """Validated, immutable container for 3D (x,y,z) point data."""

    _df: pd.DataFrame
    min_index: int | None = None
    max_index: int | None = None

    def __post_init__(self):
        df = self._df.copy()

        # Ensure frame_time column exists
        if "frame_time" not in df.columns:
            df["frame_time"] = np.nan

        missing = [c for c in WORLDPOINTS_REQUIRED if c not in df.columns]
        if missing:
            raise ValueError(f"WorldPoints missing required columns: {missing}")

        # Coerce types
        for col in ["sync_index", "point_id"]:
            df[col] = df[col].astype(int)
        for col in ["x_coord", "y_coord", "z_coord"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        object.__setattr__(self, "_df", df)

        if not df.empty:
            object.__setattr__(self, "min_index", int(df["sync_index"].min()))
            object.__setattr__(self, "max_index", int(df["sync_index"].max()))

    @property
    def df(self) -> pd.DataFrame:
        return self._df.copy()

    @property
    def points(self) -> NDArray:
        return self._df[["x_coord", "y_coord", "z_coord"]].values

    def fill_gaps(self, max_gap_size: int = 3) -> WorldPoints:
        xyz_filled = pd.DataFrame()
        base_df = self.df
        for point_id, group in base_df.groupby("point_id"):
            group = group.sort_values("sync_index")
            all_frames = pd.DataFrame(
                {"sync_index": np.arange(group["sync_index"].min(), group["sync_index"].max() + 1)}
            )
            all_frames["point_id"] = point_id
            merged = pd.merge(all_frames, group, on=["point_id", "sync_index"], how="left")
            merged["gap_size"] = (
                merged["x_coord"].isnull().astype(int).groupby((merged["x_coord"].notnull()).cumsum()).cumsum()
            )
            merged = merged[merged["gap_size"] <= max_gap_size]
            for col in ["x_coord", "y_coord", "z_coord", "frame_time"]:
                if col in merged.columns:
                    merged[col] = merged[col].interpolate(method="linear", limit=max_gap_size)
            xyz_filled = pd.concat([xyz_filled, merged])
        return WorldPoints(xyz_filled.dropna(subset=["x_coord"]))

    @classmethod
    def from_csv(cls, path: str | Path) -> WorldPoints:
        df = pd.read_csv(path)
        return cls(df)


# =============================================================================
# StereoPair
# =============================================================================

@dataclass(frozen=True)
class StereoPair:
    """Immutable stereo calibration result between two cameras.

    Encapsulates the extrinsic transformation from primary to secondary camera.
    """

    primary_cam_id: int
    secondary_cam_id: int
    error_score: float
    translation: np.ndarray
    rotation: np.ndarray

    def __post_init__(self):
        object.__setattr__(self, "translation", np.squeeze(self.translation))
        if self.translation.shape != (3,):
            raise ValueError(f"Translation must be shape (3,) after squeezing, got {self.translation.shape}")
        if self.rotation.shape != (3, 3):
            raise ValueError(f"Rotation must be shape (3,3), got {self.rotation.shape}")

    @property
    def pair(self) -> Tuple[int, int]:
        return (self.primary_cam_id, self.secondary_cam_id)

    @property
    def transformation(self) -> np.ndarray:
        R_stack = np.vstack([self.rotation, np.array([0, 0, 0])])
        t_stack = np.vstack([self.translation.reshape(3, 1), np.array([[1]])])
        return np.hstack([R_stack, t_stack])

    def inverted(self) -> StereoPair:
        inverted_transformation = np.linalg.inv(self.transformation)
        return StereoPair(
            primary_cam_id=self.secondary_cam_id,
            secondary_cam_id=self.primary_cam_id,
            error_score=self.error_score,
            rotation=inverted_transformation[0:3, 0:3],
            translation=inverted_transformation[0:3, 3],
        )

    def link(self, other: StereoPair) -> StereoPair:
        """Extend: (A->B).link(B->C) = A->C. Error scores are summed."""
        bridged_transformation = np.matmul(other.transformation, self.transformation)
        return StereoPair(
            primary_cam_id=self.primary_cam_id,
            secondary_cam_id=other.secondary_cam_id,
            error_score=self.error_score + other.error_score,
            rotation=bridged_transformation[0:3, 0:3],
            translation=bridged_transformation[0:3, 3],
        )
