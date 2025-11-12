"""
Live preview tab for Go2Kin application.

Provides interface for viewing live camera feeds in webcam mode.
"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QLabel, QMessageBox
)
from PyQt6.QtCore import Qt

from ..config import ConfigManager
from ..gopro import CameraManager

logger = logging.getLogger(__name__)

class LivePreviewTab(QWidget):
    """Live preview tab with camera selection and stream display."""
    
    def __init__(self, camera_manager: CameraManager, config_manager: ConfigManager):
        """Initialize live preview tab.
        
        Args:
            camera_manager: Camera manager instance
            config_manager: Configuration manager instance
        """
        super().__init__()
        self.camera_manager = camera_manager
        self.config_manager = config_manager
        self.current_camera = None
        
        self._setup_ui()
        logger.info("Live preview tab initialized")
    
    def _setup_ui(self):
        """Setup tab user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Title
        title_label = QLabel("Live Camera Preview")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # Controls
        controls_layout = QHBoxLayout()
        
        # Camera selector
        controls_layout.addWidget(QLabel("Camera:"))
        self.camera_combo = QComboBox()
        self.camera_combo.addItems(["GP1", "GP2", "GP3", "GP4"])
        self.camera_combo.currentTextChanged.connect(self._on_camera_changed)
        controls_layout.addWidget(self.camera_combo)
        
        controls_layout.addStretch()
        
        # Start/Stop buttons
        self.start_button = QPushButton("Start Preview")
        self.start_button.clicked.connect(self._on_start_preview)
        controls_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("Stop Preview")
        self.stop_button.clicked.connect(self._on_stop_preview)
        self.stop_button.setEnabled(False)
        controls_layout.addWidget(self.stop_button)
        
        layout.addLayout(controls_layout)
        
        # Preview area placeholder
        preview_label = QLabel("Live preview will be implemented in Phase 3")
        preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_label.setStyleSheet(
            "border: 2px dashed #ccc; "
            "background-color: #f9f9f9; "
            "color: #666; "
            "font-size: 14px; "
            "padding: 50px;"
        )
        preview_label.setMinimumHeight(400)
        layout.addWidget(preview_label)
        
        # Status
        self.status_label = QLabel("Select a camera and click Start Preview")
        self.status_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.status_label)
    
    def _on_camera_changed(self, camera_id: str):
        """Handle camera selection change."""
        self.current_camera = camera_id
        self.config_manager.set('ui.last_preview_camera', camera_id)
        logger.debug(f"Preview camera changed to: {camera_id}")
    
    def _on_start_preview(self):
        """Handle start preview button click."""
        if not self.current_camera:
            return
        
        controller = self.camera_manager.get_controller(self.current_camera)
        if not controller or not controller.is_connected:
            QMessageBox.warning(
                self,
                "Camera Not Connected",
                f"Camera {self.current_camera} is not connected.\n\n"
                "Please connect the camera first in the Camera Settings tab."
            )
            return
        
        # Start webcam mode
        controller.start_webcam()
        
        # Update UI
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText(f"Starting preview for camera {self.current_camera}...")
        
        logger.info(f"Preview started for camera {self.current_camera}")
    
    def _on_stop_preview(self):
        """Handle stop preview button click."""
        if not self.current_camera:
            return
        
        controller = self.camera_manager.get_controller(self.current_camera)
        if controller:
            controller.stop_webcam()
        
        # Update UI
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText("Preview stopped")
        
        logger.info(f"Preview stopped for camera {self.current_camera}")
    
    def on_tab_activated(self):
        """Called when tab becomes active."""
        # Restore last selected camera
        last_camera = self.config_manager.get('ui.last_preview_camera', 'GP1')
        if last_camera in [self.camera_combo.itemText(i) for i in range(self.camera_combo.count())]:
            self.camera_combo.setCurrentText(last_camera)
            self.current_camera = last_camera
        
        logger.debug("Live preview tab activated")
