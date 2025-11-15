#!/usr/bin/env python3
"""
OpenCV Live Preview - OPTIMIZED for Low Latency
GoPro UDP Stream Capture with Delay Reduction Techniques

This enhanced version implements multiple optimization strategies to reduce
the ~1 second delay in live preview streaming.

Optimizations implemented:
1. Pre-configured VideoCapture properties
2. Alternative FFmpeg parameters for low latency
3. Threading for non-blocking frame processing
4. Frame dropping to prevent buffer buildup
5. Latency measurement and comparison

Usage:
1. Run this script
2. Compare latency with original opencv_live_preview.py
3. Press 'q' to quit, 'r' to restart, 't' to toggle threading mode

Make sure GoPro 1 (serial C3501326042700) is connected via USB
"""

import sys
import time
import cv2
import numpy as np
import threading
import queue
from datetime import datetime
from pathlib import Path

# Add goproUSB to path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'goproUSB'))
from goproUSB import GPcam

# Camera configuration
SNcam1 = 'C3501326042700'  # GoPro 1
STREAM_PORT = 8554
STREAM_URL = f'udp://0.0.0.0:{STREAM_PORT}'

class OptimizedVideoCapture:
    """Enhanced VideoCapture with low-latency optimizations"""
    
    def __init__(self, source, use_threading=True):
        self.source = source
        self.use_threading = use_threading
        self.cap = None
        self.frame_queue = queue.Queue(maxsize=2)  # Small queue to prevent buildup
        self.capture_thread = None
        self.running = False
        self.frame_count = 0
        self.dropped_frames = 0
        self.last_frame_time = time.time()
        
    def _create_optimized_capture(self, ffmpeg_params=""):
        """Create VideoCapture with pre-configured low-latency settings"""
        print(f"Creating optimized capture with params: {ffmpeg_params}")
        
        # Method 1: Pre-configure before opening
        cap = cv2.VideoCapture()
        
        # Set properties BEFORE opening the stream
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimal buffer - most important!
        cap.set(cv2.CAP_PROP_FPS, 30)        # Match camera FPS
        
        # Additional low-latency properties
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('H','2','6','4'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        
        # Open with optimized FFmpeg parameters
        full_url = self.source + ffmpeg_params
        success = cap.open(full_url, cv2.CAP_FFMPEG)
        
        if success:
            print("✓ Optimized capture created successfully")
            # Verify settings were applied
            buffer_size = cap.get(cv2.CAP_PROP_BUFFERSIZE)
            fps = cap.get(cv2.CAP_PROP_FPS)
            print(f"  Buffer size: {buffer_size}")
            print(f"  FPS: {fps}")
        else:
            print("✗ Failed to create optimized capture")
            cap.release()
            cap = None
            
        return cap
    
    def open(self):
        """Open video capture with multiple fallback strategies"""
        print("Testing different optimization strategies...")
        
        # Strategy 1: Aggressive low-latency FFmpeg params
        ffmpeg_params_v1 = "?overrun_nonfatal=1&fifo_size=1000000&fflags=nobuffer&flags=low_delay&framedrop"
        self.cap = self._create_optimized_capture(ffmpeg_params_v1)
        
        if not self.cap or not self.cap.isOpened():
            print("Strategy 1 failed, trying Strategy 2...")
            
            # Strategy 2: Original params with pre-configuration
            ffmpeg_params_v2 = "?overrun_nonfatal=1&fifo_size=50000000"
            self.cap = self._create_optimized_capture(ffmpeg_params_v2)
        
        if not self.cap or not self.cap.isOpened():
            print("Strategy 2 failed, trying Strategy 3...")
            
            # Strategy 3: Minimal params
            ffmpeg_params_v3 = "?overrun_nonfatal=1"
            self.cap = self._create_optimized_capture(ffmpeg_params_v3)
        
        if not self.cap or not self.cap.isOpened():
            print("All strategies failed!")
            return False
        
        if self.use_threading:
            self._start_capture_thread()
        
        return True
    
    def _start_capture_thread(self):
        """Start background thread for continuous frame capture"""
        print("Starting threaded capture...")
        self.running = True
        self.capture_thread = threading.Thread(target=self._capture_frames, daemon=True)
        self.capture_thread.start()
    
    def _capture_frames(self):
        """Background thread function for capturing frames"""
        while self.running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                current_time = time.time()
                
                # Drop frames if queue is full (prevents buildup)
                if self.frame_queue.full():
                    try:
                        self.frame_queue.get_nowait()  # Remove old frame
                        self.dropped_frames += 1
                    except queue.Empty:
                        pass
                
                # Add timestamp to frame for latency measurement
                frame_with_timestamp = (frame, current_time)
                
                try:
                    self.frame_queue.put_nowait(frame_with_timestamp)
                    self.frame_count += 1
                except queue.Full:
                    self.dropped_frames += 1
            else:
                time.sleep(0.001)  # Brief pause on read failure
    
    def read(self):
        """Read frame (threaded or direct)"""
        if self.use_threading:
            try:
                frame_data = self.frame_queue.get_nowait()
                return True, frame_data
            except queue.Empty:
                return False, None
        else:
            # Direct read
            ret, frame = self.cap.read()
            if ret:
                current_time = time.time()
                return ret, (frame, current_time)
            return ret, None
    
    def get_stats(self):
        """Get capture statistics"""
        return {
            'frames_captured': self.frame_count,
            'frames_dropped': self.dropped_frames,
            'drop_rate': (self.dropped_frames / max(1, self.frame_count)) * 100
        }
    
    def release(self):
        """Clean up resources"""
        self.running = False
        if self.capture_thread:
            self.capture_thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()

def measure_latency(frame_timestamp):
    """Calculate approximate latency"""
    current_time = time.time()
    latency_ms = (current_time - frame_timestamp) * 1000
    return latency_ms

def main():
    print("=== OPTIMIZED OpenCV GoPro Live Preview ===")
    print(f"Camera: {SNcam1}")
    print(f"Stream Port: {STREAM_PORT}")
    print(f"Stream URL: {STREAM_URL}")
    print()
    
    # Initialize camera
    print("Initializing camera...")
    cam1 = GPcam(SNcam1)
    opt_cap = None
    
    # Configuration
    use_threading = True
    
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
        
        # Initialize Optimized VideoCapture
        print(f"Creating optimized capture for: {STREAM_URL}")
        opt_cap = OptimizedVideoCapture(STREAM_URL, use_threading=use_threading)
        
        if not opt_cap.open():
            print("ERROR: Could not open optimized video stream")
            return
        
        print("✓ Optimized OpenCV connected to stream!")
        print()
        print("=" * 70)
        print("OPTIMIZED LIVE PREVIEW ACTIVE")
        print("=" * 70)
        print("Controls:")
        print("- Press 'q' to quit")
        print("- Press 'r' to restart stream connection")
        print("- Press 't' to toggle threading mode")
        print("- Press 's' to show statistics")
        print()
        
        # Statistics tracking
        latency_samples = []
        fps_counter = 0
        fps_start_time = time.time()
        
        # Main display loop
        while True:
            ret, frame_data = opt_cap.read()
            
            if not ret or frame_data is None:
                print("Warning: Failed to read frame from optimized stream")
                time.sleep(0.01)  # Brief pause
                continue
            
            frame, frame_timestamp = frame_data
            fps_counter += 1
            
            # Calculate latency
            latency_ms = measure_latency(frame_timestamp)
            latency_samples.append(latency_ms)
            
            # Keep only recent samples for rolling average
            if len(latency_samples) > 30:
                latency_samples.pop(0)
            
            avg_latency = sum(latency_samples) / len(latency_samples)
            
            # Calculate FPS
            current_time = time.time()
            if current_time - fps_start_time >= 1.0:
                display_fps = fps_counter / (current_time - fps_start_time)
                fps_counter = 0
                fps_start_time = current_time
            else:
                display_fps = 0
            
            # Add enhanced overlay with performance metrics
            stats = opt_cap.get_stats()
            
            # Latency indicator (color-coded)
            latency_color = (0, 255, 0) if avg_latency < 300 else (0, 255, 255) if avg_latency < 500 else (0, 0, 255)
            
            cv2.putText(frame, f"Latency: {avg_latency:.0f}ms", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, latency_color, 2)
            
            cv2.putText(frame, f"FPS: {display_fps:.1f}", (10, 60), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            cv2.putText(frame, f"Frames: {stats['frames_captured']}", (10, 90), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            cv2.putText(frame, f"Dropped: {stats['frames_dropped']} ({stats['drop_rate']:.1f}%)", (10, 120), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            
            threading_status = "ON" if use_threading else "OFF"
            cv2.putText(frame, f"Threading: {threading_status}", (10, 150), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            
            # Display the frame
            cv2.imshow('Optimized GoPro Live Preview', frame)
            
            # Handle key presses
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("Quit requested by user")
                break
            elif key == ord('r'):
                print("Restarting optimized stream connection...")
                opt_cap.release()
                time.sleep(1)
                opt_cap = OptimizedVideoCapture(STREAM_URL, use_threading=use_threading)
                if opt_cap.open():
                    print("✓ Optimized stream reconnected")
                    latency_samples.clear()  # Reset statistics
                else:
                    print("ERROR: Failed to reconnect optimized stream")
                    break
            elif key == ord('t'):
                print(f"Toggling threading mode (currently: {'ON' if use_threading else 'OFF'})")
                use_threading = not use_threading
                opt_cap.release()
                time.sleep(0.5)
                opt_cap = OptimizedVideoCapture(STREAM_URL, use_threading=use_threading)
                if opt_cap.open():
                    print(f"✓ Threading mode: {'ON' if use_threading else 'OFF'}")
                    latency_samples.clear()  # Reset statistics
                else:
                    print("ERROR: Failed to restart with new threading mode")
                    break
            elif key == ord('s'):
                print("\n" + "="*50)
                print("PERFORMANCE STATISTICS")
                print("="*50)
                print(f"Average Latency: {avg_latency:.1f}ms")
                print(f"Min Latency: {min(latency_samples):.1f}ms")
                print(f"Max Latency: {max(latency_samples):.1f}ms")
                print(f"Display FPS: {display_fps:.1f}")
                print(f"Threading: {'Enabled' if use_threading else 'Disabled'}")
                print(f"Total Frames: {stats['frames_captured']}")
                print(f"Dropped Frames: {stats['frames_dropped']} ({stats['drop_rate']:.1f}%)")
                print("="*50 + "\n")
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        print("\nCleaning up...")
        
        # Close Optimized OpenCV
        if opt_cap is not None:
            opt_cap.release()
        cv2.destroyAllWindows()
        print("✓ Optimized OpenCV cleaned up")
        
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
        
        print("\nOptimized preview complete!")
        print("Compare the latency results with the original opencv_live_preview.py")

if __name__ == "__main__":
    main()
