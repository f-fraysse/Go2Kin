# Pose2Sim Halpe26 setup ported to RajagopalLaiUhlrich2023.osim

Sources: Markers_Halpe26.xml, Scaling_Setup_Pose2Sim_Halpe26.xml and IK_Setup_Pose2Sim_Halpe26.xml (all from Pose2Sim); Model_Pose2Sim_simple.osim; RajagopalLaiUhlrich2023.osim (unmodified).
The target model is used unmodified (no joint, range, lock or clamp edits), with one exception: all six ground→pelvis coordinates are unclamped. See [Changes in the Go2Kin fork](#changes-in-the-go2kin-fork-2026-10-12).

## Markersets

**Only `Markers_Halpe26_RLU2023_P2Sall.xml` (the third variant, see the end of this document) is shipped in the Go2Kin Pose2Sim fork and used for processing.** Option 1 and P2Ship below are documented for reference only.

- `Markers_Halpe26_RLU2023.xml` is Option 1: the hip, knee and ankle keypoints sit at RLU2023 joint centres.
- `Markers_Halpe26_RLU2023_P2Ship.xml` is identical except that Hip, RHip and LHip keep their Pose2Sim pelvis-frame locations.

| Marker | Parent (RLU2023) | Location (m, parent frame; R side, L mirrors z) | Source |
|---|---|---|---|
| Nose | torso | 0.116266, 0.524070, 0.000153 | Pose2Sim head marker, re-expressed in torso at neutral neck (head origin = torso + [0, 0.51146, 0]; head_torso translations are 0) |
| Head | torso | 0.015922, 0.675590, 0 | as Nose |
| Neck, Shoulders, Elbows, Wrists | unchanged | unchanged | copied; the torso, humerus and radius frames are identical in both models |
| BigToe, SmallToe, Heel | unchanged | unchanged | copied; the calcn and toes frames are identical |
| RKnee | tibia_r | 0.001731, -0.002389, -0.008452 | = RLU2023 RKJC (Pose2Sim had it on femur_r at -0.00541, -0.39789, 0.00061) |
| RAnkle | tibia_r | -0.010, -0.400, 0 | = RLU2023 RAJC (talus origin; lies on the ankle axis, so equivalent to the tibia-fixed point). Pose2Sim: -0.00029, -0.40805, 0.01496 |
| RHip (Option 1) | pelvis | -0.056276, -0.07849, 0.07726 | = RLU2023 RHJC. Pose2Sim: -0.06393, -0.08134, 0.10541 |
| Hip (Option 1) | pelvis | -0.056276, -0.07849, 0 | midpoint of the RLU2023 HJCs |
| Hip, RHip, LHip (P2Ship) | pelvis | as Pose2Sim | copied; the pelvis frame is identical |

Pose2Sim's own keypoint markers were not at its own joint centres (offsets in mm, marker minus joint centre, R side):

- Hip: +6.8 anterior, -15.2 inferior, +22.0 lateral from the Pose2Sim HJC. This is +28.1 lateral of the RLU2023 HJC.
- Knee: about 10 mm proximal to the Pose2Sim knee joint origin.
- Ankle: +22.0 proximal, +15.0 lateral from the Pose2Sim ankle centre. This is about 8 mm distal and 15 mm lateral of the RLU2023 AJC.

## Scaling setup (`Scaling_Setup_RLU2023_Halpe26.xml`)

- Removed BodyScales lumbar1 to lumbar5 (these bodies are absent from both models; the setup is shared across Pose2Sim models).
- Removed the sacrum BodyScale from the pelvis measurement.
- Removed the `head` Measurement (Head–Nose, Head–Neck pairs) and the manual Scale entry for head (it had apply = false). The head is part of the torso in RLU2023 and is scaled by the torso measurement (Shoulder–Hip pairs).
- The patella_r/l BodyScales were already in the thigh measurement; they are kept, and the bodies now exist.
- The MarkerPlacer coordinate task was renamed from L5_S1_Flex_Ext to lumbar_extension (the MarkerPlacer has apply = false).
- Everything else is unchanged: weights, mass (69), time ranges and file paths.

Effect on scale factors for identical keypoint data. The figures below are generic-model marker-pair distances at zero pose; the factor is the multiplier on the resulting scale factor relative to Pose2Sim.

| Measurement | Pose2Sim (mm) | Option 1 (mm) | Factor | P2Ship (mm) | Factor |
|---|---|---|---|---|---|
| pelvis (RHip–LHip) | 210.8 | 154.5 | x1.364 | 210.8 | x1.000 |
| thigh (Hip–Knee) | 383.4 | 408.6 | x0.938 | 407.5 | x0.941 |
| shank (Knee–Ankle) | 407.8 | 397.9 | x1.025 | 397.9 | x1.025 |
| torso (Shoulder–Hip) | 540.1 | 543.8 | x0.993 | 540.1 | x1.000 |
| arm, forearm, foot | — | — | x1.000 | — | x1.000 |

## IK setup (`IK_Setup_RLU2023_Halpe26.xml`)

- IKCoordinateTask renamed from L5_S1_Flex_Ext to lumbar_extension. It is kept as in Pose2Sim: weight 0.1, pulling towards the default value of 0.
- Marker weights are unchanged (Nose and Head 0.1, Neck 0.2). However, **Nose and Head are excluded from IK** (`apply = false`). They are rigid with the torso in RLU2023, so head turns would drag the trunk. See [Changes in the Go2Kin fork](#changes-in-the-go2kin-fork-2026-10-12).
- model_file, marker_file and output paths are unchanged (they are Pose2Sim demo paths) and must be set per run.

## Behaviour inherited from the RLU2023 model

- subtalar, mtp, wrist_flex and wrist_dev are locked at 0. All coordinates are clamped except the six pelvis coordinates (unclamped in the Go2Kin fork). This includes the shoulders (arm_flex ±90°, arm_add -120 to 90°, arm_rot ±90°), which are not clamped in Pose2Sim's model. The other limits are hip flexion -30 to 120°, hip rotation ±40° and knee 0 to 140°.
- pro_sup is free and unobservable from Halpe26.
- The patellofemoral coupler constraints are satisfied by IK (constraint_weight = Inf).

## Third variant: `Markers_Halpe26_RLU2023_P2Sall.xml`

In this variant every keypoint marker keeps its Pose2Sim bone-fixed location; only Nose and Head are re-expressed on the torso. The invariant is where the keypoint sits relative to the bone, i.e. the annotation bias. The pelvis, femur, tibia, calcn, toes, torso, humerus and radius frames are identical in both models, so this is an exact copy.

Offsets of the copied markers from the RLU2023 joint centres (mm, R side, x anterior / y superior / z lateral):

| Marker | Offset from RLU2023 joint centre |
|---|---|
| RHip | -7.7, -2.9, +28.1 from HJC (pelvis frame) |
| RKnee | -10.7, +10.6, +9.3 from RKJC (femur frame, zero pose) |
| RAnkle | +9.7, -8.0, +15.0 from AJC (tibia frame) |

Scale-factor multipliers relative to Pose2Sim, for identical keypoint data:

| Measurement | Multiplier |
|---|---|
| thigh | x0.968 |
| shank | x0.979 |
| pelvis | x1.000 |
| torso | x1.000 |

The remaining thigh and shank differences come from the RLU2023 hip, knee and ankle joint locations, not from the markers.

## Changes in the Go2Kin fork (2026-10-12)

The files are in the Go2Kin Pose2Sim fork (`https://github.com/f-fraysse/pose2sim`, `Pose2Sim/OpenSim_Setup/`) and enabled with `[kinematics] use_original_RLU2023 = true` (the Go2Kin `config/pose2sim_config_template.toml` default). Changes made after the port above, while validating on a test jump trial (Charlotte_Pilot2/jump, 1113 frames):

- **Pelvis rotations unclamped** (`RajagopalLaiUhlrich2023.osim`). pelvis_tilt, pelvis_list and pelvis_rotation were clamped to ±90°. The participant faced about 180° in the lab frame, so IK pinned pelvis_rotation at ±90°: RHip/LHip errors were about 12 cm, and hip rotation and adduction sat at their limits.
- **Pelvis translations unclamped** (pelvis_tx ±5 m, ty -1 to 2 m, tz ±3 m). This matches Pose2Sim's model, which clamps none of the six pelvis coordinates. These limits had no effect on the test trial.
- **Nose and Head excluded from IK** (`apply = false` in `IK_Setup_RLU2023_Halpe26.xml`). RLU2023 has no neck joint, so these markers on `torso` pull the whole trunk when the head turns. Neck is kept. The markers stay in the markerset as a visual reference. LEye/REye/LEar/REar (Halpe26 ids 1–4) never reach IK, because Pose2Sim's `HALPE_26` skeleton does not triangulate them.
- **Scaling: `marker_set_file` forced to `Unassigned`** (in `kinematics.py`, `perform_scaling()`; the XML is unchanged). The scaling setup's `GenericModelMaker/marker_set_file` names `Markers_Halpe26_RLU2023_P2Sall.xml` relative to the setup file. Pose2Sim runs a temporary copy of the setup from the trial's `kinematics/` folder, where that path does not resolve, and ScaleTool aborted with "No model specified". The markers are already baked into the generic model before scaling, so the field is redundant. Pose2Sim's own setups have it `Unassigned`.
- **Geometry**: the leg and foot meshes missing from Pose2Sim's `Geometry/` folder (femur, tibia, fibula, talus, foot, bofoot) were copied from the OpenSim 4.5 install. They are for display only.

Mean IK marker RMS on the test trial:

| Run | Mean RMS | Mean worst marker | Typical worst marker |
|---|---|---|---|
| Pose2Sim default model (`Model_Pose2Sim_muscles_flex.osim`) | 2.2 cm | 7.1 cm | Head |
| RLU2023, Nose/Head in IK | 3.4 cm | 10.2 cm | Head / Nose |
| RLU2023, Nose/Head excluded (current) | 1.9 cm | 4.0 cm | RHeel |

Hip and knee angle ranges agree with the default model to within about 2°.
