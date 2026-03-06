"""
Charuco board definition and image generation.

Adapted from caliscope/core/charuco.py (BSD-2-Clause, Mac Prible).
Removed PySide6 dependency; added PIL-based board_pil_image() for tkinter.
"""

import logging
from collections import defaultdict
from itertools import combinations

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

INCHES_PER_CM = 0.393701


class Charuco:
    """Create a charuco board for camera calibration."""

    # Go2Kin defaults: 7x5 board on A1 paper (59.4 x 84.1 cm)
    DEFAULT_COLUMNS = 7
    DEFAULT_ROWS = 5
    DEFAULT_BOARD_HEIGHT = 59.4  # cm (A1 short edge)
    DEFAULT_BOARD_WIDTH = 84.1   # cm (A1 long edge)
    DEFAULT_SQUARE_SIZE_CM = 11.70
    DEFAULT_DICTIONARY = "DICT_4X4_50"
    DEFAULT_ARUCO_SCALE = 0.75

    def __init__(
        self,
        columns=DEFAULT_COLUMNS,
        rows=DEFAULT_ROWS,
        board_height=DEFAULT_BOARD_HEIGHT,
        board_width=DEFAULT_BOARD_WIDTH,
        dictionary=DEFAULT_DICTIONARY,
        units="cm",
        aruco_scale=DEFAULT_ARUCO_SCALE,
        square_size_overide_cm=DEFAULT_SQUARE_SIZE_CM,
        inverted=False,
        legacy_pattern=False,
    ):
        self.columns = columns
        self.rows = rows
        self.board_height = board_height
        self.board_width = board_width
        self.dictionary = dictionary
        self.units = units
        self.aruco_scale = aruco_scale
        self.square_size_overide_cm = square_size_overide_cm
        self.inverted = inverted
        self.legacy_pattern = legacy_pattern

    @property
    def board_height_cm(self):
        if self.units == "inch":
            return self.board_height / INCHES_PER_CM
        else:
            return self.board_height

    @property
    def board_width_cm(self):
        if self.units == "inch":
            return self.board_width / INCHES_PER_CM
        else:
            return self.board_width

    def board_height_scaled(self, pixmap_scale):
        if self.board_height_cm > self.board_width_cm:
            return int(pixmap_scale)
        else:
            return int(pixmap_scale * (self.board_height_cm / self.board_width_cm))

    def board_width_scaled(self, pixmap_scale):
        if self.board_height_cm > self.board_width_cm:
            return int(pixmap_scale * (self.board_width_cm / self.board_height_cm))
        else:
            return int(pixmap_scale)

    @property
    def dictionary_object(self):
        dictionary_integer = ARUCO_DICTIONARIES[self.dictionary]
        return cv2.aruco.getPredefinedDictionary(dictionary_integer)

    @property
    def board(self):
        if self.square_size_overide_cm:
            square_length = self.square_size_overide_cm / 100  # cm to meters
        else:
            board_height_m = self.board_height_cm / 100
            board_width_m = self.board_width_cm / 100
            square_length = min([board_height_m / self.rows, board_width_m / self.columns])

        aruco_length = square_length * self.aruco_scale
        board = cv2.aruco.CharucoBoard(
            size=(self.columns, self.rows),
            squareLength=square_length,
            markerLength=aruco_length,
            dictionary=self.dictionary_object,
        )
        board.setLegacyPattern(self.legacy_pattern)
        return board

    def board_img(self, pixmap_scale=1000):
        img = self.board.generateImage(
            (self.board_width_scaled(pixmap_scale=pixmap_scale),
             self.board_height_scaled(pixmap_scale=pixmap_scale))
        )
        if self.inverted:
            img = cv2.bitwise_not(img)
        return img

    def board_pil_image(self, width=None, height=None):
        """Return PIL Image of the board, optionally resized for tkinter display."""
        img = self.board_img()
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if width and height:
            pil_img = pil_img.resize((width, height), Image.LANCZOS)
        return pil_img

    def save_image(self, path):
        cv2.imwrite(str(path), self.board_img(pixmap_scale=10000))

    def save_mirror_image(self, path):
        mirror = cv2.flip(self.board_img(pixmap_scale=10000), 1)
        cv2.imwrite(str(path), mirror)

    def get_connected_points(self) -> set[tuple[int, int]]:
        corners = np.asarray(self.board.getChessboardCorners())
        corners_x = corners[:, 0]
        corners_y = corners[:, 1]
        x_set = set(corners_x)
        y_set = set(corners_y)

        lines = defaultdict(list)
        for x_line in x_set:
            for corner, x, y in zip(range(0, len(corners)), corners_x, corners_y):
                if x == x_line:
                    lines[f"x_{x_line}"].append(corner)
        for y_line in y_set:
            for corner, x, y in zip(range(0, len(corners)), corners_x, corners_y):
                if y == y_line:
                    lines[f"y_{y_line}"].append(corner)

        connected_corners = set()
        for _lines, corner_ids in lines.items():
            for i in combinations(corner_ids, 2):
                connected_corners.add(i)
        return connected_corners

    def get_object_corners(self, corner_ids):
        corners = np.asarray(self.board.getChessboardCorners())
        return corners[corner_ids, :]

    def summary(self):
        text = f"Columns: {self.columns}\n"
        text += f"Rows: {self.rows}\n"
        text += f"Board Size: {self.board_width} x {self.board_height} {self.units}\n"
        text += f"Inverted: {self.inverted}\n\n"
        text += f"Square Edge Length: {self.square_size_overide_cm} cm"
        return text


ARUCO_DICTIONARIES = {
    "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
    "DICT_4X4_250": cv2.aruco.DICT_4X4_250,
    "DICT_4X4_1000": cv2.aruco.DICT_4X4_1000,
    "DICT_5X5_50": cv2.aruco.DICT_5X5_50,
    "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
    "DICT_5X5_250": cv2.aruco.DICT_5X5_250,
    "DICT_5X5_1000": cv2.aruco.DICT_5X5_1000,
    "DICT_6X6_50": cv2.aruco.DICT_6X6_50,
    "DICT_6X6_100": cv2.aruco.DICT_6X6_100,
    "DICT_6X6_250": cv2.aruco.DICT_6X6_250,
    "DICT_6X6_1000": cv2.aruco.DICT_6X6_1000,
    "DICT_7X7_50": cv2.aruco.DICT_7X7_50,
    "DICT_7X7_100": cv2.aruco.DICT_7X7_100,
    "DICT_7X7_250": cv2.aruco.DICT_7X7_250,
    "DICT_7X7_1000": cv2.aruco.DICT_7X7_1000,
    "DICT_ARUCO_ORIGINAL": cv2.aruco.DICT_ARUCO_ORIGINAL,
    "DICT_APRILTAG_16h5": cv2.aruco.DICT_APRILTAG_16h5,
    "DICT_APRILTAG_25h9": cv2.aruco.DICT_APRILTAG_25h9,
    "DICT_APRILTAG_36h10": cv2.aruco.DICT_APRILTAG_36h10,
    "DICT_APRILTAG_36h11": cv2.aruco.DICT_APRILTAG_36h11,
}
