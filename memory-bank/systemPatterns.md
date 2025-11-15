# System Patterns

## Architecture Overview

### High-Level System Design
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Tkinter GUI   │◄──►│  goproUSB Class  │◄──►│  GoPro Cameras  │
│   (3 Tabs)      │    │   (HTTP Client)  │    │   (HTTP Server) │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Config Manager  │    │ Threading Pool   │    │ UDP Stream      │
│ (JSON Persist)  │    │ (Concurrent Ops) │    │ (Live Preview)  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Key Technical Decisions

#### Communication Protocol
- **GoPro HTTP API** over USB (NCM protocol)
- **IP Address Pattern**: 172.2X.1YZ.51:8080 (X,Y,Z = last 3 digits of serial)
- **Keep-Alive Required**: Periodic heartbeat to maintain connection
- **USB Control**: Must enable wired USB control before API operations

#### Multi-Camera Coordination
- **ThreadPoolExecutor**: Concurrent operations across cameras
- **Status Synchronization**: Polling-based status updates
- **Error Isolation**: Individual camera failures don't affect others
- **Sequential Setup**: Connect cameras one by one, then coordinate operations

#### Live Preview Architecture (IMPLEMENTED ✅)
- **UDP Server**: App binds to port 8554, camera connects as client
- **MPEG-TS Container**: Transport stream format from camera
- **AVC/H264 Codec**: Video encoding for Hero 12 cameras
- **OpenCV Direct Capture**: `cv2.VideoCapture('udp://0.0.0.0:8554')` handles H.264 stream natively
- **Real-Time Settings Control**: Camera settings changeable during streaming without interruption
- **Digital Zoom Integration**: Live zoom control (0-100%) with immediate visual feedback
- **Single Camera**: Only one preview stream active at a time (by design)
- **Performance**: 0.5-1s latency, acceptable for research applications

## Component Relationships

### Core Classes
```python
GPcam(serial_number)           # Individual camera control
├── HTTP API methods           # Camera commands and settings
├── Status monitoring          # camBusy(), encodingActive()
├── Media management          # Download, delete operations
├── Stream control            # Preview start/stop
└── Digital zoom control      # setDigitalZoom(), getZoomLevel(), zoomIn(), zoomOut()

CameraManager                  # Multi-camera coordination
├── Camera discovery          # Auto-detect connected cameras
├── Status aggregation        # Combined status across cameras
├── Batch operations          # Apply settings to multiple cameras
└── Error handling            # Graceful failure management

StreamProcessor               # Live preview handling
├── UDP socket server         # Receive MPEG-TS data
├── MPEG-TS demuxer          # Extract H264 stream
├── Frame decoder            # OpenCV H264 decoding
└── GUI integration          # Update tkinter Canvas

ConfigManager                 # Settings persistence
├── JSON serialization       # Save/load camera configurations
├── Default values           # Initial setup and fallbacks
├── Validation              # Ensure settings compatibility
└── Migration               # Handle config format changes
```

### Data Flow Patterns

#### Recording Workflow
1. **Setup Phase**: Validate cameras → Apply settings → Create output directory
2. **Recording Phase**: Start all cameras → Monitor status → Show progress
3. **Download Phase**: Stop cameras → Wait for encoding → Download files
4. **Cleanup Phase**: Organize files → Delete from cameras → Update UI

#### Status Monitoring
- **Polling Loop**: Regular keepAlive() calls to each camera
- **State Aggregation**: Combine individual camera states
- **UI Updates**: Reflect status changes in real-time
- **Error Detection**: Identify disconnected or failed cameras

## Critical Implementation Paths

### Camera Connection Sequence
```python
1. GPcam(serial) → Calculate IP from serial number
2. USBenable() → Enable wired USB control
3. keepAlive() → Verify connection established
4. getState() → Check camera ready status
5. Apply settings → Lens, resolution, FPS configuration
```

### Multi-Camera Recording
```python
1. Validate all selected cameras connected
2. Apply settings from Tab 1 to each camera
3. ThreadPoolExecutor.map(shutterStart, cameras)
4. Monitor encoding status across all cameras
5. ThreadPoolExecutor.map(shutterStop, cameras)
6. Wait for all cameras: not camBusy() and not encodingActive()
7. ThreadPoolExecutor.map(mediaDownloadLast, cameras)
```

### Live Preview Stream (IMPLEMENTED ✅)
```python
1. previewStreamStart(port=8554) → Start camera UDP client
2. cv2.VideoCapture('udp://0.0.0.0:8554') → OpenCV handles MPEG-TS/H264 directly
3. cap.read() → Extract frames with automatic decoding
4. Frame overlay → Add status information (frame count, settings, zoom level)
5. cv2.imshow() → Display frames in OpenCV window
6. previewStreamStop() → Clean shutdown
```

### Digital Zoom Control (IMPLEMENTED ✅)
```python
1. setDigitalZoom(percent) → Direct API call with 0-100% range
2. getZoomLevel() → Query current zoom from camera state (status['75'])
3. zoomIn(step=5) → Increment zoom with boundary checking
4. zoomOut(step=5) → Decrement zoom with boundary checking
5. Real-time feedback → Zoom changes visible immediately in stream
6. Boundary handling → Prevents zoom beyond 0-100% limits
```

## Design Patterns in Use

### Observer Pattern
- GUI components observe camera status changes
- Status indicators update automatically when camera state changes
- Progress bars reflect download completion status

### Command Pattern
- Camera operations encapsulated as discrete commands
- Batch operations apply same command to multiple cameras
- Undo/retry capability for failed operations

### Factory Pattern
- Camera instances created based on serial numbers
- Stream processors created based on camera capabilities
- Configuration objects created from JSON data

### Singleton Pattern
- ConfigManager ensures single source of truth for settings
- StreamProcessor prevents multiple preview streams

## GUI Architecture (Implemented)

### 3-Tab Interface Design
1. **Camera Settings Tab**: 4-camera grid with individual configuration panels
   - Real-time status indicators (red/green circles)
   - Serial number configuration with persistence
   - Lens/Resolution/FPS dropdown controls
   - Individual Connect/Disconnect functionality

2. **Live Preview Tab**: Ready for integration with working streaming functionality
   - Camera selector dropdown (GoPro 1-4)
   - Start/Stop preview controls (functionality implemented, needs GUI integration)
   - Video display area (placeholder ready for OpenCV Canvas integration)
   - Zoom controls (slider and +/- buttons for 0-100% range)
   - Stream status indicators (connection, quality, error states)
   - Real-time settings control integration with Tab 1

3. **Recording Tab**: Complete multi-camera recording workflow
   - Output directory selection with file browser
   - Trial name input with session-level auto-increment
   - Camera selection checkboxes (multi-select)
   - Real-time progress logging with timestamps
   - Recording timer display (HH:MM:SS format)
   - Automatic file organization in single trial directory

### Package Structure
```
code/
├── go2kin.py              # Main entry point
├── GUI/
│   ├── __init__.py        # Package initialization
│   └── main_window.py     # Go2KinMainWindow class
└── goproUSB/
    └── goproUSB.py        # GPcam class
```

### Key Implementation Patterns

#### Session-Level Directory Management
- Trial directory created once per recording session
- Auto-increment only at session level (trial_001, trial_001_001, etc.)
- All camera files saved to shared directory
- Prevents per-camera directory proliferation

#### Multi-Threading Architecture
- Main GUI thread for UI responsiveness
- Background status monitoring thread (30-second intervals)
- Recording worker thread for camera operations
- ThreadPoolExecutor for concurrent camera control

#### Configuration Persistence
- JSON-based camera settings storage (`config/cameras.json`)
- Automatic config creation with sensible defaults
- Real-time saving of user changes
- Persistent output directory and trial name settings

## Error Handling Strategy

### Connection Failures
- Retry logic with exponential backoff
- Graceful degradation (continue with available cameras)
- Clear user feedback about failed connections

### Recording Failures
- Individual camera failure isolation
- Partial recording recovery
- Detailed error logging for troubleshooting

### Stream Processing Errors
- Automatic stream restart on decode failures
- Buffer overflow protection
- Frame drop handling for performance
