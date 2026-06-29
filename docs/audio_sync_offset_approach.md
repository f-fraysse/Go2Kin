# Offset-based camera sync — design exploration

> **Status: design exploration, NOT implemented.** This note evaluates replacing the
> post-recording video trim/re-encode with a *lazy offset* model. It documents the current
> architecture, candidate approaches, their consequences across the whole processing /
> visualisation chain, the risks, and a tentative phased plan. No code has been changed.

Companion notes: [`audio_sync_spec.md`](audio_sync_spec.md) (algorithm) and
[`audio_sync_performance.md`](audio_sync_performance.md) (timing breakdown).

---

## 1. Motivation

Today, after every recording Go2Kin runs audio sync and then **trims/re-encodes** all camera
videos (`hevc_nvenc`) into `video/synced/` so that frame `N` is the same instant in every
camera. Two costs:

1. **Time** — the re-encode is the dominant part of the post-recording break, which lengthens
   the gap between successive recordings.
2. **Disk** — every video exists twice: the raw download in `video/` and the synced copy in
   `video/synced/`.

The proposal: **keep only the raw downloaded videos, store the per-camera frame offset in
`trial.json`, and apply the offset lazily at each processing / visualisation step** instead of
baking it in by re-encoding.

The catch: frame alignment ("frame `N` = same instant in every camera") is *assumed* in many
places downstream. Removing the trim means each of those places must apply the offset itself,
and a missed or mis-signed offset produces subtly wrong 3D output that is easy to overlook.

---

## 2. How sync works today (baseline)

All in [`code/audio_sync.py`](../code/audio_sync.py):

- **`compute_sync_offsets()`** detects two clap onsets per camera and returns, per camera, the
  offset in samples / ms / frames / seconds plus diagnostics. **`evaluate_sync_acceptance()`**
  gates quality (both claps detected, clap1/clap2 consistent to within half a frame, and no
  inter-camera offset above 200 ms). On failure the trial is discarded (Recording) or extrinsic
  is aborted (Calibration).
- **`trim_and_sync_videos()`** re-encodes each video into `video/synced/`:
  - `drop_c = round(offset_seconds_c · fps)` front frames dropped per camera;
  - `common_frames = min(total_frames − drop − 1)` across cameras;
  - the output seek `(drop + 0.5)/fps` lands just *past* frame `drop`, so it actually discards
    `drop_c + 1` frames (hence the `− 1` in the available-frames formula).
- **`create_stitched_preview()`** builds the 2×2 QA grid from the synced videos.
- **`trial.json`** currently records only `synced: bool`. **The offsets themselves are
  discarded** once the trim is done.

---

## 3. The unifying insight

The trim is *pure frame selection* — it picks a contiguous run of frames from each raw video.
That is exactly equivalent to a lazy index mapping:

> **synced frame `i` of camera `c`  ↔  raw frame `i + drop_c`**,
> where `drop_c = round(offset_seconds_c · fps)` and all `drop_c ≥ 0`
> (the reference camera is `0` after the Step-7 re-baseline, so no camera ever needs a negative
> drop).

So the entire feature reduces to: **compute `drop_c` once, persist it, and add `drop_c`
wherever a per-camera raw video is read.** Because this reproduces the *same frames* the trim
would have selected, correctness is largely **inherited** from the existing, already-accepted
behaviour rather than re-derived.

One subtlety to lock down: the current trim discards `drop_c + 1` frames because of the
`+0.5/fps` seek nudge (which exists only to keep ffmpeg's float seek off the previous frame).
A lazy implementation uses exact integer frame indexing (`cv2.CAP_PROP_POS_FRAMES = drop_c + i`)
and so should use exactly `drop_c` — slightly *more* correct than the trim, but it must be the
**single agreed definition** used by every consumer. Pick one and centralise it (see §8).

---

## 4. Where frame-lock is assumed today (consumer inventory)

| Consumer | Where | Assumption |
|---|---|---|
| **Pose2Sim processing** | [`processing_tab.py:263-272`](../code/GUI/processing_tab.py#L263-L272) | Pipeline runs Calibration → Pose Estimation → Person Association → Triangulation → Filtering → Kinematics and **deliberately omits** Pose2Sim's own `synchronization()` step, because videos arrive pre-trimmed. |
| **Staging** | [`pose2sim_builder.py`](../code/pose2sim_builder.py) | Stages videos from `video/synced/`; uses the on-disk synced filenames as the source of truth for which cameras are present. |
| **Person assoc. / triangulation** | `code/pose2sim/Pose2Sim/{personAssociation,triangulation}.py` | For each frame `f`, match the JSON named `*_{f:06d}.json` in every camera — assumes equal frame index = same instant. |
| **Visualisation — 2D** | [`visualisation_tab.py`](../code/GUI/visualisation_tab.py) | Overlay reads `{cam}_{frame_idx:06d}.json` for the displayed frame. |
| **Visualisation — 3D (TRC)** | same | Maps the displayed `frame_idx` to the TRC `Frame#` column. |
| **Visualisation — IK (.mot)** | same | Maps `frame_idx / fps` (time) to the `.mot` row. |
| **Extrinsic calibration** | `calibration/{video_processor,extrinsic,triangulation,calibrate}.py` | A per-sample `sync_index` is assumed identical across cameras (PnP keyed by `(cam_id, sync_index)`, relative poses on common `sync_index`, origin on best `sync_index`). |

**Crucial enabling fact:** Pose2Sim's *own* synchronisation
(`code/pose2sim/Pose2Sim/synchronization.py`) already aligns cameras purely by **renaming the
per-frame JSON files** (`new = frame − offset`, dropping non-positive results) into a
`pose-sync/` directory — **no video re-encode**. That is precisely the operation we need, and
the downstream steps already prefer `pose-sync/` when it exists.

---

## 5. Approaches for the processing chain

### Approach A — inject audio offsets via JSON rename  *(recommended / tentative plan)*

Run 2D pose on the **raw** videos (it produces one JSON per video frame regardless of sync),
then add a small step that copies each `pose/cam_N/*_{f}.json` to
`pose-sync/cam_N/*_{f − drop_c}.json`, dropping frames whose shifted index ≤ 0. This mirrors
`synchronization.py` exactly, but uses our **accurate clap-based** `drop_c` instead of
Pose2Sim's motion cross-correlation. Person Association and Triangulation then read `pose-sync/`
unchanged, and the resulting TRC `Frame#` column lives in the synced timeline.

- **Pros:** keeps clap accuracy; deterministic; ~20 lines; downstream untouched; no re-encode.
- **Cons:** one new step to maintain; must respect Pose2Sim's directory/naming conventions.

### Approach B — Pose2Sim native motion sync

Feed raw videos and add `P2S.synchronization()` to the pipeline so Pose2Sim computes the
offsets itself from keypoint motion.

- **Pros:** least new code (just re-enable an existing step).
- **Cons:** discards the audio offsets and relies on motion cross-correlation — the very thing
  audio sync was built to avoid (it can fail when motion is ambiguous, and adds an analysis
  pass). Not recommended; listed for completeness.

### Approach C — offset the video reads inside pose estimation

Patch Pose2Sim's `poseEstimation` to seek `drop_c` per camera so the emitted JSONs are already
aligned.

- **Cons:** edits the vendored submodule (fragile across submodule updates); more invasive than
  A for no real gain. Rejected.

---

## 6. Consequence for visualisation

Because the synced timeline is *defined by* the derived data (renamed JSONs, TRC `Frame#`,
`.mot` time), and the visualiser shows **one camera at a time**, the only video-side change is:

> when reading the raw video for camera `c`, seek to **`frame_idx + drop_c`**.

Everything else stays in the synced timeline and is unchanged:

- 2D overlay still looks up `{cam}_{frame_idx:06d}.json` (the renamed, synced JSONs);
- 3D overlay still matches `frame_idx` against the TRC `Frame#`;
- IK overlay still maps `frame_idx / fps` to `.mot` time.

Two housekeeping items: read `drop_c` from `trial.json`, and clamp the scrub-bar length to the
common frame count so overlays exist for every displayable frame.

---

## 7. Data model — persisting offsets in `trial.json`

Add a `sync` object (keep `synced: bool` for backward compatibility). Key the cameras by **GP
camera number** (re-keyed from the path via the `_GP(\d+)` regex used in `pose2sim_builder.py`),
**not** by file path — paths are not portable between machines/sessions.

```json
"sync": {
  "method": "audio_clap",
  "fps": 100,
  "reference_camera": 1,
  "accepted": true,
  "cameras": {
    "1": {"drop_frames": 0, "offset_seconds": 0.0,   "final_offset_ms": 0.0, "clap1_ms": 0.0, "clap2_ms": 1.2, "diff_ms": 1.2},
    "2": {"drop_frames": 1, "offset_seconds": 0.005, "final_offset_ms": 5.1, "clap1_ms": 5.1, "clap2_ms": 4.9, "diff_ms": 0.2}
  }
}
```

`drop_frames` is the canonical applied integer offset; the raw floats are retained for audit and
for the summary table. Persist via the existing `ProjectManager.update_trial(...)`.

---

## 8. Risks & gotchas — "errors will be easy"

- **Single source of truth for `drop_c`.** One helper computes `drop_c` from the stored
  offsets; every consumer (JSON rename, visualisation seek, and extrinsic if ever changed) calls
  it. Document the exact definition (in particular, the lazy model should use exact `drop_c`, not
  the trim's `drop_c + 1` nudge artefact) and never recompute it ad hoc.
- **Sign / direction.** Reference camera = 0; positive offsets drop the front. This matches the
  trim exactly, so direction correctness is inherited — but it is the most likely place for a
  silent bug, so validate against the trim (§10, phase 1).
- **Re-key by camera number, not path.** The `compute_sync_offsets()` result is keyed by video
  path; convert to GP-number keys before writing `trial.json`.
- **Common length / range.** Triangulation auto-caps to `min(len(JSON))` across cameras; the
  JSON rename drops frames whose shifted index ≤ 0; the visualiser must clamp its scrub bar.
  These three must agree on "what frames exist".
- **Backward compatibility.** Existing trials have `video/synced/` + `synced: true` but no
  `sync.cameras`. Adopt this fallback order in `pose2sim_builder` and visualisation:
  1. `sync.cameras` present → raw videos + offset;
  2. else `video/synced/` exists → use synced videos with `drop = 0`;
  3. else error.
- **Camera source-of-truth shift.** `pose2sim_builder` currently infers the camera set from the
  on-disk `synced/` filenames; that role moves to the raw filenames plus the offset map.
- **Failed clap detection.** A camera with no detectable claps already fails the acceptance
  gate, which discards the whole trial — unchanged.

---

## 9. Scope decisions

- **Extrinsic calibration: unchanged.** Its sync videos are transient — used to compute camera
  poses and then discarded — so the "keep raw / save time" rationale is weak there, while the
  `sync_index` machinery (PnP, relative poses, origin selection) is the most correctness-
  sensitive code in the project. Keep the existing sync + trim of calibration videos.
- **Stitched 2×2 preview: dropped** from the automatic post-recording path (this is where most
  of the time saving comes from). Sync QA remains via the acceptance gate, the numeric offset
  summary table, and `sync_onsets.png`. On-demand regeneration from raw + offset is possible
  future work.
- **Recording flow:** keep `compute_sync_offsets()` + the acceptance gate, persist the offsets
  to `trial.json`, and skip `trim_and_sync_videos()`.

---

## 10. Tentative phased implementation (for when work begins)

1. **Persist offsets** to `trial.json` (purely additive). Can run *alongside* the current trim
   so the stored `drop_frames` can be validated against the trim's `drop`.
2. **Processing:** stage raw videos in `pose2sim_builder`, add the JSON-rename sync step
   (Approach A), and add the backward-compat fallback (§8).
3. **Visualisation:** per-camera seek offset + scrub clamp + read offsets from `trial.json`.
4. **Recording:** stop trimming; drop the automatic stitched preview.
5. **Validation:** reprocess a known-good, previously-trimmed trial through the offset path and
   confirm the 3D TRC matches within frame-rounding.

Each phase is independently testable and the fallback keeps existing trials working throughout.

---

## 11. Benefits / trade-offs summary

**Gains:** faster recording turnaround (no re-encode), a single copy of each video on disk, and
a persisted, auditable record of the sync offsets.

**Costs:** added indirection — the offset must be read and applied consistently at every
consumer — and a one-time correctness-validation effort against the current trim. The risk is
concentrated in getting `drop_c` defined and applied identically everywhere; centralising it and
validating against the existing trim mitigates most of it.
