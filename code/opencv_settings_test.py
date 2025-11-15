#!/usr/bin/env python3
"""
OpenCV Live Preview with Camera Settings Control

This script captures the GoPro UDP stream using OpenCV and allows real-time
camera setting changes while streaming to test if settings can be modified
during live preview without interrupting the stream.

Usage:
1. Run this script
2. OpenCV window displays the live camera feed
3. Use keyboard controls to change camera settings in real-time
4. Press 'q' to quit and stop the stream

Keyboard Controls:
- Lens Modes: 'w' (Wide), 'n' (Narrow), 's' (Superview), 'l' (Linear), 'm' (Max Superview)
- Resolution: '1' (1080p), '2' (1440p), '4' (4K), '5' (5K)
- Frame Rate: 'f' (30fps), 'F' (60fps)
- 'q' to quit
- 'r' to restart stream connection

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

def print_controls():
    """Print available keyboard controls"""
    print("=" * 60)
    print("KEYBOARD CONTROLS:")
    print("=" * 60)
    print("Lens Modes:")
    print("  'w' - Wide lens")
    print("  'n' - Narrow lens") 
    print("  's' - Superview lens")
    print("  'l' - Linear lens")
    print("  'm' - Max Superview lens")
    print()
    print("Frame Rate:")
    print("  'f' - 30 FPS")
    print("  'F' - 60 FPS")
    print()
    print("Digital Zoom:")
    print("  '1' - Zoom out -5%")
    print("  '2' - Zoom in +5%")
    print()
    print("Other:")
    print("  'r' - Restart stream connection")
    print("  'q' - Quit")
    print("=" * 60)
    print("Note: Resolution is fixed at 1080p for optimal streaming")

def apply_setting(cam, setting_name, setting_func):
    """Apply a camera setting and report the result"""
    print(f"Applying {setting_name}...")
    try:
        response = setting_func()
        if response.status_code == 200:
            print(f"✓ {setting_name} applied successfully")
            return True
        else:
            print(f"⚠ {setting_name} response: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error applying {setting_name}: {e}")
        return False

def main():
    print("=== OpenCV GoPro Live Preview with Settings Control ===")
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
        
        # Set camera to 1080p resolution for optimal streaming
        print("Setting camera to 1080p resolution...")
        response = cam1.setVideoResolution1080()
        if response.status_code != 200:
            print(f"WARNING: Resolution setting response: {response.status_code}")
        else:
            print("✓ Camera resolution set to 1080p")
        
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
        cap = cv2.VideoCapture(STREAM_URL, cv2.CAP_FFMPEG)
        
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
        print_controls()
        
        # Main display loop
        frame_count = 0
        current_lens = "Unknown"
        current_resolution = "1080p"  # Fixed resolution
        current_fps = "Unknown"
        current_zoom = 0  # Initialize zoom level
        
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
            
            # Add overlay information
            cv2.putText(frame, f"Frame: {frame_count}", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"Lens: {current_lens}", (10, 60), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"Resolution: {current_resolution}", (10, 90), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"FPS: {current_fps}", (10, 120), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"Zoom: {current_zoom}%", (10, 150), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Display the frame
            cv2.imshow('GoPro Live Preview - Settings Test', frame)
            
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
            
            # Lens mode controls
            elif key == ord('w'):
                if apply_setting(cam1, "Wide Lens", cam1.setVideoLensesWide):
                    current_lens = "Wide"
            elif key == ord('n'):
                if apply_setting(cam1, "Narrow Lens", cam1.setVideoLensesNarrow):
                    current_lens = "Narrow"
            elif key == ord('s'):
                if apply_setting(cam1, "Superview Lens", cam1.setVideoLensesSuperview):
                    current_lens = "Superview"
            elif key == ord('l'):
                if apply_setting(cam1, "Linear Lens", cam1.setVideoLensesLinear):
                    current_lens = "Linear"
            elif key == ord('m'):
                if apply_setting(cam1, "Max Superview Lens", cam1.setVideoLensesMaxSuperview):
                    current_lens = "Max Superview"
            
            # Digital zoom controls
            elif key == ord('1'):
                print("Zooming out (-5%)...")
                try:
                    response = cam1.zoomOut(5)
                    if response and response.status_code == 200:
                        current_zoom = max(0, current_zoom - 5)
                        print(f"✓ Zoom out successful - now at {current_zoom}%")
                    else:
                        print(f"⚠ Zoom out response: {response.status_code if response else 'None'}")
                except Exception as e:
                    print(f"✗ Error zooming out: {e}")
            elif key == ord('2'):
                print("Zooming in (+5%)...")
                try:
                    response = cam1.zoomIn(5)
                    if response and response.status_code == 200:
                        current_zoom = min(100, current_zoom + 5)
                        print(f"✓ Zoom in successful - now at {current_zoom}%")
                    else:
                        print(f"⚠ Zoom in response: {response.status_code if response else 'None'}")
                except Exception as e:
                    print(f"✗ Error zooming in: {e}")
            
            # Frame rate controls
            elif key == ord('f'):
                if apply_setting(cam1, "30 FPS", cam1.setFPS30):
                    current_fps = "30"
            elif key == ord('F'):
                if apply_setting(cam1, "60 FPS", cam1.setFPS60):
                    current_fps = "60"
        
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
