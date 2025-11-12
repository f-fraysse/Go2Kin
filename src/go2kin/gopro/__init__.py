"""
GoPro camera control module for Go2Kin.

Provides thread-safe wrappers around the goproUSB module for multi-camera
operations with PyQt6 integration.
"""

from .multi_camera_controller import GPcamController, CameraManager
from .camera_worker import CameraWorker

__all__ = ['GPcamController', 'CameraManager', 'CameraWorker']
