"""
Main application window for Go2Kin.

Provides the primary GUI interface with tabbed layout for camera settings,
live preview, and recording functionality.
"""

import sys
import logging
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QVBoxLayout, QWidget, 
    QStatusBar, QMenuBar, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QIcon

from ..config import ConfigManager
from ..gopro import CameraManager
from .camera_settings_tab import CameraSettingsTab
from .live_preview_tab import LivePreviewTab
from .recording_tab import RecordingTab

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    """Main application window with tabbed interface."""
    
    def __init__(self):
        """Initialize main window."""
        super().__init__()
        
        # Initialize configuration and camera management
        self.config_manager = ConfigManager()
        self.camera_manager = CameraManager(self.config_manager)
        
        # Setup UI
        self._setup_ui()
        self._setup_menu_bar()
        self._setup_status_bar()
        self._connect_signals()
        
        # Restore window geometry
        self._restore_geometry()
        
        logger.info("Main window initialized")
    
    def _setup_ui(self):
        """Setup the main user interface."""
        self.setWindowTitle("Go2Kin - Multi-Camera GoPro Control")
        self.setMinimumSize(1000, 700)
        
        # Create central widget with tab layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Create tabs
        self.settings_tab = CameraSettingsTab(self.camera_manager, self.config_manager)
        self.preview_tab = LivePreviewTab(self.camera_manager, self.config_manager)
        self.recording_tab = RecordingTab(self.camera_manager, self.config_manager)
        
        # Add tabs to widget
        self.tab_widget.addTab(self.settings_tab, "Camera Settings")
        self.tab_widget.addTab(self.preview_tab, "Live Preview")
        self.tab_widget.addTab(self.recording_tab, "Recording")
        
        # Set initial tab
        self.tab_widget.setCurrentIndex(0)
    
    def _setup_menu_bar(self):
        """Setup application menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        # Connect all cameras action
        connect_action = QAction("&Connect All Cameras", self)
        connect_action.setShortcut("Ctrl+C")
        connect_action.setStatusTip("Connect to all configured cameras")
        connect_action.triggered.connect(self.camera_manager.connect_all)
        file_menu.addAction(connect_action)
        
        # Disconnect all cameras action
        disconnect_action = QAction("&Disconnect All Cameras", self)
        disconnect_action.setShortcut("Ctrl+D")
        disconnect_action.setStatusTip("Disconnect from all cameras")
        disconnect_action.triggered.connect(self.camera_manager.disconnect_all)
        file_menu.addAction(disconnect_action)
        
        file_menu.addSeparator()
        
        # Exit action
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setStatusTip("Exit application")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Settings menu
        settings_menu = menubar.addMenu("&Settings")
        
        # Reset configuration action
        reset_config_action = QAction("&Reset Configuration", self)
        reset_config_action.setStatusTip("Reset all settings to defaults")
        reset_config_action.triggered.connect(self._reset_configuration)
        settings_menu.addAction(reset_config_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        # About action
        about_action = QAction("&About", self)
        about_action.setStatusTip("About Go2Kin")
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _setup_status_bar(self):
        """Setup application status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Show ready message
        self.status_bar.showMessage("Ready - Connect cameras to begin", 5000)
        
        # Setup status update timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(2000)  # Update every 2 seconds
    
    def _connect_signals(self):
        """Connect signals between components."""
        # Tab change handling
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        
        # Camera manager signals
        self.camera_manager.recordingStarted.connect(self._on_recording_started)
        self.camera_manager.recordingStopped.connect(self._on_recording_stopped)
        self.camera_manager.allDownloadsComplete.connect(self._on_downloads_complete)
    
    def _restore_geometry(self):
        """Restore window geometry from configuration."""
        geometry = self.config_manager.get('ui.window_geometry')
        if geometry:
            try:
                self.restoreGeometry(geometry)
            except Exception as e:
                logger.warning(f"Failed to restore window geometry: {e}")
    
    def _save_geometry(self):
        """Save current window geometry to configuration."""
        geometry = self.saveGeometry()
        self.config_manager.set('ui.window_geometry', geometry, save=True)
    
    def _update_status(self):
        """Update status bar with current camera information."""
        connected_cameras = self.camera_manager.get_connected_cameras()
        total_cameras = len(self.camera_manager.controllers)
        
        if not connected_cameras:
            self.status_bar.showMessage("No cameras connected")
        elif len(connected_cameras) == total_cameras:
            self.status_bar.showMessage(f"All {total_cameras} cameras connected")
        else:
            self.status_bar.showMessage(f"{len(connected_cameras)}/{total_cameras} cameras connected")
    
    def _on_tab_changed(self, index: int):
        """Handle tab change events."""
        tab_names = ["Camera Settings", "Live Preview", "Recording"]
        if 0 <= index < len(tab_names):
            logger.debug(f"Switched to {tab_names[index]} tab")
            
            # Handle tab-specific logic
            if index == 1:  # Live Preview tab
                self.preview_tab.on_tab_activated()
            elif index == 2:  # Recording tab
                self.recording_tab.on_tab_activated()
    
    def _on_recording_started(self, camera_ids: list):
        """Handle recording started event."""
        camera_list = ", ".join(camera_ids)
        self.status_bar.showMessage(f"Recording started on: {camera_list}")
        logger.info(f"Recording started on cameras: {camera_ids}")
    
    def _on_recording_stopped(self, camera_ids: list):
        """Handle recording stopped event."""
        camera_list = ", ".join(camera_ids)
        self.status_bar.showMessage(f"Recording stopped on: {camera_list}")
        logger.info(f"Recording stopped on cameras: {camera_ids}")
    
    def _on_downloads_complete(self, trial_directory: str):
        """Handle all downloads complete event."""
        self.status_bar.showMessage(f"Downloads complete: {trial_directory}")
        logger.info(f"All downloads completed to: {trial_directory}")
    
    def _reset_configuration(self):
        """Reset configuration to defaults after confirmation."""
        reply = QMessageBox.question(
            self, 
            "Reset Configuration",
            "Are you sure you want to reset all settings to defaults?\n\n"
            "This will disconnect all cameras and restore default settings.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Disconnect all cameras first
            self.camera_manager.disconnect_all()
            
            # Reset configuration
            self.config_manager.reset_to_defaults()
            
            # Show confirmation
            QMessageBox.information(
                self,
                "Configuration Reset",
                "Configuration has been reset to defaults.\n\n"
                "Please restart the application for changes to take full effect."
            )
            
            logger.info("Configuration reset to defaults")
    
    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About Go2Kin",
            "<h3>Go2Kin v0.1.0</h3>"
            "<p>Biomechanics Markerless Motion Capture Pipeline</p>"
            "<p>Stage 1: Multi-camera GoPro control via USB</p>"
            "<br>"
            "<p>Designed for academic research and lab environments.</p>"
            "<p>Built with PyQt6 and the goproUSB library.</p>"
        )
    
    def closeEvent(self, event):
        """Handle application close event."""
        # Save window geometry
        self._save_geometry()
        
        # Disconnect all cameras
        self.camera_manager.disconnect_all()
        
        # Save configuration
        self.config_manager.save()
        
        logger.info("Application closing")
        event.accept()

def main():
    """Main application entry point."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("Go2Kin")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("Go2Kin Development Team")
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    # Run application
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
