# Plan: Use RajagopalLaiUhlrich2023.osim for Pose2Sim scaling + IK

**Status: PLAN ONLY — not implemented.** Investigation done 2026-09-17; open questions at the end.

## Context

Pose2Sim's `kinematics.py` hardcodes one of two bundled OpenSim models
(`Model_Pose2Sim_simple.osim` / `Model_Pose2Sim_muscles_flex.osim`, chosen by the
`use_simple_model` config flag). We want to run scaling + inverse kinematics on the
Stanford/OpenSim-team model instead: `RajagopalLaiUhlrich2023.osim`, already copied into
`code/pose2sim/Pose2Sim/OpenSim_Setup/`. The source folder (including Geometry meshes) is
`D:\Program Files\OpenSim 4.5\resources\Models\Rajagopal`.

It is **not** a one-line swap. Two hard blockers, several warn-only mismatches.

## Model comparison

| | Model_Pose2Sim_muscles_flex | RajagopalLaiUhlrich2023 (RLU) |
|---|---|---|
| OpenSim doc version | 40000 | 40000 (no conversion needed) |
| Bodies | 30 | 22 |
| Coordinates | 63 | 36 |
| Coupler constraints | 40 | 4 (patella only) |
| Muscles | 636 DeGrooteFregly2016 | 160 Millard2012 (IK will be faster to init) |
| Built-in markers | 0 | 66 (Vicon-style; irrelevant — see below) |

Bodies in the Pose2Sim model but **missing from RLU**: `sacrum`, `lumbar1`–`lumbar5`,
`Abdomen`, `head`. All 22 remaining body names match exactly.

RLU's built-in 66-marker set is harmless: `kinematics.py` calls
`unscaled_model.set_MarkerSet(markerset)` which **replaces** the model's markers wholesale
with the Pose2Sim `Markers_*.xml` set.

### The spine difference (the part that causes both blockers)

- **Pose2Sim model**: trunk = chain of bodies `pelvis` →(weld `sacrumjnt`)→ `sacrum` →
  `lumbar5` → … → `lumbar1` → `torso`, plus `Abdomen` and a separate `head` body.
  23 spine-related coordinates, but 20 are slaved to three via
  `CoordinateCouplerConstraint`: every lumbar level + abdomen follows `L5_S1_Flex_Ext`,
  `L5_S1_Lat_Bending`, `L5_S1_axial_rotation`. Effectively a **3-DOF trunk** drawn as
  5 vertebrae.
- **RLU**: one lumped `torso` attached to pelvis by a single 3-DOF `back` joint
  (`lumbar_extension`, `lumbar_bending`, `lumbar_rotation`). Skull is part of the torso
  mesh (`hat_skull.vtp`) — no `head` body, no neck joint. Also **no wrist coordinates**
  (hands fixed to radius; Pose2Sim model has `wrist_flex_*`/`wrist_dev_*`).

So trunk kinematics are functionally equivalent (3 DOF either way); what breaks is names.

## Blockers

### Blocker 1 — markers attached to `/bodyset/head` (hard failure)

`Markers_Halpe26.xml`: `Nose`, `Head`. `Markers_LSTM.xml`: `Nose`, `REye`, `LEye`.
RLU has no `head` body → `initSystem()` fails on the missing parent frame.

**Decision (revisitable):** re-parent these markers to `/bodyset/torso` with recomputed
local offsets, in **new variant marker files** (originals untouched so the default model
keeps working). We may change this approach later (e.g. drop the markers instead — they
are low-weight in IK — or attach a headless-model-specific strategy).

### Blocker 2 — `IKCoordinateTask name="L5_S1_Flex_Ext"` in every IK setup (hard failure)

All 10 `IK_Setup_Pose2Sim_*.xml` files contain this task (weight 0.1,
`value_type = default_value`). It is a light regularizer pulling lumbar flexion toward
neutral so noisy shoulder/hip keypoints don't fold the torso. RLU has no coordinate of
that name → the IK tool errors.

Fix options (implement at runtime, not by editing the 10 XMLs):
- **Rename** the task to `lumbar_extension` when the model has that coordinate
  (preserves the regularizing intent — recommended), or
- **Drop** any `IKCoordinateTask` whose coordinate doesn't exist in the scaled model
  (fully model-agnostic).

Either way the filter runs in `perform_IK` after parsing the setup XML with lxml,
checking coordinate names against the scaled model, and logging what was changed.

## Warn-only / cosmetic mismatches (no code change required)

- **Scaling setups** list `BodyScale` entries for `sacrum`, `lumbar1–5`, `head`,
  `Abdomen`. OpenSim's ScaleTool only **warns** on unknown segments — proven in
  production today by `scapulaPhantom_r/l`, which don't exist in the current model
  either. RLU's single `torso` scale absorbs the whole trunk+head. Leave the XMLs alone.
- **Geometry**: 10 meshes referenced by RLU are missing from `OpenSim_Setup/Geometry/`
  (`r_femur.vtp`, `l_femur.vtp`, `r_tibia.vtp`, `l_tibia.vtp`, `r_fibula.vtp`,
  `l_fibula.vtp`, `r_talus.vtp`, `l_talus.vtp`, `r_foot.vtp`, `r_bofoot.vtp` — Pose2Sim
  ships the same meshes under `femur_r.vtp`-style names). Missing meshes only log
  warnings; IK/scaling results are unaffected. Copy them from the OpenSim 4.5 Rajagopal
  folder for clean visualisation.
- **Output differences to expect**: the `.mot` loses per-level lumbar columns (they were
  coupled duplicates anyway) and genuinely loses **neck** and **wrist** angles, which RLU
  doesn't model. Trunk comes out as `lumbar_extension/bending/rotation`.

## Planned changes

All in the `code/pose2sim` **git submodule** working tree except (5) and this doc.
Submodule caveat: edits show as a dirty submodule and are lost on
`git submodule update --force` — same situation as the existing local mods
(`Markers_LSTM.xml`, `Scaling_Setup_Pose2Sim_LSTM.xml`).

1. **`Pose2Sim/kinematics.py` — config-driven model selection**
   - `get_model_path(use_simple_model, osim_setup_dir, osim_model='')`: non-empty
     `osim_model` → `osim_setup_dir / osim_model` (clear error if missing); takes
     precedence over `use_simple_model`. Empty → current behavior.
   - `kinematics_all`: read `config_dict['kinematics']['osim_model']` (default `''`),
     thread through `perform_scaling`.
   - `get_markers_path(..., osim_model='')`: when set, prefer a variant
     `Markers_{pose_model}_{model_stem}.xml` if present, else fall back to the standard
     file.
2. **`perform_IK` — runtime coordinate-task fix** (Blocker 2, see options above).
3. **New marker variant files** (Blocker 1):
   `Markers_Halpe26_RajagopalLaiUhlrich2023.xml`, `Markers_LSTM_RajagopalLaiUhlrich2023.xml`
   — copies with the head markers re-parented to `/bodyset/torso`. Offsets computed by a
   throwaway script: in each model, locate the shoulder-joint centers (`acromial_r/l`
   parent-frame origins) at default pose; express each head marker relative to the
   mid-shoulder point in the Pose2Sim model; apply that offset at RLU's mid-shoulder
   point; convert into RLU's torso frame. (A direct torso-frame copy is wrong — the
   Pose2Sim torso origin sits atop the lumbar chain, RLU's at the back joint.)
   Verify visually in the OpenSim GUI (markers should sit on the skull mesh).
4. **Copy the 10 Geometry meshes** listed above into `OpenSim_Setup/Geometry/`.
5. **`config/pose2sim_config_template.toml`** — add to `[kinematics]`:
   `osim_model = 'RajagopalLaiUhlrich2023.osim'` (`''` = current default models).
   Existing per-trial Config.toml files lack the key → old behavior. Check whether
   `code/pose2sim_builder.py` rewrites/whitelists `[kinematics]` keys when staging.

Both pipeline paths are covered: Halpe26 (current config, `use_augmentation = false`)
and LSTM (marker-augmentation path).

## Verification

1. **Regression**: run kinematics on an already-processed trial with `osim_model` absent
   or `''` — outputs and `kinematics/opensim_logs.txt` unchanged.
2. **RLU path**: set the key in a trial's Config.toml, rerun kinematics (Processing tab,
   or `Pose2Sim.kinematics()` directly). Expect: scaling completes with warnings for the
   8 unknown BodyScale segments only; IK completes with the `L5_S1_Flex_Ext` task
   renamed/dropped (logged); `.mot` has `lumbar_*` columns and no `L5_S1`/`L1_L2`/neck/
   wrist columns.
3. **Marker placement**: open the scaled `.osim` in the OpenSim 4.5 GUI — head markers
   on the skull, no unexpected mesh warnings.
4. Test the LSTM path when augmentation data is available (`use_augmentation = true`).

## Open questions

- **Blocker 2 handling**: rename `L5_S1_Flex_Ext` → `lumbar_extension` (keeps the
  neutral-trunk regularizer) vs. drop unknown coordinate tasks entirely. Leaning rename.
- **Head markers**: re-parent to torso for now; revisit (drop vs. re-parent) after
  seeing IK quality on real trials.
- Whether to commit the submodule edits on a local branch/fork to survive submodule
  updates.
