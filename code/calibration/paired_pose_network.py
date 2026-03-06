"""
Paired pose network for stereo pair graph construction.

Adapted from caliscope/core/bootstrap_pose/paired_pose_network.py (BSD-2-Clause, Mac Prible).
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from itertools import permutations
from typing import Dict, Tuple

import numpy as np

from calibration.data_types import CameraArray, CameraData, StereoPair

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PairedPoseNetwork:
    """Immutable graph of stereo pair relationships between cameras."""

    _pairs: Dict[Tuple[int, int], StereoPair]

    @classmethod
    def from_raw_estimates(cls, raw_pairs: Dict[Tuple[int, int], StereoPair]) -> PairedPoseNetwork:
        """Create network from raw estimates, filling gaps via bridging."""
        all_pairs = raw_pairs.copy()
        inverted_pairs = {(inv := pair.inverted()).pair: inv for pair in all_pairs.values()}
        all_pairs.update(inverted_pairs)

        cam_ids_set: set[int] = set()
        for a, b in all_pairs.keys():
            cam_ids_set.add(a)
            cam_ids_set.add(b)
        cam_ids = sorted(cam_ids_set)

        # Iteratively fill gaps via bridging
        missing_count_last = -1
        while True:
            possible_pairs = list(permutations(cam_ids, 2))
            missing_pairs = [p for p in possible_pairs if p not in all_pairs]
            current_missing = len(missing_pairs)

            if current_missing == missing_count_last or current_missing == 0:
                break
            missing_count_last = current_missing

            for cam_id_a, cam_id_c in missing_pairs:
                best_bridge = None
                for cam_id_x in cam_ids:
                    pair_a_x = all_pairs.get((cam_id_a, cam_id_x))
                    pair_x_c = all_pairs.get((cam_id_x, cam_id_c))
                    if pair_a_x is not None and pair_x_c is not None:
                        possible_bridge = pair_a_x.link(pair_x_c)
                        if best_bridge is None or best_bridge.error_score > possible_bridge.error_score:
                            best_bridge = possible_bridge

                if best_bridge is not None:
                    all_pairs[best_bridge.pair] = best_bridge
                    inverted = best_bridge.inverted()
                    all_pairs[inverted.pair] = inverted

        logger.info(f"PairedPoseNetwork created with {len(all_pairs)} pairs")
        raw_errors = [p.error_score for p in raw_pairs.values()]
        max_raw = max(raw_errors) if raw_errors else 0
        bridged_count = sum(1 for p in all_pairs.values() if p.error_score > max_raw * 1.5)
        logger.info(f"  Estimated bridged pairs: {bridged_count}")

        return cls(_pairs=all_pairs)

    def _build_anchored_config(
        self, camera_array: CameraArray, anchor_cam_id: int
    ) -> tuple[float, Dict[int, CameraData]]:
        """Build camera config anchored to specified camera."""
        total_error = 0.0
        configured_cameras = {}

        for cam_id, cam_data in camera_array.cameras.items():
            configured_cameras[cam_id] = CameraData(
                cam_id=cam_data.cam_id,
                size=cam_data.size,
                rotation_count=cam_data.rotation_count,
                error=cam_data.error,
                matrix=cam_data.matrix,
                distortions=cam_data.distortions,
                grid_count=cam_data.grid_count,
                exposure=cam_data.exposure,
                ignore=cam_data.ignore,
                fisheye=cam_data.fisheye,
                translation=None,
                rotation=None,
            )

        # Set anchor to origin
        configured_cameras[anchor_cam_id].rotation = np.eye(3, dtype=np.float64)
        configured_cameras[anchor_cam_id].translation = np.zeros(3, dtype=np.float64)

        cam_ids = sorted(camera_array.cameras.keys())
        for cam_id in cam_ids:
            if cam_id == anchor_cam_id:
                continue
            pair_key = (anchor_cam_id, cam_id)
            if pair_key in self._pairs:
                sp = self._pairs[pair_key]
                configured_cameras[cam_id].translation = sp.translation.flatten()
                configured_cameras[cam_id].rotation = sp.rotation
                total_error += sp.error_score

        return total_error, configured_cameras

    def get_pair(self, cam_id_a: int, cam_id_b: int) -> StereoPair | None:
        return self._pairs.get((cam_id_a, cam_id_b))

    def apply_to(self, camera_array: CameraArray, anchor_cam: int | None = None) -> None:
        """Mutate camera_array in place with globally consistent camera poses."""
        cam_ids = sorted(camera_array.cameras.keys())
        main_group = self._find_largest_connected_component(cam_ids)

        if anchor_cam:
            _, best_config = self._build_anchored_config(camera_array, anchor_cam)
        else:
            # Find best anchor
            best_anchor = -1
            lowest_error = float("inf")
            best_config = None

            logger.info("Assessing best cam_id to anchor camera array")
            for cam_id in main_group:
                error, config = self._build_anchored_config(camera_array, cam_id)
                logger.info(f"    cam_id {cam_id} anchor_score = {error}")
                if error < lowest_error:
                    lowest_error = error
                    best_anchor = cam_id
                    best_config = config

            if best_anchor == -1:
                best_config = camera_array.cameras
            else:
                assert best_config is not None
                logger.info(f"Selected camera {best_anchor} as anchor")

        for cam_id, cam_data in best_config.items():
            camera_array.cameras[cam_id] = cam_data

        unposed = [c for c in cam_ids if c not in main_group]
        if unposed:
            logger.warning(f"Cameras not in main group remain unposed: {unposed}")

    def to_dict(self) -> Dict[str, dict]:
        """Serialize to dictionary format."""
        return {
            f"stereo_{a}_{b}": {
                "rotation": pair.rotation.tolist(),
                "translation": pair.translation.tolist(),
                "RMSE": pair.error_score,
            }
            for (a, b), pair in self._pairs.items()
            if a < b
        }

    def _find_largest_connected_component(self, cam_ids: list[int]) -> set[int]:
        if not self._pairs:
            return set()

        adj: dict[int, list[int]] = {cid: [] for cid in cam_ids}
        for c1, c2 in self._pairs.keys():
            if c1 in adj:
                adj[c1].append(c2)

        visited: set[int] = set()
        largest: set[int] = set()
        for cid in cam_ids:
            if cid not in visited:
                component: set[int] = set()
                q = deque([cid])
                visited.add(cid)
                while q:
                    u = q.popleft()
                    component.add(u)
                    for v in adj.get(u, []):
                        if v not in visited:
                            visited.add(v)
                            q.append(v)
                if len(component) > len(largest):
                    largest = component
        return largest
