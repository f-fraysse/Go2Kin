#!/usr/bin/env python3
"""
Test script for GoPro live preview functionality
Tests the new previewStreamStart/Stop methods and UDP server approach

Usage: Make sure GoPro 1 (serial C3501326042700) is connected via USB

Note: The camera acts as UDP CLIENT and sends data to our UDP SERVER on port 8554
"""

import sys
import time
import socket
import threading
from pathlib import Path

# Add goproUSB to path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'goproUSB'))
from goproUSB import GPcam

# Camera configuration
SNcam1 = 'C3501326042700'  # GoPro 1
STREAM_PORT = 8554
UDP_BUFFER_SIZE = 1024 * 64  # 64KB buffer for UDP packets

class UDPStreamReceiver:
    """UDP server to receive MPEG-TS stream from GoPro camera"""
    
    def __init__(self, port=8554):
        self.port = port
        self.socket = None
        self.running = False
        self.thread = None
        self.packet_count = 0
        self.total_bytes = 0
        
    def start(self):
        """Start UDP server to receive stream"""
        try:
            # Create UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Bind to GoPro network interface (host IP on GoPro network)
            gopro_host_ip = '172.27.100.51'  # Host IP on GoPro 1 network interface
            self.socket.bind((gopro_host_ip, self.port))
            print(f"UDP server listening on {gopro_host_ip}:{self.port}")
            
            self.running = True
            self.thread = threading.Thread(target=self._receive_loop)
            self.thread.daemon = True
            self.thread.start()
            
            return True
            
        except Exception as e:
            print(f"Error starting UDP server: {e}")
            return False
    
    def stop(self):
        """Stop UDP server"""
        self.running = False
        if self.socket:
            self.socket.close()
        if self.thread:
            self.thread.join(timeout=2)
        
        print(f"UDP server stopped. Received {self.packet_count} packets, {self.total_bytes} bytes total")
    
    def _receive_loop(self):
        """Main loop to receive UDP packets"""
        print("Starting UDP receive loop...")
        
        while self.running:
            try:
                # Set socket timeout so we can check self.running periodically
                self.socket.settimeout(1.0)
                
                # Receive UDP packet
                data, addr = self.socket.recvfrom(UDP_BUFFER_SIZE)
                
                self.packet_count += 1
                self.total_bytes += len(data)
                
                # Print progress every 100 packets
                if self.packet_count % 100 == 0:
                    print(f"Received {self.packet_count} packets from {addr}, latest: {len(data)} bytes")
                
                # Here we would normally parse MPEG-TS and extract video frames
                # For now, just verify we're receiving data
                
            except socket.timeout:
                # Timeout is normal, just continue loop
                continue
            except Exception as e:
                if self.running:  # Only print error if we're supposed to be running
                    print(f"Error receiving UDP data: {e}")
                break

def test_preview_stream():
    """Test live preview stream functionality with UDP server"""
    print("=== GoPro Live Preview Test (UDP Server Approach) ===")
    
    # Initialize camera
    print(f"Initializing camera with serial: {SNcam1}")
    cam1 = GPcam(SNcam1)
    
    # Initialize UDP receiver
    udp_receiver = UDPStreamReceiver(STREAM_PORT)
    
    try:
        # Enable USB control
        print("Enabling USB control...")
        response = cam1.USBenable()
        print(f"USB Enable response: {response.status_code}")
        
        # Check camera status
        print("Checking camera status...")
        response = cam1.keepAlive()
        print(f"Keep alive response: {response.status_code}")
        
        # Set video mode
        print("Setting video mode...")
        response = cam1.modeVideo()
        print(f"Video mode response: {response.status_code}")
        
        # Wait for camera to be ready
        print("Waiting for camera to be ready...")
        time.sleep(2)
        
        # Start UDP server first
        print("Starting UDP server...")
        if not udp_receiver.start():
            print("ERROR: Failed to start UDP server")
            return
        
        # Wait a moment for server to be ready
        time.sleep(1)
        
        # Start preview stream
        print(f"Starting preview stream on port {STREAM_PORT}...")
        response = cam1.previewStreamStart(port=STREAM_PORT)
        print(f"Preview stream start response: {response.status_code}")
        
        if response.status_code == 200:
            print("Preview stream started successfully!")
            print("Camera should now be sending UDP packets to our server...")
            
            # Let it run for 10 seconds to collect data
            print("Collecting stream data for 10 seconds...")
            time.sleep(10)
            
            if udp_receiver.packet_count > 0:
                print(f"SUCCESS: Received {udp_receiver.packet_count} UDP packets!")
                print("This confirms the camera is sending MPEG-TS data to our UDP server.")
                print("Next step would be to parse MPEG-TS and decode H264 frames.")
            else:
                print("WARNING: No UDP packets received.")
                print("Possible issues:")
                print("1. Camera is not streaming")
                print("2. Firewall blocking UDP traffic")
                print("3. Wrong port or network configuration")
        
        else:
            print(f"ERROR: Failed to start preview stream (status: {response.status_code})")
            
    except Exception as e:
        print(f"ERROR: {e}")
        
    finally:
        # Stop UDP server
        print("Stopping UDP server...")
        udp_receiver.stop()
        
        # Stop preview stream
        print("Stopping preview stream...")
        try:
            response = cam1.previewStreamStop()
            print(f"Preview stream stop response: {response.status_code}")
        except Exception as e:
            print(f"Error stopping stream: {e}")
        
        # Disable USB control
        print("Disabling USB control...")
        try:
            response = cam1.USBdisable()
            print(f"USB disable response: {response.status_code}")
        except Exception as e:
            print(f"Error disabling USB: {e}")

def test_delete_all_files():
    """Test the deleteAllFiles functionality"""
    print("\n=== Testing Delete All Files ===")
    
    cam1 = GPcam(SNcam1)
    
    try:
        # Enable USB control
        cam1.USBenable()
        time.sleep(1)
        
        # Get media list before deletion
        print("Getting media list before deletion...")
        response = cam1.getMediaList()
        if response.status_code == 200:
            media_data = response.json()
            file_count = sum(len(folder['fs']) for folder in media_data.get('media', []))
            print(f"Files on camera before deletion: {file_count}")
        
        # Delete all files
        print("Deleting all files...")
        response = cam1.deleteAllFiles()
        print(f"Delete all files response: {response.status_code}")
        
        if response.status_code == 200:
            print("Delete all files command sent successfully!")
            
            # Wait for deletion to complete
            time.sleep(2)
            
            # Check media list after deletion
            response = cam1.getMediaList()
            if response.status_code == 200:
                media_data = response.json()
                file_count = sum(len(folder['fs']) for folder in media_data.get('media', []))
                print(f"Files on camera after deletion: {file_count}")
        else:
            print(f"ERROR: Delete all files failed (status: {response.status_code})")
            
    except Exception as e:
        print(f"ERROR: {e}")
    
    finally:
        cam1.USBdisable()

if __name__ == "__main__":
    print("GoPro Live Preview Test Script")
    print("Make sure GoPro 1 is connected via USB and powered on")
    print()
    
    # Test preview stream
    test_preview_stream()
    
    # Ask user if they want to test file deletion
    print("\n" + "="*50)
    response = input("Do you want to test delete all files? (y/N): ")
    if response.lower() == 'y':
        test_delete_all_files()
    
    print("\nTest completed!")
