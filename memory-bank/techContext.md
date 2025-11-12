# Go2Kin Technical Context

## Development Environment
- **OS**: Windows 11
- **IDE**: Visual Studio Code
- **Shell**: PowerShell (VS Code terminal)
- **Python**: 3.10 via Conda environment "Go2Kin"
- **Working Directory**: D:\PythonProjects\Go2Kin

## Core Technologies

### GUI Framework
- **PyQt6**: Primary GUI framework (already installed)
- **QWebEngineView**: For live camera stream display
- **QThreadPool**: For non-blocking camera operations
- **Signal/Slot**: For thread-safe communication

### Camera Control
- **goproUSB Module**: Existing working implementation
  - HTTP API communication with GoPro HERO12 cameras
  - IP addressing: `172.2{last_digit}.1{last_two_digits}.51`
  - USB control mode for camera settings
  - Webcam mode for live streaming
  - Media download functionality

### Data Management
- **JSON**: Configuration persistence (cameras.json)
- **Requests**: HTTP communication (via goproUSB)
- **Concurrent.futures**: Multi-camera operations
- **Pathlib**: File system operations

## Architecture Patterns

### Threading Strategy
- **Main Thread**: GUI operations only
- **QRunnable Workers**: All camera HTTP calls
- **QThreadPool**: Managed worker execution
- **Signals**: Thread-safe status updates

### Configuration Management
- **JSON Persistence**: Camera settings and preferences
- **Default Values**: Pre-populated camera serials and settings
- **Validation**: Input validation with error recovery
- **Auto-save**: Immediate persistence of user changes

### Error Handling
- **Graceful Degradation**: Continue operation with partial camera failures
- **User Feedback**: Clear error messages and status indicators
- **Retry Logic**: Automatic retry for transient network issues
- **Logging**: Comprehensive logging for debugging

## Hardware Integration

### GoPro HERO12 Cameras
- **Serial Numbers**: 
  - C3501326042700 (GoPro 1)
  - C3501326054100 (GoPro 2)
  - C3501326054460 (GoPro 3)
  - C3501326062418 (GoPro 4)
- **Connection**: USB-C for control, WiFi for streaming
- **API**: HTTP REST API via goproUSB wrapper

### Network Configuration
- **IP Calculation**: Automatic from serial number
- **Port**: Standard HTTP (80) and streaming (8080)
- **Protocol**: HTTP GET requests for all operations

## File Organization

### Project Structure
```
Go2Kin/
├── src/go2kin/          # Main application package
├── config/              # Configuration files
├── goproUSB/           # Existing camera control module
├── output/             # Default recording output
└── memory-bank/        # Project documentation
```

### Dependencies
- **Minimal Approach**: Ask before adding new packages
- **Current**: PyQt6, requests (via goproUSB), standard library
- **Future Considerations**: opencv-python, numpy (for later pipeline stages)

## Development Constraints
- **No Modification**: goproUSB module used as-is
- **Windows Specific**: File paths and shell commands
- **Single Repository**: All pipeline parts in one repo
- **Modular Design**: Clear separation between pipeline stages
