#!/usr/bin/env python3
"""
Video Quality Comparison: Easy Mode vs Pro Mode

Records two 10-second clips on one camera to compare:
  A) Easy Mode "Highest Quality" preset
  B) Pro Mode with manual high-quality settings

Output files are saved to the tools/ directory for side-by-side comparison.

Usage:
    python tools/test_video_quality.py [camera_serial]

    Default serial: C3501326042700 (GoPro 1)
"""

import sys
import time
import os
from pathlib import Path

# Add goproUSB to path (same pattern as discover tool)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code' / 'goproUSB'))
from goproUSB import GPcam  # type: ignore

RECORD_SECONDS = 10
OUTPUT_DIR = Path(__file__).resolve().parent


def wait_for_ready(camera, label=""):
    """Wait until camera is no longer busy/encoding."""
    timeout = 60
    start = time.time()
    while camera.camBusy() or camera.encodingActive():
        if time.time() - start > timeout:
            print(f"  WARNING: Camera still busy after {timeout}s")
            break
        time.sleep(0.5)


def apply_setting(camera, setting_id, option, name, value_desc):
    """Apply a single setting with logging."""
    try:
        response = camera.setSetting(setting_id, option)
        if response.status_code == 200:
            print(f"  Set {name} = {value_desc}")
        else:
            print(f"  WARNING: {name} returned HTTP {response.status_code}")
        time.sleep(0.3)
    except Exception as e:
        print(f"  ERROR setting {name}: {e}")


def record_and_download(camera, filename, label):
    """Record a clip, download it, and delete from camera."""
    filepath = OUTPUT_DIR / filename

    print(f"\n  Starting {RECORD_SECONDS}s recording...")
    camera.shutterStart()
    time.sleep(RECORD_SECONDS)
    camera.shutterStop()
    print(f"  Recording stopped.")

    print(f"  Waiting for encoding to finish...")
    wait_for_ready(camera)

    # Print media list for diagnostics
    ml = camera.getMediaList().json()
    files = ml['media'][-1]['fs']
    target = files[-1]
    print(f"  File on camera: {target['n']} ({int(target['s']):,} bytes)")

    print(f"  Downloading to {filepath.name}...")
    camera.mediaDownloadLast(str(filepath))

    actual_size = os.path.getsize(filepath)
    print(f"  Downloaded: {actual_size:,} bytes ({actual_size / (1024*1024):.1f} MB)")

    print(f"  Deleting files from camera...")
    camera.deleteAllFiles()
    time.sleep(1)

    return filepath, actual_size


def main():
    serial = sys.argv[1] if len(sys.argv) > 1 else "C3501326042700"

    print(f"Video Quality Comparison Test")
    print(f"{'=' * 50}")
    print(f"Camera serial: {serial}")
    print(f"Record duration: {RECORD_SECONDS}s per clip")
    print(f"Output directory: {OUTPUT_DIR}\n")

    camera = GPcam(serial)

    # Connect
    print("Connecting to camera...")
    camera.USBenable()
    time.sleep(1)
    camera.keepAlive()
    print("Connected.\n")

    # Shared settings for both tests
    print("Applying shared settings...")
    apply_setting(camera, 134, 3, "Anti-Flicker", "50Hz")
    apply_setting(camera, 121, 4, "Lens", "Linear")
    time.sleep(0.5)

    results = {}

    # --- Recording A: Easy Mode "Highest Quality" ---
    print(f"\n{'=' * 50}")
    print("RECORDING A: Easy Mode - Highest Quality")
    print(f"{'=' * 50}")

    camera.modeVideo()
    time.sleep(1)

    apply_setting(camera, 175, 0, "Control Mode", "Easy")
    apply_setting(camera, 186, 0, "Video Easy Mode", "Highest Quality")
    time.sleep(1)

    filepath_a, size_a = record_and_download(camera, "test_easy_highest.mp4", "Easy")
    results['Easy Mode (Highest Quality)'] = (filepath_a, size_a)

    # --- Recording B: Pro Mode with manual settings ---
    print(f"\n{'=' * 50}")
    print("RECORDING B: Pro Mode - Manual High Quality")
    print(f"{'=' * 50}")

    camera.modeVideo()
    time.sleep(1)

    apply_setting(camera, 175, 1, "Control Mode", "Pro")
    apply_setting(camera, 135, 0, "Hypersmooth", "Off")
    apply_setting(camera, 182, 1, "Bit Rate", "High")
    apply_setting(camera, 183, 2, "Bit Depth", "10-Bit")
    apply_setting(camera, 184, 0, "Profiles", "Standard")
    apply_setting(camera, 2,   9, "Resolution", "1080p")
    apply_setting(camera, 3,   6, "FPS", "50")
    time.sleep(1)

    filepath_b, size_b = record_and_download(camera, "test_pro_high.mp4", "Pro")
    results['Pro Mode (High Quality)'] = (filepath_b, size_b)

    # --- Summary ---
    print(f"\n{'=' * 50}")
    print("RESULTS")
    print(f"{'=' * 50}")
    for label, (filepath, size) in results.items():
        print(f"  {label}:")
        print(f"    File: {filepath.name}")
        print(f"    Size: {size:,} bytes ({size / (1024*1024):.1f} MB)")
    print(f"\nCompare these files visually to check for quality differences.")
    print(f"Files are in: {OUTPUT_DIR}")

    # Restore Pro mode
    print(f"\nRestoring camera to Pro mode...")
    apply_setting(camera, 175, 1, "Control Mode", "Pro")
    print("Done.")


if __name__ == '__main__':
    main()
