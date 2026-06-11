# Regular use — a data-collection session

The routine for a normal session, assuming [first-time setup](first-time-setup/index.md)
is done.

## 1. Launch and connect

- Power up each camera and connect: **battery in → power on → USB in** ([details](first-time-setup/04-connecting-gopros.md)).
- Launch the GUI (`conda activate Go2Kin`, then `python code/go2kin.py`).
- Connect the cameras in the [bottom bar](gui/bottom-bar.md) — all indicators green.
- Set **Resolution** and **FPS** for the session (applies to all connected cameras).

> 🚧 **TODO:** recommended settings per use case (e.g. 2.7K/50 for gait vs 1080/200 for fast movements).

## 2. Session and participant

In the top bar, create a **new session** if needed, and select or create the
**participant** (height and mass are required for processing).

## 3. Calibrate {#calibrate}

Do this **every session**, and any time a camera may have moved. Intrinsics are *not*
redone — only extrinsics and origin.

1. **Extrinsic** — with cameras in their final positions, record the charuco board moving through the shared field of view. After files download and auto-sync, browse to the trial's `synced/` folder in the [Calibration tab](gui/calibration-tab.md) and click **Calibrate Extrinsics**.
2. **Set Origin** — stand the board vertically (portrait) at the lab origin (origin corner **790 mm** above the floor), record on all cameras, browse to the folder and click **Set Origin**.
3. **Save Calibration** — the top-bar indicator turns **green** (calibrated today).

> 🚧 **TODO:** capture guidance — clap near the centre of the camera volume for the extrinsic recording (sound-delay compensation can't apply yet), how long to move the board, and coverage tips.

## 4. Record trials

For each trial:

1. Enter a **trial name** and select cameras in the [Recording tab](gui/recording-tab.md).
2. **Start** recording, then perform **two loud hand claps within the first 3 seconds**.
3. Run the movement task, then **Stop**.
4. Files download and audio sync runs automatically — check the log for `WARN` (clap offsets disagree). If warned, consider re-recording with clearer claps.

## 5. Process

In the [Processing tab](gui/processing-tab.md), tick the trials and click **Process
Selected**. Trials run sequentially (pose estimation → triangulation → filtering →
OpenSim kinematics); **Stop** halts after the current step.

> 🚧 **TODO:** recommended pattern — process between trials, at end of session, or overnight?

## 6. End of session

- Disconnect each camera: **GUI Disconnect → USB out → power off** ([details](first-time-setup/04-connecting-gopros.md)).

> 🚧 **TODO:** end-of-session checklist — charge batteries, offload/backup data, board storage, anything to leave running.

**End of data collection.**
