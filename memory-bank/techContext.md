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
│   ├── go2kin.py              # Main entry point
│   ├── camera_profiles.py     # CameraProfileManager (profiles + references)
│   ├── GUI/
│   │   ├── __init__.py        # Package init (exports Go2KinMainWindow)
│   │   └── main_window.py     # Go2KinMainWindow + LivePreviewCapture
│   └── goproUSB/
│       ├── goproUSB.py        # GPcam class (camera control)
│       ├── README.md
│       └── examples/          # Usage examples (1-3 cameras)
├── config/
│   ├── cameras.json           # Main config (serials, settings, recording)
│   ├── camera_profiles/       # Per-camera JSON profiles
│   │   ├── profile_C3501326042700.json
│   │   ├── profile_C3501326054100.json
│   │   └── profile_C3501326062418.json
│   └── settings_references/   # Per-model/firmware setting definitions
│       ├── README.md
│       └── settings_reference_HERO12_Black_H23_01_02_32_00.json
├── tools/
│   └── discover_camera_settings.py  # Settings discovery utility
├── output/                    # Video recordings destination
├── project docs/              # Reference documentation, API specs
├── memory-bank/               # Project documentation (6 core files)
├── requirements.txt           # Python dependencies
└── .gitignore
```

## Technologies Used

### Core Dependencies (requirements.txt)
- **requests**: HTTP client for GoPro API communication
- **opencv-python**: Video stream capture and processing for live preview
- **Pillow**: Image conversion (PIL → ImageTk for tkinter display)

### Standard Library (no install needed)
- **tkinter**: GUI framework (built-in with Python)
- **concurrent.futures**: ThreadPoolExecutor for multi-camera operations
- **threading**: Background threads (status monitoring, frame capture)
- **queue**: Thread-safe frame queue for live preview
- **json**: Configuration and profile persistence
- **pathlib**: File system operations
- **datetime**: Timestamps
- **time**: Delays and timing

### GoPro Integration
- **openGoPro HTTP API**: Camera control over USB
- **Network Control Model (NCM)**: USB communication protocol
- **MPEG-TS**: Transport stream format for live preview
- **AVC/H264**: Video codec (Hero 12 cameras)

## Technical Constraints

### Hardware
- **USB Bandwidth**: 4 cameras simultaneously may approach USB controller limits
- **Camera Memory**: Limited storage requires post-recording file cleanup
- **Power Management**: USB power may not sustain very long recording sessions

### Software
- **Single Preview**: Only one camera can stream preview at a time
- **Threading Model**: GUI must remain responsive during camera operations
- **Error Recovery**: Network timeouts and camera disconnections handled gracefully
- **Request Timeouts**: 5s for commands, 300s for media downloads

### Performance
- **Live Preview Latency**: 0.5-1s (acceptable for camera positioning)
- **File Download Speed**: Dependent on file size and USB throughput
- **Memory Usage**: Frame queue maxsize=2 prevents buildup

## API Integration Details

### GoPro HTTP API
- **Base URL Pattern**: `http://172.2X.1YZ.51:8080` (X,Y,Z from serial number)
- **Authentication**: None required for USB connections
- **Keep-Alive**: Required every ~30 seconds to maintain connection
- **Status Polling**: Check camBusy() and encodingActive() before operations
- **All requests**: `timeout=5` seconds (media: `timeout=300`)

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

# Digital Zoom
/gopro/camera/digital_zoom?percent=X   # Set zoom (0-100%)

# Media Management
/gopro/media/list                      # Get file list
/videos/DCIM/{dir}/{file}             # Download file
/gp/gpControl/command/storage/delete/all  # Delete all files (legacy endpoint)
```

### Settings on Connect
Applied automatically when camera connects:
```python
settings_on_connect = [
    (175, 1, "Control Mode", "Pro"),
    (121, 4, "Lens", "Linear"),
    (83, 0, "GPS", "Off"),
    (167, 4, "Hindsight", "Off"),
    (135, 0, "Hypersmooth", "Off"),
    (88, 30, "LCD Brightness", "30%"),
    (134, 3, "Anti-Flicker", "50Hz"),      # 50Hz for Australia
    (180, 0, "System Video Mode", "Highest Quality"),
    (236, 0, "Auto WiFi AP", "Off"),
]
```

### Status Monitoring
```python
# Critical status flags from /gopro/camera/state
status['8']  # System Busy (0=ready, 1=busy)
status['10'] # Encoding Active (0=idle, 1=recording)
status['75'] # Zoom Level (0-100%)
```

## Development Patterns

### Threading Architecture
```
Main GUI Thread:     UI updates, user interaction, video display
Camera Threads:      Individual camera operations (connect, record, download)
Status Thread:       Periodic keep-alive and status polling (30s cycle)
Capture Thread:      Background frame reading from UDP stream
```

### Configuration Management
- **cameras.json**: Single config file for serials, UI settings, recording preferences
- **Camera Profiles**: Per-serial JSON files tracking full camera state
- **Settings References**: Per-model/firmware JSON files defining available options
- All managed through `CameraProfileManager` singleton

### Import Pattern
Currently uses `sys.path.insert()` for module resolution:
```python
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'goproUSB'))
from goproUSB import GPcam
```
This is functional but fragile — noted as future improvement candidate.

## Tool Usage Patterns

### Development Workflow
1. **Code in VSCode**: Primary development environment
2. **Test in PowerShell**: Run scripts and test camera connections
3. **Git Version Control**: Track changes (GitHub remote)
4. **Conda Environment**: Isolated Python 3.10 dependencies

### Settings Discovery
Run once per camera model/firmware combination:
```bash
python tools/discover_camera_settings.py C3501326042700
```
Generates reference file, then manually verify resolution names (known truncation issue).
