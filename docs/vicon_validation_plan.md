# Vicon ↔ Go2Kin kinematics comparison — implementation plan

**Status:** proposal, not implemented (as of 2026-09-04). No code or config for this exists
in the repo yet; this document is the design to work from when the work is picked up.

## Context

We record Vicon (marker-based) and Go2Kin (markerless, 4× GoPro → RTMPose → Pose2Sim
triangulation) **simultaneously**, giving two independent 3D point streams of the same
movement. The goal is to validate Go2Kin's kinematics against Vicon by running **two
OpenSim inverse-kinematics solutions in parallel** — one driven by the Halpe26 keypoints,
one by the Vicon markers — and comparing the resulting joint angles.

The comparison is only meaningful if both IKs solve the **same model with the same segment
lengths and the same joint definitions**. So the design is: attach both markersets to one
copy of `Model_Pose2Sim_muscles_flex.osim`, **scale it once** from the Vicon static trial,
then run IK twice against that single scaled model. The only thing differing between the
two `.mot` files is the marker input — which is exactly the quantity under test.

Sync between the two systems is explicitly **out of scope** for this proof of concept;
trials will be aligned approximately and the residual offset treated as a known limitation.

```
Model_Pose2Sim_muscles_flex.osim
  + Markers_Halpe26.xml   (shipped)          ┐
  + Markers_Vicon.xml     (to be authored)   ┘  → scale ONCE (Vicon static) → shared.osim
       ├── IK( go2kin_*.trc , Halpe26 task set ) → go2kin.mot
       └── IK( vicon_*.trc  , Vicon   task set ) → vicon.mot
                                    ↓
                         compare per coordinate
```

### Why not "swap the Halpe26 markerset"

`Markers_Halpe26.xml` is not a free choice — it is the OpenSim-side counterpart of what
RTMPose physically detects. Pose2Sim triangulates exactly those 26 keypoints into the
`.trc`; the markerset only declares *where on the model each detected keypoint is expected
to sit*. Replacing it with Vicon labels would leave IK with zero usable markers, because
OpenSim only uses markers present in the TRC **and** the model markerset **and** the IK
task set. The operation is therefore an **addition** of a second markerset, not a swap —
and that same three-way intersection rule is what lets one model carry both markersets at
once without the two runs interfering.

## Key constraint: do not edit the submodule

`code/pose2sim/` is a git submodule. Anything added under
`code/pose2sim/Pose2Sim/OpenSim_Setup/` is untracked by Go2Kin and will be lost on a
submodule update. **All new files live outside it.** The base model is read from the
submodule read-only, via the path resolved by
[`get_opensim_setup_dir()`](../code/pose2sim/Pose2Sim/kinematics.py#L68-L81).

## Deliverables

```
config/opensim_vicon/
  Markers_Vicon.xml           # Vicon markerset expressed on Model_Pose2Sim bodies
  Scaling_Setup_Vicon.xml     # ScaleTool: measurement set + MarkerPlacer
  IK_Setup_Vicon.xml          # IKMarkerTask weights for the Vicon labels
tools/vicon_validation/
  vicon_c3d_to_trc.py         # C3D → TRC (units, axes, label prefixes, occlusions)
  build_scaled_model.py       # base model + both markersets → one scaled .osim
  run_dual_ik.py              # two IK runs against that scaled model
  compare_kinematics.py       # resample to common time base + RMSE / correlation / plots
```

`tools/` already holds standalone utilities of this kind (`view_calibration.py`,
`export_toml.py`, `audio_sync_test.py`), so it is the right home.

## Steps

### 1. `vicon_c3d_to_trc.py` — Vicon C3D → TRC

Write our own rather than calling
[`Pose2Sim/Utilities/c3d_to_trc.py`](../code/pose2sim/Pose2Sim/Utilities/c3d_to_trc.py):
it is in the submodule (unpatchable) and **has a unit bug** — at
[lines 86-91](../code/pose2sim/Pose2Sim/Utilities/c3d_to_trc.py#L86-L91) it scales mm data
to metres (`unit_scale = 0.001`) but then writes `Units` = `mm` into the TRC header
([line 106](../code/pose2sim/Pose2Sim/Utilities/c3d_to_trc.py#L106)), so OpenSim divides by
1000 a second time. Use it as a structural reference for the TRC header format only.

Ours must handle:
- **Units** — emit metres and write `Units m`, consistently.
- **Axes** — Vicon lab frame is typically Z-up; the OpenSim model is Y-up. Same
  transform as [`trc_Zup_to_Yup.py`](../code/pose2sim/Pose2Sim/Utilities/trc_Zup_to_Yup.py).
- **Label prefixes** — Nexus exports `Subject:LASI`; strip to `LASI`.
- **Occlusions** — c3d flags invalid points with a negative residual. These must not reach
  IK as zeros. Simplest PoC contract: **require gap-filled trials from Nexus**, and have
  the script hard-fail with a per-marker report if any invalid samples remain.
- Reuse `c3d` 0.6.0 (already in the env; `ezc3d` is not installed and is not needed).

Run it on both the static and the dynamic Vicon trial.

### 2. `Markers_Vicon.xml` — the markerset

An OpenSim `<MarkerSet>` in the same form as
[`Markers_Halpe26.xml`](../code/pose2sim/Pose2Sim/OpenSim_Setup/Markers_Halpe26.xml): per
marker a `<socket_parent_frame>`, a `<location>` in that body's local frame, and `<fixed>`.

The model has 30 bodies; the relevant ones are:

```
pelvis  femur_r/l  tibia_r/l  talus_r/l  calcn_r/l  toes_r/l
torso  head  humerus_r/l  ulna_r/l  radius_r/l  hand_r/l
```

Mapping for our set (ASIS, PSIS, greater trochanter, thigh + shank clusters, femoral
epicondyles, malleoli, foot markers, acromion, suprasternale, T2, T10):

| Vicon markers | Body |
|---|---|
| ASIS, PSIS | `pelvis` |
| greater trochanter, thigh cluster, femoral epicondyles (med + lat) | `femur_r` / `femur_l` |
| shank cluster, malleoli (med + lat) | `tibia_r` / `tibia_l` |
| heel / hindfoot markers | `calcn_r` / `calcn_l` |
| forefoot / toe markers | `toes_r` / `toes_l` |
| acromion, suprasternale, T2, T10 | `torso` |

**Body assignment must be correct by hand; the locations do not.** Author approximate
locations with `<fixed>false</fixed>`, and let ScaleTool's `MarkerPlacer` refine them from
the static trial (step 3). This matters most for the thigh and shank **clusters**, whose
true positions are wherever the plates were strapped and are therefore subject-specific —
MarkerPlacer resolves them automatically.

Note the model's body naming (`femur_r`, `tibia_r`, `calcn_r`, `torso`, `humerus_r`) is
Rajagopal/gait2392-like, so published markersets for those models are a usable starting
point for the approximate locations.

### 3. `build_scaled_model.py` — one shared scaled model

```
load  Model_Pose2Sim_muscles_flex.osim            (read-only, from the submodule)
merge Markers_Halpe26.xml + Markers_Vicon.xml     → single MarkerSet
initSystem(); printToXML(work/shared_unscaled.osim)
run   opensim.ScaleTool(Scaling_Setup_Vicon.xml)  → work/shared_scaled.osim
```

`Scaling_Setup_Vicon.xml` uses **standard measurement-based scaling from the Vicon static
trial** — deliberately *not* Pose2Sim's approach, which derives manual segment ratios from
the markerless TRC itself
([kinematics.py:442-452](../code/pose2sim/Pose2Sim/kinematics.py#L442-L452)). Vicon is the
gold standard here, so it defines the anthropometry and scaling drops out as a confound.

Model the measurement set on
[`Scaling_Setup_Pose2Sim_Halpe26.xml`](../code/pose2sim/Pose2Sim/OpenSim_Setup/Scaling_Setup_Pose2Sim_Halpe26.xml),
which defines eight measurements (`torso arm forearm thigh shank foot head pelvis`) from
marker pairs. The Vicon equivalents come from our landmark definitions — e.g. pelvis from
ASIS-to-ASIS, thigh from hip-joint-centre to knee-epicondyle midpoint, shank from
epicondyle midpoint to malleolus midpoint.

Unlike Pose2Sim — which disables the MarkerPlacer outright by setting every `marker_file`
to `Unassigned` ([kinematics.py:453](../code/pose2sim/Pose2Sim/kinematics.py#L453)) — we
**enable** it, pointing at the static-trial TRC, with an IKTaskSet listing only the Vicon
markers.

> **Verification checkpoint:** confirm that MarkerPlacer leaves the Halpe26 markers in
> place (they have no experimental counterpart in the Vicon static trial and no task
> entry, so they should be scaled but not moved). Diff the Halpe26 `<location>` values
> between `shared_unscaled.osim` and `shared_scaled.osim` — they should differ only by the
> segment scale factors.

### 4. `run_dual_ik.py` — two IK runs

Both against `shared_scaled.osim`, following the pattern in
[`perform_IK()`](../code/pose2sim/Pose2Sim/kinematics.py#L488-L509) (parse setup XML, set
`model_file` / `marker_file` / `time_range` / `output_motion_file`, run
`InverseKinematicsTool`):

| Run | Setup file | TRC input |
|---|---|---|
| Go2Kin | `IK_Setup_Pose2Sim_Halpe26.xml` (copied out of the submodule) | `[trial]/processed/pose-3d/*_filt_*.trc` |
| Vicon | `IK_Setup_Vicon.xml` | output of step 1 (dynamic trial) |

This works because OpenSim IK only uses markers present in the TRC **and** the model
markerset **and** the IK task set — so each run silently ignores the other's markers. Set
`report_errors = true` on both.

`IK_Setup_Vicon.xml` needs an `<IKMarkerTask>` per Vicon label with a weight. Start with
uniform weight 1, dropping to ~0.5 for cluster markers. Keep the
`<IKCoordinateTask name="L5_S1_Flex_Ext">` entry from the Halpe26 setup in both runs so
the lumbar chain is constrained identically.

### 5. `compare_kinematics.py`

Both `.mot` files carry identical coordinate names, so comparison is column-wise:
`hip_flexion_r/l`, `hip_adduction_r/l`, `hip_rotation_r/l`, `knee_angle_r/l`,
`ankle_angle_r/l`, `arm_flex_r/l`, `elbow_flex_r/l`, `pelvis_tilt/list/rotation`, …

- Resample both to a common time base (Vicon rate is the sensible target).
- Per coordinate: RMSE, mean offset, Pearson r, Bland-Altman.
- Overlay plots per coordinate.

**Scope note:** joint angles below the pelvis are segment-relative and therefore
independent of each system's global frame. `pelvis_tilt/list/rotation` and the
`pelvis_tx/ty/tz` translations are **not** — they are expressed in ground, and the Vicon
lab frame and the Go2Kin calibration frame are unrelated. Report those separately and
treat them as invalid until a global alignment step is added.

## Inputs required before starting

1. **A static-trial C3D** (subject standing still) — drives both the measurement-based
   scaling and the MarkerPlacer refinement.
2. **A dynamic-trial C3D** recorded simultaneously with a Go2Kin trial, gap-filled in
   Nexus, plus the matching Go2Kin trial folder.
3. **The marker landmark definitions** — which label sits on which landmark. The exact
   label strings come free from the C3D, but the body assignments and the scaling
   measurement pairs need the anatomical intent, particularly for the cluster markers.

## Verification

- `vicon_c3d_to_trc.py`: round-trip a known frame — marker coordinates in metres, Y-up,
  and a deliberate occlusion triggers the hard-fail path.
- Scaling: inspect `opensim_logs.txt` for the scale factors; segment lengths should match
  the participant's measured anthropometry. Confirm the Halpe26-marker checkpoint in
  step 3.
- IK: `report_errors = true` gives marker RMS and max error per frame for both runs.
  Vicon RMS should land ~1-2 cm. **A markedly worse Go2Kin RMS than a normal Pose2Sim run
  is the signal that the shared-scaling design is hurting the markerless solve.** Diagnose
  by additionally running the Go2Kin IK against a normally Pose2Sim-scaled model and
  comparing marker errors; if confirmed, fall back to scaling each pipeline its own way
  and accept scaling as part of the error term.
- End to end: overlay knee flexion from both systems for a gait or squat trial. Curve
  shapes should agree closely; a constant time shift is expected and acceptable (sync is
  out of scope), a shape mismatch is not.

## Out of scope

- Temporal synchronisation between Vicon and Go2Kin.
- Global frame alignment between the Vicon lab frame and the Go2Kin calibration frame.
- Any change to the Go2Kin application itself — this is standalone validation tooling.

## Considered and rejected

**Using the LSTM / marker-augmentation set instead of authoring `Markers_Vicon.xml`.**
Setting `use_augmentation = true` makes Pose2Sim emit ~43 anatomical markers
([`Markers_LSTM.xml`](../code/pose2sim/Pose2Sim/OpenSim_Setup/Markers_LSTM.xml)) — the
OpenCap set (`r.ASIS_study`, `r_knee_study`, `r_calc_study`, `r_thigh1/2/3_study`, …),
which is close enough to a conventional gait marker set that the job could have collapsed
to a rename map, with `Scaling_Setup_Pose2Sim_LSTM.xml` and `IK_Setup_Pose2Sim_LSTM.xml`
reused as-is. Rejected in favour of authoring our own markerset against our actual Vicon
labels: the augmenter is an extra learned transformation in the markerless path, and
keeping it out means the comparison tests triangulation + IK rather than triangulation +
augmentation + IK. Worth revisiting if authoring the markerset proves slow, or if a direct
**marker-position** comparison is wanted later — that is only meaningful with the
augmented set, since raw Halpe26 keypoints are estimated joint centres with no Vicon
surface-marker counterpart.
