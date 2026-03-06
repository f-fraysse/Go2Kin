# Calibration Module — Implementation Reference

Self-contained camera calibration for Go2Kin, adapted from the [Caliscope](https://github.com/mprib/caliscope) project (BSD-2-Clause license, Mac Prible).

---

## Origin and Attribution

This module extracts the calibration algorithms from Caliscope and adapts them for Go2Kin's stack. Caliscope is a full-featured multi-camera calibration and motion capture application with a PySide6 GUI, mediapipe pose estimation, pyvista 3D visualization, numba JIT compilation, and pandera schema validation.

**What was extracted:**
- Charuco board detection and corner tracking
- Intrinsic calibration (single-camera lens calibration)
- Extrinsic calibration (multi-camera relative pose estimation)
- Bundle adjustment optimization
- Umeyama similarity transform for coordinate alignment
- Scale accuracy metrics

**What was deliberately left out:**
- PySide6 Qt GUI — replaced with tkinter (Go2Kin's existing framework)
- mediapipe pose estimation — not needed for camera calibration
- pyvista 3D visualization — replaced with matplotlib for camera position display
- numba JIT — replaced with pure numpy (see [Dependency Decisions](#dependency-decisions))
- pandera schema validation — replaced with simple column checks
- Motion capture pipeline (trackers, synchronizer, recording workflows)
- TOML persistence — replaced with JSON

All adapted code retains the BSD-2-Clause license from Caliscope. The triangulation function additionally carries the BSD-2-Clause license from Anipose (Lili Karashchuk).

---

## Architecture

### Module Map

```
code/calibration/
    __init__.py              Package marker with attribution
    charuco.py               Charuco board definition and image generation
    charuco_tracker.py       Corner detection using cv2.aruco.CharucoDetector
    data_types.py            Core data structures (6 classes)
    frame_selector.py        Smart frame selection for intrinsic calibration
    intrinsic.py             cv2.calibrateCamera wrapper
    video_processor.py       MP4 files -> ImagePoints bridge (NEW)
    extrinsic.py             PoseNetworkBuilder (PnP + pose estimation)
    paired_pose_network.py   Stereo pair graph with gap-filling
    triangulation.py         Pure-numpy DLT triangulation (NEW)
    reprojection.py          Reprojection error computation
    reprojection_report.py   Error report dataclass
    bundle_adjustment.py     PointDataBundle + scipy optimization
    alignment.py             Umeyama similarity transform
    scale_accuracy.py        Volumetric scale error metrics
    calibrate.py             High-level orchestrator (NEW)
    persistence.py           JSON save/load (NEW)

code/GUI/
    calibration_tab.py       tkinter Calibration tab (NEW)
```

Files marked **NEW** are original Go2Kin code, not adapted from Caliscope.

### Data Flow — Intrinsic Calibration

```
MP4 video file
    |
    v
video_processor.extract_charuco_points_from_video()
    |  For each sampled frame:
    |    charuco_tracker.CharucoTracker.get_points()
    |      -> cv2.aruco.CharucoDetector.detectBoard()
    |      -> cv2.cornerSubPix() (sub-pixel refinement)
    |      -> PointPacket (ids, img_loc, obj_loc)
    |
    v
ImagePoints (DataFrame: sync_index, cam_id, point_id, img_loc_x/y, obj_loc_x/y/z)
    |
    v
frame_selector.select_calibration_frames()
    |  Phase 1: Orientation anchors (8 tilt bins, min 4 required)
    |  Phase 2: Greedy spatial coverage (5x5 grid, edge/corner weights)
    |  Result: ~30 best frames
    |
    v
intrinsic.calibrate_intrinsics()
    |  cv2.calibrateCamera() or cv2.fisheye.calibrate()
    |
    v
IntrinsicCalibrationOutput
    camera_matrix (3x3)
    distortions (5 coeffs standard, 4 coeffs fisheye)
    reprojection RMSE
```

### Data Flow — Extrinsic Calibration

```
Synced MP4 files (from audio sync)
    |
    v
video_processor.discover_synced_videos()
    |  Parse _GP{N}.mp4 filenames, skip stitched_videos.mp4
    |
    v
video_processor.extract_charuco_points_from_videos()
    |  Same sync_index = same moment in time across cameras
    |
    v
ImagePoints (multi-camera observations)
    |
    v
extrinsic.PoseNetworkBuilder
    |
    |-- .estimate_camera_to_object_poses()
    |     Per (cam_id, sync_index): cv2.solvePnP() on undistorted points
    |     Returns: dict[(cam_id, sync_index)] -> (R, t, rmse)
    |
    |-- .estimate_relative_poses()
    |     For each camera pair (A, B) at each common sync_index:
    |     T_B_A = T_B_obj @ inv(T_A_obj)
    |     Returns: dict[((cam_a, cam_b), sync_index)] -> StereoPair
    |
    |-- .filter_outliers()
    |     IQR-based rejection on:
    |       - Translation magnitude
    |       - Rotation angle (geodesic from median quaternion)
    |     Threshold: 1.5x IQR (default)
    |
    |-- .build()
    |     Quaternion averaging per pair (eigen decomposition of Q@Q^T)
    |     Translation averaging (mean)
    |     Stereo RMSE computation (triangulate + reproject)
    |
    v
paired_pose_network.PairedPoseNetwork
    |  Gap-filling: if pair (A,C) is missing but (A,X) and (X,C) exist,
    |  bridge through X: T_A_C = T_X_C @ T_A_X
    |  Iterative until no more gaps can be filled
    |
    |-- .apply_to(camera_array)
    |     Find largest connected component
    |     Try each camera as anchor, pick lowest total error
    |     Set anchor to identity, pose others relative to anchor
    |
    v
CameraArray (all cameras posed)
    |
    v
triangulation.triangulate_image_points()
    |  Undistort all points -> normalized coordinates
    |  Per sync_index: group by point_id, DLT via SVD
    |  Result: WorldPoints (sync_index, point_id, x/y/z_coord)
    |
    v
bundle_adjustment.PointDataBundle
    |  Maps image observations to world points
    |
    |-- .optimize()
    |     scipy.optimize.least_squares (method="trf")
    |     Sparse Jacobian pattern for efficiency
    |     Optimizes: camera extrinsics (6 params each) + 3D points
    |     Residuals computed in normalized coordinates
    |
    v
Optimized PointDataBundle
    |  Lower reprojection error, refined camera poses + 3D points
    |
    v  (optional)
.align_to_object() or calibrate.set_origin()
    |  Umeyama similarity transform: source (triangulated) -> target (object coords)
    |  Finds rotation, translation, and scale
    |  Applies to both camera extrinsics and world points
    |
    v
Final calibrated CameraArray + WorldPoints in real-world coordinates
```

---

## Key Data Types

All defined in `data_types.py` unless noted otherwise.

### PointPacket
Return value from `CharucoTracker.get_points()`. Contains:
- `point_id` — unique corner IDs from the charuco board
- `img_loc` — (N, 2) pixel coordinates of detected corners
- `obj_loc` — (N, 3) known 3D positions in the board's frame of reference

### CameraData
Intrinsic and extrinsic state for a single camera:
- `cam_id`, `size` — identity and resolution
- `matrix`, `distortions` — intrinsic calibration (None if uncalibrated)
- `rotation`, `translation` — extrinsic pose (None if unposed)
- `fisheye` — whether to use fisheye distortion model
- Key methods: `undistort_points()`, `undistort_frame()`, `extrinsics_to_vector()`/`extrinsics_from_vector()`

### CameraArray
Container for multiple `CameraData` objects. Provides:
- `posed_cameras` — subset with valid extrinsics
- `posed_cam_id_to_index` — deterministic camera-to-index mapping for optimization
- `normalized_projection_matrices` — 3x4 projection matrices for triangulation
- `get_extrinsic_params()` / `update_extrinsic_params()` — vectorize/devectorize for scipy

### ImagePoints
Validated DataFrame container for 2D observations:
- Required columns: `sync_index`, `cam_id`, `point_id`, `img_loc_x`, `img_loc_y`
- Optional columns: `obj_loc_x`, `obj_loc_y`, `obj_loc_z`, `frame_time`
- Returns copies of internal DataFrame (immutability)
- `fill_gaps()` — linear interpolation of missing observations

### WorldPoints
Frozen dataclass wrapping a DataFrame of 3D points:
- Columns: `sync_index`, `point_id`, `x_coord`, `y_coord`, `z_coord`, `frame_time`
- `points` property returns (N, 3) numpy array
- `fill_gaps()` — linear interpolation of trajectories

### StereoPair
Relative transformation between two cameras:
- `rotation` (3x3), `translation` (3,), `error_score`
- `inverted()` — returns the reverse transform
- `link(other)` — chains transforms: (A->B).link(B->C) = A->C with summed error scores

### PointDataBundle *(in bundle_adjustment.py)*
Central optimization container binding cameras, 2D observations, and 3D points:
- `optimize()` — bundle adjustment via `scipy.optimize.least_squares`
- `reprojection_report` — cached pixel-space error metrics
- `filter_by_absolute_error()` / `filter_by_percentile_error()` — outlier removal with safety floors
- `align_to_object()` — Umeyama alignment to known object coordinates
- `compute_volumetric_scale_accuracy()` — distance error vs ground truth

---

## Intrinsic Pipeline Details

Entry point: `calibrate.run_intrinsic_calibration_from_video()`

### 1. Corner Extraction (`video_processor.py`)
- Opens video with `cv2.VideoCapture`
- Samples every Nth frame (default: 5 fps sampling rate)
- Runs `CharucoTracker.get_points()` on each frame
- Builds `ImagePoints` DataFrame with `sync_index` = sequential sample number

### 2. Frame Selection (`frame_selector.py`)
Smart selection avoids redundant frames. Two-phase approach:

**Phase 1 — Orientation Anchors**: Computes board tilt (pitch/roll) from detected corner positions. Divides tilt space into 8 radial bins. Selects one representative frame per occupied bin (the one with most corners). Requires minimum 4 bins occupied for adequate orientation diversity.

**Phase 2 — Spatial Coverage**: Divides image into a 5x5 grid. Weights edge and corner cells higher (they're more informative for distortion estimation). Greedily adds frames that improve coverage, up to target count (~30 frames).

### 3. Calibration (`intrinsic.py`)
- Extracts matched object/image point arrays per selected frame
- Calls `cv2.calibrateCamera()` (standard) or `cv2.fisheye.calibrate()` (fisheye)
- Returns `IntrinsicCalibrationOutput` with calibrated `CameraData` and coverage report

---

## Extrinsic Pipeline Details

Entry point: `calibrate.run_extrinsic_calibration()`

### 1. Video Discovery (`video_processor.py`)
- Scans synced folder for `*.mp4` files
- Skips `stitched_videos.mp4` and `timestamps.csv`
- Parses camera number from `_GP{N}.mp4` suffix (regex: `_GP(\d+)\.mp4$`)

### 2. Corner Extraction
Same as intrinsic, but sync_index alignment is critical: because videos are pre-synchronized (via audio sync), the same `sync_index` across cameras represents the same physical moment. The same charuco board position is observed from multiple viewpoints.

### 3. PnP Pose Estimation (`extrinsic.py`)
For each (camera, sync_index) pair with sufficient corners (default: 4+):
- Pre-undistort all image points to normalized coordinates
- `cv2.solvePnP(SOLVEPNP_IPPE)` with fallback to `SOLVEPNP_ITERATIVE`
- Operates in normalized space (identity camera matrix, zero distortion)
- Returns rotation matrix R, translation vector t, and reprojection RMSE

### 4. Relative Pose Computation
For each camera pair (A, B) at each common sync_index:
```
T_B_A = T_B_obj @ inv(T_A_obj)

R_rel = R_b @ R_a^T
t_rel = R_b @ (-R_a^T @ t_a) + t_b
```
This gives the transformation from camera A's frame to camera B's frame.

### 5. Outlier Rejection
Per camera pair, applies IQR-based filtering on two metrics:
- **Translation magnitude**: removes estimates where the baseline length is anomalous
- **Rotation angle**: computes geodesic distance from the median quaternion, removes outliers

Default threshold: 1.5x IQR. Pairs with fewer than 5 samples skip rejection.

### 6. Pose Aggregation
- Rotations: quaternion averaging via eigen decomposition of the quaternion outer product matrix. Uses (w,x,y,z) convention internally.
- Translations: simple mean after outlier rejection

### 7. Stereo RMSE Computation
For each aggregated pair, verifies quality by:
1. Triangulating common observations using the estimated relative pose
2. Reprojecting to both cameras
3. Computing RMS error of residuals

### 8. Graph Bridging (`paired_pose_network.py`)
If cameras A and C never see the board simultaneously, their relative pose is unknown. The graph bridges through intermediate cameras:
```
T_A_C = T_X_C @ T_A_X  (where X sees both A's and C's board positions)
```
Selects the bridge with lowest accumulated error score. Iterates until no more gaps can be filled.

### 9. Anchor Selection and Global Poses
- Finds the largest connected component of cameras
- Tries each camera as anchor (identity pose), poses all others relative to it
- Selects the anchor that yields lowest total error score
- Applies the configuration to the `CameraArray`

### 10. Triangulation (`triangulation.py`)
DLT (Direct Linear Transform) via SVD:
- Groups observations by `(sync_index, point_id)`
- For each point seen by 2+ cameras: builds the 2N x 4 design matrix A, solves via SVD
- The last row of V^T gives the homogeneous solution

### 11. Bundle Adjustment (`bundle_adjustment.py`)
Joint optimization of camera extrinsics and 3D point positions:
- **Method**: `scipy.optimize.least_squares` with Trust Region Reflective (TRF)
- **Residuals**: reprojection errors in normalized (undistorted) coordinates
- **Parameters**: [camera_rvec(3) + camera_tvec(3)] per camera + [x,y,z] per 3D point
- **Jacobian**: sparse pattern exploiting the bipartite structure (each observation depends on exactly 1 camera + 1 point)
- **Scaling**: `x_scale="jac"` for automatic parameter scaling
- Does NOT mutate the camera array during optimization — extrinsics are passed via override to avoid corrupting state with rejected trial values

### 12. Coordinate Alignment (`alignment.py`)
Umeyama similarity transform aligns the reconstruction to real-world coordinates:
- Input: triangulated 3D points and their known object positions (from the charuco board)
- Finds optimal rotation R, translation t, and uniform scale s
- `target = s * (R @ source) + t`
- Camera extrinsics are transformed correctly, preserving orthonormal rotation matrices (scale applied to position, not to the rotation block)

---

## Dependency Decisions

### Added Dependencies

| Package | Why |
|---------|-----|
| `opencv-contrib-python` | Replaces `opencv-python`. Superset that includes `cv2.aruco` for charuco detection. All existing Go2Kin code works unchanged. |
| `pandas` | `ImagePoints` and `WorldPoints` use DataFrames for groupby, merge, and filtering operations. Core to the data flow. |

### Removed/Avoided Dependencies

| Package | Caliscope uses it for | Go2Kin replacement |
|---------|----------------------|-------------------|
| `pandera` | DataFrame schema validation | Simple column-presence checks + type coercion in `ImagePoints.__init__()` |
| `numba` | JIT-compiled triangulation loop | Pure numpy (see below) |
| `PySide6` | Qt GUI + board pixmap rendering | tkinter GUI + PIL for board images |
| `pyvista` | 3D visualization | matplotlib 3D scatter plot |
| `rtoml` | TOML persistence | JSON via `persistence.py` |
| `mediapipe` | Pose estimation | Not needed (calibration only) |

### Numba Decision

The only numba-jitted function in the calibration path is `triangulate_sync_index()` — a DLT loop running SVD per point, grouped by point_id.

**Performance**: For calibration data (~hundreds of charuco observations), pure numpy takes ~1-2 seconds vs ~milliseconds with numba. This is negligible since calibration runs once per session.

**How to add numba back** (if ever needed for real-time triangulation):
1. Add `numba` to `requirements.txt`
2. In `triangulation.py`: add `@jit(nopython=True, cache=True)` decorator to `triangulate_sync_index()`
3. In `data_types.py`: change `normalized_projection_matrices` to return `numba.typed.Dict` instead of plain `dict`
4. Change list return types to `numba.typed.List`

The function interface is designed to be numba-compatible — it uses only numpy arrays, basic Python types, and dict lookups.

---

## Adaptation Details

### NumbaDict -> plain dict
`CameraArray.normalized_projection_matrices` originally returned a `numba.typed.Dict[int, np.ndarray]`. Changed to a plain Python `dict[int, np.ndarray]`. Only used as a lookup table, not for JIT compilation.

### pandera -> column checks
`ImagePointSchema` and `WorldPointSchema` (pandera DataFrameModel classes) replaced with:
- Column presence validation: `missing = [c for c in REQUIRED if c not in df.columns]`
- Type coercion: `df[col].astype(int)` / `pd.to_numeric(df[col], errors="coerce")`
- Optional columns filled with NaN if absent

### PySide6 -> PIL
`Charuco.board_pixmap()` (returned `QPixmap`) replaced with `Charuco.board_pil_image()` (returns `PIL.Image`). Used for board preview in tkinter and saving to file.

### typing_extensions.Self -> string annotation
Python 3.10 doesn't have `typing.Self` (3.11+). The `PoseNetworkBuilder` fluent methods use `-> PoseNetworkBuilder:` as the return annotation (valid with `from __future__ import annotations`).

### Consolidated data_types.py
Six classes from four different Caliscope files merged into one module:

| Class | Original Caliscope location |
|-------|---------------------------|
| `PointPacket` | `caliscope/packets.py` |
| `CameraData` | `caliscope/cameras/camera_array.py` |
| `CameraArray` | `caliscope/cameras/camera_array.py` |
| `ImagePoints` | `caliscope/core/point_data.py` |
| `WorldPoints` | `caliscope/core/point_data.py` |
| `StereoPair` | `caliscope/core/bootstrap_pose/stereopairs.py` |

### PointDataBundle.rotate() removed
The `rotate()` method (arbitrary axis rotation) was removed as it's not needed for the calibration workflow. Coordinate alignment is handled entirely by `align_to_object()`.

---

## File Provenance

| Go2Kin file | Caliscope source | Adaptations |
|-------------|-----------------|-------------|
| `charuco.py` | `core/charuco.py` | Removed PySide6, added PIL image output, Go2Kin defaults |
| `charuco_tracker.py` | `trackers/charuco_tracker.py` | Import path change only, removed abstract base class |
| `data_types.py` | `cameras/camera_array.py` + `core/point_data.py` + `packets.py` + `bootstrap_pose/stereopairs.py` | Consolidated, removed numba/pandera |
| `frame_selector.py` | `core/frame_selector.py` | Import path change only |
| `intrinsic.py` | `core/calibrate_intrinsics.py` | Import path change only |
| `extrinsic.py` | `core/bootstrap_pose/pose_network_builder.py` | Import paths, Self -> string annotation |
| `paired_pose_network.py` | `core/bootstrap_pose/paired_pose_network.py` | Import path change only |
| `triangulation.py` | `core/point_data.py` (`triangulate_sync_index`) | Rewritten without numba JIT, same algorithm |
| `reprojection.py` | `core/reprojection.py` | Import path change only |
| `reprojection_report.py` | `core/reprojection_report.py` | Import path change only |
| `bundle_adjustment.py` | `core/point_data_bundle.py` | Import paths, removed `rotate()` method |
| `alignment.py` | `core/alignment.py` | Import path change only |
| `scale_accuracy.py` | `core/scale_accuracy.py` | Import path change only |
| `video_processor.py` | — | New: MP4 -> ImagePoints bridge |
| `calibrate.py` | — | New: high-level orchestrator |
| `persistence.py` | — | New: JSON save/load |

---

## Charuco Board Configuration

The charuco board is the calibration target. Its physical geometry must be accurately described for correct calibration.

### Parameters

| Parameter | Default | Effect |
|-----------|---------|--------|
| `columns` | 5 | Number of columns on the board |
| `rows` | 7 | Number of rows on the board |
| `square_size_overide_cm` | 11.70 | Physical size of one chessboard square in cm. **Critical for scale accuracy.** |
| `dictionary` | `DICT_4X4_50` | ArUco marker dictionary. Must match the printed board. |
| `aruco_scale` | 0.75 | Ratio of ArUco marker size to square size |
| `inverted` | False | Whether the board is white-on-black (True applies `cv2.bitwise_not`) |
| `board_height` | 59.4 | Overall board height in cm (A1 short edge). Used only if `square_size_overide_cm` is None. |
| `board_width` | 84.1 | Overall board width in cm (A1 long edge). Used only if `square_size_overide_cm` is None. |

### What Matters for Accuracy

1. **`square_size_overide_cm` must match the physical board.** Measure the printed board after printing — printers don't always scale exactly. This value directly sets the real-world scale of the calibration. Wrong value = wrong 3D distances.

2. **Dictionary and aruco_scale must match the printed board.** Mismatches cause detection failure or wrong corner assignments.

3. **Board flatness matters.** A warped board introduces systematic errors. Mount on rigid material (foamboard, MDF).

### Go2Kin Defaults

Designed for an A1 (59.4 x 84.1 cm) printed charuco board:
- 5 columns x 7 rows = 24 inner corners
- 11.70 cm squares with 0.75 aruco scale
- DICT_4X4_50 (small dictionary, fast detection)

Config persists in `config/calibration/charuco_config.json`.

---

## Persistence Format

Calibration is saved as JSON to `config/calibration/calibration.json`:

```json
{
  "charuco": {
    "columns": 5,
    "rows": 7,
    "board_height": 59.4,
    "board_width": 84.1,
    "dictionary": "DICT_4X4_50",
    "aruco_scale": 0.75,
    "inverted": false,
    "square_size_overide_cm": 11.70
  },
  "cameras": {
    "1": {
      "size": [1920, 1080],
      "error": 0.42,
      "matrix": [[...], [...], [...]],
      "distortions": [...],
      "rotation": [[...], [...], [...]],
      "translation": [...],
      "fisheye": false
    }
  }
}
```

Numpy arrays are serialized as nested lists. `None` fields (uncalibrated parameters) are omitted from the JSON.

---

## Future Work

- **Numba JIT**: Add `@jit` back to `triangulate_sync_index()` if real-time triangulation is needed (e.g., live 3D preview). Interface already compatible — see [Dependency Decisions](#dependency-decisions).

- **Fisheye model refinement**: The fisheye path (`cv2.fisheye.calibrate`) exists but is lightly tested. GoPro "Linear" mode uses standard distortion. "Wide" or "SuperView" modes may benefit from the fisheye model.

- **Manual camera mapping**: Currently requires `_GP{N}.mp4` filename convention. A fallback dialog for manual file-to-camera assignment would help when filenames don't match.

- **Progress reporting**: The GUI progress callbacks are wired but minimal. Could add per-frame progress bars for long video processing.

- **Calibration quality visualization**: The matplotlib 3D scatter plot shows camera positions. Could add reprojection error heatmaps, residual distributions, or board coverage visualizations.
