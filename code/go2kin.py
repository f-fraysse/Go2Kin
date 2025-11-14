#!/usr/bin/env python3
"""
Go2Kin - Multi-Camera GoPro Control Application
Main entry point for the GUI application

Usage: python go2kin.py
"""

import sys
import tkinter as tk
from pathlib import Path

# Add GUI module to path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'GUI'))

def main():
    """Main application entry point"""
    try:
        # Import the main window class
        from GUI import Go2KinMainWindow
        
        # Create the root window
        root = tk.Tk()
        
        # Set window icon (if available)
        try:
            # You can add an icon file later
            # root.iconbitmap('icon.ico')
            pass
        except:
            pass
        
        # Create the main application
        app = Go2KinMainWindow(root)
        
        # Start the GUI event loop
        root.mainloop()
        
    except ImportError as e:
        print(f"Error importing GUI modules: {e}")
        print("Make sure all required dependencies are installed:")
        print("- tkinter (usually included with Python)")
        print("- requests (for GoPro API communication)")
        sys.exit(1)
    except Exception as e:
        print(f"Error starting Go2Kin application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("Go2Kin - Multi-Camera GoPro Control")
    print("====================================")
    print("Starting GUI application...")
    print()
    main()
