"""
QRunnable worker classes for camera operations.

Provides thread-safe execution of camera HTTP requests without blocking the UI.
"""

import sys
import traceback
from typing import Any, Callable, Optional
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal
import logging

logger = logging.getLogger(__name__)

class WorkerSignals(QObject):
    """Signals for worker thread communication."""
    
    finished = pyqtSignal()
    error = pyqtSignal(tuple)  # (exception_type, value, traceback)
    result = pyqtSignal(object)
    progress = pyqtSignal(int)

class CameraWorker(QRunnable):
    """Generic worker for executing camera operations in background thread."""
    
    def __init__(self, fn: Callable, *args, **kwargs):
        """Initialize worker.
        
        Args:
            fn: Function to execute
            *args: Arguments for function
            **kwargs: Keyword arguments for function
        """
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        
        # Only add progress callback if the function signature supports it
        # This prevents errors when calling functions that don't expect this parameter
    
    def run(self):
        """Execute the worker function."""
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logger.error(f"Worker error: {exc_value}")
            self.signals.error.emit((exc_type, exc_value, traceback.format_exception(exc_type, exc_value, exc_traceback)))
        finally:
            self.signals.finished.emit()

class CameraOperationWorker(CameraWorker):
    """Specialized worker for camera operations with additional context."""
    
    def __init__(self, camera_id: str, operation: str, fn: Callable, *args, **kwargs):
        """Initialize camera operation worker.
        
        Args:
            camera_id: ID of camera being operated on
            operation: Name of operation being performed
            fn: Function to execute
            *args: Arguments for function
            **kwargs: Keyword arguments for function
        """
        super().__init__(fn, *args, **kwargs)
        self.camera_id = camera_id
        self.operation = operation
    
    def run(self):
        """Execute the camera operation with logging."""
        logger.debug(f"Starting {self.operation} for camera {self.camera_id}")
        try:
            result = self.fn(*self.args, **self.kwargs)
            logger.debug(f"Completed {self.operation} for camera {self.camera_id}")
            self.signals.result.emit(result)
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logger.error(f"Error in {self.operation} for camera {self.camera_id}: {exc_value}")
            self.signals.error.emit((exc_type, exc_value, traceback.format_exception(exc_type, exc_value, exc_traceback)))
        finally:
            self.signals.finished.emit()

class DownloadWorker(CameraOperationWorker):
    """Specialized worker for file download operations with progress tracking."""
    
    def __init__(self, camera_id: str, fn: Callable, output_path: str, *args, **kwargs):
        """Initialize download worker.
        
        Args:
            camera_id: ID of camera being operated on
            fn: Download function to execute
            output_path: Path where file will be saved
            *args: Arguments for function
            **kwargs: Keyword arguments for function
        """
        super().__init__(camera_id, "download", fn, *args, **kwargs)
        self.output_path = output_path
    
    def run(self):
        """Execute download with manual progress tracking."""
        logger.info(f"Starting download for camera {self.camera_id} to {self.output_path}")
        
        # Emit start progress
        self.signals.progress.emit(0)
        
        try:
            # Execute download function without progress callback
            # (goproUSB doesn't support progress callbacks)
            result = self.fn(*self.args, **self.kwargs)
            
            # Emit completion progress
            self.signals.progress.emit(100)
            
            logger.info(f"Download completed for camera {self.camera_id}")
            self.signals.result.emit(result)
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logger.error(f"Download failed for camera {self.camera_id}: {exc_value}")
            self.signals.error.emit((exc_type, exc_value, traceback.format_exception(exc_type, exc_value, exc_traceback)))
        finally:
            self.signals.finished.emit()
