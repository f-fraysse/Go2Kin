# Go2Kin

Multi-camera GoPro control application for research. Controls up to 4 GoPro Hero 12 Black cameras simultaneously via USB, with a tkinter GUI for settings, live preview, and synchronized recording.

Built for biomechanics research where consistent camera settings across sessions are critical for keypoint triangulation and pose estimation.

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

3. Connect GoPro cameras via USB and power them on.

4. Run the settings discovery tool once per camera model/firmware to generate a settings reference file:
   ```
   python tools/discover_camera_settings.py <camera_serial_number>
   ```
   This creates a reference file in `config/settings_references/` that maps setting IDs to human-readable names and available options.

5. Configure camera serial numbers in `config/cameras.json`.

## Usage

```
conda activate Go2Kin
python code/go2kin.py
```

The GUI has four tabs:

### Tab 1 — Camera Settings
Connect to each camera, view status, and adjust resolution, FPS, and digital zoom. On connect, the application automatically applies a set of consistent settings (Pro control mode, Linear lens, GPS off, 50Hz anti-flicker, etc.) and restores previously saved resolution/FPS/zoom from the camera profile.

### Tab 2 — Live Preview
Stream a live preview from one camera at a time for positioning and framing. Includes real-time digital zoom control (slider, +/-, text entry). Preview runs at 1080p/30fps/Linear regardless of recording settings.

### Tab 3 — Recording
Start/stop synchronized recording across selected cameras. After recording, files are automatically downloaded from each camera and saved to `output/` with timestamps. Progress is tracked in the log.

Includes a **Synchronise Video Files** button for post-recording audio-based synchronisation (see below).

### Tab 4 — Calibration
Multi-camera calibration using a printed charuco board. The calibration pipeline computes lens parameters (intrinsic) and camera positions/orientations (extrinsic) for 3D triangulation. Includes:

- **Charuco Board Config** — set board dimensions, square size, ArUco dictionary. Save a printable board image.
- **Intrinsic Calibration** — per-camera lens calibration from a video of the board. Uses smart frame selection for orientation and spatial coverage diversity.
- **Extrinsic Calibration** — multi-camera pose estimation from synced videos. Includes PnP solving, outlier rejection, graph bridging, triangulation, and bundle adjustment.
- **Set Origin** — stand the charuco board vertically in portrait mode at the lab origin. Aligns the coordinate system using a Umeyama similarity transform. Can be re-run after loading a saved calibration.
- **Save/Load** — persist calibration to `config/calibration/calibration.json` (also auto-exports `camera_array_go2kin.toml` for Pose2Sim compatibility).

### Attribution

The calibration pipeline is adapted from [Caliscope](https://github.com/mprib/caliscope) by Mac Prible, licensed under BSD-2-Clause. Caliscope is a full-featured multi-camera calibration and motion capture application. Go2Kin extracts the core calibration algorithms (charuco detection, intrinsic/extrinsic calibration, bundle adjustment, coordinate alignment) and replaces the UI and persistence layers: PySide6 with tkinter, pyvista with matplotlib, TOML with JSON, and numba JIT with pure numpy. See [`code/calibration/CALIBRATION.md`](code/calibration/CALIBRATION.md) for full technical documentation and per-file provenance.

## Calibration Workflow

1. **Print the charuco board.** Configure board parameters in the Calibration tab and click **Save Board Image**. Print at the configured size (default: A1). Mount on a rigid flat surface. **Measure the actual printed square size** — printers don't always scale exactly.
2. **Intrinsic calibration.** For each camera, record a video of the board from various angles and distances. In the Calibration tab, browse to each video and click **Calibrate**.
3. **Extrinsic calibration.** With all cameras in their final positions, record the board being moved through the shared field of view. Use the Recording tab's **Synchronise Video Files** to align the recordings, then browse to the `synced/` folder and click **Calibrate Extrinsics**.
4. **Set origin.** Stand the board vertically in portrait mode at the desired world origin (origin corner 790mm above floor). Record with all cameras, synchronise, then browse to the synced folder and click **Set Origin**. This can also be re-run after loading a saved calibration to redefine the coordinate system.
5. **Save.** Click **Save Calibration** to persist all results. A Pose2Sim-compatible TOML file is auto-generated alongside the JSON.

## Project Structure

```
code/
  go2kin.py              # Entry point
  audio_sync.py          # Audio-based multi-camera video synchronisation
  camera_profiles.py     # Camera profile and settings reference management
  GUI/
    main_window.py        # Main GUI window (Settings, Preview, Recording tabs)
    calibration_tab.py    # Calibration tab (charuco config, intrinsic, extrinsic, origin)
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
tools/
  discover_camera_settings.py  # Settings discovery tool
  export_toml.py               # Convert calibration JSON to Pose2Sim TOML
  view_calibration.py          # Visualise saved calibration results
output/                   # Recording output directory
```

## Adapting for Different Cameras

The GUI dropdown options for Resolution (1080, 2.7K, 4K) and FPS (25, 50, 100, 200) are hardcoded for GoPro Hero 12 Black with 50Hz anti-flicker (Australia). To adapt for different cameras or regions:

- **Different anti-flicker (60Hz)**: FPS options would typically be 24, 30, 60, 120, 240. Update the combo values in `code/GUI/main_window.py` (search for `res_combo` and `fps_combo`).
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

Even when starting all cameras simultaneously, each GoPro begins recording at a slightly different time. The **Synchronise Video Files** button in the Recording tab aligns multi-camera recordings using full audio cross-correlation.

### How to use

1. At the start of each recording, perform a **loud hand clap** or other distinct sound within the first 3 seconds while all cameras are recording.
2. After files are downloaded, click **Synchronise Video Files** and select the trial folder containing the 4 MP4 files.
3. The tool cross-correlates the audio signals, computes precise time offsets between cameras, and trims all files to a common start and end point.

### Output

A `synced/` subfolder is created inside the trial directory containing:
- 4 trimmed MP4 files (same filenames as originals) — start-aligned and end-trimmed to identical duration
- `audio_waveforms.png` — diagnostic plot of the first 3 seconds of audio from each camera
- `stitched_videos.mp4` — a 2x2 grid preview (960x960) of all 4 cameras for quick visual verification of sync

Original files are never modified.

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
