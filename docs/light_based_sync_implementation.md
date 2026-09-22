# Light-based (LED flash) multi-camera sync — implementation plan

> **Status: implemented** (plan agreed 2026-09-21, implemented 2026-09-22). This document
> is kept as the design rationale; the as-built specification is
> [`light_sync_spec.md`](light_sync_spec.md). Line numbers refer to the code as of commit
> `c68f6ed` (before implementation) and have drifted; function names are the stable anchors.
> Deviations from the plan: the per-frame ROI statistic is the mean of the 16 brightest pixels
> (not the 95th percentile, which sat on the blob's edge at 1080p); ROI lookups are keyed by
> camera id (`CalibrationTab.get_led_rois()` + `light_sync.resolve_rois_for_videos`) so the
> Recording tab can gate before any file exists; the tab tracks `_loaded_calib_path` for the
> in-place ROI write; `tools/light_sync_test.py` uses the repo's constants-at-top style.

Companion notes: [`audio_sync_spec.md`](audio_sync_spec.md) (current audio algorithm),
[`audio_sync_performance.md`](audio_sync_performance.md) (timing),
[`audio_sync_offset_approach.md`](audio_sync_offset_approach.md) (lazy-offset design, out of
scope here but schema-compatible), [`testing video decoding on GPU.md`](testing%20video%20decoding%20on%20GPU.md)
(decode benchmarks that motivate the decoder choice below).

---

## 1. Context

Go2Kin currently synchronises the 4 GoPro videos after each recording by detecting two clap
onsets in the audio (`code/audio_sync.py`), then trimming every video with a frame-accurate
`hevc_nvenc` re-encode so frame N is the same instant in every camera. The speaker-generated
clap is effectively unusable in the lab (too quiet at 7 m) and manual clapping is an operator
burden.

The **light-based method**: a white LED, visible to all cameras, is off by default; an external
device automatically turns it on for 1 s within the first few seconds of each recording. Go2Kin
detects the LED-on frame in every camera and reuses the existing trim pipeline to produce
synced, equal-frame-count videos. The user selects the method (audio vs light) in the bottom
bar.

### Decisions already taken

| Topic | Decision |
|---|---|
| LED trigger | External device, fires automatically. Timing not fixed → detector scans a configurable window (default first **6 s**). **Confirm on first real use.** |
| ROI definition | Dedicated short "LED clip" recording from the Calibration tab, then a minimal dialog: one frame per camera, shared time slider, **click the LED** to place a fixed-size square ROI (default 80 px, adjustable), magnified crop for confirmation. |
| ROI storage | Per camera inside the calibration JSON (`led_roi`), since cameras and LED are fixed once extrinsics are done. |
| Ordering | In light mode the ROI must exist **before** the extrinsic recording (extrinsic videos need sync too), so the LED-ROI step sits between Intrinsic and Extrinsic in the Calibration tab. It can be re-run any time; the result is written into the currently loaded calibration file in place. |
| Trim | Unchanged. Videos are still trimmed/re-encoded into `video/synced/`. |

### Why an ROI (efficiency)

Decoding dominates, not analysis: benchmarks show 4K decode at ~15 ms/frame on CPU via cv2
and ~7 ms via NVDEC. Per-frame maths on an 80×80 crop is negligible. A full-frame search would
need per-pixel temporal analysis (memory-heavy, confused by moving people/reflections) with no
decode saving. The ROI gives robustness for free; efficiency comes from (1) a short search
window, (2) hardware decode, (3) no full-frame data crossing into Python.

---

## 2. What exists and is reused (from exploration)

**`code/audio_sync.py`** — generic, reuse unchanged:
- `StepTimer` (l.35), `check_ffmpeg` (l.64), `get_frame_count` (l.96), `get_frame_rate` (l.121).
- `trim_and_sync_videos(video_paths, offsets, output_dir, ...)` (l.648) — reads only
  `offsets[vp]["offset_seconds"]` and `["is_reference"]`; `drop = max(0, round(offset*fps))`;
  outputs to `<output_dir>/synced/<same filename>`; verifies equal frame counts.
- `create_stitched_preview(synced_dir, ...)` (l.746) — reads the `synced/` folder, method-agnostic.
- `AudioSyncError` (l.30). `evaluate_sync_acceptance` (l.306) and `format_sync_summary` (l.272)
  are audio-keyed (`clap1_ms`, `clap2_ms`, `diff_ms`) — write light-specific equivalents.
- Result-dict contract consumed downstream (l.615-625): `offset_seconds`, `is_reference`,
  `status`, `final_offset_ms`, `offset_frames`, `fps`.
- Parallel-per-camera pattern: `ThreadPoolExecutor(max_workers=n_cams)` + `ex.map` (l.381-394).

**`code/GUI/recording_tab.py`**
- `sync_method_var` passed in (l.28/49); only gates speaker playback at l.490.
- `_start_recording` (~l.150-216): creates the trial, then starts `recording_worker`.
- `_auto_sync(trial_info, timer)` (l.299-415): audio checks → `compute_sync_offsets` →
  `evaluate_sync_acceptance` → discard popup (`_show_sync_discard_dialog`, l.417) or
  trim + stitched preview + `update_trial(synced=True)` + timer table.
- `_get_calibration_tab()` and `calibration_tab.get_camera_positions_for_sync(video_paths)`
  (l.347-351) — the pattern to copy for ROI lookup.

**`code/GUI/calibration_tab.py`**
- `_create_widgets` (l.81-137): section order intrinsic → extrinsic → origin → apply.
- `_update_pipeline_state` (l.374-393): button gating.
- `_origin_start_recording` (l.538-576): template for a short multi-camera recording step.
- `_multi_record_worker(cam_list, video_dir, purpose, timestamp, status_var, on_synced=None, skip_sync=False)`
  (l.984-1059): start all → wait for stop event (**no timeout**) → stop+download →
  `_run_calib_sync` → `on_synced(synced_dir)`.
- `_run_calib_sync(...)` (l.1061-1150): `skip_sync=True` fabricates zero offsets
  (`{"offset_seconds": 0.0, "is_reference": i == 0, "status": "NO-SYNC"}`); otherwise audio
  path; abort with `show_sync_discard_dialog(..., heading="SYNC ISSUE — CALIBRATION ABORTED", on_ok=cleanup)`
  and `return None` **before** trim.
- `_ext_auto_run_calibration` (l.481-515): builds `CameraArray` from `_intrinsic_results`,
  runs `run_extrinsic_calibration`, then `_cleanup_temp_videos(video_dir, "extrinsic", timestamp)`
  — **extrinsic videos are deleted on success**.
- `_apply_calibration` (l.641-671): writes `<project>/calibrations/calibration_<stamp>.json`
  via `persistence.save_calibration(filepath, camera_array, charuco)`; sets `app_config["last_calibration"]`.
- `load_calibration_file` (l.1394), `_load_intrinsics` (l.1533: `replace(cam, rotation=None, translation=None)`).
- `_get_temp_video_dir` (l.893) → `<project>/calibrations/temp_videos/`; filenames `{purpose}_{timestamp}_GP{N}.mp4`.
- `get_camera_positions_for_sync` (l.1152-1181): `_GP(\d+)` filename → cam id mapping.
- No cv2/PIL frame display exists in this tab today.

**`code/calibration/persistence.py`** — `save_calibration` (l.23), `load_calibration` (l.64),
`_camera_data_to_dict` (l.133), `_dict_to_camera_data` (l.158) — explicit key whitelist, so
an unknown per-camera key is **silently dropped** unless added to both. TOML exporters
(`tools/export_toml.py`, `project_manager._generate_toml_content`) whitelist keys too, so a
new JSON key is safely ignored by Pose2Sim.

**`code/calibration/data_types.py`** — `CameraData` dataclass (l.70-89), plain (not frozen),
`erase_calibration_data` (l.219).

**`code/GUI/visualisation_tab.py`** — `_display_frame` (l.349-394): the cvtColor → resize →
`Image.fromarray` → `ImageTk.PhotoImage` → `canvas.create_image` recipe; keep the `scale`
factor to map canvas clicks back to full-res pixels. No mouse-drag or zoom exists anywhere.

**`code/GUI/main_window.py`** l.241-246: `sync_method_var = StringVar("manual")` with radios
Manual/Speaker; not persisted. `go2kin_config_template.json` has no `sync_method`.

**`code/GUI/components/sync_discard_dialog.py`**: `show_sync_discard_dialog(parent, table_text, reasons, *, heading, subtext, on_ok=None)`.

---

## 3. Design

### 3.1 New module `code/light_sync.py`

Constants (module-level, like `audio_sync.py:23-27`):

```python
LIGHT_SEARCH_SECONDS = 6.0      # scan window from recording start (assumption — confirm)
LIGHT_PULSE_SECONDS = 1.0       # LED on-time
PULSE_TOLERANCE_FRAMES = 3      # accepted deviation of measured pulse length
MIN_CONTRAST = 60               # grey levels, peak - baseline
BRIGHT_PERCENTILE = 95          # per-frame ROI statistic
LED_ROI_DEFAULT_SIZE = 80       # px, full-res square ROI
```

`class LightSyncError(AudioSyncError)` — subclass so existing `except AudioSyncError` branches
in both tabs keep working.

**`read_roi_signal(video_path, roi, seconds, ffmpeg_path="ffmpeg") -> np.ndarray`**
One ffmpeg subprocess per video, raw-video pipe:

```
ffmpeg -hide_banner -loglevel error -hwaccel cuda -i in.mp4 -t <seconds>
       -vf crop=w:h:x:y,format=gray -f rawvideo -pix_fmt gray pipe:1
```

Read `w*h` bytes per frame from stdout; per-frame value = `np.percentile(crop, BRIGHT_PERCENTILE)`
(robust to an ROI larger than the LED blob and to single-pixel noise; a plain mean is diluted:
a 10-px blob in an 80×80 box moves the mean by ~4 grey levels). If the `-hwaccel cuda` run
exits non-zero (LGPL conda build has no NVDEC), rerun without it (CPU decode inside ffmpeg —
still no full-frame copy into Python). Log which path was used. Clamp the ROI to the frame;
if the video size differs from the calibration `size` (e.g. 4K calibration, 2.7K trial), scale
x/y/w/h by `video_w / calib_w` and log a warning.

**`detect_pulse(signal, fps) -> dict`** (pure numpy, unit-testable):
1. `b` = median of first 10 frames (LED off); `p = max(signal)`; `contrast = p - b`; raise
   `LightSyncError("LED not detected in ROI")` if `contrast < MIN_CONTRAST`.
2. `s = clip((signal - b) / (p - b), 0, 1)`; `on` = first index with `s >= 0.5`; `off` = first
   index after `on` with `s < 0.5`. If `on == 0` → raise (LED already on at start). If no `off`
   → raise (no off-edge in window).
3. Sub-frame on-time (assumes exposure ≈ frame period; degrades gracefully to integer frames
   for short shutters): `t_on = on + 1 - s[on]` if `s[on] < 0.98` else `t_on = on - s[on-1]`.
   Same construction for `t_off`.
4. `pulse_frames = t_off - t_on`; raise if outside
   `LIGHT_PULSE_SECONDS*fps ± PULSE_TOLERANCE_FRAMES` (guards against a non-LED brightness change).
5. Return `{"on_frame", "off_frame", "t_on", "t_off", "pulse_frames", "contrast", "baseline", "peak"}`.

**`compute_light_sync_offsets(video_paths, rois, output_dir=None, progress_callback=None, timer=None) -> Dict[str, dict]`**
- `rois`: `{video_path: (x, y, w, h)}` (already resolved per file by the caller).
- `fps = get_frame_rate(video_paths[0])`.
- `read_roi_signal` for all cameras in a `ThreadPoolExecutor`, then `detect_pulse` each.
- Reference = camera with the smallest `t_on`. `offset_frames = round(t_on_c - t_on_ref)`;
  `offset_seconds = offset_frames / fps` (so `trim_and_sync_videos` reproduces the integer
  exactly); `final_offset_ms = offset_seconds * 1000`.
- Two-event consistency: `off_offset = round(t_off_c - t_off_ref)`;
  `on_off_diff_frames = off_offset - offset_frames`.
- Result dict keyed by video path:
  `offset_seconds, is_reference, status ("REF"|"PASS"|"WARN"), final_offset_ms, offset_frames, fps,
  on_frame, off_frame, t_on, pulse_frames, contrast, on_off_diff_frames`.
- Save `<output_dir>/synced/sync_led_signal.png` (one subplot per camera: signal, threshold
  line, on/off markers) — same role as `sync_onsets.png`.
- `timer.mark(...)` steps like the audio path so the Recording-tab timing table stays useful.

**`format_light_sync_summary(results) -> str`** — table: camera, on frame, t_on, pulse
frames, contrast, offset frames, final ms, status, `*` for reference.

**`evaluate_light_sync_acceptance(results, max_offset_ms=200.0) -> (bool, list[str])`**
All must hold: every camera has a pulse (detection raised otherwise); `|on_off_diff_frames| <= 1`
per non-reference camera; `|final_offset_ms| <= max_offset_ms`. Mirrors
`evaluate_sync_acceptance` but with light keys.

**`sample_frames_for_roi(video_path, seconds=LIGHT_SEARCH_SECONDS, step_seconds=0.25, width=960, ffmpeg_path) -> list[np.ndarray]`**
Same ffmpeg pipe with `-vf fps=4,scale=960:-2 -pix_fmt rgb24` (quarter-res RGB, ~24 frames
per camera ≈ 37 MB). Returns frames plus the scale factor (`video_w / 960`) for the dialog.
Seeking is deliberately avoided (GoPro GOP ≈ 1 s → each seek re-decodes up to 100 frames).

**Documented limitations** (put in a `docs/light_sync_spec.md` when implementing):
- Rolling-shutter readout gives a per-camera bias of up to ~1 frame at 100+ fps if the LED sits
  at very different image rows across cameras → place the LED at similar heights in each view.
- LED must be constant-current (no PWM dimming) and against a non-bright background so
  `contrast >= MIN_CONTRAST`.
- Integer-frame alignment inherits ±0.5 frame error, same as the audio path.

### 3.2 Persistence: `led_roi` on `CameraData`

- `data_types.py` `CameraData`: add `led_roi: tuple[int, int, int, int] | None = None`
  (x, y, w, h in the calibration image `size` coordinates).
- `persistence.py`: write `led_roi` in `_camera_data_to_dict` when not None; read via
  `d.get("led_roi")` in `_dict_to_camera_data` (convert list → tuple). Signatures of
  `save_calibration`/`load_calibration` unchanged. TOML exporters need no change.
- Clear `led_roi` wherever extrinsics are cleared: `CameraData.erase_calibration_data` and the
  intrinsics-only reload `replace(cam, rotation=None, translation=None, led_roi=None)` in
  `calibration_tab._load_intrinsics`. The ROI is tied to camera placement, like extrinsics.

Resulting JSON per camera:

```json
"1": { "size": [3840, 2160], "...": "...", "led_roi": [1812, 402, 80, 80] }
```

### 3.3 ROI dialog: `code/GUI/components/led_roi_dialog.py`

```python
def show_led_roi_dialog(parent, frames_by_cam: dict[int, list[np.ndarray]],
                        frame_scale: float, initial_rois: dict[int, tuple] | None = None,
                        default_size: int = LED_ROI_DEFAULT_SIZE) -> dict[int, tuple] | None
```

Modal `Toplevel`; returns full-res `{cam_id: (x, y, w, h)}` or `None` on cancel.

- 2×2 grid of `tk.Canvas`, one per camera; fit-to-canvas display with the
  `visualisation_tab._display_frame` recipe; store the per-canvas display scale so
  click → sampled-frame coords → full-res (`× frame_scale`).
- One shared `ttk.Scale` "time (s)" stepping through the sampled frames (LED-on lasts 1 s, so
  ≥3 samples show it on; inter-camera differences are ≤ a few frames, one slider suffices).
- `<Button-1>` on a canvas centres a square ROI (size `Spinbox`, default 80 px full-res) at the
  click; draw a red rectangle; show a 4× magnified crop of the ROI in the cell corner.
- Per-camera status line ("GP2: ROI (1812, 402, 80, 80)"); OK enabled only when every camera
  has an ROI. Prefill from `initial_rois`.
- No zoom/pan (none exists in the codebase; not needed: 80 px ROI ≈ 20 display px).

### 3.4 Calibration tab (`code/GUI/calibration_tab.py`)

- **New section "LED Sync ROI"** created between `_create_intrinsic_section` and
  `_create_extrinsic_section` in `_create_widgets`: status label ("ROI set: 4/4 cameras" /
  "not set") + indicator dot (same `STATUS_COLORS` pattern as the origin indicator), button
  **"Record LED clip & set ROI"**, button **"Set ROI from folder…"** (filedialog to any folder of
  raw `*_GP{N}.mp4`, e.g. a trial's `video/`; use the `_GP(\d+)` regex from
  `calibration/video_processor.py` `GP_PATTERN`).
- State: `self._led_rois: dict[int, tuple[int,int,int,int]]`.
- **`_multi_record_worker` refactor (small):** replace `skip_sync: bool` with
  `sync_mode: "audio" | "light" | "trim_only" | "none"` (extrinsic passes the bottom-bar
  method mapped to `"audio"`/`"light"`; origin passes `"trim_only"`), and add
  `record_seconds: float | None` → `self._calib_stop_event.wait(timeout=record_seconds)` so a
  clip auto-stops. `"none"` skips `_run_calib_sync` and calls `on_synced(video_dir)` with the
  raw folder.
- **LED clip flow** (modelled on `_origin_start_recording`): purpose `"ledroi"`,
  `sync_mode="none"`, `record_seconds=LIGHT_SEARCH_SECONDS + 1`. After download: background
  thread runs `sample_frames_for_roi` per camera (status "Decoding frames…"), then on the Tk
  thread open the dialog prefilled with `_led_rois`; store the result; then
  `_cleanup_temp_videos(video_dir, "ledroi", timestamp)`.
- **After ROI confirmed:** set `cam.led_roi` on `self._camera_array` cameras if present. If a
  calibration file is currently loaded (`app_config["last_calibration"]` points to the file
  that populated `_camera_array`), re-save it **in place** with `save_calibration` so the
  trial→calibration *name* link stays stable. Otherwise the ROI is persisted by
  `_apply_calibration`, which sets `cam.led_roi` from `_led_rois` before saving.
  `_ext_auto_run_calibration` copies `_led_rois` onto the new `CameraArray` right after
  `run_extrinsic_calibration`. `load_calibration_file` repopulates `_led_rois` from the loaded
  cameras.
- **`_run_calib_sync`:** branch on `sync_mode == "light"`: require an ROI for every video's
  camera (else `raise LightSyncError("No LED ROI for GP{N} — run 'Record LED clip' first")`);
  call `compute_light_sync_offsets`, `format_light_sync_summary`,
  `evaluate_light_sync_acceptance`; abort path identical to audio (red dialog, cleanup,
  `return None` before trim). Status line logs on-frame/offset per camera.
- **`_update_pipeline_state`:** in light mode, extrinsic button disabled until `_led_rois`
  covers the connected cameras; status text "Set LED ROI first".
- **New public helper** `get_led_rois_for_sync(video_paths) -> dict[str, dict] | None`:
  `{video_path: {"roi": (x,y,w,h), "calib_size": (w,h)}}` using the same `_GP(\d+)` mapping as
  `get_camera_positions_for_sync`; `None` if any camera lacks an ROI.

### 3.5 Bottom bar + Recording tab

- **`main_window.py`** (l.241-246): add radio **"Light"** (`value="light"`). Persist: initial
  value `app_config.get("sync_method", "manual")`; `trace_add("write", ...)` writes it back
  and saves. Add `"sync_method": "manual"` to `go2kin_config_template.json`.
- **`recording_tab._start_recording`:** in light mode, before `create_trial`, require
  `calibration_tab.get_led_rois_for_sync(...)` to cover `available_cameras`; else
  `messagebox.showerror("No LED ROI for GP{N} — define it in the Calibration tab")` and return
  (a configuration error blocks recording rather than discarding a trial).
- **`recording_tab._auto_sync`:** branch on `self.sync_method_var.get() == "light"`: skip
  `check_audio_track`, camera-position/sound-source lookup and `compute_sync_offsets`; call
  `compute_light_sync_offsets(video_paths, rois, output_dir=str(video_dir), progress_callback=..., timer=timer)`,
  `format_light_sync_summary`, `evaluate_light_sync_acceptance`. Everything after the
  acceptance gate (trim, stitched preview, `update_trial(synced=True)`, discard dialog,
  timer table) is shared unchanged. Pass `sync_method="light"|"audio"` to `update_trial`
  (matches the `method` field proposed in `audio_sync_offset_approach.md` §7).
- Speaker/sound-source logic untouched (already gated on `"speaker"`).

### 3.6 Tooling, tests, docs

- **`tools/light_sync_test.py`** (like `tools/audio_sync_test.py`): args = folder of
  `*_GP{N}.mp4` + `--calib calibration.json` or `--roi N:x,y,w,h` (repeatable); runs
  `compute_light_sync_offsets`, prints the summary table, saves the signal plot; `--dialog`
  opens the ROI dialog on that folder and prints the chosen ROIs. This is the validation path
  before any GUI wiring.
- **`tests/test_light_sync.py`** (plain-python style like `tests/test_project_manager.py`):
  `detect_pulse` on synthetic signals — clean 100-frame pulse at 100 fps; partial on/off
  frames (asserts sub-frame `t_on`); no pulse (raises); pulse too short (raises); LED already
  on at frame 0 (raises). `evaluate_light_sync_acceptance` on hand-built results.
- **Docs:** `docs/light_sync_spec.md` (algorithm, ffmpeg command, limitations); CLAUDE.md
  architecture bullet + project-structure entries; user-manual page under `docs/manual/` +
  `mkdocs.yml` nav entry (LED placement guidance; workflow: Record LED clip → click LED →
  extrinsic → trials).

---

## 4. Implementation order

1. `light_sync.py` core (`read_roi_signal`, `detect_pulse`, `compute_light_sync_offsets`,
   summary/acceptance, plot) + `tests/test_light_sync.py` + `tools/light_sync_test.py`.
   Validate on a real 4-camera LED recording with hand-typed ROIs; record StepTimer numbers.
2. `CameraData.led_roi` + persistence round-trip (+ clearing with extrinsics).
3. `led_roi_dialog.py` component (+ `--dialog` mode in the tool).
4. Calibration tab: LED clip section, `sync_mode`/`record_seconds` refactor of
   `_multi_record_worker`, light branch in `_run_calib_sync`, ROI persistence hooks,
   pipeline gating, `get_led_rois_for_sync`.
5. Bottom bar radio + persistence; Recording tab gating + `_auto_sync` branch.
6. Docs.

Each step is independently testable; steps 1–3 touch no existing behaviour.

---

## 5. Verification

- `python tests/test_light_sync.py` and `python tests/test_project_manager.py` from repo root.
- `python tools/light_sync_test.py <folder> --roi 1:x,y,w,h …` on a real LED recording: one
  pulse per camera of ~100 frames (at 100 fps), `on_off_diff_frames` ≤ 1, offsets of a few
  frames; `synced/sync_led_signal.png` shows clean steps. Check the `-hwaccel cuda` path is
  taken (log line) with the NVENC build and the CPU fallback with the LGPL build. Compare wall
  time against the audio path's StepTimer table.
- End-to-end (`python code/go2kin.py`): select Light in the bottom bar → Calibration tab:
  Record LED clip → dialog → click LED in 4 views → OK → "ROI set: 4/4" → extrinsic records and
  syncs via light → Apply → calibration JSON has `led_roi` per camera, TOML unchanged.
  Recording tab: record a trial → synced videos have equal frame counts (logged by
  `trim_and_sync_videos`), stitched preview shows the LED turning on in the same frame in all
  4 cells. Cover the LED for one trial → red discard popup with "LED not detected". Switch back
  to Manual → audio path unchanged.

## 6. Open points to confirm at implementation time

- LED pulse timing relative to shutter start (sets `LIGHT_SEARCH_SECONDS`; also the LED-clip
  recording length).
- Whether the conda ffmpeg in use supports `-hwaccel cuda` (BtbN GPL build does; LGPL does not
  — fallback covers it, but the timing differs).
- Whether the GoPro exposure at the chosen fps is close to a full frame period (affects how
  informative the sub-frame `t_on` is; integer offsets are unaffected).
