"""
Bundle adjustment via scipy.optimize.least_squares.

Adapted from caliscope/core/point_data_bundle.py (BSD-2-Clause, Mac Prible).
"""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from functools import cached_property
from typing import Literal

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix

from calibration.alignment import (
    SimilarityTransform,
    apply_similarity_transform,
    estimate_similarity_transform,
)
from calibration.data_types import CameraArray, ImagePoints, WorldPoints
from calibration.reprojection import (
    CameraIndices,
    ErrorsXY,
    ImageCoords,
    WorldCoords,
    bundle_residuals,
    reprojection_errors,
)
from calibration.reprojection_report import ReprojectionReport
from calibration.scale_accuracy import (
    FrameScaleError,
    VolumetricScaleReport,
    compute_frame_scale_error,
)

logger = logging.getLogger(__name__)

# Mapping from scipy status codes to reasons
_SCIPY_STATUS_REASONS: dict[int, str] = {
    -1: "improper_input",
    0: "max_evaluations",
    1: "converged_gtol",
    2: "converged_ftol",
    3: "converged_xtol",
    4: "converged_small_step",
}


@dataclass(frozen=True)
class OptimizationStatus:
    """Result metadata from bundle adjustment."""

    converged: bool
    termination_reason: str
    iterations: int
    final_cost: float


@dataclass(frozen=True)
class PointDataBundle:
    """Immutable bundle of cameras, image observations, and world points.

    Provides bundle adjustment optimization, reprojection error reporting,
    scale accuracy computation, and coordinate alignment.
    """

    camera_array: CameraArray
    image_points: ImagePoints
    world_points: WorldPoints
    img_to_obj_map: np.ndarray = field(init=False)
    _optimization_status: OptimizationStatus | None = field(default=None, compare=False)

    @property
    def optimization_status(self) -> OptimizationStatus | None:
        return self._optimization_status

    def __post_init__(self):
        object.__setattr__(self, "img_to_obj_map", self._compute_img_to_obj_map())
        self._validate_geometry()

    def _validate_geometry(self):
        n_img = len(self.image_points.df)
        n_world = len(self.world_points.df)
        n_cams = len(self.camera_array.posed_cameras)

        if n_img == 0:
            raise ValueError("No image observations provided")
        if n_world == 0:
            raise ValueError("No world points provided")
        if n_cams == 0:
            raise ValueError("No posed cameras in array")

        n_matched = np.sum(self.img_to_obj_map >= 0)
        if n_matched == 0:
            raise ValueError("No image observations have corresponding world points")
        if n_matched < n_world * 2:
            logger.warning(
                f"Suspicious geometry: {n_matched} matched observations for {n_world} world points"
            )

        valid_indices = self.img_to_obj_map[self.img_to_obj_map >= 0]
        if valid_indices.size > 0 and valid_indices.max() >= n_world:
            raise ValueError(f"obj_indices out-of-bounds: {valid_indices.max()} >= {n_world}")

    def _compute_img_to_obj_map(self) -> np.ndarray:
        world_df = self.world_points.df.reset_index().rename(columns={"index": "world_idx"})
        mapping = world_df.set_index(["sync_index", "point_id"])["world_idx"].to_dict()

        img_df = self.image_points.df
        keys = list(zip(img_df["sync_index"], img_df["point_id"]))
        result = np.array([mapping.get(key, -1) for key in keys], dtype=np.int32)

        n_unmatched = np.sum(result == -1)
        if n_unmatched > 0:
            logger.info(f"{n_unmatched} of {len(result)} image observations have no world point")
        return result

    def _get_matched_data(self):
        """Extract matched observations from posed cameras."""
        matched_mask = self.img_to_obj_map >= 0
        posed_cam_ids = set(self.camera_array.posed_cam_id_to_index.keys())
        posed_mask: np.ndarray = self.image_points.df["cam_id"].isin(posed_cam_ids).to_numpy()
        combined_mask = matched_mask & posed_mask

        matched_img_df = self.image_points.df[combined_mask]
        matched_obj_indices = self.img_to_obj_map[combined_mask]

        camera_indices: CameraIndices = np.array(
            [self.camera_array.posed_cam_id_to_index[c] for c in matched_img_df["cam_id"]],
            dtype=np.int16,
        )
        image_coords: ImageCoords = matched_img_df[["img_loc_x", "img_loc_y"]].values

        return combined_mask, matched_img_df, matched_obj_indices, camera_indices, image_coords

    @cached_property
    def reprojection_report(self) -> ReprojectionReport:
        """Reprojection error report in pixel units (cached)."""
        combined_mask, matched_img_df, matched_obj_indices, camera_indices, image_coords = self._get_matched_data()

        n_total = len(self.img_to_obj_map)
        n_matched = int(combined_mask.sum())

        if n_matched == 0:
            raise ValueError("No matched observations for reprojection error calculation")

        world_coords: WorldCoords = self.world_points.points[matched_obj_indices]
        errors_xy: ErrorsXY = reprojection_errors(
            self.camera_array, camera_indices, image_coords, world_coords, use_normalized=False,
        )

        euclidean_error = np.sqrt(np.sum(errors_xy ** 2, axis=1))
        raw_errors = pd.DataFrame({
            "sync_index": matched_img_df["sync_index"].values,
            "cam_id": matched_img_df["cam_id"].values,
            "point_id": matched_img_df["point_id"].values,
            "error_x": errors_xy[:, 0],
            "error_y": errors_xy[:, 1],
            "euclidean_error": euclidean_error,
        })

        overall_rmse = float(np.sqrt(np.mean(euclidean_error ** 2)))

        by_camera = {}
        for cam_id in self.camera_array.posed_cameras.keys():
            cam_errors = euclidean_error[matched_img_df["cam_id"] == cam_id]
            by_camera[cam_id] = float(np.sqrt(np.mean(cam_errors ** 2))) if len(cam_errors) > 0 else 0.0

        by_point_id = {}
        for pid in np.unique(matched_img_df["point_id"]):
            pt_errors = euclidean_error[matched_img_df["point_id"] == pid]
            by_point_id[pid] = float(np.sqrt(np.mean(pt_errors ** 2)))

        unmatched_by_camera = {}
        for cam_id in self.camera_array.cameras.keys():
            cam_total = (self.image_points.df["cam_id"] == cam_id).sum()
            cam_matched = ((self.image_points.df["cam_id"] == cam_id) & combined_mask).sum()
            unmatched_by_camera[cam_id] = int(cam_total - cam_matched)

        return ReprojectionReport(
            overall_rmse=overall_rmse,
            by_camera=by_camera,
            by_point_id=by_point_id,
            n_unmatched_observations=n_total - n_matched,
            unmatched_rate=(n_total - n_matched) / n_total if n_total > 0 else 0.0,
            unmatched_by_camera=unmatched_by_camera,
            raw_errors=raw_errors,
            n_observations_matched=n_matched,
            n_observations_total=n_total,
            n_cameras=len(self.camera_array.posed_cameras),
            n_points=len(self.world_points.points),
        )

    def optimize(
        self,
        ftol: float = 1e-8,
        max_nfev: int = 1000,
        verbose: int = 2,
    ) -> PointDataBundle:
        """Run bundle adjustment. Returns NEW optimized bundle (immutable)."""
        _, matched_img_df, _, camera_indices, image_coords = self._get_matched_data()
        combined_mask = self.img_to_obj_map >= 0
        posed_cam_ids = set(self.camera_array.posed_cam_id_to_index.keys())
        posed_mask = self.image_points.df["cam_id"].isin(posed_cam_ids).to_numpy()
        full_mask = combined_mask & posed_mask
        image_to_world_indices = self.img_to_obj_map[full_mask]

        initial_params = self._get_vectorized_params()
        sparsity = self._get_sparsity_pattern(camera_indices, image_to_world_indices)

        logger.info(f"Beginning bundle adjustment on {len(image_coords)} observations")
        result = least_squares(
            bundle_residuals,
            initial_params,
            args=(self.camera_array, camera_indices, image_coords, image_to_world_indices, True),
            jac_sparsity=sparsity,
            verbose=verbose,
            x_scale="jac",
            loss="linear",
            ftol=ftol,
            max_nfev=max_nfev,
            method="trf",
        )

        reason = _SCIPY_STATUS_REASONS.get(result.status, f"unknown_{result.status}")
        status = OptimizationStatus(
            converged=result.status in (1, 2, 3, 4),
            termination_reason=reason,
            iterations=result.nfev,
            final_cost=float(result.cost),
        )

        new_camera_array = deepcopy(self.camera_array)
        new_camera_array.update_extrinsic_params(result.x)

        n_cams = len(self.camera_array.posed_cameras)
        optimized_points = result.x[n_cams * 6:].reshape((-1, 3))

        new_world_df = self.world_points.df.copy()
        matched_unique = np.unique(image_to_world_indices)
        new_world_df.loc[matched_unique, ["x_coord", "y_coord", "z_coord"]] = optimized_points
        new_world_points = WorldPoints(new_world_df)

        return PointDataBundle(
            camera_array=new_camera_array,
            image_points=self.image_points,
            world_points=new_world_points,
            _optimization_status=status,
        )

    def _get_sparsity_pattern(
        self, camera_indices: NDArray[np.int16], obj_indices: NDArray[np.int32],
    ) -> lil_matrix:
        n_obs = len(camera_indices)
        n_cameras = len(self.camera_array.posed_cameras)
        n_points = len(self.world_points.points)
        n_residuals = n_obs * 2
        n_params = n_cameras * 6 + n_points * 3

        sparsity = lil_matrix((n_residuals, n_params), dtype=int)
        obs_idx = np.arange(n_obs)

        for cam_p in range(6):
            col = camera_indices * 6 + cam_p
            sparsity[2 * obs_idx, col] = 1
            sparsity[2 * obs_idx + 1, col] = 1

        for pt_p in range(3):
            col = n_cameras * 6 + obj_indices * 3 + pt_p
            sparsity[2 * obs_idx, col] = 1
            sparsity[2 * obs_idx + 1, col] = 1

        return sparsity

    def _get_vectorized_params(self) -> NDArray[np.float64]:
        camera_params = self.camera_array.get_extrinsic_params()
        if camera_params is None:
            raise ValueError("Camera extrinsic parameters not initialized")
        points_3d = self.world_points.points
        return np.concatenate([camera_params.ravel(), points_3d.ravel()])

    def filter_by_absolute_error(self, max_pixels: float, min_per_camera: int = 10) -> PointDataBundle:
        """Remove observations with reprojection error > max_pixels."""
        if max_pixels <= 0:
            raise ValueError(f"max_pixels must be positive, got {max_pixels}")
        thresholds = {cam_id: max_pixels for cam_id in self.camera_array.posed_cameras.keys()}
        return self._filter_by_reprojection_thresholds(thresholds, min_per_camera)

    def filter_by_percentile_error(
        self, percentile: float,
        scope: Literal["per_camera", "overall"] = "per_camera",
        min_per_camera: int = 10,
    ) -> PointDataBundle:
        """Remove worst N% of observations."""
        if not (0 < percentile <= 100):
            raise ValueError(f"percentile must be between 0 and 100, got {percentile}")

        report = self.reprojection_report
        raw_errors = report.raw_errors

        if scope == "per_camera":
            thresholds: dict[int, float] = {}
            for cam_id in self.camera_array.posed_cameras.keys():
                cam_errs = raw_errors[raw_errors["cam_id"] == cam_id]["euclidean_error"]
                if len(cam_errs) > 0:
                    thresholds[cam_id] = float(np.percentile(cam_errs, 100 - percentile))
                else:
                    thresholds[cam_id] = float(np.inf)
        elif scope == "overall":
            global_threshold = float(np.percentile(raw_errors["euclidean_error"], 100 - percentile))
            thresholds = {cam_id: global_threshold for cam_id in self.camera_array.posed_cameras.keys()}
        else:
            raise ValueError(f"scope must be 'per_camera' or 'overall', got {scope}")

        return self._filter_by_reprojection_thresholds(thresholds, min_per_camera)

    def _filter_by_reprojection_thresholds(
        self, thresholds: dict[int, float], min_per_camera: int,
    ) -> PointDataBundle:
        report = self.reprojection_report
        raw_errors = report.raw_errors

        threshold_series = raw_errors["cam_id"].map(thresholds)
        keep_mask = (raw_errors["euclidean_error"] <= threshold_series).copy()

        for cam_id in raw_errors["cam_id"].unique():
            camera_idx = raw_errors["cam_id"] == cam_id
            n_keep = keep_mask[camera_idx].sum()
            n_total = camera_idx.sum()

            if n_keep < min_per_camera and n_keep < n_total:
                n_needed = min(min_per_camera, n_total) - n_keep
                filtered_errors = raw_errors.loc[camera_idx & ~keep_mask, "euclidean_error"]
                if len(filtered_errors) >= n_needed:
                    threshold_to_add = filtered_errors.nsmallest(n_needed).iloc[-1]
                    keep_mask[camera_idx] = raw_errors.loc[camera_idx, "euclidean_error"] <= threshold_to_add

        keep_keys = raw_errors[keep_mask][["sync_index", "cam_id", "point_id"]]
        filtered_img_df = self.image_points.df.merge(keep_keys, on=["sync_index", "cam_id", "point_id"], how="inner")
        filtered_image_points = ImagePoints(filtered_img_df)

        remaining_3d_keys = filtered_img_df[["sync_index", "point_id"]].drop_duplicates()
        filtered_world_df = self.world_points.df.merge(remaining_3d_keys, on=["sync_index", "point_id"], how="inner")
        filtered_world_points = WorldPoints(filtered_world_df)

        return PointDataBundle(
            camera_array=self.camera_array,
            image_points=filtered_image_points,
            world_points=filtered_world_points,
        )

    def compute_volumetric_scale_accuracy(self) -> VolumetricScaleReport:
        """Compute multi-frame scale accuracy across the capture volume."""
        img_df = self.image_points.df
        world_df = self.world_points.df

        obj_loc_cols = ["obj_loc_x", "obj_loc_y", "obj_loc_z"]
        if not all(col in img_df.columns for col in obj_loc_cols):
            return VolumetricScaleReport.empty()

        obj_loc_mask = ~img_df[["obj_loc_x", "obj_loc_y"]].isna().any(axis=1)
        frames_with_obj_loc = img_df[obj_loc_mask]["sync_index"].unique()

        if len(frames_with_obj_loc) == 0:
            return VolumetricScaleReport.empty()

        frame_errors: list[FrameScaleError] = []
        for sync_index in frames_with_obj_loc:
            img_sub = img_df[img_df["sync_index"] == sync_index]
            world_sub = world_df[world_df["sync_index"] == sync_index]
            if img_sub.empty or world_sub.empty:
                continue

            obj_pts_df = img_sub[["point_id", "obj_loc_x", "obj_loc_y", "obj_loc_z"]].drop_duplicates(subset=["point_id"])
            merged = world_sub.merge(obj_pts_df, on="point_id", how="inner")

            if merged["obj_loc_z"].isna().all():
                merged = merged.copy()
                merged["obj_loc_z"] = 0.0

            valid = ~merged[["obj_loc_x", "obj_loc_y", "obj_loc_z"]].isna().any(axis=1)
            merged = merged[valid]
            if len(merged) < 4:
                continue

            n_cams = int(img_sub[img_sub["point_id"].isin(merged["point_id"])]["cam_id"].nunique())
            world_pts = merged[["x_coord", "y_coord", "z_coord"]].to_numpy()
            obj_pts = merged[["obj_loc_x", "obj_loc_y", "obj_loc_z"]].to_numpy()

            try:
                frame_errors.append(compute_frame_scale_error(
                    world_pts, obj_pts, int(sync_index), n_cams,
                ))
            except ValueError as e:
                logger.debug(f"Skipping sync_index {sync_index}: {e}")

        return VolumetricScaleReport(frame_errors=tuple(frame_errors))

    def align_to_object(self, sync_index: int) -> PointDataBundle:
        """Align bundle to real-world units using object point correspondences."""
        img_df = self.image_points.df
        world_df = self.world_points.df

        img_sub = img_df[img_df["sync_index"] == sync_index]
        world_sub = world_df[world_df["sync_index"] == sync_index]

        if img_sub.empty:
            raise ValueError(f"No image observations at sync_index {sync_index}")
        if world_sub.empty:
            raise ValueError(f"No world points at sync_index {sync_index}")

        merged = pd.merge(
            world_sub[["point_id", "x_coord", "y_coord", "z_coord"]],
            img_sub[["point_id", "obj_loc_x", "obj_loc_y", "obj_loc_z"]],
            on="point_id", how="inner",
        )

        if len(merged) < 3:
            raise ValueError(f"Need >= 3 correspondences at sync_index {sync_index}, got {len(merged)}")

        if merged["obj_loc_z"].isna().all():
            logger.info("obj_loc_z is all NaN, assuming planar board with z=0")
            merged["obj_loc_z"] = 0.0

        obj_cols = ["obj_loc_x", "obj_loc_y", "obj_loc_z"]
        valid = ~merged[obj_cols].isna().any(axis=1)
        merged = merged[valid]

        if len(merged) < 3:
            raise ValueError(f"Need >= 3 valid correspondences at sync_index {sync_index}, got {len(merged)}")

        source = merged[["x_coord", "y_coord", "z_coord"]].values.astype(np.float64)
        target = merged[obj_cols].values.astype(np.float64)

        transform = estimate_similarity_transform(source, target)
        logger.info(f"Alignment: scale={transform.scale:.6f}")

        new_cam, new_world = apply_similarity_transform(self.camera_array, self.world_points, transform)
        return PointDataBundle(
            camera_array=new_cam,
            image_points=self.image_points,
            world_points=new_world,
            _optimization_status=self._optimization_status,
        )

    @property
    def unique_sync_indices(self) -> np.ndarray:
        return np.sort(self.world_points.df["sync_index"].unique())
