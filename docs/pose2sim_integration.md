# Pose2Sim Integration

Go2Kin integrates [Pose2Sim](https://github.com/perfanalytics/pose2sim) to run markerless motion capture processing directly from the GUI. This document describes how the integration works.

## Overview

The Processing tab (Tab 5) allows users to select recorded trials and run the full Pose2Sim pipeline — from 2D pose estimation through to OpenSim kinematics — without leaving Go2Kin. The integration bridges Go2Kin's project/session/trial file hierarchy to Pose2Sim's expected directory layout.

Pose2Sim is included as a git submodule at `code/pose2sim/`.

## Architecture

Three components handle the integration:

| Component | File | Purpose |
|-----------|------|---------|
| Config template | `config/pose2sim_config_template.toml` | Default Pose2Sim settings (copied from example_trial) |
| Project builder + runner | `code/pose2sim_builder.py` | Stages directories and runs the pipeline |
| Processing tab | `code/GUI/processing_tab.py` | GUI for trial selection, log output, and controls |

## Directory Staging

Go2Kin trials store data in this structure:

```
[data_root]/[project]/sessions/[session]/[trial]/
├── trial.json              # subject_id, calibration_file, synced, processed
└── video/
    └── synced/             # Audio-synchronised MP4 files
        ├── Trial1_GP1.mp4
        ├── Trial1_GP2.mp4
        ├── Trial1_GP3.mp4
        └── Trial1_GP4.mp4
```

Pose2Sim expects:

```
[working_dir]/
├── Config.toml
├── calibration/
│   └── Calib.toml
└── videos/
    ├── Trial1_GP1.mp4
    ├── Trial1_GP2.mp4
    ├── Trial1_GP3.mp4
    └── Trial1_GP4.mp4
```

The `build_pose2sim_project()` function creates a `processed/` directory inside each trial folder that reproduces this structure:

1. **Calibration TOML** — copied from `[project]/calibrations/[name].toml` to `processed/calibration/Calib.toml`
2. **Video files** — symlinked from `video/synced/` into `processed/videos/` (falls back to file copy on Windows if symlinks aren't available)
3. **Config.toml** — generated from the template with participant-specific values substituted

Files skipped during video staging: `stitched_videos.mp4`, `timestamps.csv`, `audio_waveforms.png`.

## Config.toml Generation

The template at `config/pose2sim_config_template.toml` is a copy of Pose2Sim's example trial Config.toml. Three values are substituted at build time:

| Field | Template default | Substituted with |
|-------|-----------------|-----------------|
| `participant_height` | `'1.69'` | Subject's `height_m` from subject.json |
| `participant_mass` | `64.0` | Subject's `mass_kg` from subject.json |
| `use_custom_logging` | `false` | `true` (prevents Pose2Sim from overwriting Go2Kin's logging) |

Key defaults that align with Go2Kin's setup:
- `calibration_type = 'convert'` with `convert_from = 'caliscope'` — Go2Kin's calibration output is Caliscope-compatible, so the calibration step is effectively a no-op
- `frame_rate = 50` — matches 50Hz anti-flicker (Australian mains frequency)
- `pose_model = 'Body_with_feet'` (HALPE_26)
- `device = 'CUDA'` — requires an NVIDIA GPU with CUDA support

## Pipeline Steps

The pipeline runs each Pose2Sim step individually (not `runAll`) to support stop-event checking between steps:

| Step | Function | Output |
|------|----------|--------|
| 1. Calibration | `Pose2Sim.calibration()` | Reads the Caliscope TOML (no-op conversion) |
| 2. Pose Estimation | `Pose2Sim.poseEstimation()` | `processed/pose/` — 2D keypoints per camera |
| 3. Triangulation | `Pose2Sim.triangulation()` | `processed/pose-3d/` — 3D keypoint trajectories |
| 4. Filtering | `Pose2Sim.filtering()` | Smoothed 3D trajectories (Butterworth, 6Hz) |
| 5. Kinematics | `Pose2Sim.kinematics()` | `processed/kinematics/` — OpenSim IK results |

The pipeline changes the working directory to `processed/` before running (Pose2Sim relies on `os.getcwd()` for file discovery) and restores it afterwards via try/finally.

## Validation

Before building a project, the following checks must pass:

- Synced video folder exists with at least one MP4 file
- `calibration_file` in trial.json is not `"none"` and the corresponding `.toml` exists
- Subject exists with `height_m` and `mass_kg` defined

If any check fails, the trial is skipped with a clear error message in the log.

## Processing Tab

The GUI tab provides:

- **Trial tree** — sessions and trials from `ProjectManager.get_project_tree()`, with checkbox toggle for selection. Shows subject, calibration, and status (Not synced / Ready / Processed) for each trial.
- **Log output** — real-time Pose2Sim output streamed to a scrollable text widget. Uses a custom `logging.Handler` attached to the root logger, plus stdout/stderr redirection.
- **Controls** — "Process Selected" starts batch processing in a background thread; "Stop" sets an event flag checked between pipeline steps.

Processing runs in a daemon thread to keep the GUI responsive. Thread-safe log updates use `root.after(0, callback)`. After successful processing, `trial.json` is updated with `processed: true`.

## Logging

Pose2Sim uses Python's `logging` module extensively. The integration:

1. Sets `use_custom_logging = true` in Config.toml to prevent Pose2Sim from calling `logging.basicConfig()` and creating its own file handlers
2. Attaches a `_LogForwarder` handler to the root logger that forwards all log records to the GUI's log callback
3. Redirects `sys.stdout` and `sys.stderr` via `_StreamRedirector` to capture any direct print output
4. Cleans up all handlers and stream redirections in a finally block after each pipeline run
