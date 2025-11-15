#!/usr/bin/env python3
"""
OpenCV Live Preview - GoPro UDP Stream Capture

This script captures the GoPro UDP stream using OpenCV and displays it in a window.
Based on start_preview_for_vlc.py but using OpenCV instead of VLC for display.

Usage:
1. Run this script
2. OpenCV window should display the live camera feed
3. Press 'q' to quit and stop the stream

Make sure GoPro 1 (serial C3501326042700) is connected via USB
"""

import sys
import time
import cv2
import numpy as np
from pathlib import Path

# Add goproUSB to path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'goproUSB'))
from goproUSB import GPcam

# Camera configuration
SNcam1 = 'C3501326042700'  # GoPro 1
STREAM_PORT = 8554
STREAM_URL = f'udp://0.0.0.0:{STREAM_PORT}'

def main():
    print("=== OpenCV GoPro Live Preview ===")
    print(f"Camera: {SNcam1}")
    print(f"Stream Port: {STREAM_PORT}")
    print(f"Stream URL: {STREAM_URL}")
    print()
    
    # Initialize camera
    print("Initializing camera...")
    cam1 = GPcam(SNcam1)
    cap = None
    
    try:
        # Enable USB control
        print("Enabling USB control...")
        response = cam1.USBenable()
        if response.status_code != 200:
            print(f"ERROR: Failed to enable USB control (status: {response.status_code})")
            return
        print("✓ USB control enabled")
        
        # Check camera status
        print("Checking camera status...")
        response = cam1.keepAlive()
        if response.status_code != 200:
            print(f"ERROR: Camera not responding (status: {response.status_code})")
            return
        print("✓ Camera responding")
        
        # Set video mode
        print("Setting video mode...")
        response = cam1.modeVideo()
        if response.status_code != 200:
            print(f"WARNING: Video mode response: {response.status_code}")
        else:
            print("✓ Video mode set")
        
        # Set camera to 30 FPS for optimal latency
        print("Setting camera to 30 FPS...")
        response = cam1.setFPS30()
        if response.status_code != 200:
            print(f"WARNING: FPS setting response: {response.status_code}")
        else:
            print("✓ Camera FPS set to 30")
        
        # Start preview stream
        print(f"Starting preview stream on port {STREAM_PORT}...")
        response = cam1.previewStreamStart(port=STREAM_PORT)
        if response.status_code != 200:
            print(f"ERROR: Failed to start preview stream (status: {response.status_code})")
            return
        
        print("✓ Preview stream started successfully!")
        print("Waiting for stream to initialize...")
        time.sleep(2)  # Give stream time to start
        
        # Initialize OpenCV VideoCapture
        print(f"Connecting to stream: {STREAM_URL}")
        cap = cv2.VideoCapture(STREAM_URL)
        
        if not cap.isOpened():
            print("ERROR: Could not open video stream with OpenCV")
            print("This might mean:")
            print("1. OpenCV doesn't have FFmpeg support for UDP/H264")
            print("2. Stream format is not compatible")
            print("3. Stream is not ready yet")
            return
        
        # Optimize for low latency
        print("Configuring OpenCV for low latency...")
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimal buffer
        cap.set(cv2.CAP_PROP_FPS, 30)        # Match camera FPS
        print("✓ Buffer optimization applied")
        
        print("✓ OpenCV connected to stream!")
        print()
        print("=" * 60)
        print("LIVE PREVIEW ACTIVE")
        print("=" * 60)
        print("Controls:")
        print("- Press 'q' to quit")
        print("- Press 'r' to restart stream connection")
        print()
        
        # Main display loop
        frame_count = 0
        while True:
            ret, frame = cap.read()
            
            if not ret:
                print("Warning: Failed to read frame from stream")
                # Try to reconnect
                cap.release()
                time.sleep(1)
                cap = cv2.VideoCapture(STREAM_URL)
                continue
            
            frame_count += 1
            
            # Add frame counter overlay
            cv2.putText(frame, f"Frame: {frame_count}", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            # Display the frame
            cv2.imshow('GoPro Live Preview', frame)
            
            # Handle key presses
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("Quit requested by user")
                break
            elif key == ord('r'):
                print("Restarting stream connection...")
                cap.release()
                time.sleep(1)
                cap = cv2.VideoCapture(STREAM_URL)
                if cap.isOpened():
                    print("✓ Stream reconnected")
                else:
                    print("ERROR: Failed to reconnect to stream")
                    break
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        print("\nCleaning up...")
        
        # Close OpenCV
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
        print("✓ OpenCV cleaned up")
        
        # Stop preview stream
        try:
            response = cam1.previewStreamStop()
            if response.status_code == 200:
                print("✓ Preview stream stopped")
            else:
                print(f"WARNING: Stop stream response: {response.status_code}")
        except Exception as e:
            print(f"Error stopping stream: {e}")
        
        # Disable USB control
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
