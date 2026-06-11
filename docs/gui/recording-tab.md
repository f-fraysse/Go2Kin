# Tab 3 — Recording

Synchronised recording across the selected cameras, with automatic download and audio
synchronisation.

> 🚧 **TODO:** screenshot.

## Recording a trial

1. Enter a **trial name** and select the cameras.
2. **Start** — then perform **two loud hand claps within the first 3 seconds**. (Two claps enable a consistency check; one clap works, but without cross-validation.)
3. Perform the movement, then **Stop**.
4. Files are downloaded from each camera into `[project]/sessions/[session]/[trial]/video/`, and audio synchronisation runs automatically — synced files appear in `video/synced/`.

A session/trial tree view at the bottom shows all recorded trials.

## Sync outputs (per trial)

- Trimmed MP4s in `synced/` — start-aligned and end-trimmed to identical duration. Originals are never modified.
- `sync_onsets.png` — detected clap onsets on each camera's audio envelope.
- `stitched_videos.mp4` — a 2×2 grid preview for quick visual verification of sync.
- A **`WARN`** status means the two clap offsets disagree by more than one frame — consider re-recording with clearer claps.

## Sound source position (speed-of-sound compensation)

At high frame rates, differences in camera-to-clap distance cause sub-frame sync errors
(~3 m ≈ 8.8 ms). Set **Sound source X / Y / Z** (metres, in the calibration coordinate
system); with a calibration loaded, sync automatically subtracts the differential
propagation delay. Values persist in `go2kin_config.json`. Not applied during extrinsic
calibration or Set Origin.

> 🚧 **TODO:** when to bother (e.g. ≥100 fps with metres of distance difference) and how to measure the source position.
