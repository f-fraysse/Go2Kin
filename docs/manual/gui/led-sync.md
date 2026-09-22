# LED light sync

An alternative to hand claps: an LED that flashes once at the start of every recording.
Go2Kin finds the flash in each camera's video and aligns the videos on it. Hands-free,
works at any distance the cameras can see the LED, and unaffected by room noise.

> 🚧 **TODO:** photo of the LED unit and its placement in the lab.

## What you need

- A **white LED** visible to **all cameras**, off by default, switched on for **1 second**
  by an external trigger within the **first 6 seconds** of each recording. It must be
  clearly brighter than its background (no PWM dimming).
- Place it at a **similar height in every camera view** where nobody will walk in front of
  it during the first seconds (e.g. on the floor near the centre of the volume).

## Workflow

1. In the [bottom bar](bottom-bar.md), set **Sync** to **Light**. The choice is remembered
   between sessions.
2. In the [Calibration tab](calibration-tab.md), section **LED Sync ROI**, click
   **Record LED clip & set ROI**. All connected cameras record a short clip (it stops by
   itself after ~7 s — trigger the LED as you would for a trial). A window then shows one
   frame per camera:
    - drag the **time slider** until the LED is on,
    - **click the LED** in each view — a red square (the region Go2Kin will watch) and a
      magnified crop appear; adjust **ROI size** if the LED is large or small,
    - **OK** when every camera has a square.

    The section shows **ROI set: 4 cameras**. If a calibration is loaded, the ROIs are saved
    into it straight away; otherwise they are saved when you **Apply Calibration**.

3. Run the **extrinsic calibration** as usual — its recording is synced with the LED too, so
   the **Calibrate** button stays disabled until the ROI is set for every connected camera.
4. Record trials in the [Recording tab](recording-tab.md) as usual. No clapping needed.

**Set ROI from folder…** lets you define the ROI from any existing recording folder (for
example a trial's `video/` folder) instead of recording a new clip.

Redo the ROI whenever a camera or the LED is moved. Loading a calibration restores the ROIs
saved with it; *Load Intrinsics Only* clears them, like the extrinsics.

## Sync outputs

Same as audio sync — trimmed MP4s in `synced/` and the 2×2 `stitched_videos.mp4` (the LED
should light up in the same frame in all four cells) — plus `sync_led_signal.png`, the ROI
brightness over time for each camera with the detected on/off instants. The trial's
`trial.json` records `"sync_method": "light"`.

## If it fails

The red **SYNC ISSUE** popup lists the reason; the trial is discarded (or the extrinsic
calibration aborted) exactly as for a failed audio sync:

- **LED not detected in ROI** — the LED did not flash, is outside the square (camera or LED
  moved → redo the ROI), or is too dim / too small: move it closer, increase its brightness or
  the ROI size.
- **LED already on at start / never switches off within the search window** — the trigger
  fired too early or too late; the flash must start after the recording begins and finish
  within the first 6 s.
- **Brightness pulse of N frames does not match the LED** — something else changed brightness
  inside the square (someone walked through, a screen changed). Keep the square on the LED
  only.
- **LED on/off edges give offsets differing by N frames** — the two edges disagree; usually a
  partially hidden LED in one camera. Check the view and re-record.
- **No LED ROI for GPn** (before recording) — set the ROI in the Calibration tab, or switch
  Sync back to Manual.
