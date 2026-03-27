# Visualisation Tab

> **Slow and experimental.** Overlay of 2D / 3D keypoints on trial videos. Nice to visually check quality of pose detection / triangulation.

## Overview

The Visualisation tab (`code/GUI/visualisation_tab.py`) is a read-only video player that displays synced trial video from a selected camera with optional keypoint overlays. No files are created or modified.

## UI Layout

**Left panel** (~250px):
- Project / Session dropdowns, Trial listbox (single-select)
- Camera buttons (GP1–GP4) — disabled if no video for that camera
- Overlay toggles: "2D kpts", "3D kpts", and "IK joint centres", plus "View in OpenSim" button
- Info panel (subject, FPS, resolution, data availability)

**Right panel**:
- Video canvas (resizable, aspect-ratio preserved)
- Play/Pause, frame scrubber, "Go to" frame entry, frame counter with timecode

## Video Playback

Uses `cv2.VideoCapture` on the synced MP4 (`[trial]/video/synced/*_GP{N}.mp4`). Frame timing via `root.after()`. Sequential `cap.read()` for smooth playback; `cap.set(POS_FRAMES)` only on seeks (scrubber drag, frame entry).

## 2D Keypoint Overlay ("2D kpts")

Draws per-camera 2D pose detection results from OpenPose JSON files.

- **Source**: `[trial]/processed/pose/{trial}_GP{N}_json/{trial}_GP{N}_{frame:06d}.json`
- **Format**: `data["people"][i]["pose_keypoints_2d"]` — flat `[x, y, conf, x, y, conf, ...]` array indexed by skeleton node ID
- **Drawing**: Uses Pose2Sim's `draw_skel()` and `draw_keypts()` from `Pose2Sim/common.py`

## 3D Keypoint Overlay ("3D kpts")

Projects triangulated 3D markers from TRC files onto the camera view using calibration data.

- **Source**: `[trial]/processed/pose-3d/*.trc` (output of Pose2Sim triangulation + filtering, before IK)
- **Calibration**: Pose2Sim TOML from `[project]/calibrations/{name}.toml`

### Coordinate System Change

The TRC file stores coordinates in **OpenSim Y-up** convention (converted from Go2Kin Z-up by `zup2yup()` during triangulation). To reproject onto camera images using the Z-up calibration, the coordinates must be converted back:

```
TRC (Y-up):     (X_yup, Y_yup, Z_yup)  = (Y_zup, Z_zup, X_zup)
Go2Kin (Z-up):  (X_zup, Y_zup, Z_zup)  = columns [2, 0, 1] of TRC
```

Applied in `_parse_trc()`: `trc_data = trc_data[:, :, [2, 0, 1]]`

This reverses the `zup2yup` transform applied by `Pose2Sim/triangulation.py:202`.

### Camera Calibration Loading

The TOML calibration sections are keyed `cam_1` through `cam_4` (matching GP1–GP4). For the active camera, we extract K (intrinsic matrix), distortion coefficients, rvec (Rodrigues rotation), and tvec (translation). Projection uses `cv2.projectPoints(pts_3d, rvec, tvec, K, dist)`.

### Keypoint Re-indexing (TRC Order vs Skeleton ID Order)

The 2D OpenPose JSON stores keypoints indexed by **skeleton node ID** (e.g. HALPE_26: Nose=0, LShoulder=5, RShoulder=6, ..., RHeel=25). The drawing functions (`draw_skel`, `draw_keypts`) index into X/Y arrays by these same IDs.

However, the TRC file stores markers in **tree traversal order** (depth-first pre-order from `anytree.RenderTree`), which is how `Pose2Sim/triangulation.py:734` extracts keypoints from the JSON before triangulating:

```python
keypoints_ids = [node.id for _, _, node in RenderTree(model) if node.id is not None]
# HALPE_26: [19, 12, 14, 16, 21, 23, 25, 11, 13, 15, 20, 22, 24, 18, 17, 0, 6, 8, 10, 5, 7, 9]
```

TRC column `i` corresponds to skeleton ID `keypoints_ids[i]`. To pass projected 2D points to the drawing functions, we scatter them back into a skeleton-ID-indexed array:

```python
for trc_idx, skel_id in enumerate(keypoints_ids):
    x_by_id[skel_id] = x_2d[trc_idx]
```

This mapping is computed once when the video loads (`_detect_trc_data` → `self._trc_keypoint_ids`).

### Custom Drawing Functions

The 3D overlay uses dedicated `_draw_skel_3d` and `_draw_keypts_3d` methods with 2x the thickness/radius of the standard 2D drawing functions. This provides visual distinction between the overlays and allows independent control over 3D appearance without modifying shared Pose2Sim code.

| Property | 2D overlay | 3D overlay |
|----------|-----------|-----------|
| Line thickness | 2 | 4 |
| Keypoint radius | 6 | 12 |
| Color scheme | Same | Same (right=orange, left=green, center=blue; RdYlGn for confidence) |

## IK Joint Centres Overlay ("IK joint centres")

Projects OpenSim inverse kinematics body centre positions onto the video as filled circles, synchronized with playback. Shows where the model's joint centres are after IK fitting, useful for assessing IK quality against the video.

- **Source**: `.osim` (scaled model) and `.mot` (joint angles) from `[trial]/processed/kinematics/`
- **Pre-computation**: On trial load, a background thread extracts body centre positions for all frames using the OpenSim API (`body.getTransformInGround(state)`), following the pattern from `Pose2Sim/Utilities/bodykin_from_mot_osim.py`. Positions are converted from OpenSim Y-up to Go2Kin Z-up (same `[2, 0, 1]` reorder as TRC overlay).
- **Rendering**: Projects 3D body centres to 2D with `cv2.projectPoints()` using the same camera calibration as the TRC overlay. Draws filled circles (radius 12, bone color RGB 227/218/201).
- **Frame sync**: Maps video frame to motion frame via timestamp (`frame_idx / fps` → nearest motion time via `np.searchsorted`).
- **Note**: Currently displays all model bodies. May need filtering to show only relevant joint centres.

## OpenSim Visualizer ("View in OpenSim")

Launches the OpenSim simbody-visualizer in a separate popup window to play back the IK result with the full 3D model.

- **Source**: `.osim` (scaled model) and `.mot` (joint angles) from `[trial]/processed/kinematics/`
- **Button**: "View in OpenSim" in the Overlay panel, enabled when kinematics output exists for the selected trial
- **Mechanism**: Calls `opensim.VisualizerUtilities.showMotion(model, motion)` in a background thread. The simbody-visualizer opens as a separate OpenGL window with playback controls. The button shows "Visualizer Open..." while active and re-enables when the window is closed.
- **Geometry**: Model meshes are loaded from `Pose2Sim/OpenSim_Setup/Geometry/`

## Key Files

- `code/GUI/visualisation_tab.py` — the tab implementation
- `code/GUI/main_window.py` — tab registration (`create_visualisation_tab`)
- `code/pose2sim/Pose2Sim/common.py` — `draw_skel`, `draw_keypts`, `zup2yup` (reference)
- `code/pose2sim/Pose2Sim/triangulation.py` — TRC generation, keypoint ordering
- `code/pose2sim/Pose2Sim/skeletons.py` — skeleton model definitions (HALPE_26 etc.)
