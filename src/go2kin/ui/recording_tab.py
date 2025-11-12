"""
Recording tab for Go2Kin application.

Provides interface for synchronized multi-camera recording with trial management.
"""

import logging
from pathlib import Path
from typing import List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QPushButton, QLineEdit, QCheckBox, QFileDialog,
    QProgressBar, QListWidget, QListWidgetItem, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSlot

from ..config import ConfigManager
from ..gopro import CameraManager

logger = logging.getLogger(__name__)

class RecordingTab(QWidget):
    """Recording tab with trial management and multi-camera recording."""
    
    def __init__(self, camera_manager: CameraManager, config_manager: ConfigManager):
        """Initialize recording tab.
        
        Args:
            camera_manager: Camera manager instance
            config_manager: Configuration manager instance
        """
        super().__init__()
        self.camera_manager = camera_manager
        self.config_manager = config_manager
        self.is_recording = False
        self.selected_cameras = []
        
        self._setup_ui()
        self._connect_signals()
        self._load_settings()
        logger.info("Recording tab initialized")
    
    def _setup_ui(self):
        """Setup tab user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # Title
        title_label = QLabel("Multi-Camera Recording")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # Main content in grid
        main_layout = QGridLayout()
        main_layout.setSpacing(15)
        
        # Left column - Settings
        settings_group = QGroupBox("Recording Settings")
        settings_layout = QVBoxLayout(settings_group)
        
        # Output directory
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Output Directory:"))
        self.directory_edit = QLineEdit()
        self.directory_edit.setReadOnly(True)
        dir_layout.addWidget(self.directory_edit)
        
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._on_browse_directory)
        dir_layout.addWidget(self.browse_button)
        
        settings_layout.addLayout(dir_layout)
        
        # Trial name
        trial_layout = QHBoxLayout()
        trial_layout.addWidget(QLabel("Trial Name:"))
        self.trial_edit = QLineEdit()
        self.trial_edit.setPlaceholderText("Enter trial name or leave blank for auto-naming")
        trial_layout.addWidget(self.trial_edit)
        settings_layout.addLayout(trial_layout)
        
        # Camera selection
        camera_group = QGroupBox("Camera Selection")
        camera_layout = QGridLayout(camera_group)
        
        self.camera_checkboxes = {}
        camera_ids = ["GP1", "GP2", "GP3", "GP4"]
        positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
        
        for camera_id, (row, col) in zip(camera_ids, positions):
            checkbox = QCheckBox(f"Camera {camera_id}")
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(lambda state, cid=camera_id: self._on_camera_selection_changed(cid, state))
            self.camera_checkboxes[camera_id] = checkbox
            camera_layout.addWidget(checkbox, row, col)
        
        settings_layout.addWidget(camera_group)
        
        # Recording controls
        controls_layout = QHBoxLayout()
        
        self.start_button = QPushButton("Start Recording")
        self.start_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; padding: 10px; }")
        self.start_button.clicked.connect(self._on_start_recording)
        controls_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("Stop Recording")
        self.stop_button.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-weight: bold; padding: 10px; }")
        self.stop_button.clicked.connect(self._on_stop_recording)
        self.stop_button.setEnabled(False)
        controls_layout.addWidget(self.stop_button)
        
        settings_layout.addLayout(controls_layout)
        
        # Recording status
        self.status_label = QLabel("Ready to record")
        self.status_label.setStyleSheet("color: #666; font-style: italic; padding: 10px;")
        settings_layout.addWidget(self.status_label)
        
        main_layout.addWidget(settings_group, 0, 0)
        
        # Right column - Progress and files
        progress_group = QGroupBox("Recording Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        # Progress bars for each camera
        self.progress_bars = {}
        for camera_id in camera_ids:
            camera_progress_layout = QHBoxLayout()
            camera_progress_layout.addWidget(QLabel(f"{camera_id}:"))
            
            progress_bar = QProgressBar()
            progress_bar.setVisible(False)
            self.progress_bars[camera_id] = progress_bar
            camera_progress_layout.addWidget(progress_bar)
            
            progress_layout.addLayout(camera_progress_layout)
        
        # File list
        progress_layout.addWidget(QLabel("Recorded Files:"))
        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(200)
        progress_layout.addWidget(self.file_list)
        
        # Open folder button
        self.open_folder_button = QPushButton("Open Output Folder")
        self.open_folder_button.clicked.connect(self._on_open_folder)
        progress_layout.addWidget(self.open_folder_button)
        
        main_layout.addWidget(progress_group, 0, 1)
        
        layout.addLayout(main_layout)
        
        # Add stretch to push everything to top
        layout.addStretch()
    
    def _connect_signals(self):
        """Connect camera manager signals."""
        self.camera_manager.recordingStarted.connect(self._on_recording_started)
        self.camera_manager.recordingStopped.connect(self._on_recording_stopped)
        self.camera_manager.allDownloadsComplete.connect(self._on_downloads_complete)
        
        # Connect individual camera signals for progress tracking
        for camera_id, controller in self.camera_manager.controllers.items():
            controller.downloadProgress.connect(self._on_download_progress)
            controller.downloadFinished.connect(self._on_download_finished)
            # Connect to status changes for real-time UI updates
            controller.statusChanged.connect(self._on_camera_status_changed)
    
    def _load_settings(self):
        """Load settings from configuration."""
        # Load output directory
        output_dir = self.config_manager.get_output_directory()
        self.directory_edit.setText(str(output_dir))
        
        # Load selected cameras
        selected = self.config_manager.get_selected_cameras()
        for camera_id, checkbox in self.camera_checkboxes.items():
            checkbox.setChecked(camera_id in selected)
        
        self._update_selected_cameras()
    
    def _update_selected_cameras(self):
        """Update selected cameras list."""
        self.selected_cameras = [
            camera_id for camera_id, checkbox in self.camera_checkboxes.items()
            if checkbox.isChecked()
        ]
        self.config_manager.set_selected_cameras(self.selected_cameras)
    
    def _on_camera_selection_changed(self, camera_id: str, state: int):
        """Handle camera selection change."""
        self._update_selected_cameras()
        logger.debug(f"Camera selection changed: {self.selected_cameras}")
    
    def _on_browse_directory(self):
        """Handle browse directory button click."""
        current_dir = self.directory_edit.text()
        new_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            current_dir
        )
        
        if new_dir:
            self.directory_edit.setText(new_dir)
            self.config_manager.set_output_directory(Path(new_dir))
            logger.info(f"Output directory changed to: {new_dir}")
    
    def _on_start_recording(self):
        """Handle start recording button click."""
        if not self.selected_cameras:
            QMessageBox.warning(
                self,
                "No Cameras Selected",
                "Please select at least one camera for recording."
            )
            return
        
        # Filter to only connected cameras from selection
        connected_cameras = self.camera_manager.get_connected_cameras()
        recording_cameras = [cam for cam in self.selected_cameras if cam in connected_cameras]
        
        if not recording_cameras:
            QMessageBox.warning(
                self,
                "No Connected Cameras",
                "None of the selected cameras are currently connected.\n\n"
                "Please connect at least one camera before recording."
            )
            return
        
        # Start recording with available cameras
        self.camera_manager.start_recording(recording_cameras)
        
        # Update UI
        self.is_recording = True
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText(f"Recording on {len(recording_cameras)} cameras...")
        
        # Disable settings during recording
        for checkbox in self.camera_checkboxes.values():
            checkbox.setEnabled(False)
        
        logger.info(f"Recording started on cameras: {recording_cameras}")
    
    def _on_stop_recording(self):
        """Handle stop recording button click."""
        # Stop recording
        self.camera_manager.stop_recording(self.selected_cameras)
        
        # Update UI
        self.is_recording = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText("Stopping recording and downloading files...")
        
        # Re-enable settings based on connection status
        self._update_all_camera_states()
        
        # Show progress bars
        for camera_id in self.selected_cameras:
            if camera_id in self.progress_bars:
                self.progress_bars[camera_id].setVisible(True)
                self.progress_bars[camera_id].setValue(0)
        
        # Start download process
        self._start_download()
        
        logger.info(f"Recording stopped on cameras: {self.selected_cameras}")
    
    def _start_download(self):
        """Start downloading files from cameras."""
        # Generate trial name and directory
        trial_name = self.trial_edit.text().strip()
        if not trial_name:
            trial_number = self.config_manager.get_next_trial_number()
            trial_name = f"trial_{trial_number:03d}"
        
        output_dir = Path(self.directory_edit.text())
        trial_dir = output_dir / trial_name
        
        # Download files
        self.camera_manager.download_all_media(trial_dir, trial_name, self.selected_cameras)
        
        logger.info(f"Download started to: {trial_dir}")
    
    @pyqtSlot(list)
    def _on_recording_started(self, camera_ids: List[str]):
        """Handle recording started signal."""
        self.status_label.setText(f"Recording on {len(camera_ids)} cameras...")
    
    @pyqtSlot(list)
    def _on_recording_stopped(self, camera_ids: List[str]):
        """Handle recording stopped signal."""
        self.status_label.setText("Recording stopped, downloading files...")
    
    @pyqtSlot(str, int)
    def _on_download_progress(self, camera_id: str, progress: int):
        """Handle download progress update."""
        if camera_id in self.progress_bars:
            self.progress_bars[camera_id].setValue(progress)
    
    @pyqtSlot(str, str)
    def _on_download_finished(self, camera_id: str, file_path: str):
        """Handle download finished for individual camera."""
        if camera_id in self.progress_bars:
            self.progress_bars[camera_id].setValue(100)
        
        # Add file to list
        file_name = Path(file_path).name
        item = QListWidgetItem(f"{camera_id}: {file_name}")
        self.file_list.addItem(item)
        
        logger.info(f"Download completed for {camera_id}: {file_path}")
    
    @pyqtSlot(str)
    def _on_downloads_complete(self, trial_directory: str):
        """Handle all downloads complete."""
        self.status_label.setText(f"Recording complete! Files saved to: {Path(trial_directory).name}")
        
        # Hide progress bars
        for progress_bar in self.progress_bars.values():
            progress_bar.setVisible(False)
        
        # Clear trial name for next recording
        self.trial_edit.clear()
        
        logger.info(f"All downloads completed: {trial_directory}")
    
    def _on_open_folder(self):
        """Handle open folder button click."""
        output_dir = self.directory_edit.text()
        if output_dir and Path(output_dir).exists():
            import subprocess
            import sys
            
            if sys.platform == "win32":
                subprocess.run(["explorer", output_dir])
            elif sys.platform == "darwin":
                subprocess.run(["open", output_dir])
            else:
                subprocess.run(["xdg-open", output_dir])
        else:
            QMessageBox.warning(
                self,
                "Directory Not Found",
                f"Output directory does not exist:\n{output_dir}"
            )
    
    @pyqtSlot(str, str)
    def _on_camera_status_changed(self, camera_id: str, status: str):
        """Handle camera status change for real-time UI updates."""
        if camera_id in self.camera_checkboxes:
            self._update_camera_checkbox_state(camera_id, status)
    
    def _update_camera_checkbox_state(self, camera_id: str, status: str):
        """Update individual camera checkbox based on connection status."""
        if camera_id not in self.camera_checkboxes:
            return
        
        checkbox = self.camera_checkboxes[camera_id]
        is_connected = status not in ["disconnected", "error"]
        
        # Enable/disable checkbox based on connection and recording state
        checkbox.setEnabled(is_connected and not self.is_recording)
        
        # Update checkbox text to show connection status
        if is_connected:
            checkbox.setText(f"Camera {camera_id}")
        else:
            checkbox.setText(f"Camera {camera_id} (disconnected)")
            # Auto-uncheck disconnected cameras
            if checkbox.isChecked():
                checkbox.setChecked(False)
    
    def _update_all_camera_states(self):
        """Update all camera checkbox states based on current connections."""
        connected_cameras = self.camera_manager.get_connected_cameras()
        
        for camera_id, checkbox in self.camera_checkboxes.items():
            is_connected = camera_id in connected_cameras
            
            # Enable/disable checkbox based on connection and recording state
            checkbox.setEnabled(is_connected and not self.is_recording)
            
            # Update checkbox text to show connection status
            if is_connected:
                checkbox.setText(f"Camera {camera_id}")
            else:
                checkbox.setText(f"Camera {camera_id} (disconnected)")
                # Auto-uncheck disconnected cameras
                if checkbox.isChecked():
                    checkbox.setChecked(False)
    
    def on_tab_activated(self):
        """Called when tab becomes active."""
        # Update all camera availability states
        self._update_all_camera_states()
        logger.debug("Recording tab activated")
