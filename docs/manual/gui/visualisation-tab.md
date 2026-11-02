# Tab 5 — Visualisation (experimental)

Plays back synced trial video with optional overlays: **2D pose keypoints** (per-camera
detection) and **3D keypoints** (triangulated markers reprojected through the camera
calibration). Useful for visually checking pose detection and triangulation quality.

The frame counter is in **synced frames**: each camera's sync offset (from `trial.json`) is
skipped automatically, so switching cameras keeps you on the same moment. This also makes it a
quick way to check the sync — step to the clap or LED flash and switch cameras. Trials can be
viewed straight after recording, before processing.

> 🚧 **TODO:** screenshot with overlays enabled.

## Known quirks

- Selecting a different trial sometimes doesn't load the video properly — switch to another camera viewpoint to force a refresh.
- MP4 frame decoding/display via OpenCV is slow — the scrubber and **1 frame back** button take time to respond.

> 🚧 **TODO:** controls reference (camera selector, overlay toggles, playback/scrubbing) once the tab stabilises. The repo's `docs/Visualisation.md` has technical details.
