# Tab 4 — Processing

Runs the [Pose2Sim](https://github.com/perfanalytics/pose2sim) pipeline (included as a
git submodule at `code/pose2sim/`) on recorded trials.

> 🚧 **TODO:** screenshot.

## Running

- Tick trials in the tree view (grouped by session) and click **Process Selected**.
- Trials run **sequentially**, with live log output streaming in the GUI. **Stop** halts after the current step completes.
- On success, the trial is flagged `processed: true` in its `trial.json`.

## What happens per trial

1. **Stage** — trial data is laid out in Pose2Sim's expected directory structure (`[trial]/processed/`).
2. **Validate** — the trial must be synced, and its videos, the calibration TOML and participant height/mass must all exist.
3. **Run** — pose estimation (RTMPose via CUDA) → **Apply Sync** → person association → triangulation → Butterworth filtering → OpenSim kinematics.

**Apply Sync** applies the frame offsets saved at recording time (in `trial.json`) to the 2D
pose results, so all cameras line up from triangulation onwards. Frame numbers in the 3D
results (`.trc`) are synced frames — the same numbers as the Visualisation tab timeline.

## Requirements & gotchas

- **NVIDIA GPU** effectively required — CPU runs are impractically slow.
- The participant must have **height and mass** set (used for OpenSim model scaling).
- Re-running a trial can leave stale files behind — see [Known issues](../troubleshooting.md).
- Leave `frame_range = 'all'` in the Pose2Sim config — a frame range would not match between pose estimation (raw frames) and triangulation (synced frames).

> 🚧 **TODO:** output reference — what lands where after processing (.trc, .mot, scaled model, IK results) and how to open results in OpenSim. Link the repo's `docs/pose2sim_integration.md` for technical detail.
