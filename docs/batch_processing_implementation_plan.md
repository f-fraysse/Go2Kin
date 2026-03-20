# Batch Processing Implementation Plan

Implementation plan for adding GPU batch processing to the pose estimation pipeline. See `docs/batch_processing.md` for research findings and background.

## Prerequisites

- Read `docs/batch_processing.md` first for full context on ONNX model batch support, rtmlib architecture, HPEVB prior work, and tracking compatibility analysis.
- HPEVB reference code: `D:\PythonProjects\HPEVB\rtmlib\` (conda env: `HPEVB`)
- HPEVB models: `D:\PythonProjects\HPEVB\models\` (includes `rtmdet-m-640-batch.onnx`)

## Phase 1: Baseline Benchmark

**Must be done before any code changes.**

**Test trial**: `E:\Markerless_Data\tests_home\sessions\weekend_march\dancing\`
- 4 cameras (GP1-GP4), 252 frames each, synced
- Already processed — delete `processed/` folder contents to re-run

**Procedure**:
1. Delete `E:\Markerless_Data\tests_home\sessions\weekend_march\dancing\processed\` contents (or set `overwrite_pose: true` in Config.toml)
2. Run via Go2Kin GUI "Process" button (standard flow through Processing tab)
3. Record from the processing log output:
   - **Pose estimation time**: Pose2Sim logs `"Pose estimation took 00h02m30s."` per step (logged via `code/pose2sim/Pose2Sim/Pose2Sim.py` line 218-221, forwarded to GUI via log callback in `code/pose2sim_builder.py`)
   - **Full pipeline time**: From start of first step to `"Pipeline completed successfully"` (includes triangulation, filtering, kinematics)
   - **Per-video FPS**: tqdm progress bar shows frames/sec during pose estimation
4. Save results to `docs/batch_processing.md` under a new "Benchmark Results" section

**Note**: Pose2Sim processes each camera video sequentially within the pose estimation step.

## Phase 2: Switch Detector to RTMDet (batch-capable ONNX)

Replace YOLOX-x (fixed batch=1) with RTMDet-m using the batch-exported ONNX model.

### 2.1 Copy model
Copy `D:\PythonProjects\HPEVB\models\rtmdet-m-640-batch.onnx` to a Go2Kin-accessible location (e.g., `config/models/` or leave in HPEVB and reference by absolute path for prototyping).

### 2.2 Update pose2sim config template
**File**: `config/pose2sim_config_template.toml`

Currently uses preset mode (`mode = 'performance'`) which auto-selects YOLOX-x + RTMPose-x. Change to specify custom model paths.

The `[pose]` section needs new fields for custom detector/pose model paths. Check how `poseEstimation.py` reads config to determine exact field names.

### 2.3 Update pose2sim pose estimation setup
**File**: `code/pose2sim/Pose2Sim/poseEstimation.py`

Modify `setup_model_class_mode()` (~line 112) and `setup_pose_tracker()` (~line 80) to:
- Read custom model paths from config when specified
- Use rtmlib's `Custom` class (from `rtmlib/tools/solution/custom.py`) instead of preset solution classes
- Fall back to existing preset behavior when no custom paths specified

rtmlib's `Custom` class usage:
```python
from functools import partial
from rtmlib import Custom

custom = partial(Custom,
    det_class='RTMDet',
    det='/path/to/rtmdet-m-640-batch.onnx',
    det_input_size=(640, 640),
    pose_class='RTMPose',
    pose='/path/to/rtmpose-x_simcc-body7_pt-body7-halpe26_700e-384x288-*.onnx',
    pose_input_size=(384, 288),
    backend='onnxruntime',
    device='cuda')

pose_tracker = PoseTracker(custom, det_frequency=4, ...)
```

## Phase 3: Port HPEVB rtmlib Batch Changes

Prototype changes directly in Go2Kin's rtmlib: `D:\miniconda3\envs\go2kin\lib\site-packages\rtmlib\`

Once verified, clone rtmlib into a new repo and submit a PR. Keep API backward-compatible.

### 3.1 `tools/base.py` — Batch-aware inference

**Reference**: `D:\PythonProjects\HPEVB\rtmlib\rtmlib\tools\base.py`

Changes:
- `inference()` method: Handle both 3D (HWC, single image) and 4D (NCHW, batch) inputs
- Add `self.supports_batch` flag detected at init time:
  ```python
  input_shape = self.session.get_inputs()[0].shape
  self.supports_batch = isinstance(input_shape[0], str)
  ```
- Keep backward compat: 3D input still works as before (auto-adds batch dim)

### 3.2 `tools/pose_estimation/rtmpose.py` — Bbox-level batching

**Reference**: `D:\PythonProjects\HPEVB\rtmlib\rtmlib\tools\pose_estimation\rtmpose.py`

Port the HPEVB implementation:
- `preprocess()`: Accept list of bboxes, return stacked batch `(N, H, W, C)` + lists of centers/scales
- `__call__()`: Batch preprocess → transpose to NCHW → single `self.inference()` call → batch postprocess
- `postprocess()`: Accept batched outputs `(N, K, W_simcc)`, loop through per-bbox for `get_simcc_maximum`
- Key fix: use `updated_scale` from `top_down_affine()`, not original scale
- cv2-based normalization: `cv2.subtract`/`cv2.divide` instead of numpy (2x faster)
- Return signature: must still return `(keypoints, scores)` for backward compat. Timing info is optional.

### 3.3 `tools/object_detection/rtmdet.py` — Frame-level batching (NEW)

**This is new work not done in HPEVB.**

Add batch frame processing to RTMDet:
- New method `__call_batch__(self, images: list[np.ndarray])` or detect via input type
- Preprocess N frames → stack into `(N, C, H, W)` → single inference → split postprocess per frame
- Each frame may have different detection counts — return list of per-frame results
- Fallback: if `self.supports_batch` is False, loop sequentially
- cv2-based normalization (already in HPEVB's rtmdet.py)

### 3.4 `tools/solution/pose_tracker.py` — Batch frame API (NEW)

**This is new work not done in HPEVB.**

Add `process_batch(self, frames: list[np.ndarray])` method to PoseTracker:

```python
def process_batch(self, frames):
    """Process multiple frames with batched detection and pose estimation."""
    n = len(frames)

    # Step 1: Batch detection (if supported)
    if self.det_model and self.det_model.supports_batch:
        # Determine which frames need detection vs reuse cached bboxes
        det_frames = []
        det_indices = []
        for i in range(n):
            if (self.frame_cnt + i) % self.det_frequency == 0:
                det_frames.append(frames[i])
                det_indices.append(i)

        # Batch detect
        if det_frames:
            all_det_bboxes = self.det_model.__call_batch__(det_frames)

        # Assign bboxes per frame (detected or cached)
        frame_bboxes = []
        det_idx = 0
        for i in range(n):
            if i in det_indices:
                frame_bboxes.append(all_det_bboxes[det_idx])
                det_idx += 1
            else:
                frame_bboxes.append(self.bboxes_last_frame)

    # Step 2: Collect all bboxes across all frames for batch pose
    # (flatten, run batch pose, then split back per frame)
    all_bboxes = []
    bbox_counts = []
    for bboxes in frame_bboxes:
        all_bboxes.extend(bboxes)
        bbox_counts.append(len(bboxes))

    # Step 3: Batch pose estimation across all frames
    # Need to pass each bbox's source frame for cropping
    # ... (implementation details)

    # Step 4: Sequential tracking per frame (cheap CPU op)
    results = []
    for i in range(n):
        # ... IoU tracking, NMS per frame ...
        self.frame_cnt += 1

    return results
```

**Key challenge**: RTMPose needs both the image AND bboxes. For cross-frame batching, we need to crop each bbox from its source frame before stacking. This means preprocessing must know which frame each bbox belongs to.

## Phase 4: Modify Pose2Sim Frame Loop

**File**: `code/pose2sim/Pose2Sim/poseEstimation.py`

Modify `process_video()` (~line 330) to support batch processing.

### Current flow (sequential):
```python
while cap.isOpened():
    success, frame = cap.read()
    keypoints, scores = pose_tracker(frame)
    # NMS, tracking, save JSON per frame
```

### New flow (batched):
```python
batch_size = config.get('batch_size', 1)  # from Config.toml

while cap.isOpened():
    # Read batch of frames
    frames = []
    for _ in range(batch_size):
        success, frame = cap.read()
        if not success:
            break
        frames.append(frame)

    if not frames:
        break

    # Batch inference
    if batch_size > 1 and hasattr(pose_tracker, 'process_batch'):
        batch_results = pose_tracker.process_batch(frames)
    else:
        batch_results = [(pose_tracker(f)) for f in frames]

    # Process results per frame (NMS, tracking, JSON save — same as before)
    for frame, (keypoints, scores) in zip(frames, batch_results):
        # ... existing NMS code ...
        # ... existing tracking code ...
        # ... existing JSON save code ...
        frame_idx += 1
        pbar.update(1)
```

### Config.toml addition:
```toml
[pose]
batch_size = 8  # Number of frames to batch (1 = sequential, no change)
```

### Considerations:
- `det_frequency` within batch: handled by PoseTracker.process_batch()
- Tracking must still be sequential per-frame (handled in the per-frame loop after batch inference)
- `batch_size = 1` should produce identical behavior to current code (safe default)
- Memory: batch_size * 3 * 640 * 640 * 4 bytes per detector batch (~47MB for batch=8)
- tqdm progress bar: update per frame within batch, not per batch

## Phase 5: Post-Change Benchmark & Verification

Using same test trial as Phase 1 baseline.

1. Re-run with batch processing enabled (batch_size=8)
2. Compare pose estimation step time vs baseline
3. Compare full pipeline time vs baseline
4. Output comparison: JSON keypoint files should produce near-identical results
   - Note: RTMDet-m vs YOLOX-x may give slightly different detections — that's expected
   - Pose keypoints for same detections should be identical
5. Test different batch sizes: 4, 8, 16 — find optimal for available VRAM
6. Test with `det_frequency=1` and `det_frequency=4`

## API Compatibility Notes (for future PRs)

These changes target two upstream libraries. Keep backward compat for PR submission:

### rtmlib PR:
- `PoseTracker.__call__(image)` must still work for single-frame input
- `RTMPose.__call__(image, bboxes)` must still work for single frame
- `RTMDet.__call__(image)` must still work for single frame
- New batch methods should be separate (e.g., `process_batch()`) or auto-detected via input type
- Models with fixed batch=1 must gracefully fall back to sequential processing
- Detect batch support at init: `isinstance(session.get_inputs()[0].shape[0], str)`
- Timing/profiling info should be optional (off by default)

### pose2sim PR:
- `batch_size = 1` must produce identical behavior to current code
- Config.toml addition is backward-compatible (new optional field)
- No changes to output format (same JSON files, same directory structure)

## Critical Files Summary

| File | What to Do |
|------|------------|
| `D:\miniconda3\envs\go2kin\lib\site-packages\rtmlib\tools\base.py` | Add 3D/4D input handling, `supports_batch` flag |
| `D:\miniconda3\envs\go2kin\lib\site-packages\rtmlib\tools\pose_estimation\rtmpose.py` | Port HPEVB bbox batching |
| `D:\miniconda3\envs\go2kin\lib\site-packages\rtmlib\tools\object_detection\rtmdet.py` | Add frame-level batch detection (NEW) |
| `D:\miniconda3\envs\go2kin\lib\site-packages\rtmlib\tools\solution\pose_tracker.py` | Add `process_batch()` method (NEW) |
| `code/pose2sim/Pose2Sim/poseEstimation.py` | Batch frame loop in `process_video()` |
| `config/pose2sim_config_template.toml` | Add `batch_size`, custom model paths |
| **Reference implementations (read-only):** | |
| `D:\PythonProjects\HPEVB\rtmlib\rtmlib\tools\base.py` | Batch inference handling |
| `D:\PythonProjects\HPEVB\rtmlib\rtmlib\tools\pose_estimation\rtmpose.py` | Bbox batch preprocess/inference/postprocess |
| `D:\PythonProjects\HPEVB\rtmlib\rtmlib\tools\object_detection\rtmdet.py` | cv2 normalization optimization |
| `D:\PythonProjects\HPEVB\models\rtmdet-m-640-batch.onnx` | Batch-capable detector ONNX |
