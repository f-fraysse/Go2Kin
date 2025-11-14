# Technical Context

## Development Environment

### Platform & Tools
- **Operating System**: Windows 11
- **IDE**: Visual Studio Code
- **Terminal**: PowerShell (default)
- **Python Environment**: Conda environment "Go2Kin" (Python 3.10)
- **Project Location**: D:\PythonProjects\Go2Kin

### Project Structure
```
Go2Kin/
├── code/
│   └── goproUSB/
│       ├── goproUSB.py          # Core camera control class
│       ├── README.md
│       └── examples/
│           ├── goproRecordVideo.py
│           ├── goproRecordVideo_twoCameras.py
│           └── goproRecordVideo_threeCameras.py  # Tested working
├── output/                      # Video files destination
├── project docs/
│   ├── Cline_GUI_initial_prompt.md
│   ├── openGoPro api specs.json
│   └── live preview specs table.md
├── memory-bank/                 # Project documentation
└── config/                      # Configuration files (to be created)
```

## Technologies Used

### Core Dependencies
- **tkinter**: GUI framework (built-in with Python)
- **requests**: HTTP client for GoPro API communication
- **concurrent.futures**: Multi-threading for camera operations
- **json**: Configuration persistence
- **datetime**: Timestamp handling
- **pathlib**: File system operations

### Additional Dependencies (Required)
- **opencv-python**: Video stream processing and H264 decoding
- **numpy**: Array operations for video frames
- **socket**: UDP server for live preview streams

### GoPro Integration
- **openGoPro API**: HTTP-based camera control
- **Network Control Model (NCM)**: USB communication protocol
- **MPEG-TS**: Transport stream format for live preview
- **AVC/H264**: Video codec (Hero 12 cameras)

## Technical Constraints

### Hardware Limitations
- **USB Bandwidth**: 4 cameras simultaneously may approach USB controller limits
- **Camera Memory**: Limited storage requires regular file cleanup
- **Power Management**: USB power may not sustain long recording sessions

### Software Constraints
- **Single Preview**: Only one camera can stream preview at a time. May explore multi preview at a later stage. May explore preview while recording at a later stage.
- **Threading Model**: GUI must remain responsive during camera operations
- **Error Recovery**: Network timeouts and camera disconnections must be handled gracefully

### Performance Considerations
- **Live Preview Latency**: ~210ms minimum (acceptable for positioning)
- **File Download Speed**: Large video files may take significant time
- **Memory Usage**: Video frame buffers require careful management

## API Integration Details

### GoPro HTTP API
- **Base URL Pattern**: `http://172.2X.1YZ.51:8080` (X,Y,Z from serial number)
- **Authentication**: None required for USB connections
- **Keep-Alive**: Required every ~60 seconds to maintain connection
- **Status Polling**: Regular checks for camera busy/encoding states

### Key API Endpoints
```python
# Connection Control
/gopro/camera/control/wired_usb?p=1    # Enable USB control
/gopro/camera/keep_alive               # Maintain connection

# Recording Control  
/gopro/camera/shutter/start            # Start recording
/gopro/camera/shutter/stop             # Stop recording

# Settings
/gopro/camera/setting?setting=X&option=Y  # Configure camera

# Preview Stream
/gopro/camera/stream/start?port=8554   # Start UDP stream
/gopro/camera/stream/stop              # Stop stream

# Media Management
/gopro/media/list                      # Get file list
/videos/DCIM/{dir}/{file}             # Download file
/gopro/camera/delete/all              # Delete all files
```

### Status Monitoring
```python
# Critical status flags from /gopro/camera/state
status['8']  # System Busy (0=ready, 1=busy)
status['10'] # Encoding Active (0=idle, 1=recording)
```

## Development Patterns

### Error Handling Strategy
- **Connection Timeouts**: 5-second timeout for HTTP requests
- **Retry Logic**: 3 attempts with exponential backoff
- **Graceful Degradation**: Continue with available cameras if some fail
- **User Feedback**: Clear error messages and status indicators

### Threading Architecture
```python
# Main GUI Thread: UI updates and user interaction
# Camera Threads: Individual camera operations (connect, record, download)
# Status Thread: Periodic keep-alive and status polling
# Stream Thread: UDP data reception and frame processing
```

### Configuration Management
```json
{
  "cameras": {
    "1": {"serial": "C3501326042700", "lens": "Narrow", "resolution": "1080p", "fps": 30},
    "2": {"serial": "C3501326054100", "lens": "Narrow", "resolution": "1080p", "fps": 30},
    "3": {"serial": "C3501326054460", "lens": "Narrow", "resolution": "1080p", "fps": 30},
    "4": {"serial": "C3501326062418", "lens": "Narrow", "resolution": "1080p", "fps": 30}
  },
  "recording": {
    "output_directory": "D:\\PythonProjects\\Go2Kin\\output",
    "last_trial_name": "trial_001"
  }
}
```

## Tool Usage Patterns

### Development Workflow
1. **Code in VSCode**: Primary development environment
2. **Test in PowerShell**: Run scripts and test camera connections
3. **Git Version Control**: Track changes and collaborate
4. **Conda Environment**: Isolated Python dependencies

### Testing Strategy
- **Unit Tests**: Individual camera operations
- **Integration Tests**: Multi-camera coordination
- **Hardware Tests**: Real camera connections and recording
- **GUI Tests**: User interaction workflows

### Debugging Approach
- **HTTP Logging**: Capture API requests/responses
- **Status Monitoring**: Track camera state changes
- **Performance Profiling**: Monitor threading and memory usage
- **Error Logging**: Detailed failure information for troubleshooting
