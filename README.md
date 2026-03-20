# Go2Kin
WIP

Multi-camera GoPro control application for research. Controls up to 4 GoPro Hero 12 Black cameras simultaneously via USB, with a tkinter GUI for settings, live preview, synchronized recording, and multi-camera calibration.

Built for biomechanics research where consistent camera settings and accurate camera calibration are critical for 3D keypoint triangulation and pose estimation.

Includes built-in [Pose2Sim](https://github.com/perfanalytics/pose2sim) integration — run pose estimation, triangulation, filtering, and kinematics directly from the GUI

GoPro control via USB HTTP API (inspired by https://github.com/drukasz/goproUSB ) - connect, manage settings, preview, record, download, audio-based video sync

Calibration method taken from Caliscope (https://github.com/mprib/caliscope)

Demo video - note this is Pose2Sim output (OpenSim visualisation) NOT the output of this repo! But this shows that good quality data can be obtained reliably with 4x GoPro and Caliscope calibration.

https://github.com/user-attachments/assets/df12f3de-d97a-499a-bcfe-97afe6419e71

## Hardware Requirements

- **Cameras**: Up to 4 GoPro Hero 12 Black cameras
- **Connection**: USB cables (one per camera) to a single PC
- **OS**: Windows 11 (tested on Windows 11 Enterprise LTSC 2024)

Each camera is identified by its serial number. The GoPro HTTP API is accessed over USB at an IP address derived from the serial number (`172.2X.1YZ.51:8080`).

## Setup

1. Create and activate the Conda environment:
   ```
   conda create -n Go2Kin python=3.10
   conda activate Go2Kin
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   conda install -c conda-forge ffmpeg
   ```

3. Install pose2sim as a submodule:
    ```
   git submodule init
   git submodule update
   pip install -e ./code/pose2sim
   pip uninstall onnxruntime
   pip install onnxruntime-gpu==1.20.1
   ```

4. Install opensim:
    ```
    conda install -c opensim-org opensim
    ```

5. Set up the application config:
   ```
   cp go2kin_config_template.json go2kin_config.json
   ```
   Edit `go2kin_config.json`:
   - `data_root`: path where Go2Kin will store project data (e.g. `D:/Markerless_Projects`)
   - `gopro_serial_numbers`: serial numbers of your GoPro cameras (found on the camera label or via USB connection)
   - Leave `last_project` and `last_session` empty — these are managed by the app

   If you skip this step, Go2Kin will prompt you to select a data root folder on first launch.

6. Connect GoPro cameras via USB and power them on.

7. Run the settings discovery tool once per camera model/firmware to generate a settings reference file:
   ```
   python tools/discover_camera_settings.py <camera_serial_number>
   ```
   This creates a reference file in `config/settings_references/` that maps setting IDs to human-readable names and available options.

8. Configure camera serial numbers in `go2kin_config.json` (see step 3).

## Usage

```
conda activate Go2Kin
python code/go2kin.py
```

The GUI has five tabs and a fixed bottom bar:

### Bottom Bar — Camera Status & Controls
Always visible at the bottom of the window, regardless of which tab is selected. Shows per-camera connection status (green/red indicator), connect/disconnect toggle buttons, and battery status. Includes global Resolution and FPS dropdowns that apply to all connected cameras simultaneously. Camera serial numbers are read from `go2kin_config.json`.

### Tab 1 — Project
Select or create projects, sessions, and subjects. Your last selection is remembered between sessions. This tab organises all data under the configured `data_root`.

### Tab 2 — Live Preview
Stream a live preview from one camera at a time for positioning and framing. Includes real-time digital zoom control (slider, +/-, text entry). Preview runs at 1080p/30fps/Linear regardless of recording settings.

### Tab 3 — Recording
Select a participant and calibration file for the trial, enter a trial name, and start/stop synchronized recording across selected cameras. Files are downloaded from each camera and saved to the project directory (`[project]/sessions/[session]/[trial]/video/`). After download, audio synchronisation runs automatically — synced files appear in `video/synced/`. A session/trial tree view at the bottom shows all recorded trials. See **Video Synchronisation** below for details.

### Tab 4 — Calibration
Multi-camera calibration using a printed charuco board. The calibration pipeline computes lens parameters (intrinsic) and camera positions/orientations (extrinsic) for 3D triangulation. Includes:

- **Charuco Board Config** — set board dimensions, square size, ArUco dictionary. Save a printable board image.
- **Intrinsic Calibration** — per-camera lens calibration from a video of the board. Uses smart frame selection for orientation and spatial coverage diversity.
- **Extrinsic Calibration** — multi-camera pose estimation from synced videos. Includes PnP solving, outlier rejection, graph bridging, triangulation, and bundle adjustment.
- **Set Origin** — stand the charuco board vertically in portrait mode at the lab origin. Aligns the coordinate system using a Umeyama similarity transform. Can be re-run after loading a saved calibration.
- **Save/Load** — persist calibration to `config/calibration/calibration.json` (also auto-exports `camera_array_go2kin.toml` for Pose2Sim compatibility).

### Tab 5 — Processing
Run the [Pose2Sim](https://github.com/perfanalytics/pose2sim) pipeline on recorded trials. Select trials from a tree view (with session grouping and checkbox selection), then click **Process Selected** to run pose estimation, triangulation, filtering, and kinematics sequentially. Real-time log output streams in the GUI. Pose2Sim is included as a git submodule at `code/pose2sim/`.

The processing pipeline:
1. **Stages** trial data into Pose2Sim's expected directory structure (`[trial]/processed/`)
2. **Validates** that synced videos, calibration TOML, and subject data (height, mass) exist
3. **Runs** each Pose2Sim step: calibration (no-op — reads existing TOML), pose estimation (RTMPose via CUDA), triangulation, Butterworth filtering, and OpenSim kinematics
4. **Updates** `trial.json` with `processed: true` on success

Batch processing runs trials sequentially. A **Stop** button halts processing after the current step completes. See [`docs/pose2sim_integration.md`](docs/pose2sim_integration.md) for technical details.

### Attribution

The calibration pipeline is adapted from [Caliscope](https://github.com/mprib/caliscope) by Mac Prible, licensed under BSD-2-Clause. Caliscope is a full-featured multi-camera calibration and motion capture application. Go2Kin extracts the core calibration algorithms (charuco detection, intrinsic/extrinsic calibration, bundle adjustment, coordinate alignment) and replaces the UI and persistence layers: PySide6 with tkinter, pyvista with matplotlib, TOML with JSON, and numba JIT with pure numpy. See [`code/calibration/CALIBRATION.md`](code/calibration/CALIBRATION.md) for full technical documentation and per-file provenance.

## Calibration Workflow

1. **Print the charuco board.** Configure board parameters in the Calibration tab and click **Save Board Image**. Print at the configured size (default: A1). Mount on a rigid flat surface. **Measure the actual printed square size** — printers don't always scale exactly.
2. **Intrinsic calibration.** For each camera, record a video of the board from various angles and distances. In the Calibration tab, browse to each video and click **Calibrate**.
3. **Extrinsic calibration.** With all cameras in their final positions, record the board being moved through the shared field of view. The Recording tab automatically synchronises files after download. Browse to the `synced/` folder and click **Calibrate Extrinsics**.
4. **Set origin.** Stand the board vertically in portrait mode at the desired world origin (origin corner 790mm above floor). Record with all cameras, synchronise, then browse to the synced folder and click **Set Origin**. This can also be re-run after loading a saved calibration to redefine the coordinate system.
5. **Save.** Click **Save Calibration** to persist all results. A Pose2Sim-compatible TOML file is auto-generated alongside the JSON.

## Project Structure

```
code/
  go2kin.py              # Entry point
  audio_sync.py          # Audio-based multi-camera video synchronisation
  camera_profiles.py     # Camera profile and settings reference management
  project_manager.py     # Project/session/trial/subject file hierarchy management
  pose2sim_builder.py    # Build Pose2Sim project dirs + run pipeline
  GUI/
    main_window.py        # Main GUI window
    project_tab.py        # Project tab (project/session/subject management)
    calibration_tab.py    # Calibration tab (charuco config, intrinsic, extrinsic, origin)
    processing_tab.py     # Processing tab (Pose2Sim pipeline execution)
  goproUSB/
    goproUSB.py           # GoPro HTTP API client (GPcam class)
  calibration/            # Camera calibration pipeline (adapted from Caliscope, BSD-2-Clause)
    calibrate.py           # High-level orchestrator (intrinsic, extrinsic, set origin)
    charuco.py             # Charuco board definition and image generation
    charuco_tracker.py     # Corner detection using cv2.aruco.CharucoDetector
    intrinsic.py           # cv2.calibrateCamera wrapper with smart frame selection
    extrinsic.py           # Multi-camera pose estimation (PnP + outlier rejection)
    bundle_adjustment.py   # Joint optimisation of camera poses and 3D points
    triangulation.py       # DLT triangulation via SVD
    alignment.py           # Umeyama similarity transform for coordinate alignment
    persistence.py         # JSON save/load for calibration results (auto-exports TOML)
    CALIBRATION.md         # Detailed implementation reference
config/
  cameras.json            # Camera serial numbers and GUI state
  camera_profiles/        # Per-camera JSON profiles (settings persist across sessions)
  settings_references/    # Per-model/firmware setting definitions (generated by discovery tool)
  calibration/            # Charuco config and calibration results (JSON)
  pose2sim_config_template.toml  # Pose2Sim Config.toml template
tools/
  discover_camera_settings.py  # Settings discovery tool
  export_toml.py               # Convert calibration JSON to Pose2Sim TOML
  view_calibration.py          # Visualise saved calibration results
output/                   # Legacy recording output (unused by current version)
go2kin_config_template.json  # Template for app config (copy to go2kin_config.json)
```

## Adapting for Different Cameras

The GUI dropdown options for Resolution (1080, 2.7K, 4K) and FPS (25, 50, 100, 200) are hardcoded for GoPro Hero 12 Black with 50Hz anti-flicker (Australia). To adapt for different cameras or regions:

- **Different anti-flicker (60Hz)**: FPS options would typically be 24, 30, 60, 120, 240. Update the combo values in `code/GUI/main_window.py` (search for `global_fps_var` and `global_res_var`).
- **Different camera model**: Run the discovery tool to generate a new settings reference, then update combo values to match the camera's capabilities.
- **Runtime safety**: If a user selects an option the camera doesn't support, the camera rejects it with an error and a popup displays the actually available options.

## Settings Applied on Connect

These settings are automatically applied each time a camera connects to ensure consistency:

| Setting | Value | Reason |
|---------|-------|--------|
| Control Mode | Pro | Full manual control |
| Video Lens | Linear | No distortion for CV/pose estimation |
| GPS | Off | Not needed, saves battery |
| HindSight | Off | Not needed |
| Hypersmooth | Off | Introduces frame warping |
| LCD Brightness | 30% | Save battery |
| Anti-Flicker | 50Hz | Australia mains frequency |
| Auto WiFi AP | Off | Not needed over USB |

Resolution, FPS, lens, and digital zoom are restored from the camera's saved profile.

## Video Synchronisation

Even when starting all cameras simultaneously, each GoPro begins recording at a slightly different time. Audio synchronisation runs automatically after each recording — no manual button press or file selection required.

### How to use

1. At the start of each recording, perform a **loud hand clap** or other distinct sound within the first 3 seconds while all cameras are recording.
2. After files are downloaded, synchronisation runs automatically. The progress log shows time offsets and peak cross-correlation quality for each camera pair.
3. If any camera pair has a peak correlation below 0.7, a warning is displayed — consider re-recording with a louder clap.

### Output

A `synced/` subfolder is created inside the trial's `video/` directory containing:
- Trimmed MP4 files (same filenames as originals) — start-aligned and end-trimmed to identical duration
- `audio_waveforms.png` — diagnostic plot of the first 3 seconds of audio from each camera
- `stitched_videos.mp4` — a 2x2 grid preview (960x960) of all cameras for quick visual verification of sync

Original files are never modified. `trial.json` is updated with `synced: true` on success.

### Technical approach

| Step | Method | Detail |
|------|--------|--------|
| Audio extraction | ffmpeg pipe | First 3s extracted as 48kHz mono WAV via stdout pipe (no temp files) |
| Sync alignment | Full cross-correlation | `scipy.signal.correlate` on entire audio signals for sub-millisecond accuracy — robust to multiple transients |
| Reference selection | Latest start | Camera that started recording last (largest offset) is the reference; others trimmed from the start |
| End alignment | Common duration | All files trimmed to the shortest remaining duration after start alignment |
| Video trimming | ffmpeg stream copy | `-ss` + `-t` + `-c copy` — no re-encoding, lossless, fast |
| Stitched preview | ffmpeg xstack filter | 4 inputs downscaled to 480x480, arranged in 2x2 grid, encoded with built-in mpeg4 codec |

### Requirements

- **ffmpeg** must be installed and in PATH (included when installed via `conda install -c conda-forge ffmpeg`)
- **numpy**, **scipy**, and **matplotlib** (included in `requirements.txt`)

## TODO

- [ ] Set FPS in Pose2Sim config from video files — currently "Process Selected" only sets subject height/weight in the config template, but doesn't detect or set the video FPS to match the recordings
