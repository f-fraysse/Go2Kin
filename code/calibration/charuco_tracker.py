"""
Charuco board corner detection.

Adapted from caliscope/trackers/charuco_tracker.py (BSD-2-Clause, Mac Prible).
Simplified: removed abstract Tracker base class (not needed for Go2Kin).
"""

import logging

import cv2
import numpy as np

from calibration.data_types import PointPacket

logger = logging.getLogger(__name__)


class CharucoTracker:
    """Detects Charuco board corners in video frames."""

    def __init__(self, charuco):
        self.charuco = charuco
        self.board = charuco.board
        self.detector = cv2.aruco.CharucoDetector(self.board)

        # Sub-pixel refinement parameters
        self.criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.0001)
        self.conv_size = (11, 11)

    def get_points(self, frame: np.ndarray, cam_id: int = 0, rotation_count: int = 0) -> PointPacket:
        """Detect charuco corners. Falls back to mirror image if none found."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self.charuco.inverted:
            gray = cv2.bitwise_not(gray)

        ids, img_loc = self.find_corners_single_frame(gray, mirror=False)

        if not ids.any():
            gray = cv2.flip(gray, 1)
            ids, img_loc = self.find_corners_single_frame(gray, mirror=True)

        obj_loc = self.get_obj_loc(ids)
        return PointPacket(ids, img_loc, obj_loc)

    def find_corners_single_frame(self, gray_frame, mirror):
        ids = np.array([], dtype=np.int32)
        img_loc = np.empty((0, 2), dtype=np.float64)

        _img_loc, _ids, marker_corners, marker_ids = self.detector.detectBoard(gray_frame)

        if _ids is not None and len(_ids) > 0:
            try:
                _img_loc = cv2.cornerSubPix(
                    gray_frame, _img_loc, self.conv_size, (-1, -1), self.criteria,
                )
            except Exception as e:
                logger.debug(f"Sub pixel detection failed: {e}")

            ids = _ids[:, 0]
            img_loc = _img_loc[:, 0]

            frame_width = gray_frame.shape[1]
            if mirror:
                img_loc[:, 0] = frame_width - img_loc[:, 0]

        return ids, img_loc

    def get_obj_loc(self, ids: np.ndarray):
        """Object position of charuco corners in board frame of reference."""
        if len(ids) > 0:
            corners = self.board.getChessboardCorners()[ids, :]
            if corners.shape[1] == 2:
                corners = np.column_stack([corners, np.zeros(len(ids))])
            return corners
        else:
            return np.empty((0, 3), dtype=np.float64)

    def scatter_draw_instructions(self, point_id: int) -> dict:
        return {"radius": 5, "color": (0, 0, 220), "thickness": 3}
