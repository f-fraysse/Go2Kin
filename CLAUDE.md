# Go2Kin

Multi-camera GoPro control application for research. Controls up to 4 GoPro Hero 12 cameras via USB using the GoPro HTTP API, with a tkinter GUI.

## Dev Environment

- **OS**: Windows 11
- **Python**: 3.10 in Conda environment `Go2Kin` (`conda activate Go2Kin`)
- **IDE**: VSCode
- **Run**: `python code/go2kin.py`
- **Dependencies**: `pip install -r requirements.txt` (requests, opencv-contrib-python, Pillow, numpy, scipy, pandas)
- **External tools**: `ffmpeg` in PATH (for audio sync feature; install via `conda install -c conda-forge ffmpeg`)

## Project Structure

```
code/
  go2kin.py              # Entry point
  audio_sync.py          # Audio-based multi-camera video synchronisation
  camera_profiles.py     # CameraProfileManager (profiles + settings references)
  GUI/
    __init__.py           # Exports Go2KinMainWindow
    main_window.py        # Go2KinMainWindow + LivePreviewCapture
    calibration_tab.py    # CalibrationTab (tkinter calibration UI)
  goproUSB/
    goproUSB.py           # GPcam class (camera HTTP API client)
  calibration/            # Camera calibration (adapted from Caliscope, BSD-2-Clause)
    __init__.py
    charuco.py            # Charuco board definition
    charuco_tracker.py    # Corner detection (cv2.aruco.CharucoDetector)
    data_types.py         # PointPacket, CameraData, CameraArray, ImagePoints, WorldPoints, StereoPair
    frame_selector.py     # Smart frame selection (orientation + spatial coverage)
    intrinsic.py          # Intrinsic calibration (cv2.calibrateCamera)
    video_processor.py    # MP4 → ImagePoints bridge
    extrinsic.py          # PoseNetworkBuilder (PnP + relative poses + outlier rejection)
    paired_pose_network.py  # Stereo pair graph with bridging
    triangulation.py      # Pure-numpy DLT triangulation
    reprojection.py       # Reprojection error computation
    reprojection_report.py  # ReprojectionReport dataclass
    bundle_adjustment.py  # PointDataBundle + scipy least_squares optimization
    alignment.py          # Umeyama similarity transform
    scale_accuracy.py     # Volumetric scale error metrics
    calibrate.py          # High-level orchestrator (intrinsic, extrinsic, origin)
    persistence.py        # JSON save/load for calibration (auto-exports TOML on save)
config/
  cameras.json            # Main config (serials, settings, recording prefs)
  camera_profiles/        # Per-camera JSON profiles (profile_{serial}.json)
  settings_references/    # Per-model/firmware setting definitions
  calibration/            # Calibration output (charuco_config.json, calibration.json)
tools/
  discover_camera_settings.py  # Run once per model/firmware to generate reference
  test_video_quality.py        # Easy Mode vs Pro Mode quality comparison test
  export_toml.py               # Convert calibration.json → Pose2Sim TOML
output/                   # Recording output directory
memory-bank/              # Legacy project documentation
```

## Architecture

- **GPcam** (`goproUSB.py`): HTTP client for one camera. IP derived from serial: `172.2X.1YZ.51:8080`
- **CameraProfileManager** (`camera_profiles.py`): Singleton managing per-camera profiles and per-model settings references
- **Go2KinMainWindow** (`GUI/main_window.py`): 4-tab tkinter GUI (Settings, Preview, Recording, Calibration)
- **LivePreviewCapture** (`GUI/main_window.py`): Threaded OpenCV capture from UDP stream

## Hardware

4 GoPro Hero 12 cameras:
- C3501326042700 = GoPro 1
- C3501326054100 = GoPro 2
- C3501326054460 = GoPro 3
- C3501326062418 = GoPro 4

## Coding Conventions

- **Keep it simple** — research-focused, not enterprise. Avoid over-engineering.
- **Profile-driven settings** — references define available options, profiles track camera state, GUI populates from both
- **Error isolation** — one camera's failure must not affect others
- **Threading model**: GUI thread for display, ThreadPoolExecutor for multi-camera ops, background threads for status polling and frame capture
- **HTTP timeouts**: 5s for commands, 300s for media downloads
- **Settings via generic API**: prefer `setSetting(setting_id, option_id)` over legacy convenience methods

## GoPro API Essentials

```
# Connection
/gopro/camera/control/wired_usb?p=1    # Enable USB control
/gopro/camera/keep_alive               # Heartbeat (every 30s)

# Recording
/gopro/camera/shutter/start
/gopro/camera/shutter/stop

# Settings
/gopro/camera/setting?setting=X&option=Y

# Preview
/gopro/camera/stream/start?port=8554   # UDP stream
/gopro/camera/stream/stop

# Media
/gopro/media/list
/videos/DCIM/{dir}/{file}              # Download
/gp/gpControl/command/storage/delete/all  # Delete (legacy endpoint)
```

## Known Quirks

- `sys.path.insert()` used for imports — fragile but functional
- `deleteAllFiles()` uses legacy `/gp/gpControl/` endpoint — works, leave as-is
- Preview forces 1080p/30fps/Linear — intentional for low-bandwidth positioning
- Setting 236 (Auto WiFi AP) not in discovery tool but applied on connect
- `camBusy()`/`encodingActive()` return False on errors (fail-safe design)
- **GUI dropdown options are hardcoded for Hero 12 + 50Hz anti-flicker**: Resolution (1080, 2.7K, 4K) and FPS (25, 50, 100, 200) in `main_window.py` lines ~280/292. For different cameras or 60Hz anti-flicker, update these values. Invalid selections are caught at runtime (camera returns 403 with valid options popup).

## Audio Sync Feature

The "Synchronise Video Files" button in the Recording tab aligns multi-camera recordings using full audio cross-correlation:
1. User selects a trial folder containing 2 or more MP4 files
2. Extracts first 3 seconds of audio from each file (ffmpeg pipe → numpy)
3. Full cross-correlation (`scipy.signal.correlate`) of entire audio signals to find precise time offsets
4. Reference = camera that started recording last (largest offset). Other files trimmed from start to align
5. All files trimmed to shortest common duration (time-based)
6. Frame equalization: counts frames in each output, trims excess files to the minimum frame count (`-frames:v N -c copy`)
7. Output: `synced/` subfolder with trimmed files + `stitched_videos.mp4` (auto-sized grid preview, 480x480 per camera) + `audio_waveforms.png` (diagnostic plot)
8. Uses ffmpeg stream-copy for trimming (no re-encoding, lossless). Stitched preview re-encodes at low resolution.

## Camera Calibration

The Calibration tab (4th tab) provides intrinsic and extrinsic camera calibration using Charuco board detection. Code adapted from the Caliscope project (BSD-2-Clause, Mac Prible).

### Dependencies
- `opencv-contrib-python` (replaces `opencv-python` — superset, needed for `cv2.aruco`)
- `pandas` (for ImagePoints/WorldPoints DataFrames)

### Default Charuco Board
7x5, A1 paper (59.4x84.1cm), 11.70cm squares, DICT_4X4_50, aruco_scale=0.75

### Calibration Workflow
1. **Charuco config**: Set board parameters in Calibration tab (or accept defaults). Print board, measure actual square size.
2. **Intrinsic**: For each camera, select a video of charuco board → "Calibrate" → verify RMSE < 1.0px
3. **Extrinsic**: Record all cameras simultaneously with charuco board visible. Audio sync → synced/ folder. Select synced folder → "Calibrate Extrinsics" → verify 3D camera positions
4. **Set Origin**: Stand charuco vertically in portrait mode at lab origin (origin corner 790mm above floor), take short recording. Select folder → "Set Origin". Can also be re-run after loading a saved calibration (no need to redo extrinsic).
5. **Save**: Save calibration to `config/calibration/calibration.json` (also auto-generates `camera_array_go2kin.toml` for Pose2Sim)

### Pipeline Architecture
```
Intrinsic: Video → CharucoTracker → PointPackets → frame_selector → cv2.calibrateCamera
Extrinsic: Synced videos → PnP per camera → relative poses → IQR outlier rejection
           → quaternion averaging → stereo pair graph (with bridging)
           → anchor selection → global poses → DLT triangulation
           → bundle adjustment (scipy least_squares) → Umeyama alignment
```

### Global Coordinate System (after Set Origin)
- **X** = along charuco rows (horizontal, short axis on default 7×5 board)
- **Y** = along board normal (horizontal, perpendicular to board surface)
- **Z** = up (vertical). Auto-corrected: if Umeyama produces Z-down, a 180° rotation around X is applied.
- **Origin** = floor below the first interior corner of the charuco board (adjacent to ArUco marker ID 0). The board's origin corner is at (0, 0, 0.790).

### File-to-Camera Mapping
Synced folder MP4 filenames must follow `{trial}_GP{N}.mp4` convention (e.g., `Trial1_GP1.mp4`). The parser extracts camera number from the `_GP{N}` suffix. Files `stitched_videos.mp4` and `timestamps.csv` are automatically skipped.

## Known Issues / TODO

- **Video quality investigation (paused)**: Downloaded videos appear smoothed/processed. Confirmed the correct MP4 is downloaded (not LRV). Added High bitrate (182), 8-Bit depth (183), and Standard profile (184) to connect settings. Protune settings (Sharpness 117, Color 116, etc.) are not officially exposed via the HTTP API. Next step: run `tools/test_video_quality.py` to compare Easy Mode vs Pro Mode output, and/or set Protune options manually on camera LCD.
