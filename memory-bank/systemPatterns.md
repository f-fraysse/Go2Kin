# Go2Kin System Patterns

## Architecture Overview

### Component Hierarchy
```
MainWindow (QMainWindow)
├── CameraManager (Coordination Layer)
│   ├── GPcamController[1-4] (Individual Camera Wrappers)
│   │   └── GPcam (goproUSB Module)
│   └── ConfigManager (Settings Persistence)
├── CameraSettingsTab (QWidget)
├── LivePreviewTab (QWidget)
└── RecordingTab (QWidget)
```

## Core Design Patterns

### Controller Pattern
**GPcamController**: Wraps each GPcam instance with:
- Thread-safe operation queuing
- Status monitoring and caching
- Signal emission for UI updates
- Error handling and retry logic

**CameraManager**: Coordinates multiple controllers:
- Bulk operations (start/stop all cameras)
- Configuration management
- Inter-camera synchronization
- Resource allocation

### Observer Pattern
**Signal/Slot Communication**:
- `statusChanged(camera_id, status)`: Camera connectivity updates
- `recordingStarted(camera_id)`: Recording state changes
- `downloadProgress(camera_id, progress)`: File transfer updates
- `errorOccurred(camera_id, error_msg)`: Error notifications

### Worker Pattern
**QRunnable Workers** for all blocking operations:
- Camera HTTP requests
- File downloads
- Status polling
- Configuration changes

### State Management
**Camera States**:
- `DISCONNECTED`: No communication established
- `CONNECTED`: Basic communication working
- `READY`: Configured and ready for operations
- `RECORDING`: Currently recording video
- `DOWNLOADING`: Transferring files
- `ERROR`: Requires user intervention

## Key Implementation Patterns

### IP Address Calculation
```python
def calculate_ip(serial_number):
    """Convert serial to IP: 172.2X.1YZ.51"""
    last_digit = serial_number[-1]
    last_two = serial_number[-2:]
    return f"172.2{last_digit}.1{last_two}.51"
```

### Configuration Persistence
```python
# Default camera configuration
DEFAULT_CAMERAS = {
    "GP1": {"serial": "C3501326042700", "lens": "Narrow", "resolution": "1080p", "fps": 30},
    "GP2": {"serial": "C3501326054100", "lens": "Narrow", "resolution": "1080p", "fps": 30},
    "GP3": {"serial": "C3501326054460", "lens": "Narrow", "resolution": "1080p", "fps": 30},
    "GP4": {"serial": "C3501326062418", "lens": "Narrow", "resolution": "1080p", "fps": 30}
}
```

### Threading Safety
- All camera operations via QThreadPool
- UI updates only on main thread via signals
- Shared state protected by proper synchronization
- Worker completion handled through callbacks

### Error Recovery
**Graceful Degradation**:
- Individual camera failures don't stop other cameras
- Automatic retry for transient network issues
- Clear user feedback for persistent problems
- Fallback options for critical operations

**Status Monitoring**:
- Periodic keepAlive calls to maintain connection
- Real-time status indicators in UI
- Automatic reconnection attempts
- User-initiated manual recovery options

## File Organization Patterns

### Trial Management
```
output/
├── trial_001/
│   ├── trial_001_GP1.mp4
│   ├── trial_001_GP2.mp4
│   ├── trial_001_GP3.mp4
│   └── trial_001_GP4.mp4
└── trial_002/
    └── ...
```

### Auto-incrementing Logic
- Check existing trial directories
- Find highest numeric suffix
- Increment for new trials
- Handle user-specified names

### Configuration Structure
```json
{
  "cameras": {
    "GP1": {"serial": "...", "settings": {...}},
    "GP2": {"serial": "...", "settings": {...}}
  },
  "recording": {
    "output_directory": "D:/PythonProjects/Go2Kin/output",
    "last_trial_number": 5
  },
  "ui": {
    "window_geometry": "...",
    "selected_cameras": ["GP1", "GP2"]
  }
}
```

## Critical Implementation Details

### USB/Webcam Mode Management
1. **Recording Mode**: USB enabled, webcam disabled
2. **Preview Mode**: USB disabled, webcam enabled
3. **Transition**: Always disable current mode before enabling new mode
4. **Error Handling**: Restore previous state on failure

### Synchronization Strategy
- Use threading.Event for coordination
- Start all cameras within tight time window
- Monitor for successful start before proceeding
- Handle partial failures gracefully

### Resource Management
- Limit concurrent operations per camera
- Queue operations when camera busy
- Clean up resources on application exit
- Handle interrupted operations
