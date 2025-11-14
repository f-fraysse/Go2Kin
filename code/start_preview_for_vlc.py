#!/usr/bin/env python3
"""
Simple script to start GoPro preview stream for VLC testing

Usage: 
1. Run this script
2. Open VLC and use "Open Network Stream" with: udp://@0.0.0.0:8554
3. Press Enter in this script to stop the stream

Make sure GoPro 1 (serial C3501326042700) is connected via USB
"""

import sys
import time
from pathlib import Path

# Add goproUSB to path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'goproUSB'))
from goproUSB import GPcam

# Camera configuration
SNcam1 = 'C3501326042700'  # GoPro 1
STREAM_PORT = 8554

def main():
    print("=== GoPro Preview Stream Starter for VLC Testing ===")
    print(f"Camera: {SNcam1}")
    print(f"Stream Port: {STREAM_PORT}")
    print()
    
    # Initialize camera
    print("Initializing camera...")
    cam1 = GPcam(SNcam1)
    
    try:
        # Enable USB control
        print("Enabling USB control...")
        response = cam1.USBenable()
        if response.status_code != 200:
            print(f"ERROR: Failed to enable USB control (status: {response.status_code})")
            return
        print("✓ USB control enabled")
        time.sleep(1)  # Wait between API calls
        
        # Check camera status
        print("Checking camera status...")
        response = cam1.keepAlive()
        if response.status_code != 200:
            print(f"ERROR: Camera not responding (status: {response.status_code})")
            return
        print("✓ Camera responding")
        time.sleep(1)  # Wait between API calls
        
        # Set video mode
        print("Setting video mode...")
        response = cam1.modeVideo()
        if response.status_code != 200:
            print(f"WARNING: Video mode response: {response.status_code}")
        else:
            print("✓ Video mode set")
        time.sleep(1)  # Wait between API calls
        
        # Wait for camera to be ready
        print("Waiting for camera to be ready...")
        time.sleep(2)
        
        # Start preview stream
        print(f"Starting preview stream on port {STREAM_PORT}...")
        response = cam1.previewStreamStart(port=STREAM_PORT)
        if response.status_code != 200:
            print(f"ERROR: Failed to start preview stream (status: {response.status_code})")
            return
        
        print("✓ Preview stream started successfully!")
        time.sleep(1)  # Wait for stream to initialize
        print()
        print("=" * 60)
        print("STREAM IS NOW ACTIVE")
        print("=" * 60)
        print("1. Open VLC Media Player")
        print("2. Go to Media > Open Network Stream")
        print("3. Enter this URL: udp://@0.0.0.0:8554")
        print("4. Click Play")
        print()
        print("If you see video in VLC, the camera streaming is working!")
        print("If not, there may be a camera configuration issue.")
        print()
        print("Press ENTER to stop the stream and exit...")
        
        # Wait for user input
        input()
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"ERROR: {e}")
    
    finally:
        # Stop preview stream
        print("\nStopping preview stream...")
        try:
            response = cam1.previewStreamStop()
            if response.status_code == 200:
                print("✓ Preview stream stopped")
            else:
                print(f"WARNING: Stop stream response: {response.status_code}")
        except Exception as e:
            print(f"Error stopping stream: {e}")
        
        time.sleep(1)  # Wait between API calls
        
        # Disable USB control
        print("Disabling USB control...")
        try:
            response = cam1.USBdisable()
            if response.status_code == 200:
                print("✓ USB control disabled")
            else:
                print(f"WARNING: USB disable response: {response.status_code}")
        except Exception as e:
            print(f"Error disabling USB: {e}")
        
        print("\nDone!")

if __name__ == "__main__":
    main()
