# Go2Kin

**WORK IN PROGRESS**

Integrated markerless motion capture pipeline from 2-4 USB-connected GoPro cameras. Single GUI for the full workflow - from camera setup to OpenSim output.

**Pipeline**: Camera connection & control (OpenGoPro HTTP API) → multi-camera calibration (Caliscope) → recording → audio-based synchronisation → pose estimation, triangulation, filtering, interpolation (Pose2Sim, RTMlib) → kinematics (openSim)

Designed mainly for indoor motion capture labs, to replicate a traditional marker-based workflow (e.g. Vicon Nexus). Opinionated choices like USB-connected cameras and audio sync via hand claps keep things simple and reliable in a lab setting.

**Hardware**: Up to 4 GoPro cameras connected via USB to a single PC. developed and tested with Hero 12. Should work with any GoPro supporting the HTTP API (9+).

**Built on**:
- [Pose2Sim](https://github.com/perfanalytics/pose2sim) - pose estimation, triangulation, filtering, and kinematics (included as a submodule, run directly from the GUI)
- [Caliscope](https://github.com/mprib/caliscope) - multi-camera calibration algorithms (charuco detection, intrinsic/extrinsic calibration, bundle adjustment), adapted and re-implemented
- [Open GoPro  API](https://gopro.github.io/OpenGoPro/http) over USB (inspired by [goproUSB](https://github.com/drukasz/goproUSB))

Also includes: live camera preview, project/session/trial/participant management, and basic visualisation of pose estimation results.

### Related Projects

- **GoPro control over WiFi**: [Go2Rep](https://github.com/ShabahangShayegan/Go2Rep)
- **Calibration only**: [Caliscope](https://github.com/mprib/caliscope)
- [Pose2Sim](https://github.com/perfanalytics/pose2sim)
- **Visualisation**: [MStudio](https://github.com/hunminkim98/MStudio)

### Demo

GoPro footage + OpenSim output:

https://github.com/user-attachments/assets/df12f3de-d97a-499a-bcfe-97afe6419e71

## Hardware Requirements

- **Cameras**: Up to 4 GoPro Hero 12 Black cameras
- **Connection**: USB cables (one per camera) to a single PC
- **OS**: Windows 11 (tested on Windows 11 Enterprise LTSC 2024)

Each camera is identified by its serial number. The GoPro HTTP API is accessed over USB at an IP address derived from the serial number (`172.2X.1YZ.51:8080`).

## Setup

1. Clone the repository:
   ```
   git clone https://github.com/f-fraysse/Go2Kin.git
   cd Go2Kin
   ```

2. Create and activate the Conda environment:
   ```
   conda create -n Go2Kin python=3.10
   conda activate Go2Kin
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   conda install -c conda-forge ffmpeg
   ```

4. Install pose2sim as a submodule:
    ```
   git submodule init
   git submodule update
   pip install -e ./code/pose2sim
   pip uninstall onnxruntime
   pip install onnxruntime-gpu==1.20.1
   ```

5. Install opensim:
    ```
    conda install -c opensim-org opensim
    ```

6. Set up the application config:
   ```
   cp go2kin_config_template.json go2kin_config.json
   ```
   Edit `go2kin_config.json`:
   - `data_root`: path where Go2Kin will store project data (e.g. `D:/Markerless_Projects`)
   - `gopro_serial_numbers`: serial numbers of your GoPro cameras (found on the camera label or via USB connection)
   - Leave `last_project` and `last_session` empty - these are managed by the app

   If you skip this step, Go2Kin will prompt you to select a data root folder on first launch.

7. Connect GoPro cameras via USB and power them on.

8. (Optional) Run the settings discovery tool once per camera model/firmware to generate a settings reference file:
   ```
   python tools/discover_camera_settings.py <camera_serial_number>
   ```
   This creates a reference file in `config/settings_references/` that maps setting IDs to human-readable names and available options.

## Usage

```
python code/go2kin.py
```

The GUI has six tabs and a fixed bottom bar:

### Bottom Bar - Camera Status & Controls
Always visible at the bottom of the window, regardless of which tab is selected. Shows per-camera connection status (green/red indicator), connect/disconnect toggle buttons, and battery status. Includes global Resolution and FPS dropdowns that apply to all connected cameras simultaneously. Camera serial numbers are read from `go2kin_config.json`.

### Tab 1 - Project
Select or create projects, sessions, and subjects. Your last selection is remembered between sessions. This tab organises all data under the configured `data_root`.

### Tab 2 - Live Preview
Stream a live preview from one camera at a time for positioning and framing. Includes real-time digital zoom control (slider, +/-, text entry). Preview runs at 1080p/30fps/Linear regardless of recording settings.

### Tab 3 - Calibration
Multi-camera calibration using a printed charuco board. The calibration pipeline computes lens parameters (intrinsic) and camera positions/orientations (extrinsic) for 3D triangulation. Includes:

- **Charuco Board Config** - set board dimensions, square size, ArUco dictionary. Save a printable board image.
- **Intrinsic Calibration** - per-camera lens calibration from a video of the board. Uses smart frame selection for orientation and spatial coverage diversity.
- **Extrinsic Calibration** - multi-camera pose estimation from synced videos. Includes PnP solving, outlier rejection, graph bridging, triangulation, and bundle adjustment.
- **Set Origin** - stand the charuco board vertically in portrait mode at the lab origin. Aligns the coordinate system using a Umeyama similarity transform. Can be re-run after loading a saved calibration.
- **Sound Source Position** - optional X/Y/Z coordinates (in metres) of the sync sound source (speaker or clap location). Used for speed-of-sound compensation during audio sync. Displayed as a black cross in the 3D viewer.
- **Save/Load** - persist calibration to `config/calibration/calibration.json` (also auto-exports `camera_array_go2kin.toml` for Pose2Sim compatibility).

### Tab 4 - Recording
Select a participant and calibration file for the trial, enter a trial name, and start/stop synchronized recording across selected cameras. Files are downloaded from each camera and saved to the project directory (`[project]/sessions/[session]/[trial]/video/`). After download, audio synchronisation runs automatically - synced files appear in `video/synced/`. A session/trial tree view at the bottom shows all recorded trials. See **Video Synchronisation** below for details.

### Tab 5 - Processing
Run the [Pose2Sim](https://github.com/perfanalytics/pose2sim) pipeline on recorded trials. Select trials from a tree view (with session grouping and checkbox selection), then click **Process Selected** to run pose estimation, triangulation, filtering, and kinematics sequentially. Real-time log output streams in the GUI. Pose2Sim is included as a git submodule at `code/pose2sim/`.

The processing pipeline:
1. **Stages** trial data into Pose2Sim's expected directory structure (`[trial]/processed/`)
2. **Validates** that synced videos, calibration TOML, and subject data (height, mass) exist
3. **Runs** each Pose2Sim step: calibration (no-op - reads existing TOML), pose estimation (RTMPose via CUDA), triangulation, Butterworth filtering, and OpenSim kinematics
4. **Updates** `trial.json` with `processed: true` on success

Batch processing runs trials sequentially. A **Stop** button halts processing after the current step completes. See [`docs/pose2sim_integration.md`](docs/pose2sim_integration.md) for technical details.

### Tab 6 - Visualisation (experimental)
Slow and experimental. Plays back synced trial video with optional overlay of 2D pose keypoints (from per-camera detection) and 3D keypoints (triangulated markers reprojected via camera calibration). Useful for visually checking pose detection and triangulation quality. See [`docs/Visualisation.md`](docs/Visualisation.md) for technical details.

### Attribution

The calibration pipeline is adapted from [Caliscope](https://github.com/mprib/caliscope) by Mac Prible, licensed under BSD-2-Clause. Caliscope is a full-featured multi-camera calibration and motion capture application. Go2Kin extracts the core calibration algorithms (charuco detection, intrinsic/extrinsic calibration, bundle adjustment, coordinate alignment) and replaces the UI and persistence layers: PySide6 with tkinter, pyvista with matplotlib, TOML with JSON, and numba JIT with pure numpy. See [`code/calibration/CALIBRATION.md`](code/calibration/CALIBRATION.md) for full technical documentation and per-file provenance.

## Calibration Workflow

1. **Print the charuco board.** Configure board parameters in the Calibration tab and click **Save Board Image**. Print at the configured size (default: A1). Mount on a rigid flat surface. **Measure the actual printed square size** - printers don't always scale exactly. Highly recommend also printing the "inverted" image and making a double-sided board (see Caliscope).
2. **Intrinsic calibration.** For each camera, record a video of the board from various angles and distances. In the Calibration tab, browse to each video and click **Calibrate**. Done infrequently - one need to be redone if changing camera Zoom, or camera model altogether. 
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
    visualisation_tab.py  # Visualisation tab (video playback + keypoint overlays)
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

Even when starting all cameras simultaneously, each GoPro begins recording at a slightly different time. Audio synchronisation runs automatically after each recording - no manual button press or file selection required.

### How to use

1. At the start of each recording, perform **two loud hand claps** within the first 3 seconds while all cameras are recording. Two claps enable a consistency check; a single clap also works but without cross-validation.
2. After files are downloaded, synchronisation runs automatically. The progress log shows a step-by-step onset detection report with a summary table of offsets and consistency status per camera.
3. If any camera shows status `WARN` (clap 1 and clap 2 offsets disagree by more than 1 frame), a red warning is displayed - consider re-recording with clearer claps.

### Output

A `synced/` subfolder is created inside the trial's `video/` directory containing:
- Trimmed MP4 files (same filenames as originals) - start-aligned and end-trimmed to identical duration
- `sync_onsets.png` - diagnostic plot showing detected clap onsets on audio envelopes (cropped around claps)
- `stitched_videos.mp4` - a 2x2 grid preview (960x960) of all cameras for quick visual verification of sync

Original files are never modified. `trial.json` is updated with `synced: true` on success.

### Technical approach

| Step | Method | Detail |
|------|--------|--------|
| Audio extraction | ffmpeg pipe | First 3s extracted as 48kHz mono WAV via stdout pipe (no temp files) |
| Envelope | Hilbert transform | Analytic signal → abs → 5ms moving average smoothing |
| Onset detection | Derivative threshold | Positive-only first derivative, threshold at 20% of peak, 0.3s cooldown between claps |
| Consistency check | Dual-clap | If both claps detected in all cameras, clap 1 vs clap 2 offsets must agree within 1 frame |
| Reference selection | Earliest onset | Camera with earliest clap 1 onset is the reference; others offset relative to it |
| End alignment | Common duration | All files trimmed to the shortest remaining duration after start alignment |
| Video trimming | ffmpeg stream copy | `-ss` + `-t` + `-c copy` - no re-encoding, lossless, fast |
| Stitched preview | ffmpeg xstack filter | 4 inputs downscaled to 480x480, arranged in 2x2 grid, encoded with built-in mpeg4 codec |
| Speed-of-sound compensation | Optional | If calibration is loaded and a sound source position is set, subtracts differential sound propagation delay (distance / 340 m/s) from measured offsets |

### Speed-of-sound compensation

When cameras are at different distances from the clap/speaker, sound arrives at each microphone at slightly different times (e.g. 3m difference = ~8.8ms). At high frame rates (100+ fps) this can cause sub-frame sync errors.

To correct for this, set the sound source position in the **Calibration tab** (Sound Source Position section - X, Y, Z in metres in the calibration coordinate system). When a calibration with camera positions is loaded and a sound source position is set, the sync algorithm automatically subtracts the differential propagation delay from measured offsets. Both raw and compensated offsets are logged in the console.

The sound source position is saved in the calibration JSON file and restored when loading a calibration.

### Requirements

- **ffmpeg** must be installed and in PATH (included when installed via `conda install -c conda-forge ffmpeg`)
- **numpy**, **scipy**, and **matplotlib** (included in `requirements.txt`)

## TODO

Big ones:
1. calibration: we need a way to save calibration "quality metrics" for extrinsics (ie RMSE etc). For intrinsics we already do this (RMSE). Need to figure out what to keep and where to store it. And define heuristics for extrinsic calib quality check.
2. sync (audio based): criteria for "sync pass / good sync" is : all cameras detect 2 peaks AND all peaks to background noise ratio is above a set threshold (tbc) AND the 2 offsets computed from the 2 peaks are <10ms apart AND final offset for any camera is <300ms (check value). If all true = good sync / pass / green circle, delete raw unsynced videos and keep only synced ones. If not: keep raw videos, only trim end of videos so frame numbers match and keep those. Whether audio sync passes or fails we only keep 1 video per camera
3. Currently functionality is: after recording ends, save raw videos to [trial data path]/video/ (with /synced/ subfolder) and create trial.json with calib file name and participant name. Then when Processing trial, create the staging folder (move videos, copy calib file, copy pose2sim config file). New functionality: staging folder is created after recording and sync ends. Move video files to the right place in staging folder and copy calibration file too. (see above for sync pass fail: if sync pass, copy synced and cropped files. If sync failed copy raw unsynced files cropped to same frame numbers)
4. user manual

To fix:
- check camera configs (double up between old system in config/ and go2kin_config in root)
- audio sync: if quality checks fail: move the unsynced videos to processing staging folder (need to crop to same frames first? check pose2sim)
- create pose2sim staging folder after recording rather than at Processing step - move videos and calib file (if exists) right after recording, create trial JSON (already done then?) Safer to move calib file while we know it exists. 


Potential optimisations (low hanging fruit):
- defer or remove the creation of "stitched preview" after sync (takes ~10sec) - we have clean audio sync now - maybe enforce need for 2 claps as this is how we check consistency

Misc / small:
- keep extra info in JSON calib file (e.g. quality metrics - to be displayed in Calibration tab later)
- visualisation tab: does not handle 2d / 3d keypoints having different number of frames than video (e.g. if person is not detected at start of recording) - need to investigate what pose2sim does with video frames that do not return a pose / if it discards some video frames in whole pipeline
- make charuco board vertical offset editable by user (one/few times setup probably)
- check how calibration age is set in top bar (should be date only)
- bigger tabs / tab names, more visible in UI
- remove scrollable left panel in Calibration (does not need to be scrollable anymore)
- when connecting cameras get popup warning (camera checkbox not available) this is from deleting camera selection in Recording tab, need to remove checkbox set on connect as it does not exist anymore
- fix trial time display on bottom bar that keeps running after stopping recording (extrinsic / set origin / record trial, intrinsic untested)
