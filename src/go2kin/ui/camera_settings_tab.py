"""
Camera settings tab for Go2Kin application.

Provides interface for connecting and configuring up to 4 GoPro cameras
with individual control panels for each camera.
"""

import logging
from typing import Dict, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QPushButton, QComboBox, QLineEdit, QInputDialog,
    QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QPixmap, QPainter, QColor

from ..config import ConfigManager
from ..gopro import CameraManager, GPcamController
from ..gopro.multi_camera_controller import CameraState

logger = logging.getLogger(__name__)

class StatusIndicator(QLabel):
    """Visual status indicator for camera connection state."""
    
    def __init__(self, size: int = 16):
        """Initialize status indicator.
        
        Args:
            size: Size of the indicator in pixels
        """
        super().__init__()
        self.size = size
        self.setFixedSize(size, size)
        self.set_status("disconnected")
    
    def set_status(self, status: str):
        """Update status indicator color.
        
        Args:
            status: Camera status string
        """
        # Create colored pixmap
        pixmap = QPixmap(self.size, self.size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Choose color based on status
        if status == "connected" or status == "ready":
            color = QColor(0, 255, 0)  # Green
        elif status == "connecting":
            color = QColor(255, 255, 0)  # Yellow
        elif status == "recording":
            color = QColor(255, 0, 0)  # Red
        elif status == "downloading":
            color = QColor(0, 0, 255)  # Blue
        elif status == "webcam":
            color = QColor(255, 165, 0)  # Orange
        elif status == "error":
            color = QColor(128, 0, 128)  # Purple
        else:  # disconnected
            color = QColor(128, 128, 128)  # Gray
        
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, self.size - 4, self.size - 4)
        painter.end()
        
        self.setPixmap(pixmap)
        self.setToolTip(f"Status: {status}")

class CameraPanel(QGroupBox):
    """Individual camera control panel."""
    
    def __init__(self, camera_id: str, controller: GPcamController, config_manager: ConfigManager):
        """Initialize camera panel.
        
        Args:
            camera_id: Camera identifier (e.g., 'GP1')
            controller: Camera controller instance
            config_manager: Configuration manager
        """
        super().__init__(f"Camera {camera_id}")
        self.camera_id = camera_id
        self.controller = controller
        self.config_manager = config_manager
        
        self._setup_ui()
        self._connect_signals()
        self._load_settings()
        
        logger.debug(f"Initialized panel for camera {camera_id}")
    
    def _setup_ui(self):
        """Setup panel user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        
        # Status and connection section
        status_layout = QHBoxLayout()
        
        # Status indicator
        self.status_indicator = StatusIndicator()
        status_layout.addWidget(self.status_indicator)
        
        # Status label
        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        
        # Connect/Disconnect buttons
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self._on_connect_clicked)
        status_layout.addWidget(self.connect_button)
        
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self._on_disconnect_clicked)
        self.disconnect_button.setEnabled(False)
        status_layout.addWidget(self.disconnect_button)
        
        layout.addLayout(status_layout)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)
        
        # Camera information section
        info_layout = QGridLayout()
        
        # Serial number
        info_layout.addWidget(QLabel("Serial Number:"), 0, 0)
        self.serial_label = QLabel(self.controller.serial_number)
        self.serial_label.setStyleSheet("font-family: monospace;")
        info_layout.addWidget(self.serial_label, 0, 1)
        
        self.edit_serial_button = QPushButton("Edit...")
        self.edit_serial_button.clicked.connect(self._on_edit_serial_clicked)
        info_layout.addWidget(self.edit_serial_button, 0, 2)
        
        # IP address
        info_layout.addWidget(QLabel("IP Address:"), 1, 0)
        self.ip_label = QLabel(self.controller.ip_address)
        self.ip_label.setStyleSheet("font-family: monospace;")
        info_layout.addWidget(self.ip_label, 1, 1, 1, 2)
        
        layout.addLayout(info_layout)
        
        # Settings section
        settings_layout = QGridLayout()
        
        # Lens setting
        settings_layout.addWidget(QLabel("Lens:"), 0, 0)
        self.lens_combo = QComboBox()
        self.lens_combo.addItems(["Narrow", "Wide", "Linear", "Superview"])
        self.lens_combo.currentTextChanged.connect(self._on_lens_changed)
        settings_layout.addWidget(self.lens_combo, 0, 1)
        
        # Resolution setting
        settings_layout.addWidget(QLabel("Resolution:"), 1, 0)
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["1080p", "1440p", "4K"])
        self.resolution_combo.currentTextChanged.connect(self._on_resolution_changed)
        settings_layout.addWidget(self.resolution_combo, 1, 1)
        
        # FPS setting
        settings_layout.addWidget(QLabel("FPS:"), 2, 0)
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["24", "25", "30", "60"])
        self.fps_combo.currentTextChanged.connect(self._on_fps_changed)
        settings_layout.addWidget(self.fps_combo, 2, 1)
        
        layout.addLayout(settings_layout)
        
        # Stretch to fill remaining space
        layout.addStretch()
    
    def _connect_signals(self):
        """Connect controller signals to panel updates."""
        self.controller.statusChanged.connect(self._on_status_changed)
        self.controller.errorOccurred.connect(self._on_error_occurred)
    
    def _load_settings(self):
        """Load settings from configuration."""
        config = self.config_manager.get_camera_config(self.camera_id)
        
        # Set combo box values
        lens = config.get('lens', 'Narrow')
        if lens in [self.lens_combo.itemText(i) for i in range(self.lens_combo.count())]:
            self.lens_combo.setCurrentText(lens)
        
        resolution = config.get('resolution', '1080p')
        if resolution in [self.resolution_combo.itemText(i) for i in range(self.resolution_combo.count())]:
            self.resolution_combo.setCurrentText(resolution)
        
        fps = str(config.get('fps', 30))
        if fps in [self.fps_combo.itemText(i) for i in range(self.fps_combo.count())]:
            self.fps_combo.setCurrentText(fps)
    
    @pyqtSlot(str, str)
    def _on_status_changed(self, camera_id: str, status: str):
        """Handle camera status change."""
        if camera_id != self.camera_id:
            return
        
        # Update status indicator and label
        self.status_indicator.set_status(status)
        self.status_label.setText(status.title())
        
        # Update button states
        is_connected = status not in ["disconnected", "error"]
        self.connect_button.setEnabled(not is_connected)
        self.disconnect_button.setEnabled(is_connected)
        
        # Disable settings during certain operations
        settings_enabled = status in ["connected", "ready"]
        self.lens_combo.setEnabled(settings_enabled)
        self.resolution_combo.setEnabled(settings_enabled)
        self.fps_combo.setEnabled(settings_enabled)
        
        logger.debug(f"Camera {camera_id} status updated: {status}")
    
    @pyqtSlot(str, str)
    def _on_error_occurred(self, camera_id: str, error_message: str):
        """Handle camera error."""
        if camera_id != self.camera_id:
            return
        
        QMessageBox.warning(
            self,
            f"Camera {camera_id} Error",
            f"An error occurred with camera {camera_id}:\n\n{error_message}"
        )
        
        logger.error(f"Camera {camera_id} error: {error_message}")
    
    def _on_connect_clicked(self):
        """Handle connect button click."""
        self.controller.connect()
        logger.info(f"Connect requested for camera {self.camera_id}")
    
    def _on_disconnect_clicked(self):
        """Handle disconnect button click."""
        self.controller.disconnect()
        logger.info(f"Disconnect requested for camera {self.camera_id}")
    
    def _on_edit_serial_clicked(self):
        """Handle edit serial number button click."""
        current_serial = self.controller.serial_number
        
        new_serial, ok = QInputDialog.getText(
            self,
            f"Edit Serial Number - Camera {self.camera_id}",
            "Enter new serial number:",
            QLineEdit.EchoMode.Normal,
            current_serial
        )
        
        if ok and new_serial and new_serial != current_serial:
            # Validate serial number format (basic check)
            if len(new_serial) < 10:
                QMessageBox.warning(
                    self,
                    "Invalid Serial Number",
                    "Serial number appears to be too short.\n\n"
                    "Please enter a valid GoPro serial number."
                )
                return
            
            # Update controller and UI
            self.controller.update_serial(new_serial)
            self.serial_label.setText(new_serial)
            self.ip_label.setText(self.controller.ip_address)
            
            logger.info(f"Serial number updated for camera {self.camera_id}: {new_serial}")
    
    def _on_lens_changed(self, lens: str):
        """Handle lens setting change."""
        self.config_manager.set(f'cameras.{self.camera_id}.lens', lens)
        logger.debug(f"Camera {self.camera_id} lens set to: {lens}")
    
    def _on_resolution_changed(self, resolution: str):
        """Handle resolution setting change."""
        self.config_manager.set(f'cameras.{self.camera_id}.resolution', resolution)
        logger.debug(f"Camera {self.camera_id} resolution set to: {resolution}")
    
    def _on_fps_changed(self, fps: str):
        """Handle FPS setting change."""
        try:
            fps_value = int(fps)
            self.config_manager.set(f'cameras.{self.camera_id}.fps', fps_value)
            logger.debug(f"Camera {self.camera_id} FPS set to: {fps_value}")
        except ValueError:
            logger.error(f"Invalid FPS value: {fps}")

class CameraSettingsTab(QWidget):
    """Camera settings tab with 4-camera grid layout."""
    
    def __init__(self, camera_manager: CameraManager, config_manager: ConfigManager):
        """Initialize camera settings tab.
        
        Args:
            camera_manager: Camera manager instance
            config_manager: Configuration manager instance
        """
        super().__init__()
        self.camera_manager = camera_manager
        self.config_manager = config_manager
        self.camera_panels: Dict[str, CameraPanel] = {}
        
        self._setup_ui()
        logger.info("Camera settings tab initialized")
    
    def _setup_ui(self):
        """Setup tab user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Title and controls
        header_layout = QHBoxLayout()
        
        title_label = QLabel("Camera Configuration")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Global connect/disconnect buttons
        self.connect_all_button = QPushButton("Connect All")
        self.connect_all_button.clicked.connect(self.camera_manager.connect_all)
        header_layout.addWidget(self.connect_all_button)
        
        self.disconnect_all_button = QPushButton("Disconnect All")
        self.disconnect_all_button.clicked.connect(self.camera_manager.disconnect_all)
        header_layout.addWidget(self.disconnect_all_button)
        
        layout.addLayout(header_layout)
        
        # Camera panels in 2x2 grid
        grid_layout = QGridLayout()
        grid_layout.setSpacing(15)
        
        # Create panels for each camera
        camera_ids = ["GP1", "GP2", "GP3", "GP4"]
        positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
        
        for camera_id, (row, col) in zip(camera_ids, positions):
            controller = self.camera_manager.get_controller(camera_id)
            if controller:
                panel = CameraPanel(camera_id, controller, self.config_manager)
                self.camera_panels[camera_id] = panel
                grid_layout.addWidget(panel, row, col)
            else:
                # Create placeholder for missing controller
                placeholder = QGroupBox(f"Camera {camera_id}")
                placeholder_layout = QVBoxLayout(placeholder)
                placeholder_layout.addWidget(QLabel("Controller not available"))
                grid_layout.addWidget(placeholder, row, col)
        
        layout.addLayout(grid_layout)
        
        # Add stretch to push everything to top
        layout.addStretch()
    
    def get_panel(self, camera_id: str) -> Optional[CameraPanel]:
        """Get camera panel by ID.
        
        Args:
            camera_id: Camera identifier
            
        Returns:
            Camera panel or None if not found
        """
        return self.camera_panels.get(camera_id)
