# Surfacing Bounding Boxes from rtmlib

## Problem

rtmlib's detection models (YOLOX, RTMDet) compute bounding boxes and confidence scores internally, but discard the scores before returning. The data flows through 3 wrapper layers, each stripping information:

```
YOLOX.postprocess()     → computes (final_boxes, final_scores, final_cls_inds)
YOLOX.__call__()        → returns final_boxes only (scores discarded)
Body.__call__()         → passes bboxes to pose model, returns (keypoints, kpt_scores)
PoseTracker.__call__()  → returns (keypoints, kpt_scores) — bboxes discarded again
```

Pose2Sim (`poseEstimation.py:351-370`) receives only `(keypoints, scores)` and must **recompute bboxes from keypoints** (min/max x,y) for its own NMS and tracking. This is:
- **Redundant**: bboxes already existed inside YOLOX
- **Lossy**: detector confidence is replaced by mean keypoint confidence
- **Architecturally wrong**: the detection→tracking→pose pipeline should flow naturally, not reconstruct earlier outputs from later ones

## Current rtmlib architecture

### YOLOX (`rtmlib/tools/object_detection/yolox.py`)
- `postprocess()`: decodes grid predictions, computes `scores = objectness * class_scores`, runs multiclass NMS, produces `(final_boxes, final_scores, final_cls_inds)`
- `__call__()`: calls preprocess → inference → postprocess, returns only `final_boxes` (mode='human') or `(final_boxes, final_cls_inds)` (mode='multiclass')
- `final_scores` is a local variable — never stored or returned

### RTMDet (`rtmlib/tools/object_detection/rtmdet.py`)
- Same pattern as YOLOX — scores computed in postprocess, discarded in `__call__`

### Body / Wholebody / Custom (`rtmlib/tools/solution/`)
- `__call__()`: calls `self.det_model(image)` → gets bboxes → passes to `self.pose_model(image, bboxes=bboxes)` → returns `(keypoints, scores)`
- Bboxes are consumed by pose model and not returned

### PoseTracker (`rtmlib/tools/solution/pose_tracker.py`)
- Wraps a solution class, adds IoU-based tracking
- Internally recomputes bboxes from keypoints via `pose_to_bbox()` for its own tracking
- Returns only `(keypoints, scores)`

## Pose2Sim's workaround (`poseEstimation.py:341-380`)

```python
keypoints, scores = pose_tracker(frame)                          # line 351

# Re-derive bboxes from keypoints (lines 353-370)
mask_scores = np.mean(scores, axis=1) > 0.2
likely_bboxes = bbox_xyxy_compute(frame_shape, likely_keypoints)  # min/max x,y
score_likely_bboxes = np.nanmean(likely_scores, axis=1)           # proxy for bbox confidence
keep = nms(valid_bboxes, valid_scores, nms_thr=0.45)              # NMS on reconstructed bboxes

# Tracking on keypoints (lines 372-380)
sort_people_sports2d(prev_keypoints, keypoints, ...)              # spatial distance matching
```

This is NMS applied **twice** (once inside YOLOX, once in pose2sim on worse data) and tracking done on keypoints instead of bboxes.

## Proposed solution: attribute side-channel

### Core idea

Store bbox scores as an attribute on the detection model object during inference. This requires no change to return signatures and is fully backward compatible.

### Changes to rtmlib (minimal PR)

**YOLOX** (`yolox.py`):
```python
# In __init__:
self.last_scores = np.array([])

# In postprocess, after computing final_scores (around line 142-145):
self.last_scores = final_scores[keep]  # store after NMS filtering

# __call__ return signature: UNCHANGED
```

**RTMDet** (`rtmdet.py`): same pattern.

**PoseTracker** (`pose_tracker.py`):
```python
# In __init__:
self.last_bboxes = np.array([])
self.last_bbox_scores = np.array([])

# In __call__, after detection (around line 201):
bboxes = self.det_model(image)
self.last_bboxes = bboxes
self.last_bbox_scores = self.det_model.last_scores
```

**Body / Wholebody / Custom**: optionally same pattern, or consumers can access `body.det_model.last_scores` directly.

### Low-level rtmlib classes are directly importable

Stock rtmlib (pip-installed) exports the low-level model classes:
```python
from rtmlib import YOLOX, RTMDet, RTMPose, RTMO
```
These can be called directly without going through `Body`, `PoseTracker`, or any solution class. 

### Usage from pose2sim (with low-level classes)

```python
from rtmlib import YOLOX, RTMPose

det = YOLOX(onnx_model=det_url, model_input_size=(640,640), backend=backend, device=device)
pose = RTMPose(onnx_model=pose_url, model_input_size=(192,256), backend=backend, device=device)

# Per frame:
bboxes = det(frame)
bbox_scores = det.last_scores           # from side-channel PR
keypoints, kpt_scores = pose(frame, bboxes=bboxes)
# All arrays are 1:1 (N bboxes → N keypoints), no filtering
# Caller does own NMS/tracking with real bbox_scores
```

### Properties
- **Backward compatible**: existing code calling `det_model(image)` or `pose_tracker(frame)` works unchanged
- **Zero performance overhead**: storing a numpy array reference is O(1)
- **Tiny diff**: ~5-10 lines across 2-3 files
- **PR-friendly**: no API breakage, purely additive

## Alternatives considered

| Approach | Pros | Cons |
|---|---|---|
| **Attribute side-channel (recommended)** | Tiny diff, backward compat, no new classes | None significant |
| Change return signature to `(boxes, scores)` | Clean API | Breaks all existing consumers |
| Add `detect_with_scores()` method | No breakage | Duplicates method, maintenance burden |
| New solution classes (`CustomDetOnly`, `CustomPoseOnly`) | Clean separation | Unnecessary — low-level classes already importable |
| Extract inference code from rtmlib | Full control | Maintain pre/postprocessing yourself |

## Downstream: pose2sim changes

Two PRs:

### PR 1: rtmlib (tiny)
Add `self.last_scores = final_scores[keep]` to YOLOX and RTMDet postprocess methods. ~2 lines per class.

### PR 2: pose2sim (config option for low-level rtmlib pipeline)

**Config option** in `Config.toml`:
```toml
[pose]
pipeline = 'posetracker'   # default: existing PoseTracker behavior (backward compatible)
# pipeline = 'detpose'     # new: low-level YOLOX + RTMPose, exposes bboxes + scores
```

**Branch point** in `estimate_pose_all()` (poseEstimation.py line ~690):
```python
if pipeline == 'detpose':
    det_model, pose_model_instance = setup_detpose(mode, backend, device)
    # dispatch to process_video_detpose()
else:
    pose_tracker = setup_pose_tracker(...)
    # dispatch to process_video() as before
```

**New function `process_video_detpose()`**: parallel to existing `process_video()`, same video I/O / JSON save / visualization code, but inner loop is:
```python
bboxes = det_model(frame)
bbox_scores = det_model.last_scores           # from PR 1
keypoints, kpt_scores = pose_model(frame, bboxes=bboxes)
# All arrays are 1:1 (N bboxes → N keypoints), no filtering
# Caller does own NMS/tracking with real bbox_scores
```

Duplicating `process_video()` with a different inner loop is more reviewable than refactoring the shared code. ~70% of the function (video setup, JSON output, visualization) is identical boilerplate.

**New function `setup_detpose()`**: maps `mode` ('balanced', etc.) to YOLOX + RTMPose model URLs (same URLs as `Body.MODE` dict), instantiates them directly:
```python
from rtmlib import YOLOX, RTMPose
det = YOLOX(onnx_model=det_url, model_input_size=(640,640), backend=backend, device=device)
pose = RTMPose(onnx_model=pose_url, model_input_size=(192,256), backend=backend, device=device)
```

## Key files

- `rtmlib/tools/object_detection/yolox.py` — YOLOX detection, scores discarded at line 163
- `rtmlib/tools/object_detection/rtmdet.py` — RTMDet detection, same pattern
- `rtmlib/tools/solution/body.py` — Body solution, bboxes not forwarded (line 141-144)
- `rtmlib/tools/solution/pose_tracker.py` — PoseTracker, recomputes bboxes from kpts (line 237)
- `pose2sim/Pose2Sim/poseEstimation.py` — Consumer, re-derives bboxes at lines 353-370
- `D:\PythonProjects\HPEVB\rtmlib\` — Prior fork with partial changes (det returns scores, batch pose inference)

## Prior work (HPEVB)

The `D:\PythonProjects\HPEVB\rtmlib\` fork already modified YOLOX/RTMDet to return `(boxes, scores)` and RTMPose to do batch inference. However:
- Solution classes (Body, Custom) were not updated to match the new detection return format
- PoseTracker still uses stock IoU tracking from keypoint-derived bboxes
- The return signature change breaks backward compatibility

The attribute side-channel approach achieves the same goal without those issues.
