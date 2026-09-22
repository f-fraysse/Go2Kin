# Light-based (LED flash) multi-camera sync — specification

Companion to [`audio_sync_spec.md`](audio_sync_spec.md). Implementation plan and design
rationale: [`light_based_sync_implementation.md`](light_based_sync_implementation.md).
Code: `code/light_sync.py`, `code/GUI/components/led_roi_dialog.py`, wiring in
`code/GUI/calibration_tab.py`, `code/GUI/recording_tab.py`, `code/GUI/main_window.py`.

---

## 1. Principle

A white LED visible to every camera is off by default. An external trigger turns it on for
**1 s** within the first few seconds of each recording. Go2Kin locates the on-edge of that
pulse in every camera's video and uses it as the sync event, then reuses the audio path's
`trim_and_sync_videos` / `create_stitched_preview` so `video/synced/` is produced exactly as
before (start-aligned, equal frame counts, 2×2 preview).

The user selects **Light** in the bottom bar (`Sync:` radio, persisted as `sync_method` in
`go2kin_config.json`). Manual/Speaker keep the audio path unchanged.

## 2. ROI (region of interest)

Decoding dominates the cost, not analysis, so only a small square around the LED is ever
brought into Python. The ROI is defined once per camera placement:

- **Calibration tab → "LED Sync ROI"** section (between Intrinsic and Extrinsic, because the
  extrinsic recording is synced too): **Record LED clip & set ROI** records
  `LIGHT_SEARCH_SECONDS + 1` s on all connected cameras (auto-stop), decodes ~24 reduced
  frames per camera (`sample_frames_for_roi`, 4 fps, 960 px wide, one sequential ffmpeg
  decode — no seeking, since a GoPro GOP is ~1 s), and opens the picker dialog. **Set ROI from
  folder…** does the same from any folder of `*_GP{N}.mp4` (e.g. a trial's `video/`).
- **Dialog** (`show_led_roi_dialog`): 2×2 views, shared time slider, ROI-size spinbox
  (default 80 px full-res), click the LED → square ROI centred on the click, red rectangle +
  4× magnified crop in the cell corner. OK only when every camera has an ROI.
- **Storage**: in memory as `CalibrationTab._led_rois = {cam: {"roi": (x, y, w, h), "size": (w, h)}}`
  (`size` = frame size the ROI was drawn on), and per camera as `led_roi` in the calibration
  JSON (`CameraData.led_roi`, in the camera's calibration `size` coordinates). If a
  calibration file is loaded, setting the ROI rewrites that file in place; otherwise the ROI
  is written by **Apply Calibration**. It is cleared with the extrinsics (`Load Intrinsics
  Only`, `erase_calibration_data`) because it is tied to camera placement. TOML export
  ignores it.
- **Resolution changes**: `scale_roi` rescales the ROI when a trial's resolution differs from
  the frame the ROI was drawn on (e.g. 4K ROI, 2.7K trial). A log line reports the scaling.

## 3. Detection

### 3.1 Signal extraction — `read_roi_signal`

One ffmpeg process per video, raw grayscale crop piped to Python:

```
ffmpeg -hide_banner -loglevel error [-hwaccel cuda] -i in.mp4 -t 6.0
       -vf crop=w:h:x:y,format=gray -f rawvideo -pix_fmt gray pipe:1
```

`-hwaccel cuda` (NVDEC) is tried first; if ffmpeg exits non-zero (LGPL conda build has no
NVDEC) the call is repeated without it and the result is cached for the process. A log line
says which path is used. The four cameras are decoded in parallel (`ThreadPoolExecutor`).

Per-frame value = **mean of the 16 brightest pixels** of the crop (`BRIGHT_TOP_PIXELS`). A
fixed pixel count is independent of the LED blob size relative to the ROI: on the validation
recording (1080p) the blob covers ~115 of the 6400 ROI pixels, which moves the crop mean by
only ~8 grey levels and puts the 95th percentile on the blob's edge, while the top-16 mean
goes from ~110 (off) to 255 (on).

### 3.2 Pulse detection — `detect_pulse(signal, fps)`

Pure numpy, unit-tested (`tests/test_light_sync.py`):

1. `baseline` = median of the first 10 frames (LED off); `peak` = max; `contrast = peak − baseline`.
   `contrast < MIN_CONTRAST (60)` → `LightSyncError("LED not detected in ROI")`.
2. Normalise `s = clip((signal − baseline) / contrast, 0, 1)`. `on` = first frame with
   `s ≥ 0.5`; `off` = first frame after `on` with `s < 0.5`. `on == 0` → "LED already on at
   start"; no `off` → "never switches off within the search window".
3. Sub-frame edges (assume exposure ≈ frame period): if frame `on` is partially lit
   (`s[on] < 0.98`) then `t_on = on + 1 − s[on]`, else the turn-on fell in the previous frame:
   `t_on = on − s[on−1]`. Symmetrically `t_off = off + s[off]` or `off − 1 + s[off−1]`.
4. `pulse_frames = t_off − t_on` must be within `LIGHT_PULSE_SECONDS·fps ± PULSE_TOLERANCE_FRAMES (3)`
   — rejects brightness changes that are not the LED (someone walking through the ROI, a
   display changing).

### 3.3 Offsets — `compute_light_sync_offsets`

Reference = camera with the smallest `t_on`. Per camera `offset_frames = round(t_on − t_on_ref)`,
`offset_seconds = offset_frames / fps` (so `trim_and_sync_videos` reproduces the integer
exactly), `final_offset_ms`. Two-event consistency: `on_off_diff_frames =
round(t_off − t_off_ref) − offset_frames`; `|diff| > 1` → status `WARN`, else `PASS` (`REF`
for the reference).

Result dict per video path (superset of the audio contract consumed by
`trim_and_sync_videos`): `offset_seconds, is_reference, status, final_offset_ms,
offset_frames, fps, on_frame, off_frame, t_on, t_off, pulse_frames, contrast,
on_off_diff_frames`.

`evaluate_light_sync_acceptance(results, max_offset_ms=200)`: all non-reference cameras
have `|on_off_diff_frames| ≤ 1`, and no `|final_offset_ms| > 200`. A missing pulse raises in
detection instead. On failure the shared red popup is shown: trial discarded (Recording tab)
or extrinsic calibration aborted before the trim (Calibration tab) — same flow as audio.

Outputs: `synced/sync_led_signal.png` (per-camera signal, 50 % threshold, on/off markers),
the summary table in the log, and `sync_method: "light"` in `trial.json`.

## 4. Constants (`light_sync.py`)

| Constant | Value | Meaning |
|---|---|---|
| `LIGHT_SEARCH_SECONDS` | 6.0 | Scan window from recording start; LED clip length is this + 1 s |
| `LIGHT_PULSE_SECONDS` | 1.0 | Expected LED on-time |
| `PULSE_TOLERANCE_FRAMES` | 3 | Accepted deviation of the measured pulse length |
| `MIN_CONTRAST` | 60 | Minimum peak − baseline (grey levels) |
| `BRIGHT_TOP_PIXELS` | 16 | Per-frame statistic: mean of the N brightest ROI pixels |
| `LED_ROI_DEFAULT_SIZE` | 80 | Default ROI side (full-res px) |

## 5. Validation (2026-09-22)

Recording `tests_Francois/sessions/Charlotte_Pilot2/LED_loc/video` — 4 × Hero 12, 1080p,
100 fps, LED on the floor ~3 s after start. `tools/light_sync_test.py`:

| Camera | On frame | Pulse (fr) | Contrast | Offset (fr) | On/Off diff |
|---|---|---|---|---|---|
| GP1 | 301 | 100.0 | 137 | +4 | −1 |
| GP2 (ref) | 297 | 101.1 | 139 | 0 | 0 |
| GP3 | 301 | 101.0 | 133 | +4 | 0 |
| GP4 | 298 | 100.0 | 128 | +1 | −1 |

Acceptance PASS; 3.0 s wall time for detection (1.9 s NVDEC decode of 4 × 600 frames,
1.0 s plot). Run on the same trial's audio-synced `synced/` folder, the LED on-frames were
298 / 296 / 297 / 298 — a 2-frame spread, consistent with speed-of-sound differences that the
uncompensated audio sync cannot remove. `t_on` was within 0.03 of an integer in every camera:
the GoPro shutter is much shorter than the 10 ms frame period here, so frames are either fully
on or off and only integer offsets carry information.

## 6. Limitations

- **Integer-frame alignment** (±0.5 frame per camera) as with audio; sub-frame `t_on` is only
  informative when the exposure approaches the frame period (dim scenes / low fps).
- **Rolling shutter**: the LED's image row is read out at a different time within the frame;
  place the LED at similar heights in each view to keep the per-camera bias small (≤ ~1 frame
  at 100+ fps for very different rows).
- **LED requirements**: constant-current (no PWM dimming), bright against its background so
  `contrast ≥ 60`, and inside the ROI in every camera. A camera that cannot see the LED
  cannot be synced.
- **Timing**: the pulse must start after frame 0 and end within `LIGHT_SEARCH_SECONDS`.
- **ROI validity**: tied to camera placement — recreate it whenever a camera or the LED moves
  (the Calibration tab section can be re-run any time; the extrinsic button is gated on it in
  light mode).
- **Exposure**: auto-exposure may saturate the blob; that is fine for detection but removes
  sub-frame information.

## 7. Tools & tests

- `python tests/test_light_sync.py` — synthetic pulses (clean, partial edges, no pulse, short /
  long pulse, already-on, no off-edge), acceptance rules, ROI scaling, `led_roi` JSON round-trip.
- `python tools/light_sync_test.py [folder]` — runs the detector on a folder of raw
  `*_GP{N}.mp4` with the `ROIS` typed at the top of the script (or `CALIB_FILE`), prints the
  summary + acceptance + `StepTimer` table, writes `synced/sync_led_signal.png`. Set
  `USE_DIALOG = True` to open the ROI picker on that folder and print the chosen ROIs.
