# Go2Kin

Multi-camera GoPro control application for research. Controls up to 4 GoPro Hero 12 cameras via USB using the GoPro HTTP API, with a tkinter GUI.

## Dev Environment

- **OS**: Windows 11
- **Python**: 3.10 in Conda environment `Go2Kin` (`conda activate Go2Kin`)
- **IDE**: VSCode
- **Run**: `python code/go2kin.py`
- **Dependencies**: `pip install -r requirements.txt` (requests, opencv-contrib-python, Pillow, numpy, scipy, pandas, matplotlib, sounddevice)
- **External tools**: `ffmpeg` in PATH (for audio sync; install via `conda install -c conda-forge ffmpeg`)
- **Tests**: `python tests/test_project_manager.py` (run from repo root)

## Project Structure

```
code/
  go2kin.py              # Entry point — loads config, creates ProjectManager + GUI
  audio_sync.py          # Audio-based multi-camera video synchronisation
  camera_profiles.py     # CameraProfileManager (profiles + settings references)
  project_manager.py     # ProjectManager (project/session/trial/subject file hierarchy)
  pose2sim_builder.py    # Build Pose2Sim project dirs + run pipeline
  GUI/
    __init__.py           # Exports Go2KinMainWindow
    main_window.py        # Go2KinMainWindow — tab creation + bottom camera bar
    top_bar.py            # TopBar — persistent project/session/participant selection
    live_preview_tab.py   # LivePreviewTab — camera preview with zoom
    calibration_tab.py    # CalibrationTab — intrinsic/extrinsic calibration + 3D viewer
    recording_tab.py      # RecordingTab — record, download, sync videos
    processing_tab.py     # ProcessingTab — Pose2Sim pipeline execution
    visualisation_tab.py  # VisualisationTab — video playback with keypoint overlays
    components/
      session_trials_list.py   # SessionTrialsList — Canvas-based trial list (shared by Recording + Processing)
      collapsible_section.py   # CollapsibleSection — expandable UI panel
  goproUSB/
    goproUSB.py           # GPcam class (camera HTTP API client)
  calibration/            # Camera calibration (adapted from Caliscope, BSD-2-Clause)
    calibrate.py          # High-level orchestrator (intrinsic → extrinsic → origin)
    persistence.py        # JSON save/load (auto-exports TOML for Pose2Sim)
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
  pose2sim/               # Git submodule (https://github.com/perfanalytics/pose2sim)
config/
  cameras.json            # Main config (serials, settings, recording prefs)
  camera_profiles/        # Per-camera JSON profiles (profile_{serial}.json)
  settings_references/    # Per-model/firmware setting definitions
  calibration/            # Calibration output (charuco_config.json, calibration.json)
  pose2sim_config_template.toml  # Pose2Sim Config.toml template
tools/
  discover_camera_settings.py  # Run once per model/firmware to generate reference
  view_calibration.py     # Standalone 3D viewer for calibration camera positions
  export_toml.py          # Convert calibration.json → Pose2Sim TOML
  audio_sync_test.py      # Audio sync test utility
tests/
  test_project_manager.py  # ProjectManager unit tests
go2kin_config.json         # App config (data_root, serials, last selection) — gitignored
go2kin_config_template.json # Template for go2kin_config.json (tracked in git)
```

## Architecture

- **Go2KinMainWindow** (`GUI/main_window.py`): 5-tab tkinter GUI (Preview, Calibration, Recording, Processing, Visualisation) + persistent TopBar above tabs + fixed bottom camera bar. Starts on Calibration tab.
- **TopBar** (`GUI/top_bar.py`): Persistent project/session/participant dropdowns + calibration status indicator. Always visible above tabs.
- **Bottom camera bar** (`GUI/main_window.py`): Per-camera connect/disconnect toggle, status indicators, battery display. Global resolution/FPS dropdowns apply to all cameras.
- **GPcam** (`goproUSB/goproUSB.py`): HTTP client for one camera. IP derived from serial: `172.2X.1YZ.51:8080`.
- **CameraProfileManager** (`camera_profiles.py`): Singleton managing per-camera profiles and per-model settings references.
- **ProjectManager** (`project_manager.py`): Manages project/session/trial/subject file hierarchy at `data_root`. GUI-agnostic — filesystem and JSON only. See `docs/project_manager.md`.
- **SessionTrialsList** (`GUI/components/session_trials_list.py`): Canvas-based trial list with colored status indicators. Shared by Recording and Processing tabs.
- **LivePreviewCapture** (`GUI/main_window.py`): Threaded OpenCV capture from UDP stream.
- **Audio sync** (`audio_sync.py`): Clap-onset detection + ffmpeg trim. Runs automatically after recording. See `docs/audio_sync_spec.md`.
- **Calibration** (`calibration/`): Charuco-based intrinsic/extrinsic calibration adapted from Caliscope (BSD-2-Clause). Orchestrated by `calibrate.py`.
- **Pose2Sim integration** (`pose2sim_builder.py`): Stages trial data into Pose2Sim directory structure and runs the pipeline. See `docs/pose2sim_integration.md`.
- **Visualisation** (`GUI/visualisation_tab.py`): Video playback with keypoint overlays. See `docs/Visualisation.md`.

## Hardware

4 GoPro Hero 12 cameras:
- C3501326042700 = GoPro 1
- C3501326054100 = GoPro 2
- C3501326054460 = GoPro 3
- C3501326062418 = GoPro 4

## Coding Conventions

- **Keep it simple** — research-focused, not enterprise. Avoid over-engineering.
- **Profile-driven settings** — references define available options, profiles track camera state, GUI populates from both.
- **Error isolation** — one camera's failure must not affect others.
- **Threading model**: GUI thread for display, ThreadPoolExecutor for multi-camera ops, background threads for status polling and frame capture.
- **HTTP timeouts**: 5s for commands, 300s for media downloads.
- **Settings via generic API**: prefer `setSetting(setting_id, option_id)` over legacy convenience methods.

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

- `sys.path.insert()` used for imports — fragile but functional.
- `deleteAllFiles()` uses legacy `/gp/gpControl/` endpoint — works, leave as-is.
- Preview forces 1080p/30fps/Linear — intentional for low-bandwidth positioning.
- Setting 236 (Auto WiFi AP) not in discovery tool but applied on connect.
- `camBusy()`/`encodingActive()` return False on errors (fail-safe design).
- GUI dropdown options for resolution/FPS are hardcoded for Hero 12 + 50Hz anti-flicker. For different cameras or 60Hz, update values in `main_window.py` (bottom camera bar). Invalid selections are caught at runtime (camera returns 403).

## Known Issues / TODO

- **Sync sound** (disabled): Automatic speaker-generated clap playback for hands-free sync. Lab HDMI speaker at ~7m is too quiet for GoPro mics. Needs a louder/closer speaker.
