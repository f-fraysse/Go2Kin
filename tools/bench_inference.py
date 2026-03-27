"""
Benchmark: Break down pose estimation inference into individual stages.
Measures preprocess (CPU), host->device transfer, GPU compute, device->host transfer, postprocess (CPU).

Usage:
    conda activate Go2Kin
    python tools/bench_inference.py
"""

import os
import sys
import time

# --- CONFIG (edit these) ---
VIDEO_PATH = r"E:\Markerless_Data\tests_home\sessions\weekend_march\dancing\video\synced\dancing_GP1.mp4"
MAX_FRAMES = 100
WARMUP_FRAMES = 10
# ---------------------------

# Ensure CUDA_PATH is set for PyNvVideoCodec
cuda_path = os.environ.get('CUDA_PATH') or os.environ.get('CUDA_PATH_V12_4')
if cuda_path:
    os.environ['CUDA_PATH'] = cuda_path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code', 'pose2sim'))

import cv2
import numpy as np
import onnxruntime as ort
from Pose2Sim.poseEstimation import setup_pose_tracker, setup_model_class_mode


def time_ms(func, *args, **kwargs):
    t0 = time.perf_counter()
    result = func(*args, **kwargs)
    return (time.perf_counter() - t0) * 1000, result


def bench_det_breakdown(det_model, frame):
    """Break down YOLOX detection into preprocess, transfer+compute, postprocess."""
    # 1. Preprocess (CPU): resize, pad, transpose, contiguous
    t0 = time.perf_counter()
    padded_img, ratio = det_model.preprocess(frame)
    # Also include the transpose + contiguous that base.inference() does
    img_chw = padded_img.transpose(2, 0, 1)
    input_tensor = np.ascontiguousarray(img_chw, dtype=np.float32)[None, :, :, :]
    preprocess_ms = (time.perf_counter() - t0) * 1000

    # 2. Inference via io_binding (separate H2D, compute, D2H)
    session = det_model.session
    input_name = session.get_inputs()[0].name
    output_names = [o.name for o in session.get_outputs()]
    output_shapes = [o.shape for o in session.get_outputs()]

    io_binding = session.io_binding()

    # 2a. Bind input: copies CPU numpy -> GPU (H2D transfer)
    t0 = time.perf_counter()
    input_ort = ort.OrtValue.ortvalue_from_numpy(input_tensor, 'cuda', 0)
    h2d_ms = (time.perf_counter() - t0) * 1000

    io_binding.bind_ortvalue_input(input_name, input_ort)
    for name in output_names:
        io_binding.bind_output(name, 'cuda')

    # 2b. GPU compute
    t0 = time.perf_counter()
    session.run_with_iobinding(io_binding)
    compute_ms = (time.perf_counter() - t0) * 1000

    # 2c. D2H transfer
    t0 = time.perf_counter()
    outputs = io_binding.copy_outputs_to_cpu()
    d2h_ms = (time.perf_counter() - t0) * 1000

    # 3. Postprocess (CPU)
    # YOLOX.__call__ does self.inference(image)[0] before postprocess
    t0 = time.perf_counter()
    bboxes = det_model.postprocess(outputs[0], ratio)
    postprocess_ms = (time.perf_counter() - t0) * 1000

    return {
        'preprocess': preprocess_ms,
        'h2d': h2d_ms,
        'compute': compute_ms,
        'd2h': d2h_ms,
        'postprocess': postprocess_ms,
        'total': preprocess_ms + h2d_ms + compute_ms + d2h_ms + postprocess_ms,
    }, bboxes


def bench_pose_breakdown(pose_model, frame, bboxes):
    """Break down RTMPose into preprocess, transfer+compute, postprocess for all bboxes."""
    if len(bboxes) == 0:
        return {'preprocess': 0, 'h2d': 0, 'compute': 0, 'd2h': 0, 'postprocess': 0, 'total': 0, 'n_persons': 0}

    session = pose_model.session
    input_name = session.get_inputs()[0].name
    output_names = [o.name for o in session.get_outputs()]

    total_preprocess = 0
    total_h2d = 0
    total_compute = 0
    total_d2h = 0
    total_postprocess = 0

    for bbox in bboxes:
        # 1. Preprocess (CPU): warpAffine + normalize
        t0 = time.perf_counter()
        resized_img, center, scale = pose_model.preprocess(frame, bbox)
        img_chw = resized_img.transpose(2, 0, 1)
        input_tensor = np.ascontiguousarray(img_chw, dtype=np.float32)[None, :, :, :]
        total_preprocess += (time.perf_counter() - t0) * 1000

        # 2a. H2D transfer
        io_binding = session.io_binding()
        t0 = time.perf_counter()
        input_ort = ort.OrtValue.ortvalue_from_numpy(input_tensor, 'cuda', 0)
        total_h2d += (time.perf_counter() - t0) * 1000

        io_binding.bind_ortvalue_input(input_name, input_ort)
        for name in output_names:
            io_binding.bind_output(name, 'cuda')

        # 2b. GPU compute
        t0 = time.perf_counter()
        session.run_with_iobinding(io_binding)
        total_compute += (time.perf_counter() - t0) * 1000

        # 2c. D2H transfer
        t0 = time.perf_counter()
        outputs = io_binding.copy_outputs_to_cpu()
        total_d2h += (time.perf_counter() - t0) * 1000

        # 3. Postprocess (CPU)
        t0 = time.perf_counter()
        _ = pose_model.postprocess(outputs, center, scale)
        total_postprocess += (time.perf_counter() - t0) * 1000

    return {
        'preprocess': total_preprocess,
        'h2d': total_h2d,
        'compute': total_compute,
        'd2h': total_d2h,
        'postprocess': total_postprocess,
        'total': total_preprocess + total_h2d + total_compute + total_d2h + total_postprocess,
        'n_persons': len(bboxes),
    }


def print_results(label, records):
    """Print average breakdown for a list of per-frame timing dicts."""
    keys = ['preprocess', 'h2d', 'compute', 'd2h', 'postprocess', 'total']
    n = len(records)
    print(f"\n{label} ({n} frames)")
    print(f"  {'Stage':<14} {'Avg (ms)':>10} {'Median':>10} {'Min':>10} {'Max':>10} {'% of total':>10}")
    print(f"  {'-'*14} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
    avg_total = np.mean([r['total'] for r in records])
    for key in keys:
        vals = [r[key] for r in records]
        pct = (np.mean(vals) / avg_total * 100) if avg_total > 0 else 0
        marker = " <--" if key != 'total' and pct > 30 else ""
        print(f"  {key:<14} {np.mean(vals):>10.2f} {np.median(vals):>10.2f} "
              f"{np.min(vals):>10.2f} {np.max(vals):>10.2f} {pct:>9.1f}%{marker}")
    if 'n_persons' in records[0]:
        avg_persons = np.mean([r['n_persons'] for r in records])
        print(f"  Avg persons detected: {avg_persons:.1f}")


def main():
    if not os.path.isfile(VIDEO_PATH):
        print(f"ERROR: VIDEO_PATH not found: {VIDEO_PATH}")
        return

    cap = cv2.VideoCapture(VIDEO_PATH)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = round(cap.get(cv2.CAP_PROP_FPS))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Video: {os.path.basename(VIDEO_PATH)}")
    print(f"Resolution: {w}x{h} @ {fps}fps, {total} frames")

    for mode_name in ['performance', 'balanced']:
        print(f"\n{'='*60}")
        print(f"MODE: {mode_name}")
        print(f"{'='*60}")

        pose_model, ModelClass, mode = setup_model_class_mode('HALPE_26', mode_name)
        pose_tracker = setup_pose_tracker(ModelClass, det_frequency=1, mode=mode_name,
                                           tracking=False, backend='onnxruntime', device='cuda')

        det = pose_tracker.det_model
        pose = pose_tracker.pose_model

        # Warmup
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        for _ in range(WARMUP_FRAMES):
            ok, frame = cap.read()
            if ok:
                pose_tracker(frame)

        # Benchmark
        cap.set(cv2.CAP_PROP_POS_FRAMES, WARMUP_FRAMES)
        det_records = []
        pose_records = []

        for i in range(MAX_FRAMES):
            ok, frame = cap.read()
            if not ok:
                break

            det_timing, bboxes = bench_det_breakdown(det, frame)
            det_records.append(det_timing)

            pose_timing = bench_pose_breakdown(pose, frame, bboxes)
            pose_records.append(pose_timing)

        print_results(f"YOLOX Detection ({mode_name})", det_records)
        print_results(f"RTMPose ({mode_name})", pose_records)

        # Combined
        combined = []
        for d, p in zip(det_records, pose_records):
            combined.append({
                'preprocess': d['preprocess'] + p['preprocess'],
                'h2d': d['h2d'] + p['h2d'],
                'compute': d['compute'] + p['compute'],
                'd2h': d['d2h'] + p['d2h'],
                'postprocess': d['postprocess'] + p['postprocess'],
                'total': d['total'] + p['total'],
            })
        print_results(f"Combined pipeline ({mode_name})", combined)

    cap.release()


if __name__ == "__main__":
    main()
