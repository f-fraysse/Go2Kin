"""
Multi-camera controller for GoPro cameras.

Provides thread-safe wrappers around goproUSB.GPcam with PyQt6 integration
for coordinated multi-camera operations.
"""

import sys
import os
from enum import Enum
from typing import Dict, List, Optional, Any
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal, QThreadPool, QTimer
import logging

# Add goproUSB to path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "goproUSB"))
from goproUSB import GPcam

from ..config import ConfigManager, calculate_camera_ip
from .camera_worker import CameraOperationWorker, DownloadWorker

logger = logging.getLogger(__name__)

class CameraState(Enum):
    """Camera connection and operation states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    READY = "ready"
    RECORDING = "recording"
    DOWNLOADING = "downloading"
    WEBCAM_MODE = "webcam"
    ERROR = "error"

class GPcamController(QObject):
    """Thread-safe wrapper around GPcam with state management."""
    
    # Signals for UI updates
    statusChanged = pyqtSignal(str, str)  # camera_id, status
    recordingStarted = pyqtSignal(str)    # camera_id
    recordingStopped = pyqtSignal(str)    # camera_id
    downloadProgress = pyqtSignal(str, int)  # camera_id, progress
    downloadFinished = pyqtSignal(str, str)  # camera_id, file_path
    errorOccurred = pyqtSignal(str, str)  # camera_id, error_message
    
    def __init__(self, camera_id: str, serial_number: str, config_manager: ConfigManager):
        """Initialize camera controller.
        
        Args:
            camera_id: Unique identifier (e.g., 'GP1')
            serial_number: GoPro serial number
            config_manager: Configuration manager instance
        """
        super().__init__()
        self.camera_id = camera_id
        self.serial_number = serial_number
        self.config_manager = config_manager
        self.thread_pool = QThreadPool()
        
        # Initialize camera instance
        self._camera = None
        self._state = CameraState.DISCONNECTED
        self._ip_address = calculate_camera_ip(serial_number)
        
        # Status monitoring timer
        self._status_timer = QTimer()
        self._status_timer.timeout.connect(self._check_status)
        self._status_timer.setInterval(5000)  # Check every 5 seconds
        
        logger.info(f"Initialized controller for {camera_id} (SN: {serial_number}, IP: {self._ip_address})")
    
    @property
    def state(self) -> CameraState:
        """Get current camera state."""
        return self._state
    
    @property
    def ip_address(self) -> str:
        """Get camera IP address."""
        return self._ip_address
    
    @property
    def is_connected(self) -> bool:
        """Check if camera is connected."""
        return self._state not in [CameraState.DISCONNECTED, CameraState.ERROR]
    
    @property
    def is_recording(self) -> bool:
        """Check if camera is recording."""
        return self._state == CameraState.RECORDING
    
    def _set_state(self, new_state: CameraState):
        """Update camera state and emit signal."""
        if self._state != new_state:
            old_state = self._state
            self._state = new_state
            logger.debug(f"Camera {self.camera_id} state: {old_state.value} -> {new_state.value}")
            self.statusChanged.emit(self.camera_id, new_state.value)
    
    def _execute_operation(self, operation: str, fn, *args, **kwargs):
        """Execute camera operation in worker thread."""
        worker = CameraOperationWorker(self.camera_id, operation, fn, *args, **kwargs)
        worker.signals.result.connect(lambda result: self._on_operation_success(operation, result))
        worker.signals.error.connect(lambda error: self._on_operation_error(operation, error))
        self.thread_pool.start(worker)
        return worker
    
    def _on_operation_success(self, operation: str, result):
        """Handle successful operation completion."""
        logger.debug(f"Operation {operation} succeeded for camera {self.camera_id}")
        
        # Update state based on operation
        if operation == "connect":
            self._set_state(CameraState.CONNECTED)
        elif operation == "start_recording":
            self._set_state(CameraState.RECORDING)
            self.recordingStarted.emit(self.camera_id)
        elif operation == "stop_recording":
            self._set_state(CameraState.READY)
            self.recordingStopped.emit(self.camera_id)
        elif operation == "webcam_start":
            self._set_state(CameraState.WEBCAM_MODE)
        elif operation == "webcam_stop":
            self._set_state(CameraState.READY)
    
    def _on_operation_error(self, operation: str, error):
        """Handle operation error."""
        exc_type, exc_value, exc_traceback = error
        error_msg = str(exc_value)
        logger.error(f"Operation {operation} failed for camera {self.camera_id}: {error_msg}")
        
        self._set_state(CameraState.ERROR)
        self.errorOccurred.emit(self.camera_id, f"{operation}: {error_msg}")
    
    def _check_status(self):
        """Periodic status check via keepAlive."""
        if self._camera and self.is_connected:
            def check_alive():
                try:
                    response = self._camera.keepAlive()
                    return response.status_code == 200
                except Exception as e:
                    logger.warning(f"Status check failed for camera {self.camera_id}: {e}")
                    return False
            
            worker = CameraOperationWorker(self.camera_id, "status_check", check_alive)
            worker.signals.result.connect(self._on_status_result)
            worker.signals.error.connect(lambda error: self._set_state(CameraState.ERROR))
            self.thread_pool.start(worker)
    
    def _on_status_result(self, is_alive: bool):
        """Handle status check result."""
        if not is_alive and self.is_connected:
            logger.warning(f"Camera {self.camera_id} appears disconnected")
            self._set_state(CameraState.DISCONNECTED)
    
    def connect(self):
        """Connect to camera and enable USB control."""
        if self._state == CameraState.CONNECTING:
            return
        
        self._set_state(CameraState.CONNECTING)
        
        def do_connect():
            self._camera = GPcam(self.serial_number)
            # Test connection with keepAlive
            response = self._camera.keepAlive()
            if response.status_code == 200:
                # Enable USB control
                self._camera.USBenable()
                return True
            else:
                raise ConnectionError(f"Failed to connect to camera at {self._ip_address}")
        
        self._execute_operation("connect", do_connect)
        self._status_timer.start()
    
    def disconnect(self):
        """Disconnect from camera."""
        self._status_timer.stop()
        
        if self._camera:
            def do_disconnect():
                self._camera.USBdisable()
                return True
            
            self._execute_operation("disconnect", do_disconnect)
            self._camera = None
        
        self._set_state(CameraState.DISCONNECTED)
    
    def start_recording(self):
        """Start video recording."""
        if not self.is_connected or self._camera is None:
            self.errorOccurred.emit(self.camera_id, "Camera not connected")
            return
        
        def do_start_recording():
            # Ensure we're in video mode
            self._camera.modeVideo()
            # Apply current settings
            self._apply_current_settings()
            # Start recording
            self._camera.shutterStart()
            return True
        
        self._execute_operation("start_recording", do_start_recording)
    
    def stop_recording(self):
        """Stop video recording."""
        if not self.is_recording or self._camera is None:
            return
        
        def do_stop_recording():
            self._camera.shutterStop()
            return True
        
        self._execute_operation("stop_recording", do_stop_recording)
    
    def start_webcam(self):
        """Start webcam mode for live preview."""
        if not self.is_connected or self._camera is None:
            self.errorOccurred.emit(self.camera_id, "Camera not connected")
            return
        
        def do_start_webcam():
            # Disable USB control for webcam mode
            self._camera.USBdisable()
            # Start webcam
            self._camera.webcamStart()
            return True
        
        self._execute_operation("webcam_start", do_start_webcam)
    
    def stop_webcam(self):
        """Stop webcam mode and return to USB control."""
        if self._state != CameraState.WEBCAM_MODE or self._camera is None:
            return
        
        def do_stop_webcam():
            # Stop webcam
            self._camera.webcamStop()
            # Re-enable USB control
            self._camera.USBenable()
            return True
        
        self._execute_operation("webcam_stop", do_stop_webcam)
    
    def download_last_media(self, output_path: str):
        """Download the last recorded media file."""
        if not self.is_connected or self._camera is None:
            self.errorOccurred.emit(self.camera_id, "Camera not connected")
            return
        
        self._set_state(CameraState.DOWNLOADING)
        
        def do_download():
            # Wait for encoding to finish
            while self._camera.encodingActive():
                pass
            
            # Download the file
            self._camera.mediaDownloadLast(output_path)
            return output_path
        
        worker = DownloadWorker(self.camera_id, do_download, output_path)
        worker.signals.result.connect(lambda path: self._on_download_complete(path))
        worker.signals.error.connect(lambda error: self._on_operation_error("download", error))
        worker.signals.progress.connect(lambda progress: self.downloadProgress.emit(self.camera_id, progress))
        self.thread_pool.start(worker)
    
    def _on_download_complete(self, file_path: str):
        """Handle download completion."""
        self._set_state(CameraState.READY)
        self.downloadFinished.emit(self.camera_id, file_path)
        logger.info(f"Download completed for camera {self.camera_id}: {file_path}")
    
    def _apply_current_settings(self):
        """Apply current configuration settings to camera."""
        config = self.config_manager.get_camera_config(self.camera_id)
        
        # Apply lens setting
        lens = config.get('lens', 'Narrow')
        if lens == 'Narrow':
            self._camera.setVideoLensesNarrow()
        elif lens == 'Wide':
            self._camera.setVideoLensesWide()
        elif lens == 'Linear':
            self._camera.setVideoLensesLinear()
        elif lens == 'Superview':
            self._camera.setVideoLensesSuperview()
        
        # Apply resolution setting
        resolution = config.get('resolution', '1080p')
        if resolution == '1080p':
            self._camera.setVideoResolution1080()
        elif resolution == '1440p':
            self._camera.setVideoResolution1440()
        elif resolution == '4K':
            self._camera.setVideoResolution4k()
        
        # Apply FPS setting
        fps = config.get('fps', 30)
        if fps == 24:
            self._camera.setFPS24()
        elif fps == 25:
            self._camera.setFPS25()
        elif fps == 30:
            self._camera.setFPS30()
        elif fps == 60:
            self._camera.setFPS60()
    
    def update_serial(self, new_serial: str):
        """Update camera serial number and reconnect."""
        if new_serial != self.serial_number:
            self.disconnect()
            self.serial_number = new_serial
            self._ip_address = calculate_camera_ip(new_serial)
            self.config_manager.set_camera_serial(self.camera_id, new_serial)
            logger.info(f"Updated serial for {self.camera_id}: {new_serial} (IP: {self._ip_address})")

class CameraManager(QObject):
    """Manages multiple camera controllers for coordinated operations."""
    
    # Signals for bulk operations
    allCamerasConnected = pyqtSignal()
    recordingStarted = pyqtSignal(list)  # list of camera_ids
    recordingStopped = pyqtSignal(list)  # list of camera_ids
    allDownloadsComplete = pyqtSignal(str)  # trial_directory
    
    def __init__(self, config_manager: ConfigManager):
        """Initialize camera manager.
        
        Args:
            config_manager: Configuration manager instance
        """
        super().__init__()
        self.config_manager = config_manager
        self.controllers: Dict[str, GPcamController] = {}
        
        # Initialize controllers for all configured cameras
        self._initialize_controllers()
    
    def _initialize_controllers(self):
        """Initialize camera controllers from configuration."""
        camera_configs = self.config_manager.get('cameras', {})
        
        for camera_id, config in camera_configs.items():
            serial = config.get('serial', '')
            if serial:
                controller = GPcamController(camera_id, serial, self.config_manager)
                self.controllers[camera_id] = controller
                logger.info(f"Initialized controller for {camera_id}")
    
    def get_controller(self, camera_id: str) -> Optional[GPcamController]:
        """Get controller for specific camera."""
        return self.controllers.get(camera_id)
    
    def get_connected_cameras(self) -> List[str]:
        """Get list of connected camera IDs."""
        return [cid for cid, controller in self.controllers.items() if controller.is_connected]
    
    def connect_all(self):
        """Connect to all configured cameras."""
        for controller in self.controllers.values():
            controller.connect()
    
    def disconnect_all(self):
        """Disconnect from all cameras."""
        for controller in self.controllers.values():
            controller.disconnect()
    
    def start_recording(self, camera_ids: Optional[List[str]] = None):
        """Start recording on specified cameras.
        
        Args:
            camera_ids: List of camera IDs to record. If None, use all connected cameras.
        """
        if camera_ids is None:
            camera_ids = self.get_connected_cameras()
        
        recording_cameras = []
        for camera_id in camera_ids:
            controller = self.controllers.get(camera_id)
            if controller and controller.is_connected:
                controller.start_recording()
                recording_cameras.append(camera_id)
        
        if recording_cameras:
            self.recordingStarted.emit(recording_cameras)
    
    def stop_recording(self, camera_ids: Optional[List[str]] = None):
        """Stop recording on specified cameras.
        
        Args:
            camera_ids: List of camera IDs to stop. If None, use all recording cameras.
        """
        if camera_ids is None:
            camera_ids = [cid for cid, controller in self.controllers.items() if controller.is_recording]
        
        stopped_cameras = []
        for camera_id in camera_ids:
            controller = self.controllers.get(camera_id)
            if controller and controller.is_recording:
                controller.stop_recording()
                stopped_cameras.append(camera_id)
        
        if stopped_cameras:
            self.recordingStopped.emit(stopped_cameras)
    
    def download_all_media(self, trial_directory: Path, trial_name: str, camera_ids: Optional[List[str]] = None):
        """Download media from all specified cameras.
        
        Args:
            trial_directory: Directory to save files
            trial_name: Base name for trial files
            camera_ids: List of camera IDs to download from. If None, use all connected cameras.
        """
        if camera_ids is None:
            camera_ids = self.get_connected_cameras()
        
        trial_directory.mkdir(parents=True, exist_ok=True)
        
        for camera_id in camera_ids:
            controller = self.controllers.get(camera_id)
            if controller and controller.is_connected:
                output_path = trial_directory / f"{trial_name}_{camera_id}.mp4"
                controller.download_last_media(str(output_path))
