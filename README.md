# Go2Kin

📖 **[User Manual & Documentation](https://f-fraysse.github.io/Go2Kin/)**

**WORK IN PROGRESS**

Integrated markerless motion capture pipeline from 2-4 USB-connected GoPro cameras. Single GUI for the full workflow, from camera setup to OpenSim output.

**Pipeline**: Camera connection & control (OpenGoPro HTTP API) → multi-camera calibration (Caliscope) → recording → synchronisation (hand claps or LED flash) → pose estimation, triangulation, filtering, interpolation (Pose2Sim, RTMlib) → kinematics (openSim)

Designed mainly for indoor motion capture labs, to replicate a traditional marker-based workflow (e.g. Vicon Nexus). Opinionated choices like USB-connected cameras and sync via hand claps (or an LED flash) keep things simple and reliable in a lab setting.

**Hardware**: Up to 4 GoPro cameras connected via USB to a single PC. developed and tested with Hero 12. Should work with any GoPro supporting the HTTP API (9+).

**Built on**:
- [Pose2Sim](https://github.com/perfanalytics/pose2sim) - pose estimation, triangulation, filtering, and kinematics (included as a submodule pinned to a frozen fork, [f-fraysse/pose2sim](https://github.com/f-fraysse/pose2sim), with Go2Kin-specific changes; run directly from the GUI)
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

1. Clone the repository (with the Pose2Sim submodule):
   ```
   git clone --recurse-submodules https://github.com/f-fraysse/Go2Kin.git
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

   **(Optional) Replace ffmpeg with a full NVIDIA build.** No longer required: sync stores
   frame offsets and never re-encodes, so the conda-forge ffmpeg (LGPL, no NVENC/NVDEC) is
   enough. A full GPL build only lets light sync decode on the GPU (`-hwaccel cuda`; it falls
   back to CPU otherwise). To swap one in:

   1. **Close Go2Kin** if running (so `ffmpeg.exe` isn't locked).
   2. Download a build matching your NVIDIA driver's NVENC API. The **n7.1** build from
      [BtbN's FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds/releases) —
      `ffmpeg-n7.1-latest-win64-gpl-7.1.zip` — works with current drivers. (The `master`
      build needs a very new driver, 610+, and otherwise fails with *"Driver does not
      support the required nvenc API version"*.)
   3. Unzip and copy its `bin\ffmpeg.exe` and `bin\ffprobe.exe` **over** the ones in the
      Conda env, e.g. `<conda>\envs\Go2Kin\Library\bin\` (back the originals up first).
   4. Verify: `ffmpeg -hide_banner -encoders | findstr nvenc` lists `hevc_nvenc`.

   > `conda update ffmpeg` (or recreating the env) reverts to the conda build.

4. Install pose2sim as a submodule. `code/pose2sim` is a frozen fork of Pose2Sim
   ([f-fraysse/pose2sim](https://github.com/f-fraysse/pose2sim)); do not pull from upstream inside it.
   Clones made before the switch to the fork need `git submodule sync` once.
    ```
   git submodule sync
   git submodule update --init
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

The GUI has five tabs, a persistent top bar, and a fixed bottom bar:

### Top Bar - Project, Session & Participant Selection
Always visible above the tabs. Project, Session, and Participant dropdowns (with "+" buttons to create new ones) and a calibration status indicator (green = today, orange = older, red = none). A **Manage** button opens a dialog to view and create subjects (initials, age, sex, height, mass). Selections persist between sessions.

### Bottom Bar - Camera Status & Controls
Always visible at the bottom of the window, regardless of which tab is selected. Shows per-camera connection status (green/red indicator), connect/disconnect toggle buttons, and battery status. Includes global Resolution and FPS dropdowns that apply to all connected cameras simultaneously, and a **Sync** selector — **Manual** (hand claps), **Speaker** (PC-played claps, currently too quiet in the lab) or **Light** (LED flash) — remembered between sessions. Camera serial numbers are read from `go2kin_config.json`.

### Tab 1 - Live Preview
Stream a live preview from one camera at a time for positioning and framing. Includes real-time digital zoom control (slider, +/-, text entry). Preview runs at 1080p/30fps/Linear regardless of recording settings.

### Tab 2 - Calibration
Multi-camera calibration using a printed charuco board. The calibration pipeline computes lens parameters (intrinsic) and camera positions/orientations (extrinsic) for 3D triangulation. Includes:

- **Charuco Board Config** - set board dimensions, square size, ArUco dictionary. Save a printable board image.
- **Intrinsic Calibration** - per-camera lens calibration from a video of the board. Uses smart frame selection for orientation and spatial coverage diversity.
- **LED Sync ROI** - only for Light sync. Record a short clip (or pick an existing recording folder) and click the LED in each camera view; Go2Kin watches that small square for the flash. Stored with the calibration and cleared with the extrinsics; redo it whenever a camera or the LED moves. In Light mode, extrinsic calibration is disabled until every connected camera has an ROI.
- **Extrinsic Calibration** - multi-camera pose estimation from synced videos. Includes PnP solving, outlier rejection, graph bridging, triangulation, and bundle adjustment. Videos are not trimmed: corner extraction skips each camera's sync offset frames.
- **Set Origin** - stand the charuco board vertically in portrait mode at the lab origin. Records a short video on all cameras (sync is skipped — the board is static, zero offsets), then aligns the coordinate system using a Umeyama similarity transform. Can be re-run after loading a saved calibration.
- **Saving / Load** - no save button: extrinsic calibration auto-saves a new `[project]/calibrations/calibration_YYYY-MM-DD-HH-MM.json` (plus a Pose2Sim `.toml`), Set Origin updates it, and LED ROI changes are written into it. This active calibration is shown in the top bar, referenced by new trials and reloaded at startup. **Load Calibration** switches to another saved file.

### Tab 3 - Recording
Enter a trial name and start/stop synchronized recording across selected cameras. Files are downloaded from each camera straight into the trial's Pose2Sim folder (`[project]/sessions/[session]/[trial]/processed/videos/`) - the only copy, kept as recorded. After download, synchronisation runs automatically with the method selected in the bottom bar and stores per-camera frame offsets in `trial.json` (no trimming or re-encoding). A session/trial tree view at the bottom shows all recorded trials. See **Video Synchronisation** below for details.

### Tab 4 - Processing
Run the [Pose2Sim](https://github.com/perfanalytics/pose2sim) pipeline on recorded trials. Select trials from a tree view (with session grouping and checkbox selection), then click **Process Selected** to run pose estimation, sync, person association, triangulation, filtering, and kinematics sequentially. Real-time log output streams in the GUI. Pose2Sim is included as a git submodule at `code/pose2sim/` (frozen fork).

The processing pipeline:
1. **Stages** trial data into Pose2Sim's expected directory structure (`[trial]/processed/`; the videos are already in `processed/videos/`)
2. **Validates** that the trial is synced, and that its videos, calibration TOML, and subject data (height, mass) exist
3. **Runs** each Pose2Sim step: calibration (no-op - reads existing TOML), pose estimation (RTMPose via CUDA), **Apply Sync** (writes `pose-sync/` from the stored frame offsets), person association, triangulation, Butterworth filtering, and OpenSim kinematics. Everything from triangulation on is in synced frames (TRC `Frame#` = synced frame)
4. **Updates** `trial.json` with `processed: true` on success

**OpenSim model:** kinematics (scaling + inverse kinematics) uses the **RajagopalLaiUhlrich2023** model by default, with Halpe26 marker, scaling and IK setups adapted from Pose2Sim's. This is set by `use_original_RLU2023 = true` under `[kinematics]` in `config/pose2sim_config_template.toml`; set it to `false` to use Pose2Sim's stock model.
- The head is rigid with the torso in RLU2023, so the head keypoints (Nose, Head) are excluded from IK.
- The pelvis coordinates are unclamped.

See [`docs/CHANGELOG_Halpe26_to_RLU2023.md`](docs/CHANGELOG_Halpe26_to_RLU2023.md) for the full list of changes, and *Pose2Sim vs RLU2023 kinematic models and Halpe26 keypoint positions.docx* in `docs/` for a model comparison.

Batch processing runs trials sequentially. A **Stop** button halts processing after the current step completes. See [`docs/pose2sim_integration.md`](docs/pose2sim_integration.md) for technical details.

### Tab 5 - Visualisation (experimental)
Experimental. Plays back synced trial video (raw videos with each camera's sync offset skipped, so the timeline is in synced frames) with optional overlay of 2D pose keypoints (from per-camera detection) and 3D keypoints (triangulated markers reprojected via camera calibration). Useful for visually checking pose detection and triangulation quality. See [`docs/Visualisation.md`](docs/Visualisation.md) for technical details.

**Known issues:** 
- selecting a different trial sometimes does not load the video properly. Select another camera viewpoint to force refresh.
- mp4 frame decoding / display is slow with cv2. "1 frame back" button, and using the scrubber, take time to respond.

### Attribution

The calibration pipeline is adapted from [Caliscope](https://github.com/mprib/caliscope) by Mac Prible, licensed under BSD-2-Clause. Caliscope is a full-featured multi-camera calibration and motion capture application. Go2Kin extracts the core calibration algorithms (charuco detection, intrinsic/extrinsic calibration, bundle adjustment, coordinate alignment) and replaces the UI and persistence layers: PySide6 with tkinter, pyvista with matplotlib, TOML with JSON, and numba JIT with pure numpy. See [`code/calibration/CALIBRATION.md`](code/calibration/CALIBRATION.md) for full technical documentation and per-file provenance.

## Calibration Workflow

from [Caliscope](https://github.com/mprib/caliscope)

1. **Print the charuco board.** Configure board parameters in the Calibration tab and click **Save Board Image**. Print at the configured size (default: A1). Mount on a rigid flat surface. **Measure the actual printed square size** - printers don't always scale exactly. Highly recommend also printing the "inverted" image and making a double-sided board (see Caliscope).
2. **Intrinsic calibration.** For each camera, record a video of the board from various angles and distances. In the Calibration tab, browse to each video and click **Calibrate**. Done infrequently - one need to be redone if changing camera Zoom, or camera model altogether. 
3. **Extrinsic calibration.** With all cameras in their final positions, click **Calibrate**, move the board through the shared field of view, then **STOP**. Files are downloaded and synced, and the calibration runs automatically.
4. **Set origin.** Stand the board vertically in portrait mode at the desired world origin (origin corner 790mm above floor) and click **Set Origin** — it records on all cameras and aligns the coordinate system. This can also be re-run after loading a saved calibration to redefine the coordinate system.
5. **Saving is automatic.** Results are saved after steps 3 and 4 — there is no save button. A Pose2Sim-compatible TOML file is generated alongside the JSON.

## Project Structure

```
code/
  go2kin.py              # Entry point
  audio_sync.py          # Audio-based multi-camera video synchronisation (hand claps)
  light_sync.py          # LED-flash-based synchronisation (ROI brightness pulse detection)
  camera_profiles.py     # Camera profile and settings reference management
  project_manager.py     # Project/session/trial/subject file hierarchy management
  pose2sim_builder.py    # Build Pose2Sim project dirs + run pipeline
  GUI/
    main_window.py        # Main GUI window (tabs + bottom camera bar)
    top_bar.py            # Top bar (project/session/participant selection)
    live_preview_tab.py   # Live Preview tab (camera preview with zoom)
    calibration_tab.py    # Calibration tab (charuco config, intrinsic, LED ROI, extrinsic, origin)
    recording_tab.py      # Recording tab (record, download, sync)
    processing_tab.py     # Processing tab (Pose2Sim pipeline execution)
    visualisation_tab.py  # Visualisation tab (video playback + keypoint overlays)
    components/           # Shared widgets (trial list, collapsible section, sync-issue popup, LED ROI picker)
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
  audio_sync_test.py           # Audio sync development / validation script
  light_sync_test.py           # Run light sync on a folder / open the LED ROI picker
tests/
  test_project_manager.py      # ProjectManager unit tests
  test_light_sync.py           # Light sync pulse detection / acceptance / ROI tests
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

Even when starting all cameras simultaneously, each GoPro begins recording at a slightly different time. Synchronisation runs automatically after each recording - no manual button press or file selection required. Two methods, chosen with the **Sync** selector in the bottom bar:

- **Hand claps** (Manual) - audio-based, described first below.
- **LED flash** (Light) - hands-free and unaffected by room noise; see [Light (LED) sync](#light-led-sync).

Both produce the same output (frame offsets in `trial.json`) and use the same pass/fail popup.

### How to use (hand claps)

1. At the start of each recording, perform **two loud hand claps** within the first 3 seconds while all cameras are recording. Two claps are required for the consistency check.
2. After files are downloaded, synchronisation runs automatically. The terminal log shows a step-by-step onset detection report with a summary table of offsets and consistency status per camera.

#### Pass/fail criteria and auto-discard

A sync is considered **acceptable** only when all of the following hold:
- **Two claps** are detected on every camera.
- For each camera, the offsets derived from clap 1 vs clap 2 agree within **half a frame** (10 ms at 50 fps; scales with frame rate).
- No camera's final offset relative to the reference exceeds **200 ms**.

If any criterion fails — or a file has no audio track / no clap is detected at all — a **red popup** appears showing the sync table and the failure reasons, headed *"SYNC ISSUE — TRIAL DISCARDED"*. Clicking **OK** deletes the entire trial folder so you can simply re-record. (Environment problems such as a missing ffmpeg do **not** discard the trial — they only log an error.)

The **same criteria and popup apply to extrinsic calibration recording**: if the calibration sync fails, the popup is headed *"SYNC ISSUE — CALIBRATION ABORTED"* and the calibration is aborted immediately — before the multi-minute extrinsic computation — so you can re-record without waiting. (Set Origin is not gated: the board is static, so no clap sync is needed.)

### Output

Videos are **not trimmed or re-encoded** — the raw camera files in `processed/videos/` are kept (higher bitrate, original quality), and the wait between trials is short. On success, `trial.json` gets the per-camera frame offsets:

```json
"synced": true, "sync_method": "light",
"sync": {"fps": 100.0, "reference_cam": 3, "offset_frames": {"1": 3, "2": 2, "3": 0, "4": 5}}
```

`offset_frames[k]` = leading raw frames to skip in camera k (all >= 0, reference = 0); synced frame `s` is raw frame `s + offset_frames[k]`. Processing (the **Apply Sync** step), the Visualisation tab and extrinsic calibration apply these offsets.

- `sync_onsets.png` - diagnostic plot showing detected clap onsets on audio envelopes (cropped around claps), saved in `processed/videos/` (Pose2Sim ignores it)

To re-run the sync on an existing trial: `python tools/resync_trial.py "<project>/sessions/<session>/<trial>" [audio|light]` (writes `trial.json["sync"]` only if the sync passes; light sync uses the LED ROIs from the trial's calibration file).

### Technical approach

| Step | Method | Detail |
|------|--------|--------|
| Audio extraction | ffmpeg pipe | First 3s extracted as 48kHz mono WAV via stdout pipe (no temp files) |
| Envelope | Hilbert transform | Analytic signal → abs → 5ms moving average smoothing |
| Onset detection | Derivative threshold | Positive-only first derivative, threshold at 20% of peak, 0.3s cooldown between claps |
| Consistency check | Dual-clap | If both claps detected in all cameras, clap 1 vs clap 2 offsets must agree within 1 frame |
| Reference selection | Earliest onset | Camera with earliest clap 1 onset is the reference; others offset relative to it |
| Stored offsets | Integer frames | `round(offset × fps)` per camera, saved in `trial.json["sync"]` (`audio_sync.offsets_to_trial_sync`); applied by readers instead of trimming |
| Speed-of-sound compensation | Optional | If calibration is loaded and a sound source position is set, subtracts differential sound propagation delay (distance / 340 m/s) from measured offsets |

### Speed-of-sound compensation

When cameras are at different distances from the clap/speaker, sound arrives at each microphone at slightly different times (e.g. 3m difference = ~8.8ms). At high frame rates (100+ fps) this can cause sub-frame sync errors.

To correct for this, set the sound source position in the **Recording tab** (Sound source X / Y / Z in metres, in the calibration coordinate system). When a calibration is loaded so camera world positions are known, the sync algorithm automatically subtracts the differential propagation delay (distance / 340 m/s) from measured offsets. Both raw and compensated offsets are logged in the console. The Recording tab persists its own sound-source values to `go2kin_config.json` so they survive between sessions.

Compensation is **not** applied during extrinsic calibration (camera poses don't yet exist when the calibration video is synced) or during Set Origin (sync is skipped entirely — the board is static, zero offsets). For extrinsic calibration, clap near the centre of the camera volume so per-camera distance differences largely cancel.

### Light (LED) sync

An alternative to claps: a white LED, visible to all cameras, flashes for 1 second near the start of each recording. Go2Kin finds the flash in each video and aligns on it. Full user guide: [LED light sync](https://f-fraysse.github.io/Go2Kin/gui/led-sync/); technical spec: [`docs/light_sync_spec.md`](docs/light_sync_spec.md).

**How to use**

1. Set **Sync** to **Light** in the bottom bar.
2. With cameras and LED in place, go to the Calibration tab → **LED Sync ROI** → **Record LED clip & set ROI**, and click the LED in each camera view.
3. Run the extrinsic calibration as usual (its recording is synced with the LED too).
4. Record trials as usual. Trigger the LED so it switches on for **1 s** and is off again within the **first 6 s** of the recording.

**LED requirements**: white, constant current (no PWM dimming), clearly brighter than its background, and at a similar height in every camera view where nobody walks in front of it.

**Pass/fail**: the flash must be found in every camera (enough brightness contrast, ~1 s long), each camera's offsets from the LED switching on and switching off must agree within 1 frame, and no camera's offset may exceed 200 ms. Otherwise the same red popup appears and the trial is discarded (or the extrinsic calibration aborted), as for claps.

**Output**: as for audio sync (frame offsets in `trial.json`, `"sync_method": "light"`), plus `sync_led_signal.png` in `processed/videos/` (ROI brightness per camera with the detected on/off instants).

| Step | Method | Detail |
|------|--------|--------|
| Signal extraction | ffmpeg pipe | Only the grayscale ROI crop of the first 6 s is decoded; NVIDIA GPU decode (`-hwaccel cuda`) with automatic CPU fallback; cameras decoded in parallel |
| Brightness per frame | Top-16 mean | Mean of the 16 brightest ROI pixels, so the result does not depend on how big the LED looks |
| Pulse detection | 50 % threshold | Baseline from the first 10 frames; first frame above halfway = on, next below = off; pulse length must be 1 s ± 3 frames |
| Offsets | Integer frames | Camera with the earliest on-edge is the reference; others offset relative to it |
| Stored offsets | Shared with audio sync | Same `trial.json["sync"]` block; no trimming |

### Requirements

- **ffmpeg** and **ffprobe** must be installed and in PATH (audio extraction, LED ROI decoding, frame rate). Light sync uses NVIDIA GPU decoding when the ffmpeg build supports it and falls back to CPU otherwise - no extra setup. No NVENC build is needed (nothing is re-encoded).
- **numpy**, **scipy**, and **matplotlib** (included in `requirements.txt`)

## TODO

Big ones:
1. calibration: save calibration "quality metrics" for extrinsics (ie RMSE etc). For intrinsics we already do this. Need to figure out what to keep and where to store it. And define heuristics for extrinsic calib quality check.
2. sync (audio based): pass/fail criteria + auto-discard now implemented — all cameras detect 2 peaks AND the 2 offsets per camera agree within half a frame AND final offset for any camera <200ms; on failure a red popup shows the sync table and the trial folder is discarded. Remaining: peak-to-background-noise ratio criterion (tbc). (Done: only 1 video per camera is kept — sync is stored as frame offsets in `trial.json`, raw videos are not trimmed.) (LED light sync is now available as a hands-free alternative to claps — see [Light (LED) sync](#light-led-sync).)
3. Pose2Sim staging at recording time: done for videos — raw videos are downloaded straight into [trial]/processed/videos/ (no duplicates, no trimming; sync offsets in trial.json). Remaining: the calib TOML and Config.toml are still staged at the Processing step (safer to copy the calib file while we know it exists).
4. user manual — scaffolded & published to GitHub Pages (MkDocs, `docs/manual/`); content still being written

Misc / small:
- extrinsic calibration at 2.7K misses too many ArUco/charuco markers for a reliable calibration — record extrinsic at 4K. Investigate why 2.7K detection is poor (resolution/sharpness, detector params).
- check camera configs (double up between old system in config/ and go2kin_config in root)
- keep extra info in JSON calib file (e.g. quality metrics - to be displayed in Calibration tab later)
- make charuco board vertical offset editable by user (one/few times setup probably)
- check how calibration age is set in top bar (should be date only)
- bigger tabs / tab names, more visible in UI. All text bigger in UI?
- remove scrollable left panel in Calibration (does not need to be scrollable anymore)
- when connecting cameras get popup warning (camera checkbox not available) this is from deleting camera selection in Recording tab, need to remove checkbox set on connect as it does not exist anymore
- fix trial time display on bottom bar that keeps running after stopping recording (extrinsic / set origin / record trial, intrinsic untested)
- set camera datetime on camera connect
- top bar "manage" button redundant with "+" butto nto add participant
- Pose2Sim re-runs leave stale files in `pose-3d/` and `kinematics/` (e.g. a `processed_0-256_filt_butterworth.trc` from a previous frame range alongside today's `processed_0-255_*`) that get globbed by kinematics as phantom "person 1" entries — extra OpenSim scaling with default 1.75m/70kg, extra IK filter pass. Fix: wipe `pose-3d/` and `kinematics/` at the start of `build_pose2sim_project()` (keep `pose/` and `pose-associated/` so `overwrite_pose=false` workflow stays viable).
