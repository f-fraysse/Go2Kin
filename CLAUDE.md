# Go2Kin

Multi-camera GoPro control application for research. Controls up to 4 GoPro Hero 12 cameras via USB using the GoPro HTTP API, with a tkinter GUI.

## Dev Environment

- **OS**: Windows 11
- **Python**: 3.10 in Conda environment `Go2Kin` (`conda activate Go2Kin`)
- **IDE**: VSCode
- **Run**: `python code/go2kin.py`
- **Dependencies**: `pip install -r requirements.txt` (requests, opencv-contrib-python, Pillow, numpy, scipy, pandas, matplotlib, sounddevice)
- **External tools**: `ffmpeg` in PATH (for audio sync; install via `conda install -c conda-forge ffmpeg`).
  - No NVENC/GPL build is needed any more: sync stores frame offsets instead of re-encoding
    (the conda-forge LGPL build is fine; light sync's `-hwaccel cuda` decode falls back to CPU).
- **Tests**: `python tests/test_project_manager.py`, `python tests/test_light_sync.py` and `python tests/test_sync_offsets.py` (run from repo root)

## Pose2Sim fork (submodule)

`code/pose2sim` is a git submodule pointing at a **frozen fork**: `https://github.com/f-fraysse/pose2sim`,
branch `main` (forked from upstream commit `491d564`). Pose2Sim is pip-installed in editable mode from
`code/pose2sim`. **Do not pull from upstream** (`origin` = perfanalytics). The local `main` tracks `myfork/main`.

- **Changing Pose2Sim:** commit inside `code/pose2sim` → `git -C code/pose2sim push myfork main` →
  in Go2Kin `git add code/pose2sim` (records the new submodule commit) → commit → push Go2Kin.
  Always push the fork **before** Go2Kin, otherwise Go2Kin points at a commit GitHub doesn't have.
- **Getting changes on another machine:**
  ```
  git pull
  git submodule sync            # one-time, after the switch from upstream to the fork
  git submodule update --init
  pip show pose2sim             # "Editable project location" must be ...\Go2Kin\code\pose2sim
  ```
  If it isn't an editable install: `pip install -e code/pose2sim`.
- **Fork patch:** `[kinematics] use_original_RLU2023 = true` (template default) uses the
  RajagopalLaiUhlrich2023 model + Halpe26 setups in `Pose2Sim/OpenSim_Setup/*RLU2023*` (markerset `..._P2Sall.xml`).
  Deviations from the stock RLU2023 / ported setups:
  - all 6 pelvis coordinates unclamped;
  - Nose/Head `apply=false` in the IK setup (head rigid with torso);
  - `perform_scaling()` forces `marker_set_file = Unassigned`.
  - `personAssociation.py`: reads JSONs from the folder it listed them from (upstream's `os.path.exist`
    typo meant `pose-sync/` names were read from `pose/`, silently undoing any sync).
  - `common.sort_people_sports2d`: pads `frames_since_last_seen` to the number of person slots
    (triangulation crashed with a broadcast error when a person entered the view mid-trial).
  - Docs: `docs/pose2sim_integration.md`, `docs/CHANGELOG_Halpe26_to_RLU2023.md` (port + fork changes + validation), and
    `docs/Pose2Sim vs RLU2023 kinematic models and Halpe26 keypoint positions.docx` (comparison of the *unmodified* models).

## Project Structure

```
code/
  go2kin.py              # Entry point — loads config, creates ProjectManager + GUI
  audio_sync.py          # Audio-based multi-camera video synchronisation
  light_sync.py          # LED-flash-based synchronisation (ROI brightness pulse detection)
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
      sync_discard_dialog.py   # Red "sync issue" popup (shared by Recording + Calibration)
      led_roi_dialog.py        # LED ROI picker (2x2 frames, click the LED) for light sync
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
  pose2sim/               # Git submodule — frozen fork (https://github.com/f-fraysse/pose2sim), see "Pose2Sim fork"
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
  light_sync_test.py      # Light sync test utility (run detector on a folder / open ROI picker)
  resync_trial.py         # Re-run audio/light sync on a recorded trial, write trial.json offsets
tests/
  test_project_manager.py  # ProjectManager unit tests
  test_light_sync.py       # light_sync pulse detection / acceptance / led_roi persistence tests
  test_sync_offsets.py     # trial.json sync block + apply_sync_offsets (pose -> pose-sync) tests
docs/
  manual/                 # Published user manual (MkDocs Material) → GitHub Pages
  *.md                    # Dev/technical notes (NOT published; cited from Architecture)
go2kin_config.json         # App config (data_root, serials, last selection) — gitignored
go2kin_config_template.json # Template for go2kin_config.json (tracked in git)
mkdocs.yml                 # MkDocs config (docs_dir: docs/manual)
.github/workflows/deploy-docs.yml  # Auto-deploys manual to GitHub Pages on push to main
```

## Architecture

- **Go2KinMainWindow** (`GUI/main_window.py`): 5-tab tkinter GUI (Preview, Calibration, Recording, Processing, Visualisation) + persistent TopBar above tabs + fixed bottom camera bar. Starts on Calibration tab.
- **TopBar** (`GUI/top_bar.py`): Persistent project/session/participant dropdowns + calibration status indicator. Always visible above tabs.
- **Bottom camera bar** (`GUI/main_window.py`): Per-camera connect/disconnect toggle, status indicators, battery display. Global resolution/FPS dropdowns apply to all cameras. `Sync:` radio (Manual / Speaker / Light) selects the sync method; persisted as `sync_method` in `go2kin_config.json`.
- **GPcam** (`goproUSB/goproUSB.py`): HTTP client for one camera. IP derived from serial: `172.2X.1YZ.51:8080`.
- **CameraProfileManager** (`camera_profiles.py`): Singleton managing per-camera profiles and per-model settings references.
- **ProjectManager** (`project_manager.py`): Manages project/session/trial/subject file hierarchy at `data_root`. GUI-agnostic — filesystem and JSON only. See `docs/project_manager.md`.
- **SessionTrialsList** (`GUI/components/session_trials_list.py`): Canvas-based trial list with colored status indicators. Shared by Recording and Processing tabs.
- **LivePreviewCapture** (`GUI/main_window.py`): Threaded OpenCV capture from UDP stream.
- **Sync by stored offsets**: videos are never trimmed or re-encoded. Raw downloads go to `[trial]/processed/videos/` (the only copy; the sync plot sits there too). After an accepted sync, `audio_sync.offsets_to_trial_sync()` writes `trial.json["sync"] = {fps, reference_cam, offset_frames: {"<GP n>": frames to skip}}`; synced frame s = raw frame s + offset. Readers apply it: Processing (`pose2sim_builder.apply_sync_offsets` writes `pose-sync/` with shifted JSON frame numbers after pose estimation), Visualisation (timeline in synced frames), extrinsic calibration (`start_frames` in corner extraction). `ProjectManager.get_sync_offsets()` returns `{}` for legacy trials (pre-trimmed `video/synced/`, zero offsets). Keep Pose2Sim `frame_range = 'all'`. Re-sync a trial with `tools/resync_trial.py`.
- **Audio sync** (`audio_sync.py`): Clap-onset detection. Runs automatically after recording. `evaluate_sync_acceptance()` gates quality (2 claps + half-frame consistency + <200ms inter-camera offset); on failure a shared red popup appears and the trial is discarded (Recording tab) or extrinsic calibration is aborted before the expensive compute (Calibration tab). A `StepTimer` prints a per-step timing table after each Recording-tab sync. See `docs/audio_sync_spec.md` and `docs/audio_sync_performance.md` (timing breakdown from the old trim era + CrowdStrike first-run gotcha).
- **Light sync** (`light_sync.py`): LED-flash alternative to claps, selected with the bottom-bar `Light` radio. Per-camera ROI around the LED (set in the Calibration tab "LED Sync ROI" section via `led_roi_dialog.py`, stored as `CameraData.led_roi` in the calibration JSON, cleared with extrinsics). ffmpeg pipes only the grayscale ROI crop of the first 6 s (`-hwaccel cuda` with CPU fallback); `detect_pulse()` finds the 1 s on/off pulse; offsets are integer frames vs the earliest camera. Same result-dict contract as audio, so `offsets_to_trial_sync` and the red discard popup are reused. `LightSyncError` subclasses `AudioSyncError`. See `docs/light_sync_spec.md`.
- **Calibration** (`calibration/`): Charuco-based intrinsic/extrinsic calibration adapted from Caliscope (BSD-2-Clause). Orchestrated by `calibrate.py`.
- **Pose2Sim integration** (`pose2sim_builder.py`): Stages trial data into Pose2Sim directory structure and runs the pipeline. Kinematics uses the RajagopalLaiUhlrich2023 model via the fork's `use_original_RLU2023` key. See `docs/pose2sim_integration.md`.
- **Visualisation** (`GUI/visualisation_tab.py`): Video playback with keypoint overlays. See `docs/Visualisation.md`.

## Documentation

- **User manual**: MkDocs (Material theme), source in `docs/manual/`, published to GitHub Pages at https://f-fraysse.github.io/Go2Kin/ (linked from the README). Config: `mkdocs.yml` (`docs_dir: docs/manual`).
- **Auto-deploy**: pushing to `main` with changes under `docs/manual/**` or `mkdocs.yml` triggers `.github/workflows/deploy-docs.yml`, which runs `mkdocs gh-deploy --force` to rebuild the `gh-pages` branch. Never edit `gh-pages` directly — it is generated output.
- **Editing**: edit the `.md` files in `docs/manual/` and push to `main`. A new page must also be added to `nav:` in `mkdocs.yml`. Images go in `docs/manual/assets/`.
- **Local preview**: `pip install mkdocs-material` then `mkdocs serve` (build-only dep; not in `requirements.txt`).
- **Dev/technical notes** live at `docs/` root (e.g. `pose2sim_integration.md`, `project_manager.md`, `Visualisation.md`) and are deliberately **not** part of the published site.

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

### From the climbing pilot (Oct 2026)

That session was calibrated, synced and processed offline with scripts. They're not in the repo; they're in `C:\Markerless_Data\climbing\scripts\` (README) on the lab PC. The full write-up is `...\climbing\sessions\urbanclimb_14_10_26\urbanclimb_14_10_26_quality_report_v3.docx`.

- **Extrinsic sampling:**
  - `sample_fps` defaults to 5 (`calibrate.py`, `video_processor.py`), and `calibration_tab.py` never passes it. With 2 cameras that gave a 10% scale error; 25 fps was stable. Make 25 the default.
  - `compute_volumetric_scale_accuracy()` (`bundle_adjustment.py`) is never called.
- **LED on-time:** `light_sync.detect_pulse` rejects anything but a 1 s ± `PULSE_TOLERANCE_FRAMES` pulse. The remote LED is switched by hand and stayed on 0.4–2.3 s. Accept a range of on-times. The on/off edge agreement gate already exists (`evaluate_light_sync_acceptance`).
- **Calibration quality not saved:** the JSON stores only the intrinsic `error`. Add the extrinsic RMSE (overall and per camera), scale RMSE and baseline, and show them in the tab.
- **Sync by stored offsets:** done (Nov 2026, see Architecture). Still open: a failed Recording-tab sync deletes the trial; it could instead keep the raw videos with `synced=False` for a later `tools/resync_trial.py`.
- **Pose2Sim fork bugs** (monkeypatched in the climbing scripts only; the `frames_since_last_seen` one is now fixed in the fork):
  - `personAssociation.compute_affinity` gives persons with no valid keypoints affinity 1, so they steal the match from the real person.
- **No per-trial quality metrics** in Go2Kin. Reference implementations are the scripts' `collect_metrics.py` and `ik_diagnostics.py`.
- **RLU2023 joint ranges are too tight for climbing:** shoulder flexion ±90°, hip flexion 120°, hip rotation ±40°.
  - The "wide_flex" variant clamps shoulder flexion to −90..180°, hip flexion to −30..140°, hip adduction to −70..30° and hip rotation to ±60°, and keeps shoulder abduction at 120°.
  - It fixed most of the arm IK error.
  - Never unclamp the 3-angle ball joints (Euler aliasing) or the pin joints (knees and elbows invert).
  - Undecided: whether this becomes a per-project model option.
