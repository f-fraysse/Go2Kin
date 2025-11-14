# Go2Kin Project Brief

## Project Overview
Go2Kin is a research-focused Python application for academics/lab users that provides multi-camera GoPro control through USB via a tkinter GUI. The goal is to implement lean and simple multi-camera recording capabilities.

## Core Requirements

### Primary Objectives
- Multi-camera GoPro control through USB using GoPro HTTP API
- Tkinter-based GUI for ease of use
- Support for up to 4 GoPro cameras simultaneously
- Live preview capability for one camera at a time
- Synchronized recording across multiple cameras
- Automatic file download and organization

### Target Hardware
- 4 GoPro Hero 12 cameras with known serial numbers:
  - C3501326042700 = GoPro 1
  - C3501326054100 = GoPro 2  
  - C3501326054460 = GoPro 3
  - C3501326062418 = GoPro 4

### Environment
- Windows 11, Visual Studio Code
- Conda environment "Go2Kin" (Python 3.10)
- Local project folder: D:\PythonProjects\Go2Kin
- PowerShell terminal

### Key Features
1. **Camera Settings Tab**: Connect/configure up to 4 cameras with status indicators
2. **Recording Tab**: Multi-camera synchronized recording with progress tracking
3. **Live Preview Tab**: Real-time preview stream from selected camera

### Success Criteria
- Reliable multi-camera USB connection and control
- Intuitive GUI for non-technical lab users
- Robust file management and organization
- Acceptable live preview latency (~210ms)
- Persistent configuration settings

## Constraints
- Research/academic focus (not enterprise-grade)
- Keep implementation lean and simple
- USB connection only (no WiFi)
- Windows 11 compatibility required
