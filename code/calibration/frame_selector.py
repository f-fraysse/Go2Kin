"""Automatic frame selection for intrinsic camera calibration.

Two-phase deterministic algorithm:
Phase 1 (Orientation Diversity): Ensures min orientation diversity from
    distinct tilt directions — hard constraint for focal length observability (Zhang 2000).
Phase 2 (Spatial Coverage): Fills remaining slots with greedy coverage
    optimization, prioritizing edge/corner regions for distortion estimation.

Adapted from caliscope/core/frame_selector.py (BSD-2-Clause, Mac Prible).
"""

from dataclasses import dataclass
from typing import NamedTuple, cast

import cv2
import numpy as np
import pandas as pd

from calibration.data_types import ImagePoints

GridCell = tuple[int, int]
CoveredCells = set[GridCell]
PoseFeatures = np.ndarray


class OrientationFeatures(NamedTuple):
    tilt_direction: float
    tilt_magnitude: float
    in_plane_rotation: float


_POSE_CENTROID_X = 0
_POSE_CENTROID_Y = 1
_POSE_SPREAD_X = 2
_POSE_SPREAD_Y = 3
_POSE_ASPECT_RATIO = 4

_NUM_TILT_DIRECTION_BINS = 8
MIN_TILT_FOR_DIVERSITY = 0.1


@dataclass(frozen=True)
class FrameCoverageData:
    covered_cells: CoveredCells
    pose_features: PoseFeatures
    orientation: OrientationFeatures


@dataclass(frozen=True)
class IntrinsicCoverageReport:
    selected_frames: list[int]
    coverage_fraction: float
    edge_coverage_fraction: float
    corner_coverage_fraction: float
    pose_diversity: float
    orientation_sufficient: bool
    orientation_count: int
    eligible_frame_count: int
    total_frame_count: int


def select_calibration_frames(
    image_points: ImagePoints,
    cam_id: int,
    image_size: tuple[int, int],
    *,
    target_frame_count: int = 30,
    min_corners_per_frame: int = 6,
    min_orientations: int = 4,
    grid_size: int = 5,
) -> IntrinsicCoverageReport:
    cam_df = cast(pd.DataFrame, image_points.df[image_points.df["cam_id"] == cam_id].copy())
    total_frame_count = int(cam_df["sync_index"].nunique())

    if total_frame_count == 0:
        return IntrinsicCoverageReport(
            selected_frames=[], coverage_fraction=0.0, edge_coverage_fraction=0.0,
            corner_coverage_fraction=0.0, pose_diversity=0.0,
            orientation_sufficient=False, orientation_count=0,
            eligible_frame_count=0, total_frame_count=0,
        )

    eligible_frames = _filter_eligible_frames(cam_df, min_corners_per_frame)

    if not eligible_frames:
        return IntrinsicCoverageReport(
            selected_frames=[], coverage_fraction=0.0, edge_coverage_fraction=0.0,
            corner_coverage_fraction=0.0, pose_diversity=0.0,
            orientation_sufficient=False, orientation_count=0,
            eligible_frame_count=0, total_frame_count=total_frame_count,
        )

    frame_data: dict[int, FrameCoverageData] = {}
    for sync_index in eligible_frames:
        frame_df = cast(pd.DataFrame, cam_df[cam_df["sync_index"] == sync_index])
        coverage = _compute_frame_coverage(frame_df, image_size, grid_size)
        pose = _compute_pose_features(frame_df, image_size)
        orientation = _compute_orientation_features(frame_df)
        frame_data[sync_index] = FrameCoverageData(coverage, pose, orientation)

    anchor_frames, covered_bins = _select_orientation_anchors(frame_data, min_orientations)
    orientation_count = len(covered_bins)
    orientation_sufficient = orientation_count >= min_orientations

    remaining_budget = target_frame_count - len(anchor_frames)
    if remaining_budget > 0:
        coverage_frames = _greedy_select_coverage(
            frame_data, already_selected=anchor_frames,
            target_count=remaining_budget, grid_size=grid_size,
        )
        selected_frames = anchor_frames + coverage_frames
    else:
        selected_frames = anchor_frames[:target_frame_count]

    metrics = _compute_quality_metrics(frame_data, selected_frames, grid_size)

    return IntrinsicCoverageReport(
        selected_frames=selected_frames,
        coverage_fraction=metrics["coverage_fraction"],
        edge_coverage_fraction=metrics["edge_coverage_fraction"],
        corner_coverage_fraction=metrics["corner_coverage_fraction"],
        pose_diversity=metrics["pose_diversity"],
        orientation_sufficient=orientation_sufficient,
        orientation_count=orientation_count,
        eligible_frame_count=len(eligible_frames),
        total_frame_count=total_frame_count,
    )


def _filter_eligible_frames(cam_df: pd.DataFrame, min_corners: int) -> list[int]:
    eligible: list[int] = []
    grouped = cam_df.groupby("sync_index")
    for sync_index_key, frame_group in grouped:
        frame_df = cast(pd.DataFrame, frame_group)
        sync_index = int(sync_index_key)
        if len(frame_df) >= min_corners:
            eligible.append(sync_index)
    return sorted(eligible)


def _compute_frame_coverage(
    frame_df: pd.DataFrame, image_size: tuple[int, int], grid_size: int,
) -> CoveredCells:
    width, height = image_size
    cell_width = width / grid_size
    cell_height = height / grid_size
    covered: CoveredCells = set()
    for _, point in frame_df.iterrows():
        grid_col = max(0, min(int(point["img_loc_x"] / cell_width), grid_size - 1))
        grid_row = max(0, min(int(point["img_loc_y"] / cell_height), grid_size - 1))
        covered.add((grid_row, grid_col))
    return covered


def _compute_pose_features(frame_df: pd.DataFrame, image_size: tuple[int, int]) -> PoseFeatures:
    width, height = image_size
    centroid_x = frame_df["img_loc_x"].mean() / width
    centroid_y = frame_df["img_loc_y"].mean() / height
    spread_x = frame_df["img_loc_x"].std() / width if len(frame_df) > 1 else 0.0
    spread_y = frame_df["img_loc_y"].std() / height if len(frame_df) > 1 else 0.0
    aspect_ratio = spread_x / spread_y if spread_y > 1e-6 else 1.0
    return np.array([centroid_x, centroid_y, spread_x, spread_y, aspect_ratio])


def _compute_orientation_features(frame_df: pd.DataFrame) -> OrientationFeatures:
    obj_points = frame_df[["obj_loc_x", "obj_loc_y"]].to_numpy(dtype=np.float32)
    img_points = frame_df[["img_loc_x", "img_loc_y"]].to_numpy(dtype=np.float32)

    if len(obj_points) < 4:
        return OrientationFeatures(0.0, 0.0, 0.0)

    obj_range = obj_points.max(axis=0) - obj_points.min(axis=0)
    obj_range[obj_range < 1e-6] = 1.0
    obj_normalized = (obj_points - obj_points.min(axis=0)) / obj_range

    H, mask = cv2.findHomography(obj_normalized, img_points, cv2.RANSAC, 5.0)
    if H is None:
        return OrientationFeatures(0.0, 0.0, 0.0)

    H = H / H[2, 2]
    tilt_direction = float(np.arctan2(H[2, 1], H[2, 0]))
    if tilt_direction < 0:
        tilt_direction += 2 * np.pi
    tilt_magnitude = float(np.sqrt(H[2, 0] ** 2 + H[2, 1] ** 2))

    A = H[:2, :2]
    U, S, Vt = np.linalg.svd(A)
    R = U @ Vt
    in_plane_rotation = float(np.arctan2(R[1, 0], R[0, 0]))
    if in_plane_rotation < 0:
        in_plane_rotation += 2 * np.pi

    return OrientationFeatures(tilt_direction, tilt_magnitude, in_plane_rotation)


def _get_orientation_bin(orientation: OrientationFeatures) -> int | None:
    if orientation.tilt_magnitude < MIN_TILT_FOR_DIVERSITY:
        return None
    bin_index = int(orientation.tilt_direction / (2 * np.pi) * _NUM_TILT_DIRECTION_BINS)
    return min(bin_index, _NUM_TILT_DIRECTION_BINS - 1)


def _score_frame(
    candidate_coverage: CoveredCells, selected_coverage: CoveredCells,
    candidate_pose: PoseFeatures, selected_poses: list[PoseFeatures],
    grid_size: int, edge_weight: float = 0.2, corner_weight: float = 0.3,
    diversity_weight: float = 0.3,
) -> float:
    new_cells = candidate_coverage - selected_coverage
    score = float(len(new_cells))

    edge_indices = {0, grid_size - 1}
    edge_cells = {c for c in new_cells if c[0] in edge_indices or c[1] in edge_indices}
    score += len(edge_cells) * edge_weight

    corners = {(0, 0), (0, grid_size - 1), (grid_size - 1, 0), (grid_size - 1, grid_size - 1)}
    corner_cells = new_cells & corners
    score += len(corner_cells) * corner_weight

    if selected_poses:
        distances = [float(np.linalg.norm(candidate_pose - p)) for p in selected_poses]
        score += min(distances) * diversity_weight

    return score


def _select_orientation_anchors(
    frame_data: dict[int, FrameCoverageData], min_orientations: int,
) -> tuple[list[int], set[int]]:
    bin_to_frames: dict[int, list[tuple[int, float]]] = {}
    for sync_index, data in frame_data.items():
        bin_idx = _get_orientation_bin(data.orientation)
        if bin_idx is not None:
            if bin_idx not in bin_to_frames:
                bin_to_frames[bin_idx] = []
            bin_to_frames[bin_idx].append((sync_index, data.orientation.tilt_magnitude))

    selected_anchors: list[int] = []
    covered_bins: set[int] = set()
    for bin_idx in sorted(bin_to_frames.keys()):
        frames = bin_to_frames[bin_idx]
        frames.sort(key=lambda x: (-x[1], x[0]))
        selected_anchors.append(frames[0][0])
        covered_bins.add(bin_idx)

    return selected_anchors, covered_bins


def _greedy_select_coverage(
    frame_data: dict[int, FrameCoverageData], already_selected: list[int],
    target_count: int, grid_size: int, min_score: float = 0.01,
) -> list[int]:
    selected_coverage: CoveredCells = set()
    selected_poses: list[PoseFeatures] = []
    for sync_index in already_selected:
        data = frame_data[sync_index]
        selected_coverage |= data.covered_cells
        selected_poses.append(data.pose_features)

    remaining = set(frame_data.keys()) - set(already_selected)
    newly_selected: list[int] = []

    while len(newly_selected) < target_count and remaining:
        scores: list[tuple[float, int]] = []
        for sync_index in remaining:
            data = frame_data[sync_index]
            score = _score_frame(
                data.covered_cells, selected_coverage,
                data.pose_features, selected_poses, grid_size,
            )
            scores.append((score, sync_index))
        scores.sort(key=lambda x: (-x[0], x[1]))

        best_score, best_frame = scores[0]
        if best_score < min_score:
            break

        best_data = frame_data[best_frame]
        newly_selected.append(best_frame)
        selected_coverage |= best_data.covered_cells
        selected_poses.append(best_data.pose_features)
        remaining.remove(best_frame)

    return newly_selected


def _compute_quality_metrics(
    frame_data: dict[int, FrameCoverageData], selected_frames: list[int], grid_size: int,
) -> dict[str, float]:
    if not selected_frames:
        return {"coverage_fraction": 0.0, "edge_coverage_fraction": 0.0,
                "corner_coverage_fraction": 0.0, "pose_diversity": 0.0}

    total_coverage: CoveredCells = set()
    poses: list[PoseFeatures] = []
    for sync_index in selected_frames:
        data = frame_data[sync_index]
        total_coverage |= data.covered_cells
        poses.append(data.pose_features)

    total_cells = grid_size * grid_size
    coverage_fraction = len(total_coverage) / total_cells

    edge_indices = {0, grid_size - 1}
    all_edge_cells = {
        (r, c) for r in range(grid_size) for c in range(grid_size)
        if r in edge_indices or c in edge_indices
    }
    covered_edge_cells = total_coverage & all_edge_cells
    edge_coverage_fraction = len(covered_edge_cells) / len(all_edge_cells) if all_edge_cells else 0.0

    corner_cells = {(0, 0), (0, grid_size - 1), (grid_size - 1, 0), (grid_size - 1, grid_size - 1)}
    covered_corners = total_coverage & corner_cells
    corner_coverage_fraction = len(covered_corners) / len(corner_cells)

    if len(poses) > 1:
        pose_array = np.array(poses)
        pose_diversity = float(np.mean(np.var(pose_array, axis=0)))
    else:
        pose_diversity = 0.0

    return {
        "coverage_fraction": coverage_fraction,
        "edge_coverage_fraction": edge_coverage_fraction,
        "corner_coverage_fraction": corner_coverage_fraction,
        "pose_diversity": pose_diversity,
    }
