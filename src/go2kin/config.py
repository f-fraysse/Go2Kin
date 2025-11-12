"""
Configuration management for Go2Kin application.

Handles JSON-based persistence of camera settings, recording preferences,
and UI state.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Default camera configuration
DEFAULT_CAMERAS = {
    "GP1": {
        "serial": "C3501326042700",
        "lens": "Narrow",
        "resolution": "1080p",
        "fps": 30,
        "enabled": True
    },
    "GP2": {
        "serial": "C3501326054100",
        "lens": "Narrow",
        "resolution": "1080p",
        "fps": 30,
        "enabled": True
    },
    "GP3": {
        "serial": "C3501326054460",
        "lens": "Narrow",
        "resolution": "1080p",
        "fps": 30,
        "enabled": True
    },
    "GP4": {
        "serial": "C3501326062418",
        "lens": "Narrow",
        "resolution": "1080p",
        "fps": 30,
        "enabled": True
    }
}

DEFAULT_CONFIG = {
    "cameras": DEFAULT_CAMERAS,
    "recording": {
        "output_directory": str(Path.cwd() / "output"),
        "last_trial_number": 0,
        "auto_increment": True
    },
    "ui": {
        "window_geometry": None,
        "selected_cameras": ["GP1", "GP2", "GP3", "GP4"],
        "last_preview_camera": "GP1"
    },
    "app": {
        "version": "0.1.0",
        "first_run": True
    }
}

class ConfigManager:
    """Manages application configuration with JSON persistence."""
    
    def __init__(self, config_path: Optional[Path] = None):
        """Initialize configuration manager.
        
        Args:
            config_path: Path to configuration file. Defaults to config/cameras.json
        """
        if config_path is None:
            config_path = Path.cwd() / "config" / "cameras.json"
        
        self.config_path = config_path
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default."""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                # Merge with defaults to handle new keys
                return self._merge_with_defaults(config)
            else:
                logger.info(f"Creating default configuration at {self.config_path}")
                self._save_config(DEFAULT_CONFIG)
                return DEFAULT_CONFIG.copy()
        except Exception as e:
            logger.error(f"Error loading config: {e}. Using defaults.")
            return DEFAULT_CONFIG.copy()
    
    def _merge_with_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge loaded config with defaults to handle missing keys."""
        merged = DEFAULT_CONFIG.copy()
        
        # Deep merge for nested dictionaries
        for key, value in config.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key].update(value)
            else:
                merged[key] = value
        
        return merged
    
    def _save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to file."""
        try:
            # Create a copy of config for serialization
            serializable_config = self._make_serializable(config)
            with open(self.config_path, 'w') as f:
                json.dump(serializable_config, f, indent=2)
            logger.debug(f"Configuration saved to {self.config_path}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def _make_serializable(self, obj: Any) -> Any:
        """Convert objects to JSON-serializable format."""
        if hasattr(obj, '__dict__'):
            return {key: self._make_serializable(value) for key, value in obj.__dict__.items()}
        elif isinstance(obj, dict):
            return {key: self._make_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._make_serializable(item) for item in obj]
        elif hasattr(obj, 'data') and callable(obj.data):
            # Handle QByteArray and similar Qt objects
            try:
                return obj.data().decode('utf-8') if obj.data() else None
            except:
                return str(obj) if obj else None
        elif obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        else:
            # Convert other objects to string representation
            return str(obj) if obj else None
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key path (e.g., 'cameras.GP1.serial')."""
        keys = key.split('.')
        value = self._config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any, save: bool = True) -> None:
        """Set configuration value by key path."""
        keys = key.split('.')
        config = self._config
        
        # Navigate to parent of target key
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # Set the value
        config[keys[-1]] = value
        
        if save:
            self._save_config(self._config)
    
    def get_camera_config(self, camera_id: str) -> Dict[str, Any]:
        """Get configuration for specific camera."""
        return self.get(f'cameras.{camera_id}', {})
    
    def set_camera_config(self, camera_id: str, config: Dict[str, Any], save: bool = True) -> None:
        """Set configuration for specific camera."""
        self.set(f'cameras.{camera_id}', config, save)
    
    def get_camera_serial(self, camera_id: str) -> str:
        """Get serial number for camera."""
        return self.get(f'cameras.{camera_id}.serial', '')
    
    def set_camera_serial(self, camera_id: str, serial: str, save: bool = True) -> None:
        """Set serial number for camera."""
        self.set(f'cameras.{camera_id}.serial', serial, save)
    
    def get_output_directory(self) -> Path:
        """Get recording output directory."""
        return Path(self.get('recording.output_directory', str(Path.cwd() / "output")))
    
    def set_output_directory(self, path: Path, save: bool = True) -> None:
        """Set recording output directory."""
        self.set('recording.output_directory', str(path), save)
    
    def get_next_trial_number(self) -> int:
        """Get next trial number and increment counter."""
        current = self.get('recording.last_trial_number', 0)
        next_num = current + 1
        self.set('recording.last_trial_number', next_num)
        return next_num
    
    def get_selected_cameras(self) -> list:
        """Get list of selected camera IDs."""
        return self.get('ui.selected_cameras', list(DEFAULT_CAMERAS.keys()))
    
    def set_selected_cameras(self, camera_ids: list, save: bool = True) -> None:
        """Set selected camera IDs."""
        self.set('ui.selected_cameras', camera_ids, save)
    
    def save(self) -> None:
        """Explicitly save current configuration."""
        self._save_config(self._config)
    
    def reset_to_defaults(self) -> None:
        """Reset configuration to defaults."""
        self._config = DEFAULT_CONFIG.copy()
        self._save_config(self._config)
        logger.info("Configuration reset to defaults")

def calculate_camera_ip(serial_number: str) -> str:
    """Calculate camera IP address from serial number.
    
    Args:
        serial_number: GoPro serial number
        
    Returns:
        IP address in format 172.2X.1YZ.51
    """
    if len(serial_number) < 3:
        raise ValueError(f"Invalid serial number: {serial_number}")
    
    last_digit = serial_number[-1]
    last_two = serial_number[-2:]
    return f"172.2{last_digit}.1{last_two}.51"
