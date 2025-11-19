"""
Camera Profile Management System

This module handles:
- Loading/saving camera profiles (per serial number)
- Loading settings references (per model/firmware)
- Parsing camera state into human-readable format
- Validating setting changes
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple


class CameraProfileManager:
    """Manages camera profiles and settings references"""
    
    def __init__(self, config_dir: Path = None):
        """
        Initialize the profile manager
        
        Args:
            config_dir: Base configuration directory (default: ./config)
        """
        if config_dir is None:
            config_dir = Path('config')
        
        self.config_dir = Path(config_dir)
        self.profiles_dir = self.config_dir / 'camera_profiles'
        self.references_dir = self.config_dir / 'settings_references'
        
        # Create directories if they don't exist
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.references_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache for loaded references
        self._reference_cache = {}
    
    def get_profile_path(self, serial_number: str) -> Path:
        """Get the file path for a camera profile"""
        return self.profiles_dir / f"profile_{serial_number}.json"
    
    def get_reference_path(self, model: str, firmware: str) -> Path:
        """Get the file path for a settings reference"""
        safe_model = model.replace(' ', '_').replace('/', '_')
        safe_firmware = firmware.replace('.', '_')
        filename = f"settings_reference_{safe_model}_{safe_firmware}.json"
        return self.references_dir / filename
    
    def load_camera_profile(self, serial_number: str) -> Optional[Dict]:
        """
        Load a camera profile by serial number
        
        Returns:
            Camera profile dict or None if not found
        """
        profile_path = self.get_profile_path(serial_number)
        
        if not profile_path.exists():
            return None
        
        try:
            with open(profile_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading camera profile: {e}")
            return None
    
    def save_camera_profile(self, serial_number: str, profile: Dict):
        """
        Save a camera profile
        
        Args:
            serial_number: Camera serial number
            profile: Profile dictionary to save
        """
        profile_path = self.get_profile_path(serial_number)
        
        try:
            with open(profile_path, 'w') as f:
                json.dump(profile, f, indent=2)
        except Exception as e:
            print(f"Error saving camera profile: {e}")
    
    def load_settings_reference(self, model: str, firmware: str) -> Optional[Dict]:
        """
        Load settings reference for a specific model/firmware
        
        Returns:
            Settings reference dict or None if not found
        """
        # Check cache first
        cache_key = f"{model}_{firmware}"
        if cache_key in self._reference_cache:
            return self._reference_cache[cache_key]
        
        reference_path = self.get_reference_path(model, firmware)
        
        if not reference_path.exists():
            return None
        
        try:
            with open(reference_path, 'r') as f:
                reference = json.load(f)
                self._reference_cache[cache_key] = reference
                return reference
        except Exception as e:
            print(f"Error loading settings reference: {e}")
            return None
    
    def parse_camera_state(self, state: Dict, reference: Dict) -> Tuple[Dict, Dict]:
        """
        Parse raw camera state into human-readable format using reference
        
        Args:
            state: Raw state from camera.getState()
            reference: Settings reference dictionary
        
        Returns:
            Tuple of (parsed_settings, parsed_status)
        """
        parsed_settings = {}
        parsed_status = {}
        
        # Parse settings
        for setting_id_str, value in state.get('settings', {}).items():
            setting_id = str(setting_id_str)
            
            if setting_id in reference.get('settings', {}):
                setting_info = reference['settings'][setting_id]
                setting_name = setting_info['name']
                
                # Get value name from available options
                value_str = str(value)
                value_name = setting_info['available_options'].get(value_str, f"Unknown ({value})")
                
                parsed_settings[setting_id] = {
                    'value': value,
                    'name': setting_name,
                    'value_name': value_name
                }
        
        # Parse status
        for status_id_str, value in state.get('status', {}).items():
            status_id = str(status_id_str)
            
            if status_id in reference.get('status_names', {}):
                status_name = reference['status_names'][status_id]
                
                parsed_status[status_id] = {
                    'value': value,
                    'name': status_name
                }
        
        return parsed_settings, parsed_status
    
    def create_or_update_profile(self, camera_info: Dict, state: Dict, 
                                 reference: Dict) -> Dict:
        """
        Create or update a camera profile with current state
        
        Args:
            camera_info: Camera info from getCameraInfo()
            state: Camera state from getState()
            reference: Settings reference
        
        Returns:
            Updated profile dictionary
        """
        serial_number = camera_info['serial_number']
        model = camera_info['model_name']
        firmware = camera_info['firmware_version']
        
        # Load existing profile or create new one
        profile = self.load_camera_profile(serial_number) or {}
        
        # Parse current state
        parsed_settings, parsed_status = self.parse_camera_state(state, reference)
        
        # Update profile
        profile.update({
            'serial_number': serial_number,
            'model': model,
            'firmware': firmware,
            'last_connected': datetime.now().isoformat(),
            'settings_reference_file': self.get_reference_path(model, firmware).name,
            'current_settings': parsed_settings,
            'current_status': parsed_status
        })
        
        # Save profile
        self.save_camera_profile(serial_number, profile)
        
        return profile
    
    def get_setting_options(self, setting_id: int, reference: Dict) -> Dict[str, str]:
        """
        Get available options for a setting
        
        Args:
            setting_id: Setting ID number
            reference: Settings reference
        
        Returns:
            Dictionary of {option_id: option_name}
        """
        setting_id_str = str(setting_id)
        
        if setting_id_str in reference.get('settings', {}):
            return reference['settings'][setting_id_str].get('available_options', {})
        
        return {}
    
    def validate_setting_value(self, setting_id: int, value: int, 
                               reference: Dict) -> bool:
        """
        Check if a setting value is valid according to the reference
        
        Args:
            setting_id: Setting ID number
            value: Value to validate
            reference: Settings reference
        
        Returns:
            True if valid, False otherwise
        """
        options = self.get_setting_options(setting_id, reference)
        return str(value) in options
    
    def get_setting_name(self, setting_id: int, reference: Dict) -> str:
        """Get human-readable name for a setting"""
        setting_id_str = str(setting_id)
        
        if setting_id_str in reference.get('settings', {}):
            return reference['settings'][setting_id_str]['name']
        
        return f"Setting {setting_id}"
    
    def get_value_name(self, setting_id: int, value: int, reference: Dict) -> str:
        """Get human-readable name for a setting value"""
        options = self.get_setting_options(setting_id, reference)
        return options.get(str(value), f"Unknown ({value})")


# Global instance for easy access
_profile_manager = None

def get_profile_manager() -> CameraProfileManager:
    """Get the global profile manager instance"""
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = CameraProfileManager()
    return _profile_manager
