"""
Reprojection error report dataclass.

Adapted from caliscope/core/reprojection_report.py (BSD-2-Clause, Mac Prible).
"""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ReprojectionReport:
    """Comprehensive snapshot of reprojection error metrics."""

    overall_rmse: float
    by_camera: dict[int, float]
    by_point_id: dict[int, float]

    n_unmatched_observations: int
    unmatched_rate: float
    unmatched_by_camera: dict[int, int]

    raw_errors: pd.DataFrame  # columns: sync_index, cam_id, point_id, error_x, error_y, euclidean_error

    n_observations_matched: int
    n_observations_total: int
    n_cameras: int
    n_points: int
