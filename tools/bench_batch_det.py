"""
Benchmark: RTMDet-m detection with varying batch sizes.
Compares throughput of batch=1 vs batch=2,4,8 frame batching.

Uses rtmdet-m-640-batch.onnx (dynamic batch axes) from HPEVB.

Usage:
    conda activate Go2Kin
    python tools/bench_batch_det.py
"""

import os
import sys
import time

# --- CONFIG (edit these) ---
VIDEO_PATH = r"E:\Markerless_Data\tests_home\sessions\weekend_march\dancing\video\synced\dancing_GP1.mp4"
RTMDET_BATCH_MODEL = r"D:\PythonProjects\HPEVB\models\rtmdet-m-640-batch.onnx"
MAX_FRAMES = 200       # total frames to process (after warmup)
WARMUP_FRAMES = 10
BATCH_SIZES = [1, 2, 4, 8]
# ---------------------------

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code', 'pose2sim'))

import cv2
import numpy as np
import onnxruntime as ort


def preprocess_rtmdet(img, model_input_size=(640, 640), mean=(103.53, 116.28, 123.675), std=(57.375, 57.12, 58.395)):
    """RTMDet preprocessing: letterbox resize + normalize. Returns (chw_tensor, ratio)."""
    if img.shape[:2] == model_input_size:
        padded = img.copy()
        ratio = 1.0
    else:
        padded = np.ones((model_input_size[0], model_input_size[1], 3), dtype=np.uint8) * 114
        ratio = min(model_input_size[0] / img.shape[0], model_input_size[1] / img.shape[1])
        resized = cv2.resize(img, (int(img.shape[1] * ratio), int(img.shape[0] * ratio)),
                             interpolation=cv2.INTER_LINEAR).astype(np.uint8)
        padded[:resized.shape[0], :resized.shape[1]] = resized

    # normalize
    mean_arr = np.array(mean)
    std_arr = np.array(std)
    padded = (padded - mean_arr) / std_arr

    # HWC -> CHW, float32
    chw = padded.transpose(2, 0, 1).astype(np.float32)
    return chw, ratio


def postprocess_rtmdet_batch(dets_batch, labels_batch, ratios, score_thr=0.3):
    """Postprocess RTMDet batch output. Returns list of bbox arrays (one per frame)."""
    results = []
    for i in range(dets_batch.shape[0]):
        dets = dets_batch[i]       # (num_dets, 5) = xyxy + score
        labels = labels_batch[i]   # (num_dets,)
        # Filter by score and class (class 0 = person)
        mask = (dets[:, 4] > score_thr) & (labels == 0)
        boxes = dets[mask, :4] / ratios[i]
        results.append(boxes)
    return results


def read_frames(video_path, n_frames, skip=0):
    """Read n_frames from video, skipping first `skip` frames."""
    cap = cv2.VideoCapture(video_path)
    for _ in range(skip):
        cap.read()
    frames = []
    for _ in range(n_frames):
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    return frames


def bench_batch(session, frames, batch_size):
    """Benchmark detection at a given batch size. Returns per-frame timing breakdown."""
    input_name = session.get_inputs()[0].name
    n_frames = len(frames)
    n_batches = (n_frames + batch_size - 1) // batch_size

    preprocess_ms = []
    compute_ms = []
    postprocess_ms = []

    for b in range(n_batches):
        batch_frames = frames[b * batch_size: (b + 1) * batch_size]
        actual_batch = len(batch_frames)

        # Preprocess
        t0 = time.perf_counter()
        tensors = []
        ratios = []
        for frame in batch_frames:
            chw, ratio = preprocess_rtmdet(frame)
            tensors.append(chw)
            ratios.append(ratio)
        input_tensor = np.stack(tensors)  # (N, 3, 640, 640)
        preprocess_ms.append((time.perf_counter() - t0) * 1000)

        # Inference
        t0 = time.perf_counter()
        dets_out, labels_out = session.run(None, {input_name: input_tensor})
        compute_ms.append((time.perf_counter() - t0) * 1000)

        # Postprocess
        t0 = time.perf_counter()
        _ = postprocess_rtmdet_batch(dets_out, labels_out, ratios)
        postprocess_ms.append((time.perf_counter() - t0) * 1000)

    # Convert to per-frame metrics
    total_preprocess = sum(preprocess_ms)
    total_compute = sum(compute_ms)
    total_postprocess = sum(postprocess_ms)
    total_time = total_preprocess + total_compute + total_postprocess

    return {
        'batch_size': batch_size,
        'n_frames': n_frames,
        'n_batches': n_batches,
        'preprocess_total_ms': total_preprocess,
        'compute_total_ms': total_compute,
        'postprocess_total_ms': total_postprocess,
        'total_ms': total_time,
        'per_frame_ms': total_time / n_frames,
        'compute_per_frame_ms': total_compute / n_frames,
        'compute_per_batch_ms': np.mean(compute_ms),
        'fps': n_frames / (total_time / 1000),
    }


def main():
    if not os.path.isfile(VIDEO_PATH):
        print(f"ERROR: VIDEO_PATH not found: {VIDEO_PATH}")
        return
    if not os.path.isfile(RTMDET_BATCH_MODEL):
        print(f"ERROR: RTMDET_BATCH_MODEL not found: {RTMDET_BATCH_MODEL}")
        return

    # Video info
    cap = cv2.VideoCapture(VIDEO_PATH)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = round(cap.get(cv2.CAP_PROP_FPS))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    print(f"Video: {os.path.basename(VIDEO_PATH)}")
    print(f"Resolution: {w}x{h} @ {fps}fps, {total} frames")
    print(f"Model: {os.path.basename(RTMDET_BATCH_MODEL)}")
    print(f"Processing {MAX_FRAMES} frames (after {WARMUP_FRAMES} warmup)")

    # Load model
    print("\nLoading RTMDet-m (batch-capable)...")
    session = ort.InferenceSession(
        RTMDET_BATCH_MODEL,
        providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
    )
    input_shape = session.get_inputs()[0].shape
    print(f"Input shape: {input_shape}")

    # Read all frames into memory (so decode time doesn't affect benchmark)
    print("Reading frames into memory...")
    frames = read_frames(VIDEO_PATH, WARMUP_FRAMES + MAX_FRAMES)
    warmup_frames = frames[:WARMUP_FRAMES]
    bench_frames = frames[WARMUP_FRAMES:WARMUP_FRAMES + MAX_FRAMES]
    print(f"Loaded {len(bench_frames)} frames for benchmarking")

    # Warmup the GPU / ONNX session
    print("Warming up...")
    for frame in warmup_frames:
        chw, _ = preprocess_rtmdet(frame)
        session.run(None, {session.get_inputs()[0].name: chw[None]})

    # Benchmark each batch size
    print(f"\n{'='*70}")
    print("RTMDet-m BATCH INFERENCE BENCHMARK")
    print(f"{'='*70}")

    results = []
    for bs in BATCH_SIZES:
        print(f"\nRunning batch_size={bs}...")
        r = bench_batch(session, bench_frames, bs)
        results.append(r)

    # Print results table
    print(f"\n{'='*70}")
    header = ["Batch", "Frames", "Batches", "Preproc (ms)", "Compute (ms)",
              "Post (ms)", "Total (ms)", "ms/frame", "FPS", "Speedup"]
    baseline_fps = results[0]['fps']

    rows = []
    for r in results:
        rows.append([
            str(r['batch_size']),
            str(r['n_frames']),
            str(r['n_batches']),
            f"{r['preprocess_total_ms']:.0f}",
            f"{r['compute_total_ms']:.0f}",
            f"{r['postprocess_total_ms']:.0f}",
            f"{r['total_ms']:.0f}",
            f"{r['per_frame_ms']:.2f}",
            f"{r['fps']:.1f}",
            f"{r['fps']/baseline_fps:.2f}x",
        ])

    col_widths = [max(len(str(row[i])) for row in [header] + rows) for i in range(len(header))]
    fmt = "  ".join(f"{{:>{w}}}" for w in col_widths)
    print(fmt.format(*header))
    print(fmt.format(*["-" * w for w in col_widths]))
    for row in rows:
        print(fmt.format(*row))

    # Compute-only comparison
    print(f"\n{'='*70}")
    print("COMPUTE ONLY (GPU inference time)")
    print(f"{'='*70}")
    print(f"  {'Batch':>5}  {'Compute/batch (ms)':>18}  {'Compute/frame (ms)':>18}  {'Speedup':>8}")
    print(f"  {'-----':>5}  {'------------------':>18}  {'------------------':>18}  {'--------':>8}")
    baseline_cpf = results[0]['compute_per_frame_ms']
    for r in results:
        speedup = baseline_cpf / r['compute_per_frame_ms'] if r['compute_per_frame_ms'] > 0 else 0
        print(f"  {r['batch_size']:>5}  {r['compute_per_batch_ms']:>18.2f}  "
              f"{r['compute_per_frame_ms']:>18.2f}  {speedup:>7.2f}x")


if __name__ == "__main__":
    main()
