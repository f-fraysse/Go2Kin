# Post-triangulation participant filter

## Context

After Pose2Sim triangulation, the `pose-3d/` folder contains one TRC file per detected
person (e.g. `<trial>_P0_<f0>-<f1>.trc`, `<trial>_P1_…`, …). In multi-person mode,
spurious detections — bystanders, reflections, persistent ID drift — produce extra TRC
files that pollute the downstream Filtering and Kinematics steps. We want to discard any
participant who is not actually inside the capture volume for a meaningful share of the
recording.

The rule: define a vertical-axis inclusion volume centred on the world origin (Z
unbounded) and require the Hip keypoint (HALPE_26 id 19, name `"Hip"`) to fall inside
this volume for at least `percent_time_inside_volume` of the triangulated frames
(default 2 %, rounded down, minimum 1 frame). Any TRC file that fails this test is
deleted before Pose2Sim Filtering runs.

User decisions captured up-front:
- New visible step **"Participant Filter"** in the Pipeline Progress UI, between
  Triangulation and Filtering.
- Discarded TRC files are **deleted** (no archive copy).
- Volume size driver: the **horizontal** (XY-plane) distance from origin to each
  camera in the calibration's Z-up world frame, averaged across cameras → `D`.
  The computed `D` is **printed to the terminal** for every trial.

### DECISION PENDING — volume shape

Two candidates, both centred on origin and unbounded in Z:

| Shape | Membership test | Volume parameter |
| --- | --- | --- |
| **Square prism** (original ask) | `\|hip_x\| ≤ X/2` AND `\|hip_y\| ≤ X/2` (in world Z-up; in TRC frame the equivalent is `\|TRC_X\| ≤ X/2` AND `\|TRC_Z\| ≤ X/2`) | side `X = D` |
| **Cylinder** (alternative) | `sqrt(hip_x² + hip_y²) ≤ R` (single horizontal-plane distance check; coordinate-system-agnostic — same expression in TRC frame using TRC X and TRC Z) | radius `R = D / 2` if matching the square's inscribed circle, or `R = D` if matching the bounding circle. Recommend `R = D / 2` so the cylinder's footprint matches the square's footprint area-wise. |

Pros of cylinder:
- One scalar comparison instead of two — cleaner code, no per-axis reasoning.
- No need to think about which TRC axis is which (the horizontal radius is invariant
  under the `zup2yup` permutation since that permutation only swaps the *labels* of
  the two horizontal axes).
- Rotationally symmetric — better matches the physical reality of a calibration whose
  origin is centred but whose camera ring isn't on a perfect grid.

Pick before implementing. The rest of this plan is written assuming **square prism**;
switching to cylinder changes only the membership-test expression and the name of the
config constant. Suggested cylinder defaults if chosen: `radius_m = D / 2`, config
constant renamed `inclusion_radius_factor = 0.5` (so `radius = inclusion_radius_factor
* D`).

## Coordinate-system note

`triangulation.make_trc` calls `common.zup2yup` ([common.py:734](../code/pose2sim/Pose2Sim/common.py#L734))
which permutes columns: `(Xz, Yz, Zz) → (Yz, Zz, Xz)`. So inside a TRC file the
**vertical** axis is **Y** (= world Z), and **TRC X** / **TRC Z** map to world Y / world
X.

Both candidate volume shapes are centred on the origin and rotationally / mirror
symmetric in the horizontal plane, so the membership test can be expressed directly in
TRC frame using TRC X and TRC Z (with TRC Y unbounded). No need to rotate points back
to the calibration's Z-up frame.

## Files to change / create

### New: `code/post_triangulation_filter.py`

Single self-contained module. Top-of-file configuration constant:

```python
# Minimum fraction of triangulated frames a participant's Hip must spend inside
# the inclusion volume to be kept. Rounded down, minimum 1 frame.
percent_time_inside_volume = 0.02
```

Public entry point called by the pipeline:

```python
def filter_participants_by_volume(processed_path: Path, calib_json_path: Path) -> None
```

Behaviour:

1. **Compute volume size driver `D`** from `calib_json_path`
   (Go2Kin's authoritative calibration JSON — has rotation as a 3×3 matrix, so no
   Rodrigues conversion needed; format documented in
   [persistence.py:37-50](../code/calibration/persistence.py#L37-L50)).
   For each camera: `pos_world = -R.T @ t` (formula from
   [view_calibration.py:27-28](../tools/view_calibration.py#L27-L28) and
   [alignment.py:157](../code/calibration/alignment.py#L157)). Take the **horizontal**
   norm `sqrt(x² + y²)`, average across cameras → `D`.
   Print: `[Participant Filter] Mean horizontal camera-origin distance D = {D:.3f} m
   (over N cameras)`. Then derive the volume parameter from `D` per the chosen shape
   (square: `X = D`; cylinder: `R = D/2`) and print the resulting bound.

2. **Iterate `processed_path/pose-3d/*.trc`** (top-level only — Pose2Sim Filtering globs
   the same set, so deleting from this folder is enough; no subfolder bookkeeping
   needed since the user chose deletion).

3. **For each TRC file**:
   - Read it with `pandas.read_csv(..., sep='\t', skiprows=4)` (line 3 is the
     marker-name header, line 4 is the X1/Y1/Z1 sub-header — see
     [triangulation.py:178-182](../code/pose2sim/Pose2Sim/triangulation.py#L178-L182)).
   - Read the marker-name header line (line 3) directly to find the **column index of
     `"Hip"`**. Do NOT trust positional index 19 — the TRC writes keypoints in
     skeleton-tree traversal order. In HALPE_26, `Hip` is the root node
     ([skeletons.py:50](../code/pose2sim/Pose2Sim/skeletons.py#L50)) so it ends up at
     position 0, but look it up by name to stay robust to skeleton changes.
   - Locate the data columns: for marker at position `k` (0-indexed in the
     keypoint list), the X/Y/Z data columns are `[2 + 3k, 3 + 3k, 4 + 3k]`
     (column 0 = Frame#, column 1 = Time).
   - Compute mask:
     - Square: `inside = (|hip_trc_x| ≤ X/2) & (|hip_trc_z| ≤ X/2)`
     - Cylinder: `inside = sqrt(hip_trc_x² + hip_trc_z²) ≤ R`

     Ignore NaN frames (NaN → not inside).
   - `total_frames = len(df)`,
     `threshold = max(1, math.floor(total_frames * percent_time_inside_volume))`.
   - If `inside.sum() < threshold`: print
     `[Participant Filter] Discarding {trc.name} ({inside_count}/{total_frames}
     frames inside, threshold {threshold})` and `trc.unlink()`.
   - Else: print `[Participant Filter] Keeping {trc.name} ({inside_count}/{total_frames}
     frames inside)`.

4. After the loop, print a one-line summary: `[Participant Filter] Kept K, discarded D
   participant TRC files.` Raise no error if all are discarded — let downstream
   Filtering decide what to do with an empty `pose-3d/`.

The function must NOT touch `os.getcwd()` — `processing_tab.py` already chdirs to
`processed_path` and we accept paths explicitly so the function is independently
testable.

### Modify: `code/GUI/processing_tab.py`

1. Add `"Participant Filter"` to `_PIPELINE_STEPS`
   ([processing_tab.py:17-24](../code/GUI/processing_tab.py#L17-L24)) between
   `"Triangulation"` and `"Filtering"`. This automatically grows the row of progress
   circles in `_build_ui` since it iterates that list.

2. In `_run_pipeline_with_progress`
   ([processing_tab.py:233-293](../code/GUI/processing_tab.py#L233-L293)):
   - Resolve the calibration JSON path **before** the steps loop, using the trial's
     `calibration_file` and `pm.get_calibration_path(project, calib_name, fmt="json")`.
     This means the function needs access to `project`, `session`, `trial_name` —
     extend its signature (caller already has all three at line 206).
   - Insert the new step in the `steps` list at line 254-261:
     ```python
     ("Triangulation", P2S.triangulation),
     ("Participant Filter",
      lambda: filter_participants_by_volume(processed_path, calib_json_path)),
     ("Filtering", P2S.filtering),
     ```
   - Import at the top of the function:
     `from post_triangulation_filter import filter_participants_by_volume`.

3. Update the call site at [processing_tab.py:206](../code/GUI/processing_tab.py#L206) to
   pass the extra args.

### No change needed

- `pose2sim_builder.py` — staging is unaffected.
- `Pose2Sim` submodule — untouched (Filtering picks up whichever TRC files remain).
- TOML config template — no new keys.

## Reused utilities / patterns

- **Camera world-position formula**: matches the existing
  [view_calibration.py:17-30](../tools/view_calibration.py#L17-L30) `load_cameras()` (we
  duplicate the 3-line formula rather than import the GUI tool — it's inside `tools/`
  and not on the import path).
- **Calibration JSON access**: `pm.get_calibration_path(project, calib_name,
  fmt="json")` (already used in `pose2sim_builder.py` for the TOML variant at
  [pose2sim_builder.py:139](../code/pose2sim_builder.py#L139)).
- **HALPE_26 Hip node**: id 19, name `"Hip"`, root of tree —
  [skeletons.py:50](../code/pose2sim/Pose2Sim/skeletons.py#L50).
- **TRC layout**: header lines 0–4 then data; column 0 = Frame#, col 1 = Time, then
  X/Y/Z triples in skeleton-tree order — see
  [triangulation.py:178-188](../code/pose2sim/Pose2Sim/triangulation.py#L178-L188).

## Verification

1. **Dry run on existing trial**: pick a trial that already produced multiple TRC
   files in `pose-3d/`. Run the pipeline from the Processing tab and watch the
   terminal:
   - Confirm the printed `D` value is a sensible distance (a couple of metres for a
     typical 4-camera setup).
   - Confirm the per-TRC keep/discard lines list `inside/total` counts.
   - Confirm any discarded `.trc` is gone from `pose-3d/` after the step.
2. **Single-person mode**: a trial with exactly one TRC file and a clearly in-volume
   subject must keep the file. Sanity-check by setting
   `percent_time_inside_volume = 0.99` temporarily — the file should now be deleted
   if the participant ever leaves the volume.
3. **Edge case — empty TRC / no Hip**: a TRC with all-NaN Hip rows should be
   discarded (inside count 0 < threshold ≥ 1).
4. **Pipeline UI**: confirm 6 colored circles render (Calibration, Pose Estimation,
   Triangulation, Participant Filter, Filtering, Kinematics) and that the new step's
   circle goes blue → green during a successful run.
5. **Downstream Filtering**: after the new step, the standard Pose2Sim Filtering step
   must still run and produce `*_filt_*.trc` files for the kept participants only.
