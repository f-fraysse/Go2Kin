#!/usr/bin/env python3
"""
GoPro Settings Discovery Tool

This tool connects to a GoPro camera and discovers all available settings
and their possible values. It generates a settings reference file that can
be used by the Go2Kin application.

Usage:
    python tools/discover_camera_settings.py <camera_serial_number>

Example:
    python tools/discover_camera_settings.py C3501326042700

The tool will:
1. Connect to the camera
2. Query camera info (model, firmware)
3. Discover all available settings and their options
4. Save a reference file in config/settings_references/

This only needs to be run once per camera model/firmware combination.
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

# Add goproUSB to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code' / 'goproUSB'))
from goproUSB import GPcam

# Import setting name mappings
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'project docs'))
from settings_name_value_pairs import SETTING_ID_TO_NAME
from status_name_value_pairs import STATUS_ID_TO_NAME


def discover_camera_settings(camera):
    """
    Universal settings discovery that works for ANY GoPro model.
    Returns complete settings reference for that specific model/firmware.
    """
    
    print("\n" + "="*70)
    print("GoPro Settings Discovery Tool")
    print("="*70)
    
    # 1. Get camera info
    print("\n[1/4] Querying camera information...")
    try:
        info_response = camera.getCameraInfo()
        if info_response.status_code != 200:
            print(f"❌ Failed to get camera info (status: {info_response.status_code})")
            return None
        
        info = info_response.json()
        model = info['model_name']
        firmware = info['firmware_version']
        serial = info['serial_number']
        
        print(f"✓ Camera Model: {model}")
        print(f"✓ Firmware Version: {firmware}")
        print(f"✓ Serial Number: {serial}")
        
    except Exception as e:
        print(f"❌ Error getting camera info: {e}")
        return None
    
    # 2. Get current camera state
    print("\n[2/4] Querying current camera state...")
    try:
        state_response = camera.getState()
        if state_response.status_code != 200:
            print(f"❌ Failed to get camera state (status: {state_response.status_code})")
            return None
        
        state = state_response.json()
        print(f"✓ Retrieved {len(state.get('settings', {}))} current settings")
        print(f"✓ Retrieved {len(state.get('status', {}))} status values")
        
    except Exception as e:
        print(f"❌ Error getting camera state: {e}")
        return None
    
    # 3. Discover available options for each setting
    print(f"\n[3/4] Discovering available options for {len(SETTING_ID_TO_NAME)} settings...")
    print("This may take 2-3 minutes...\n")
    
    settings_reference = {}
    successful = 0
    failed = 0
    
    for setting_id, setting_name in SETTING_ID_TO_NAME.items():
        try:
            # Send invalid option request to get supported options
            response = camera.querySetting(setting_id, option=-1)
            
            if response.status_code == 403:  # Expected error with options list
                data = response.json()
                
                # Extract available options
                available_options = {}
                for option in data.get('supported_options', []):
                    available_options[str(option['id'])] = option['display_name']
                
                if available_options:
                    settings_reference[str(setting_id)] = {
                        'name': setting_name,
                        'available_options': available_options
                    }
                    successful += 1
                    print(f"  ✓ Setting {setting_id:3d} ({setting_name}): {len(available_options)} options")
                else:
                    failed += 1
                    print(f"  ⚠ Setting {setting_id:3d} ({setting_name}): No options returned")
            
            elif response.status_code == 200:
                # Setting accepted -1 as valid (unusual but possible)
                print(f"  ⚠ Setting {setting_id:3d} ({setting_name}): Accepted invalid option")
                failed += 1
            
            else:
                # Other error
                failed += 1
                print(f"  ✗ Setting {setting_id:3d} ({setting_name}): HTTP {response.status_code}")
            
            # Small delay to avoid overwhelming the camera
            time.sleep(0.1)
            
        except Exception as e:
            failed += 1
            print(f"  ✗ Setting {setting_id:3d} ({setting_name}): {e}")
    
    print(f"\n✓ Discovery complete: {successful} successful, {failed} failed")
    
    # 4. Build complete reference structure
    print("\n[4/4] Building settings reference...")
    
    reference = {
        'metadata': {
            'camera_model': model,
            'firmware_version': firmware,
            'discovery_date': datetime.now().isoformat(),
            'discovered_by': 'Go2Kin Settings Discovery Tool',
            'total_settings': len(settings_reference)
        },
        'settings': settings_reference,
        'status_names': {str(k): v for k, v in STATUS_ID_TO_NAME.items()}
    }
    
    return reference, model, firmware


def save_reference(reference, model, firmware):
    """Save the settings reference to a JSON file"""
    
    # Create output directory
    output_dir = Path('config/settings_references')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create filename from model and firmware
    safe_model = model.replace(' ', '_').replace('/', '_')
    safe_firmware = firmware.replace('.', '_')
    filename = f"settings_reference_{safe_model}_{safe_firmware}.json"
    filepath = output_dir / filename
    
    # Save to file
    with open(filepath, 'w') as f:
        json.dump(reference, f, indent=2)
    
    print(f"\n✓ Settings reference saved to: {filepath}")
    print(f"  File size: {filepath.stat().st_size / 1024:.1f} KB")
    
    return filepath


def main():
    """Main entry point"""
    
    if len(sys.argv) < 2:
        print("Usage: python tools/discover_camera_settings.py <camera_serial_number>")
        print("\nExample:")
        print("  python tools/discover_camera_settings.py C3501326042700")
        sys.exit(1)
    
    serial_number = sys.argv[1]
    
    print(f"\nConnecting to camera with serial number: {serial_number}")
    
    try:
        # Create camera instance
        camera = GPcam(serial_number)
        
        # Enable USB control
        print("Enabling USB control...")
        response = camera.USBenable()
        if response.status_code != 200:
            print(f"❌ Failed to enable USB control (status: {response.status_code})")
            sys.exit(1)
        
        time.sleep(1)
        
        # Verify connection
        print("Verifying connection...")
        response = camera.keepAlive()
        if response.status_code != 200:
            print(f"❌ Camera not responding (status: {response.status_code})")
            sys.exit(1)
        
        print("✓ Camera connected successfully")
        
        # Discover settings
        result = discover_camera_settings(camera)
        
        if result is None:
            print("\n❌ Settings discovery failed")
            sys.exit(1)
        
        reference, model, firmware = result
        
        # Save reference file
        filepath = save_reference(reference, model, firmware)
        
        print("\n" + "="*70)
        print("✓ Discovery Complete!")
        print("="*70)
        print(f"\nThe settings reference file has been created and can now be used")
        print(f"by Go2Kin for all {model} cameras running firmware {firmware}.")
        print(f"\nReference file: {filepath}")
        
    except KeyboardInterrupt:
        print("\n\n⚠ Discovery interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
