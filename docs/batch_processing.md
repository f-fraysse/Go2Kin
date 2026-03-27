# Batch Frame Processing for Pose Estimation

Research findings on GPU batch processing for the rtmlib/pose2sim pose estimation pipeline.

## Background

Pose estimation in Go2Kin runs through Pose2Sim -> rtmlib's `PoseTracker`. The current pipeline processes each video frame sequentially: one frame at a time through the detector (YOLOX), then one bounding box at a time through the pose estimator (RTMPose). This underutilizes the GPU, which has massive parallelism but sits mostly idle processing single tensors.

**Batch processing** sends multiple inputs through the model in a single inference call (e.g., `(N, 3, 640, 640)` instead of `(1, 3, 640, 640)`), allowing the GPU to process them in parallel. This can improve throughput by 2-4x depending on model size and available VRAM.

## ONNX Model Batch Support

Checked with `ort.InferenceSession(path).get_inputs()[0].shape` — a string in the batch dimension means dynamic (supports batching), an integer means fixed.

| Model | Input Shape | Dynamic Batch? | Notes |
|-------|-------------|----------------|-------|
| YOLOX-x (Go2Kin default detector) | `[1, 3, 640, 640]` | No | Fixed batch=1 |
| RTMPose-x HALPE26 384x288 (Go2Kin default pose) | `['batch', 3, 384, 288]` | **Yes** | Already supports batching |
| RTMDet-m `rtmdet-m-640.onnx` | `[1, 3, 640, 640]` | No | Standard export |
| RTMDet-m `rtmdet-m-640-batch.onnx` | `['batch', 3, 'height', 'width']` | **Yes** | Re-exported with dynamic axes |
| RTMDet-l `rtmdet-l-640.onnx` | `[1, 3, 640, 640]` | No | |
| RTMDet-x `rtmdet-x-640.onnx` | `[1, 3, 640, 640]` | No | |
| RTMDet nano (rtmlib default, hand only) | `[1, 3, 320, 320]` | No | Only model shipped with rtmlib |

**Key takeaway**: RTMPose already supports dynamic batch natively. For the detector, we need a batch-exported ONNX model (like `rtmdet-m-640-batch.onnx`).

## rtmlib Architecture (v0.0.15)

rtmlib processes everything single-frame, with no batch_size parameter anywhere in its API:

- `BaseTool.inference()` in `base.py` always wraps input as `(1, C, H, W)` via `img[None, :, :, :]`
- `RTMPose.__call__(image, bboxes)` loops through bounding boxes one at a time, calling inference per bbox
- `RTMDet.__call__(image)` / `YOLOX.__call__(image)` processes one frame per call
- `PoseTracker.__call__(frame)` orchestrates: detect bboxes -> estimate pose per bbox
- Pose2Sim calls `pose_tracker(frame)` in a sequential `while` loop (`poseEstimation.py` ~line 351)

### Key files in rtmlib (site-packages)

- `tools/base.py` — Base inference class, ONNX session management
- `tools/pose_estimation/rtmpose.py` — RTMPose per-bbox inference
- `tools/object_detection/rtmdet.py` — RTMDet single-frame detection
- `tools/object_detection/yolox.py` — YOLOX single-frame detection
- `tools/solution/pose_tracker.py` — PoseTracker orchestrator (det -> pose, tracking, det_frequency)
- `tools/solution/body_with_feet.py` — BodyWithFeet solution class (picks detector+pose model URLs by mode preset)
- `tools/solution/custom.py` — Custom solution class (allows specifying detector and pose model separately)

### Pose2Sim integration point

`code/pose2sim/Pose2Sim/poseEstimation.py`:
- `setup_pose_tracker()` (~line 80): Creates `PoseTracker` with model class, det_frequency, mode, backend, device
- `process_video()` (~line 330): Sequential frame loop — `cap.read()` -> `pose_tracker(frame)` -> NMS -> tracking -> save JSON
- `estimate_pose_all()` (~line 554): Entry point called by `Pose2Sim.poseEstimation()`

## Prior Work in HPEVB

The `D:\PythonProjects\HPEVB\rtmlib` repo (conda env: `HPEVB`) contains working batch implementations for **bbox-level batching** (all detected bboxes in one frame batched into a single RTMPose inference call).

### What was implemented

- **`rtmpose.py`**: Batch preprocess (`np.stack` all bbox crops) -> single ONNX inference call -> batch postprocess
  - Key fix: stores `updated_scale` from `top_down_affine()` instead of original `scale`
  - cv2-based normalization (`cv2.subtract`/`cv2.divide`) replacing numpy ops (~2x faster)
- **`base.py`**: `inference()` handles both 3D (HWC, single image) and 4D (NCHW, batch) inputs
- **`rtmdet.py`**: cv2-based normalization optimization
- **Profiling infrastructure**: Detailed timing breakdown (preprocess/prep/model/postprocess) with CSV logging

### What was NOT implemented

- Frame-level batching (multiple frames through detector in one call) — not attempted anywhere
- Integration with pose2sim's frame loop
- Batch postprocessing for `get_simcc_maximum` (still loops per bbox)
- Note: `det_frequency` experiment (detect every N frames, track in between) was tried in HPEVB and reverted — degraded tracking quality

## Frame Batching Compatibility with Tracking

**Verified**: The detector is fully stateless and receives no feedback from the tracker. The data flow is strictly one-directional:

```
Detector(frame) → bboxes           (pure function, batchable)
Tracker(bboxes) → track_ids        (sequential, Kalman/IoU state, cheap CPU op)
Pose(frame, tracked_bboxes) → kpts (pure function, batchable)
```

Evidence:
- **rtmlib PoseTracker** (`pose_tracker.py` lines 184-212): `self.det_model(image)` takes only the raw frame. On non-detection frames (`det_frequency > 1`), it reuses `self.bboxes_last_frame` — cached, never fed back to detector.
- **rtmlib tracking** (lines 236-243): IoU-based tracking runs AFTER pose estimation, on pose-derived bboxes. Does not affect detection.
- **HPEVB ByteTracker** (`byte_tracker.py`): `update()` takes only detector output (bboxes + scores). Uses internal Kalman state for matching but never sends information back to the detector.
- **Pose2Sim tracking** (`poseEstimation.py` lines 373-380): sports2d and deepsort tracking both run after pose estimation, not before detection.
- **HPEVB detector protocol** (`detector_base.py` lines 19-37): All detectors (RTMDet, YOLOX, RF-DETR, RT-DETR) follow same interface — `__call__(self, frame: np.ndarray)` — frame only, no tracker state.

**Conclusion**: Can safely batch N frames through detector in one inference call, then process tracking sequentially (cheap CPU operation), then batch all bboxes across all frames through pose estimation.

**With `det_frequency > 1`**: Only detection frames need batching. Non-detection frames reuse cached bboxes as before.

### HPEVB Performance Baseline (from profiling logs)

| Component | Time (ms) | Notes |
|-----------|-----------|-------|
| Detection (RTMDet-m) | ~20 | preprocess 2ms, model 16.5ms, postprocess 1.2ms |
| Pose estimation (RTMPose-m, batched bboxes) | ~10 | Single inference for all bboxes |
| Total pipeline | ~48 | ~21 FPS |

### HPEVB models directory

`D:\PythonProjects\HPEVB\models\` contains 19 ONNX models:
- Detection: rtmdet (nano/tiny/s/m/l/x), yolox (m/l), rf-detr-M, rtdetrv2
- Pose: rtmpose (t/s/m/l/x) in various input sizes and keypoint configs (COCO-17, HALPE-26)

### Other HPEVB resources

- `misc project docs/gpu_pipeline_approaches.md` — Design doc for 3 GPU optimization strategies (NVIDIA Video SDK, TensorRT, PyTorch-based)
- `profiling_logs/` — CSV timing data for different detector/model combinations
- `scripts/MAIN.py` — Main pipeline script supporting RTMDet, RT-DETR, YOLOX, RF-DETR via factory pattern

## Frame Batching Benchmark Results

Benchmarked RTMDet-m detection with varying batch sizes using `rtmdet-m-640-batch.onnx` (dynamic batch axes). All frames pre-loaded into memory to isolate decode time. See `tools/bench_batch_det.py`.

**Hardware**: Windows 10, NVIDIA GPU with CUDA 12.4, 4K GoPro Hero 12 footage (3840x2160 @ 50fps, h.264)

**Config**: RTMDet-m, ONNX Runtime + CUDA EP, 200 frames after 10-frame warmup

### End-to-end (preprocess + compute + postprocess)

| Batch | Frames | Batches | Preproc (ms) | Compute (ms) | Post (ms) | Total (ms) | ms/frame | FPS  | Speedup |
|-------|--------|---------|-------------|-------------|----------|-----------|---------|------|---------|
| 1     | 200    | 200     | 2509        | 2347        | 5        | 4861      | 24.31   | 41.1 | 1.00x   |
| 2     | 200    | 100     | 2475        | 1903        | 4        | 4381      | 21.91   | 45.7 | 1.11x   |
| 4     | 200    | 50      | 2489        | 1734        | 3        | 4226      | 21.13   | 47.3 | 1.15x   |
| 8     | 200    | 25      | 2467        | 1712        | 3        | 4182      | 20.91   | 47.8 | 1.16x   |

### Compute only (GPU inference time)

| Batch | Compute/batch (ms) | Compute/frame (ms) | Speedup |
|-------|-------------------|-------------------|---------|
| 1     | 11.73             | 11.73             | 1.00x   |
| 2     | 19.03             | 9.51              | 1.23x   |
| 4     | 34.67             | 8.67              | 1.35x   |
| 8     | 68.50             | 8.56              | 1.37x   |

### Analysis

- **GPU compute scales sublinearly**: batch=8 gives only 1.37x compute speedup (ideal would be 8x). The GPU is already fairly saturated at batch=1 for RTMDet-m — the model is large enough that GPU ALUs are well-utilized with a single frame.
- **Diminishing returns**: batch=4 and batch=8 are nearly identical in compute/frame (8.67 vs 8.56ms). Batching amortizes kernel launch overhead but the gains plateau fast.
- **Preprocessing becomes the bottleneck**: CPU preprocessing (`cv2.resize` + normalize) is ~2.5s constant regardless of batch size. At batch=8, preprocessing is 59% of total time vs 52% at batch=1.
- **End-to-end: batch=8 is only 1.16x faster than batch=1**. Modest gain for the implementation complexity.

## Implementation Approach

### Step 1: Switch detector to RTMDet (batch-capable ONNX)

Replace YOLOX-x (fixed batch=1) with RTMDet using `rtmdet-m-640-batch.onnx`. Use rtmlib's `Custom` class to specify detector and pose models separately instead of the `performance` mode preset.

### Step 2: Port HPEVB bbox-level batching to Go2Kin's rtmlib

Apply HPEVB's changes to `base.py` and `rtmpose.py` in the Go2Kin conda env's rtmlib site-packages. This gives us batched pose estimation across all bboxes in a single frame.

### Step 3: Add frame-level batching

Extend RTMDet to accept N frames in one inference call (using the batch-capable ONNX), and extend PoseTracker with a `process_batch(frames)` method.

### Step 4: Modify pose2sim frame loop

Change `poseEstimation.py`'s `process_video()` to read N frames at once, batch through detector+pose, then process results (NMS, tracking, JSON save) per frame.

### API Compatibility (for future PRs)

- `PoseTracker.__call__(image)` must still work for single-frame input (backward compat)
- `RTMPose.__call__(image, bboxes)` must still work for single frame
- `RTMDet.__call__(image)` must still work for single frame
- Models with fixed batch=1 must gracefully fall back to sequential processing
- Detect batch support at init: `isinstance(session.get_inputs()[0].shape[0], str)`
- Timing/profiling should be optional (off by default)
