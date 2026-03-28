# Pose2Sim: Person Tracking & Association Pipeline

## Overview

Pose2Sim processes multi-camera video to produce 3D keypoints. Before triangulation can happen, the system must solve two association problems:

1. **Within-camera tracking** (Stage 1): The same physical person should have the same index across frames in a single camera's output.
2. **Cross-camera association** (Stage 2): Person index `i` in camera 1 should refer to the same physical person as index `i` in camera 2.

Only after both are resolved can keypoints be triangulated into 3D (Stage 3).

**Important constraint:** Throughout the entire pipeline, keypoints are never reassigned between persons. Each person is an atomic unit — all 26 keypoints stay bound to whichever person the pose estimator originally assigned them to.

---

## Pipeline Flowchart

```
╔══════════════════════════════════════════════════════════════════════╗
║                    POSE2SIM PERSON PIPELINE                        ║
╚══════════════════════════════════════════════════════════════════════╝

┌──────────────────────────────────────────────────────────────────────┐
│  STAGE 1: POSE ESTIMATION  (per camera, per frame)                  │
│  poseEstimation.py                                                  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │ 1a. RTMLib PoseTracker                                   │        │
│  │     Input:  frame (H, W, 3)                              │        │
│  │     Output: keypoints [n, 26, 2], scores [n, 26]         │        │
│  │     n = persons detected (arbitrary order each frame)     │        │
│  └──────────────────────┬──────────────────────────────────┘        │
│                         ▼                                            │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │ 1b. NMS (redundant with RTMLib's internal NMS)           │        │
│  │     - Filter low-confidence persons (mean score > 0.2)   │        │
│  │     - Compute bboxes FROM keypoints (not from detector)  │        │
│  │     - Apply NMS on bboxes (IoU threshold 0.45)           │        │
│  │     - Bboxes discarded after this step                   │        │
│  │     - Alreaady done in RTMlib yolox.py / rtmdet.py       │        │
│  └──────────────────────┬──────────────────────────────────┘        │
│                         ▼                                            │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │ 1c. Tracking (sports2d or deepsort)                      │        │
│  │     - Reorders the n dimension so that index i            │        │
│  │       corresponds to the same physical person across      │        │
│  │       frames (within this camera)                         │        │
│  │     - sports2d: Hungarian algorithm on mean keypoint      │        │
│  │       distance vs previous frame                          │        │
│  │     - Whole-person association only (no keypoint swap)    │        │
│  └──────────────────────┬──────────────────────────────────┘        │
│                         ▼                                            │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │ 1d. Save to JSON (per frame)                             │        │
│  │     One file per frame, "people" array with n entries     │        │
│  │     person_id always [-1] (tracking info not written)     │        │
│  └─────────────────────────────────────────────────────────┘        │
│                                                                      │
│  Result: consistent person indices across FRAMES, per camera         │
│  Camera 1: person 0 = Alice, person 1 = Bob (all frames)            │
│  Camera 2: person 0 = ???, person 1 = ??? (no cross-cam link yet)   │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STAGE 2: PERSON ASSOCIATION  (across cameras, per frame)           │
│  personAssociation.py                                                │
│                                                                      │
│  Goal: determine which person index in each camera corresponds       │
│  to the same physical person across all cameras                      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │ SINGLE PERSON MODE                                         │     │
│  │                                                             │     │
│  │  For a tracked keypoint (e.g. hip):                         │     │
│  │  1. Generate all combinations of person IDs across cams     │     │
│  │     e.g. (cam1-p0, cam2-p0, cam3-p0),                      │     │
│  │         (cam1-p0, cam2-p0, cam3-p1), ...                    │     │
│  │     Cartesian product across ALL cameras simultaneously     │     │
│  │  2. Triangulate the keypoint for each combination (DLT)     │     │
│  │  3. Reproject 3D -> 2D, compute reprojection error          │     │
│  │  4. Keep combination with smallest error                    │     │
│  │     (drop cameras one-by-one if error too high)             │     │
│  └────────────────────────────────────────────────────────────┘     │
│                          OR                                          │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │ MULTI PERSON MODE                                          │     │
│  │                                                             │     │
│  │  1. For each person in each camera, compute Plucker rays    │     │
│  │     (camera center -> keypoint lines in 3D)                 │     │
│  │  2. For each camera pair, compute ray-to-ray distances      │     │
│  │     across ALL joints (reciprocal product)                  │     │
│  │  3. Build affinity matrix: affinity = 1 - dist/max_dist    │     │
│  │  4. Solve optimal assignment (which cam1-person matches     │     │
│  │     which cam2-person)                                      │     │
│  └────────────────────────────────────────────────────────────┘     │
│                                                                      │
│  Output: filtered JSON files -- same person index across all cameras │
│  Still whole-person units -- no keypoint reassignment                │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STAGE 3: TRIANGULATION                                             │
│  triangulation.py                                                    │
│                                                                      │
│  Person 0 across all cameras = same physical person                  │
│  -> Triangulate all keypoints into 3D per person per frame           │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Stage Details

### Stage 1: Pose Estimation (`poseEstimation.py`)

Runs independently per camera (per video file).

| Step | What happens | Data shape |
|------|-------------|------------|
| **1a. RTMLib** | Detects all persons and their keypoints in each frame | `keypoints [n, 26, 2]`, `scores [n, 26]` |
| **1b. NMS** | Filters low-confidence detections, computes bboxes from keypoints, applies NMS. Bboxes are discarded after this step — they exist only for NMS. | Same shape, reduced `n` |
| **1c. Tracking** | Reorders `n` dimension so the same index = same person across frames. Uses Hungarian algorithm (sports2d) or DeepSORT. | Same shape, reordered `n` |
| **1d. Save** | Writes one JSON per frame with `n` person entries. `person_id` field is always `[-1]`. | JSON files on disk |

**sports2d tracking algorithm:**
- Distance metric: mean Euclidean distance across all keypoints between previous and current frame
- Assignment: Hungarian algorithm (`scipy.optimize.linear_sum_assignment`)
- Unmatched detections beyond `max_dist` threshold become new persons

### Stage 2: Person Association (`personAssociation.py`)

Runs across all cameras simultaneously, per frame.

**Single person mode:**
- Uses one tracked keypoint (configurable, e.g. hip)
- Generates cartesian product of person IDs across all cameras
- Triangulates each combination using DLT, picks lowest reprojection error
- Can drop cameras iteratively if error exceeds threshold

**Multi person mode:**
- Computes Plucker ray coordinates (camera center to keypoint) for each person in each view
- Ray-to-ray distance via reciprocal product of Plucker coordinates (no actual 3D triangulation needed)
- Builds affinity matrix from distances, solves assignment problem
- Inspired by EasyMocap approach

### Stage 3: Triangulation (`triangulation.py`)

With person indices now consistent across both frames and cameras, triangulates each keypoint into 3D using DLT with the calibrated camera projection matrices.

---

## Key Source Files

| File | Role |
|------|------|
| `Pose2Sim/poseEstimation.py` | Stage 1: detection, NMS, tracking, JSON output |
| `Pose2Sim/common.py` (`sort_people_sports2d`) | Sports2D tracking implementation (Hungarian algorithm) |
| `Pose2Sim/personAssociation.py` | Stage 2: cross-camera person matching |
| `Pose2Sim/triangulation.py` | Stage 3: 3D triangulation |

---

## Considerations: Legacy vs Top-Down Architecture

The current pose2sim pipeline was originally designed around OpenPose, which is a bottom-up pose estimator: it detects keypoints for the whole frame first, then groups them into persons. OpenPose produces no bounding boxes, so pose2sim had to:

1. Compute bboxes from keypoints
2. Run NMS to remove duplicate detections
3. Track persons across frames using keypoint-based methods (sports2d)

Recently pose2sim was changed to use RTMlib instead of OpenPose for pose estimation. RTMLib uses a top-down approach: a detector (YOLOX or RTMDet) first finds person bounding boxes, then a pose model estimates keypoints within each bbox. This means:

### Step 1b (bbox + NMS) is redundant

RTMLib's internal detector already performs NMS on bounding boxes before pose estimation runs. Pose2sim then recomputes bboxes from keypoints and applies NMS again — this is purely redundant and could be removed.

### Tracking could operate on bboxes instead of keypoints

Since RTMLib already has bounding boxes and bbox confidence scores (from YOLOX/RTMDet), these could be surfaced and used for tracking instead of the current keypoint-based approach. Benefits:

- **Bbox tracking is well-established**: algorithms like ByteTrack produce consistent person tracking from bounding boxes and are widely used in multi-object tracking
- **More robust**: bboxes are less noisy than individual keypoints for frame-to-frame association
- **Cleaner separation of concerns**: detection/tracking operates on bboxes, pose estimation provides keypoints within tracked persons

Almost all top-down pose estimation approaches use bboxes rather than keypoints for tracking (ByteTrack, BoT-SORT and all the xx-SORT).

The current keypoint-based sports2d tracking works but is a workaround inherited from the bottom-up (OpenPose) era. With top-down models, bbox-based tracking (e.g. ByteTrack / BoT-SORT) is the more natural and performant approach.
