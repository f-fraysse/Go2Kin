#!/usr/bin/env python3
"""
Go2Kin - Multi-Camera GoPro Control Application

Main entry point for the Go2Kin biomechanics motion capture application.
Stage 1: Multi-camera GoPro control via USB with PyQt6 GUI.
"""

import sys
import logging
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.go2kin.ui.main_window import main

if __name__ == "__main__":
    main()
