# Known issues, tips & FAQ

A loose collection of notes — promote items into the main guide as they firm up.

## Cameras & connection

- **Camera won't connect** — check the order (battery → power on → USB), that the cable is data-capable, and that the serial number is in `go2kin_config.json`. *(🚧 TODO: further diagnostics — does it enumerate in Windows? Can you reach the derived IP?)*
- **Popup warning when connecting** ("camera checkbox not available") — harmless; a leftover from a removed Recording-tab checkbox. Fix planned.
- **Camera rejects a Resolution/FPS option** — the camera returns an error and a popup lists the actually available options; pick one of those.
- **60 Hz regions / other camera models** — the Resolution/FPS lists are hardcoded for the Hero 12 with 50 Hz anti-flicker (Australia). For 60 Hz regions the options are typically 24/30/60/120/240 — edit the combo values in `code/GUI/main_window.py` (`global_fps_var`, `global_res_var`). For other models, run the settings discovery tool first.

## Synchronisation

- **`WARN` status** — the offsets from the two claps disagree by more than one frame. Re-record with louder, sharper, well-separated claps inside the first 3 seconds.
- **Claps not detected** — *(🚧 TODO: common causes — background noise, claps too quiet or too late — and fixes.)*
- **High frame rates** — at 100+ fps, camera-to-source distance differences cause sub-frame errors; set the sound source position in the Recording tab (requires a loaded calibration).
- **During extrinsic calibration** — sound-delay compensation can't apply (camera poses don't exist yet); clap near the centre of the camera volume so distance differences largely cancel.
- **Sync fails with "ffmpeg trim failed … received no packets" / "error in an external library" / "Driver does not support the required nvenc API version"** — at high resolution / frame rate (e.g. 2.7K @ 200 fps) the trim step needs ffmpeg's `hevc_nvenc` (GPU) encoder. The default conda ffmpeg has no NVENC; install a full NVENC build and (if you get the *nvenc API version* message) one matching your NVIDIA driver. See [Installation → NVENC ffmpeg](first-time-setup/01-installation.md).

## Calibration

- **Printed board doesn't match the configured size** — always measure the printed squares and enter the measured value in the board config.
- **Poor extrinsic result** — *(🚧 TODO: symptoms and fixes; quality metrics and pass/fail heuristics are on the roadmap.)*
- **Re-defining the lab axes** — Set Origin can be re-run after loading a saved calibration.

## Processing

- **Painfully slow** — you're probably running on CPU. Check `onnxruntime-gpu` is installed (not `onnxruntime`) and that the log reports CUDA.
- **Phantom "person 1" with default 1.75 m / 70 kg** — stale files from a previous run in `pose-3d/` and `kinematics/` get globbed into the new run. Workaround: delete those two folders inside the trial's `processed/` directory before re-running. An automatic fix is planned.
- **Validation fails** — check that synced videos exist, a calibration was saved, and the participant has height and mass entered.

## Tips

- Keep digital zoom **fixed** after intrinsic calibration — changing it invalidates intrinsics.
- Hypersmooth and HindSight are turned off on connect deliberately (frame warping / battery) — don't re-enable them.

> 🚧 **TODO:** accumulate lab wisdom here — battery life expectations, cable routing, board handling and storage…

## FAQ

- **Can I use WiFi instead of USB?** No — by design, for reliability in the lab. For WiFi-based GoPro control, see [Go2Rep](https://github.com/ShabahangShayegan/Go2Rep).
- **More than 4 cameras?** Not currently supported.
- **Can I use it outdoors?** Not the design target — audio-clap synchronisation is unlikely to be reliable outside.
- **Other GoPro models?** Any model with the HTTP API (Hero 9+) should work — run the settings discovery tool and adjust the Resolution/FPS lists to match.

> 🚧 **TODO:** add questions as they come up.
