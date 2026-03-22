# Pose Estimation Data Flow

Data flow through Pose2Sim's `poseEstimation.py` and rtmlib during the pose estimation step.

## Entry Point

`Pose2Sim.poseEstimation()` → `estimate_pose_all(config_dict)` in `poseEstimation.py`

## Setup (once per trial)

1. **Config reads**: video directory, model type, mode, det_frequency, backend, device, tracking_mode
2. **Backend/device selection** (`setup_backend_device()`): CUDA+ONNXRuntime > ROCm > MPS > CPU+OpenVINO
3. **Model setup** (`setup_model_class_mode()`): Selects detector + pose model based on `pose_model` and `mode`
   - Default: `Body_with_feet` (HALPE_26) + `performance` mode → YOLOX-x + RTMPose-l
4. **PoseTracker creation** (`setup_pose_tracker()`): Creates single rtmlib `PoseTracker` instance
   - Loads ONNX models into GPU memory (stays loaded for all videos)
   - Contains detection model (YOLOX) + pose model (RTMPose)

## Per-Video Processing

```
estimate_pose_all()
  for each video file:
      pose_tracker.reset()          # clear frame counter, cached bboxes, track IDs
      process_video(video_path, pose_tracker, ...)
```

**No shared state between videos** — `reset()` clears all tracking state. Videos are independent.

## process_video() — Frame Loop

```
for each frame in video:
    ┌─────────────────────────────────────────────────────────┐
    │  STEP 1: rtmlib inference                               │
    │  keypoints, scores = pose_tracker(frame)                │
    │                                                         │
    │  Inside PoseTracker.__call__():                          │
    │                                                         │
    │  A) Detection (every det_frequency frames):             │
    │     bboxes = det_model(frame)                           │
    │     → YOLOX returns list of [x1, y1, x2, y2] per person│
    │                                                         │
    │  B) Non-detection frames:                               │
    │     bboxes = self.bboxes_last_frame  (reuse cached)     │
    │                                                         │
    │  C) For each bbox:                                      │
    │     crop frame → affine transform → RTMPose inference   │
    │     → SimCC heatmaps → get_simcc_maximum() → keypoints  │
    │                                                         │
    │  D) IoU tracking: reorder people to match previous IDs  │
    │                                                         │
    │  Returns:                                               │
    │    keypoints: (num_people, 26, 2)  — x,y pixel coords   │
    │    scores:    (num_people, 26)     — confidence [0,1]    │
    └─────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────┐
    │  STEP 2: Pose2Sim post-processing                       │
    │                                                         │
    │  a) Score filter: mean score per person > 0.2           │
    │     → replace low-confidence people with NaN            │
    │                                                         │
    │  b) Compute bboxes from filtered keypoints              │
    │     likely_bboxes = bbox_xyxy_compute(keypoints)        │
    │                                                         │
    │  c) NMS (Non-Maximum Suppression, IoU threshold 0.45)   │
    │     → remove duplicate/overlapping detections           │
    │                                                         │
    │  d) Tracking (optional, per config):                    │
    │     - sports2d: Hungarian algorithm, max_distance_px    │
    │     - deepsort: deep appearance features + motion model │
    │     → reorder people rows to maintain identity across   │
    │       frames; pad with NaN if person lost               │
    └─────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────┐
    │  STEP 3: JSON export                                    │
    │  save_to_openpose(json_path, keypoints, scores)         │
    │                                                         │
    │  Output: one JSON file per frame                        │
    │  Path: pose/{video_name}_json/{video_name}_{frame:06d}.json │
    │                                                         │
    │  Format (OpenPose):                                     │
    │  {                                                      │
    │    "version": 1.3,                                      │
    │    "people": [                                          │
    │      {                                                  │
    │        "person_id": [-1],                               │
    │        "pose_keypoints_2d": [x0,y0,c0, x1,y1,c1, ...], │
    │        ...                                              │
    │      }                                                  │
    │    ]                                                    │
    │  }                                                      │
    │  → 78 floats per person (26 keypoints × 3: x, y, conf) │
    └─────────────────────────────────────────────────────────┘

    STEP 4: Visualization (optional)
    If display_detection, save_video, or save_images enabled:
    → draw skeleton, keypoints, bounding boxes on frame copy
    → write to video file / image files / cv2 window
```

## Data Shape Transformations

| Step | Shape | Notes |
|------|-------|-------|
| rtmlib output | keypoints `(P, 26, 2)`, scores `(P, 26)` | P = detected people |
| Score filter | same shape, low-confidence → NaN | mean score per person > 0.2 |
| NMS | `(P', 26, 2)`, `(P', 26)` | P' ≤ P, overlapping removed |
| Tracking | same shape, rows reordered | person identity preserved |
| JSON export | flat array per person | `[x0, y0, c0, x1, y1, c1, ...]` |

## Error Handling

- If rtmlib throws an exception on a frame: all-NaN keypoints `(1, 26, 2)` are saved. Frame is not skipped.
- If no people detected: JSON written with `"people": []`
- Every frame produces a JSON file regardless of detection success.

## Mutable State

### Within a video (frame-to-frame):
- `pose_tracker.frame_cnt` — frame counter (controls det_frequency)
- `pose_tracker.bboxes_last_frame` — cached bboxes for non-detection frames
- `pose_tracker.track_ids_last_frame` — person ID tracking
- `prev_keypoints` (local var) — used by sports2d tracking

### Between videos:
- **None.** `pose_tracker.reset()` clears all state. Videos are fully independent.

## Key Files

| File | Role |
|------|------|
| `code/pose2sim/Pose2Sim/poseEstimation.py` | Main loop: `estimate_pose_all()`, `process_video()`, `save_to_openpose()` |
| `code/pose2sim/Pose2Sim/Pose2Sim.py` | Pipeline orchestrator, calls `estimate_pose_all(config_dict)` |
| `rtmlib/tools/solution/pose_tracker.py` | `PoseTracker.__call__()`: detection + pose + IoU tracking |
| `rtmlib/tools/base.py` | `BaseTool`: ONNX session creation and `inference()` method |
| `rtmlib/tools/object_detection/rtmdet.py` or `yolox.py` | Frame → bounding boxes |
| `rtmlib/tools/pose_estimation/rtmpose.py` | Bbox crop → keypoints + scores |
