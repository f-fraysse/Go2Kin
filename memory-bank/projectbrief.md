# Go2Kin Project Brief

## Project Overview
Go2Kin is a research-focused Python application for biomechanics markerless motion capture, designed for academics and lab users. The project prioritizes clarity over enterprise-grade robustness and maintains a lean, hackable implementation.

## Core Requirements
- PyQt6-based GUI covering 6 pipeline parts (long-term)
- Current scope (Stage 1): Multi-camera GoPro control via USB
- Modular internal structure within single repository
- Windows 11 environment with Conda "Go2Kin" (Python 3.10)
- Working directory: D:\PythonProjects\Go2Kin

## Stage 1 Scope: GoPro Control GUI
**Objective**: Implement multi-camera GoPro control through USB using existing goproUSB module with minimal PyQt GUI.

**Target Hardware**: 4 GoPro HERO12 cameras with known serials:
- C3501326042700 = GoPro 1
- C3501326054100 = GoPro 2  
- C3501326054460 = GoPro 3
- C3501326062418 = GoPro 4

**GUI Structure**: 3-tab interface
1. Camera Settings: Connect/configure up to 4 cameras
2. Live Preview: Webcam mode with stream display
3. Recording: Synchronized recording with trial management

## Success Criteria
- Functional multi-camera control interface
- Reliable synchronized recording capability
- Proper file management and organization
- Responsive UI with threaded operations
- Configuration persistence between sessions

## Technical Constraints
- Leverage existing goproUSB module without modification
- Maintain separation of pipeline parts for future expansion
- Keep dependencies minimal (ask before adding packages)
- Use established IP addressing scheme: 172.2X.1YZ.51
