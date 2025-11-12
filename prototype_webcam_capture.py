#!/usr/bin/env python3
"""
Minimal prototype for GoPro webcam capture using OpenCV.

This script tests the basic functionality of:
1. Putting a GoPro into webcam mode
2. Capturing the USB video stream with OpenCV
3. Displaying the live feed
4. Clean shutdown

Usage: python prototype_webcam_capture.py
Press 'q' to quit
"""

import cv2
import time
import sys
import logging
from goproUSB.goproUSB import GPcam

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
GOPRO_SERIAL = "C3501326042700"  # GoPro 1 - change this to test different cameras
CAMERA_DEVICE_INDICES = [0, 1, 2, 3, 4, 5]  # Try multiple USB camera indices
WEBCAM_START_DELAY = 3  # Seconds to wait after starting webcam mode

def find_gopro_camera_device():
    """
    Try to find the GoPro camera device by testing multiple indices.
    
    Returns:
        int or None: Camera device index if found, None otherwise
    """
    logger.info("Searching for GoPro camera device...")
    
    for device_index in CAMERA_DEVICE_INDICES:
        logger.info(f"Trying camera device index {device_index}...")
        cap = cv2.VideoCapture(device_index)
        
        if cap.isOpened():
            # Test if we can read a frame
            ret, frame = cap.read()
            if ret and frame is not None:
                height, width = frame.shape[:2]
                logger.info(f"Found camera at index {device_index}: {width}x{height}")
                cap.release()
                return device_index
            else:
                logger.info(f"Camera at index {device_index} opened but no frame available")
        else:
            logger.info(f"No camera found at index {device_index}")
        
        cap.release()
    
    logger.error("No suitable camera device found")
    return None

def main():
    """Main function to test GoPro webcam capture."""
    logger.info("=== GoPro Webcam Capture Prototype ===")
    logger.info(f"Using GoPro serial: {GOPRO_SERIAL}")
    
    # Initialize GoPro
    try:
        gopro = GPcam(GOPRO_SERIAL)
        logger.info(f"Initialized GoPro with base URL: {gopro.base_url}")
    except Exception as e:
        logger.error(f"Failed to initialize GoPro: {e}")
        return False
    
    # Check if GoPro is responsive
    try:
        logger.info("Testing GoPro connection...")
        response = gopro.keepAlive()
        if response.status_code != 200:
            logger.error(f"GoPro not responding. Status code: {response.status_code}")
            logger.error("Make sure the GoPro is connected via USB and powered on")
            return False
        logger.info("GoPro connection successful")
    except Exception as e:
        logger.error(f"Failed to connect to GoPro: {e}")
        logger.error("Make sure the GoPro is connected via USB and powered on")
        return False
    
    # Disable USB control (required for webcam mode)
    try:
        logger.info("Disabling USB control...")
        gopro.USBdisable()
        time.sleep(1)
    except Exception as e:
        logger.error(f"Failed to disable USB control: {e}")
        return False
    
    # Start webcam mode
    try:
        logger.info("Starting webcam mode...")
        response = gopro.webcamStart()
        if response.status_code != 200:
            logger.error(f"Failed to start webcam mode. Status code: {response.status_code}")
            return False
        logger.info("Webcam mode started successfully")
        
        # Wait for webcam mode to initialize
        logger.info(f"Waiting {WEBCAM_START_DELAY} seconds for webcam mode to initialize...")
        time.sleep(WEBCAM_START_DELAY)
        
    except Exception as e:
        logger.error(f"Failed to start webcam mode: {e}")
        return False
    
    # Find camera device
    camera_index = find_gopro_camera_device()
    if camera_index is None:
        logger.error("Could not find GoPro camera device")
        logger.info("Stopping webcam mode...")
        try:
            gopro.webcamStop()
        except:
            pass
        return False
    
    # Initialize video capture
    logger.info(f"Initializing video capture from device {camera_index}...")
    cap = cv2.VideoCapture(camera_index)
    
    if not cap.isOpened():
        logger.error("Failed to open video capture")
        logger.info("Stopping webcam mode...")
        try:
            gopro.webcamStop()
        except:
            pass
        return False
    
    # Set capture properties for better performance
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce buffer to minimize latency
    
    # Get stream info
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    logger.info(f"Stream properties: {width}x{height} @ {fps} FPS")
    logger.info("Starting live preview... Press 'q' to quit")
    
    # Main capture loop
    frame_count = 0
    start_time = time.time()
    
    try:
        while True:
            ret, frame = cap.read()
            
            if not ret:
                logger.warning("Failed to read frame")
                continue
            
            frame_count += 1
            
            # Add frame counter and FPS info to display
            elapsed_time = time.time() - start_time
            if elapsed_time > 0:
                actual_fps = frame_count / elapsed_time
                cv2.putText(frame, f"Frame: {frame_count}", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, f"FPS: {actual_fps:.1f}", (10, 70), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, "Press 'q' to quit", (10, height - 20), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            
            # Display frame
            cv2.imshow('GoPro Webcam Stream', frame)
            
            # Check for quit key
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                logger.info("Quit key pressed")
                break
                
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Error during capture: {e}")
    
    # Cleanup
    logger.info("Cleaning up...")
    cap.release()
    cv2.destroyAllWindows()
    
    # Stop webcam mode
    try:
        logger.info("Stopping webcam mode...")
        gopro.webcamStop()
        time.sleep(1)
        
        # Re-enable USB control
        logger.info("Re-enabling USB control...")
        gopro.USBenable()
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
    
    logger.info("Prototype test completed")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
