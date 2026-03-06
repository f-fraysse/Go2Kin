"""
Scale accuracy computation for calibration quality assessment.

Adapted from caliscope/core/scale_accuracy.py (BSD-2-Clause, Mac Prible).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import numpy as np
from scipy.spatial.distance import pdist


@dataclass(frozen=True)
class FrameScaleError:
    """Per-frame scale accuracy comparing triangulated to ground truth distances.

    Sign convention: positive error = measured distance larger than true.
    All distance metrics are in millimeters.
    """

    sync_index: int
    distance_rmse_mm: float
    distance_mean_signed_error_mm: float
    distance_max_error_mm: float
    n_corners: int
    n_distance_pairs: int
    n_cameras_contributing: int
    sum_squared_errors_m2: float
    centroid: tuple[float, float, float]


@dataclass(frozen=True)
class VolumetricScaleReport:
    """Aggregate scale accuracy across multiple frames."""

    frame_errors: tuple[FrameScaleError, ...]

    @cached_property
    def pooled_rmse_mm(self) -> float:
        if not self.frame_errors:
            return 0.0
        total_sse = sum(fe.sum_squared_errors_m2 for fe in self.frame_errors)
        total_pairs = sum(fe.n_distance_pairs for fe in self.frame_errors)
        if total_pairs == 0:
            return 0.0
        return float(np.sqrt(total_sse / total_pairs) * 1000)

    @cached_property
    def median_rmse_mm(self) -> float:
        if not self.frame_errors:
            return 0.0
        return float(np.median([fe.distance_rmse_mm for fe in self.frame_errors]))

    @cached_property
    def max_rmse_mm(self) -> float:
        if not self.frame_errors:
            return 0.0
        return float(max(fe.distance_rmse_mm for fe in self.frame_errors))

    @cached_property
    def worst_frame(self) -> FrameScaleError | None:
        if not self.frame_errors:
            return None
        return max(self.frame_errors, key=lambda fe: fe.distance_rmse_mm)

    @cached_property
    def n_frames_sampled(self) -> int:
        return len(self.frame_errors)

    @cached_property
    def mean_signed_error_mm(self) -> float:
        if not self.frame_errors:
            return 0.0
        weighted_sum = sum(fe.distance_mean_signed_error_mm * fe.n_distance_pairs for fe in self.frame_errors)
        total_pairs = sum(fe.n_distance_pairs for fe in self.frame_errors)
        if total_pairs == 0:
            return 0.0
        return float(weighted_sum / total_pairs)

    @classmethod
    def empty(cls) -> VolumetricScaleReport:
        return cls(frame_errors=())


def compute_frame_scale_error(
    world_points: np.ndarray,
    object_points: np.ndarray,
    sync_index: int,
    n_cameras_contributing: int,
) -> FrameScaleError:
    """Compare triangulated inter-point distances to known ground truth.

    Uses ALL pairwise distances for robust statistics.

    Args:
        world_points: (N, 3) triangulated positions (meters)
        object_points: (N, 3) ideal positions (meters)
        sync_index: Frame index
        n_cameras_contributing: Number of cameras that observed corners

    Returns:
        FrameScaleError with distance error statistics
    """
    if world_points.shape != object_points.shape:
        raise ValueError(f"Shape mismatch: {world_points.shape} vs {object_points.shape}")
    if len(world_points) < 2:
        raise ValueError(f"Need >= 2 points, got {len(world_points)}")

    mean_pos = np.mean(world_points, axis=0)
    centroid = (float(mean_pos[0]), float(mean_pos[1]), float(mean_pos[2]))

    measured_distances = pdist(world_points)
    true_distances = pdist(object_points)
    distance_errors = measured_distances - true_distances
    abs_errors = np.abs(distance_errors)

    rmse_mm = float(np.sqrt(np.mean(distance_errors ** 2))) * 1000
    mean_signed_error_mm = float(np.mean(distance_errors)) * 1000
    max_error_mm = float(np.max(abs_errors)) * 1000
    sum_squared_errors_m2 = float(np.sum(distance_errors ** 2))

    return FrameScaleError(
        sync_index=sync_index,
        distance_rmse_mm=rmse_mm,
        distance_mean_signed_error_mm=mean_signed_error_mm,
        distance_max_error_mm=max_error_mm,
        n_corners=len(world_points),
        n_distance_pairs=len(distance_errors),
        n_cameras_contributing=n_cameras_contributing,
        sum_squared_errors_m2=sum_squared_errors_m2,
        centroid=centroid,
    )
