# System Patterns

## Architecture Overview

### High-Level System Design
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Tkinter GUI   │◄──►│  GPcam Class     │◄──►│  GoPro Cameras  │
│ Go2KinMainWindow│    │   (HTTP Client)  │    │   (HTTP Server) │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ CameraProfile   │    │ Threading Pool   │    │ UDP Stream      │
│   Manager       │    │ (Concurrent Ops) │    │ (Live Preview)  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │
         ▼
┌─────────────────┐
│ JSON Config     │
│ (cameras.json)  │
└─────────────────┘
```

### Key Technical Decisions

#### Communication Protocol
- **GoPro HTTP API** over USB (NCM protocol)
- **IP Address Pattern**: 172.2X.1YZ.51:8080 (X,Y,Z = last 3 digits of serial)
- **Keep-Alive Required**: Periodic heartbeat every 30s to maintain connection
- **USB Control**: Must enable wired USB control before API operations
- **Request Timeouts**: 5s default, 300s for media downloads

#### Multi-Camera Coordination
- **ThreadPoolExecutor**: Concurrent operations across cameras
- **Status Synchronization**: Polling-based status updates
- **Error Isolation**: Individual camera failures don't affect others
- **Sequential Setup**: Connect cameras one by one, then coordinate operations

#### Live Preview Architecture
- **UDP Stream**: Camera sends to port 8554, app captures via OpenCV
- **MPEG-TS Container**: Transport stream format from camera
- **AVC/H264 Codec**: Video encoding for Hero 12 cameras
- **OpenCV Direct Capture**: `cv2.VideoCapture('udp://0.0.0.0:8554')` handles H.264 stream natively
- **Threaded Capture**: Background thread reads frames, GUI thread displays
- **Digital Zoom Integration**: Live zoom control (0-100%) with immediate visual feedback
- **Single Camera**: Only one preview stream active at a time (by design)
- **Fixed Preview Settings**: 1080p/30fps/Linear forced for positioning (intentional)
- **Performance**: 0.5-1s latency, acceptable for research applications

## Actual Component Structure

### Core Classes (as implemented)
```python
GPcam(serial_number)              # Individual camera control (goproUSB.py)
├── HTTP API methods              # All with 5s timeout
├── Status monitoring             # camBusy(), encodingActive() with error handling
├── Media management              # Download (300s timeout), delete operations
├── Stream control                # streamStart(port), streamStop()
├── Digital zoom control          # setDigitalZoom(), getZoomLevel()
└── Generic settings API          # setSetting(), querySetting()

CameraProfileManager              # Profile & reference management (camera_profiles.py)
├── load/save_camera_profile()    # Per-camera JSON profiles
├── load_settings_reference()     # Per-model/firmware references (cached)
├── create_or_update_profile()    # Parse state into human-readable format
├── get_setting_options()         # Available options for a setting
└── validate_setting_value()      # Check if value is valid

Go2KinMainWindow                   # Main GUI class (main_window.py)
├── Camera connection/disconnect   # With profile integration
├── Settings tab (Tab 1)          # 4-camera grid, dropdowns from profiles
├── Live Preview tab (Tab 2)      # Streaming with zoom controls
├── Recording tab (Tab 3)         # Multi-camera recording workflow
├── Status monitoring thread       # 30s keepAlive cycle
└── Configuration persistence      # cameras.json save/load

LivePreviewCapture                 # Threaded video capture (main_window.py)
├── start_capture()               # Open optimized VideoCapture
├── _capture_frames()             # Background thread, frame queue
├── get_latest_frame()            # Latest frame for display
└── stop_capture()                # Cleanup
```

### Package Structure
```
Go2Kin/
├── code/
│   ├── go2kin.py              # Main entry point
│   ├── camera_profiles.py     # CameraProfileManager class
│   ├── GUI/
│   │   ├── __init__.py        # Package initialization
│   │   └── main_window.py     # Go2KinMainWindow + LivePreviewCapture
│   └── goproUSB/
│       ├── goproUSB.py        # GPcam class
│       ├── README.md
│       └── examples/
├── config/
│   ├── cameras.json           # Main config (serials, settings, recording)
│   ├── camera_profiles/       # Per-camera profile JSONs
│   └── settings_references/   # Per-model/firmware reference JSONs
├── tools/
│   └── discover_camera_settings.py  # Settings discovery utility
├── output/                    # Recording output directory
├── memory-bank/               # Project documentation
├── project docs/              # Reference documentation
└── requirements.txt           # Python dependencies
```

## Data Flow Patterns

### Camera Connection Sequence
```
1. GPcam(serial) → Calculate IP from serial number
2. USBenable() → Enable wired USB control
3. keepAlive() → Verify connection established
4. getCameraInfo() → Get model, firmware, serial
5. Load settings reference for model/firmware
6. modeVideo() → Force video mode
7. Apply settings_on_connect (Pro, Linear, GPS off, etc.)
8. getState() → Query full camera state
9. Restore saved zoom level from profile
10. create_or_update_profile() → Parse state, save profile
11. populate_dropdowns_from_profile() → Update GUI
```

### Recording Workflow
```
1. Validate selected cameras are connected
2. Create trial directory from trial name
3. For each camera (ThreadPoolExecutor):
   a. modeVideo()
   b. Apply resolution, FPS, lens from profile
   c. Apply zoom from profile
   d. shutterStart()
4. Wait for stop signal (user clicks Stop)
5. For each camera (ThreadPoolExecutor):
   a. shutterStop()
   b. Wait: not camBusy() and not encodingActive()
   c. mediaDownloadLast() → save to trial_dir
   d. deleteAllFiles() → cleanup camera storage
6. Auto-increment trial name
```

### Live Preview Stream
```
1. Apply fixed settings (1080p, 30fps, Linear)
2. Restore saved zoom from profile
3. streamStart(port=8554) → Camera starts UDP stream
4. LivePreviewCapture opens cv2.VideoCapture('udp://0.0.0.0:8554')
5. Background thread: cap.read() → frame_queue (maxsize=2)
6. GUI thread: get_latest_frame() → resize → ImageTk → display (~30 FPS)
7. On stop: cleanup capture → streamStop() → reset UI
```

## Design Patterns in Use

### Singleton Pattern
- `CameraProfileManager` via `get_profile_manager()` global instance
- Ensures single source of truth for profile operations

### Observer-like Pattern
- Camera status changes trigger `update_camera_status()` which updates:
  - Visual indicator (red/green circle)
  - Preview camera dropdown
- Recording state changes update UI buttons and timer

### Producer-Consumer Pattern
- `LivePreviewCapture._capture_frames()` produces frames into queue
- `update_video_display()` consumes frames from queue for display
- Queue maxsize=2 prevents memory buildup (old frames dropped)

### Profile-Driven Configuration
- Settings reference (per model/firmware) defines what's available
- Camera profile (per serial) tracks current state
- GUI dropdowns populated from reference, values from profile
- Changes applied immediately and persisted to profile

## Configuration Architecture

### Single Config File: `config/cameras.json`
```json
{
  "cameras": {
    "1": {"serial": "C3501326042700", "lens": "Linear", "resolution": "1080", "fps": 30}
  },
  "recording": {
    "output_directory": "D:\\PythonProjects\\Go2Kin\\output",
    "last_trial_name": "trial_001"
  }
}
```

### Camera Profiles: `config/camera_profiles/profile_{serial}.json`
- Full parsed settings with human-readable names
- Current zoom level
- Last connected timestamp
- Reference to settings reference file

### Settings References: `config/settings_references/settings_reference_{model}_{firmware}.json`
- All available settings and their options
- Status names for human-readable display
- Generated by `tools/discover_camera_settings.py`

## Error Handling Strategy

### HTTP Request Robustness
- All requests have `timeout=5` (media: `timeout=300`)
- `camBusy()` and `encodingActive()` return False on communication errors (fail-safe)
- `mediaDownloadLast()` has 60s timeout on encoding wait loop

### Connection Failures
- Clear user feedback via log messages and error dialogs
- Camera connection failures don't affect other cameras
- Status monitoring auto-detects disconnected cameras

### Recording Failures
- Individual camera failure isolation via ThreadPoolExecutor
- 5-minute timeout on download operations
- Graceful cleanup on window close (stops recording, disconnects cameras)
