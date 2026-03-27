"""
Benchmark: cv2.VideoCapture vs PyNvVideoCodec (NVDEC) video decode
for the pose estimation pipeline.

Usage:
    conda activate Go2Kin
    python tools/bench_decode.py
"""

import os
import sys
import time

# --- CONFIG (edit these) ---
VIDEO_PATH = r"E:\Markerless_Data\tests_home\sessions\weekend_march\dancing\video\synced\dancing_GP1.mp4"  # <-- set to a GoPro MP4
MAX_FRAMES = 200       # number of frames to benchmark (after warmup)
WARMUP_FRAMES = 10     # frames to discard before timing
POSE_MODEL = 'HALPE_26'
MODE = 'balanced'
# ---------------------------

# Ensure CUDA_PATH is set for PyNvVideoCodec
cuda_path = os.environ.get('CUDA_PATH') or os.environ.get('CUDA_PATH_V12_4')
if cuda_path:
    os.environ['CUDA_PATH'] = cuda_path

# Add Pose2Sim to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code', 'pose2sim'))

import ctypes
import cv2
import numpy as np
from Pose2Sim.poseEstimation import setup_pose_tracker, setup_model_class_mode, setup_backend_device


def nv_frame_to_numpy(frame, height, width):
    """Convert a PyNvVideoCodec DecodedFrame (host memory, RGB) to a numpy array."""
    ptr = frame.GetPtrToPlane(0)
    raw = np.ctypeslib.as_array(
        ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint8)),
        shape=(frame.framesize(),)
    )
    return raw.reshape(height, width, 3)


def bench_cv2_decode(video_path, n_frames):
    """Benchmark cv2.VideoCapture decode speed (no inference)."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {video_path}")

    # warmup
    for _ in range(WARMUP_FRAMES):
        cap.read()

    times = []
    for _ in range(n_frames):
        t0 = time.perf_counter()
        ok, frame = cap.read()
        t1 = time.perf_counter()
        if not ok:
            break
        times.append((t1 - t0) * 1000)

    cap.release()
    return times


def bench_pynv_decode(video_path, n_frames, height, width):
    """Benchmark PyNvVideoCodec SimpleDecoder decode speed (no inference)."""
    import PyNvVideoCodec as nvc
    from PyNvVideoCodec.decoders.SimpleDecoder import SimpleDecoder

    decoder = SimpleDecoder(
        video_path,
        gpu_id=0,
        use_device_memory=False,
        output_color_type=nvc.OutputColorType.RGB,
    )

    # Warmup via sequential batch
    decoder.get_batch_frames(WARMUP_FRAMES)

    times = []
    for _ in range(n_frames):
        t0 = time.perf_counter()
        batch = decoder.get_batch_frames(1)
        if not batch:
            break
        rgb = nv_frame_to_numpy(batch[0], height, width)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)

    return times


def bench_with_inference(video_path, n_frames, pose_tracker, height, width):
    """Benchmark decode + inference for both backends."""
    # --- cv2 path ---
    cap = cv2.VideoCapture(video_path)
    for _ in range(WARMUP_FRAMES):
        cap.read()

    cv2_decode_ms, cv2_infer_ms = [], []
    for _ in range(n_frames):
        t0 = time.perf_counter()
        ok, frame = cap.read()
        t1 = time.perf_counter()
        if not ok:
            break
        kp, sc = pose_tracker(frame)
        t2 = time.perf_counter()
        cv2_decode_ms.append((t1 - t0) * 1000)
        cv2_infer_ms.append((t2 - t1) * 1000)

    cap.release()
    n_cv2 = len(cv2_decode_ms)

    # --- PyNvVideoCodec path ---
    import PyNvVideoCodec as nvc
    from PyNvVideoCodec.decoders.SimpleDecoder import SimpleDecoder

    decoder = SimpleDecoder(
        video_path,
        gpu_id=0,
        use_device_memory=False,
        output_color_type=nvc.OutputColorType.RGB,
    )

    # Warmup via sequential batch
    decoder.get_batch_frames(WARMUP_FRAMES)

    nv_decode_ms, nv_infer_ms = [], []
    for _ in range(n_frames):
        t0 = time.perf_counter()
        batch = decoder.get_batch_frames(1)
        if not batch:
            break
        rgb = nv_frame_to_numpy(batch[0], height, width)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        t1 = time.perf_counter()
        kp, sc = pose_tracker(bgr)
        t2 = time.perf_counter()
        nv_decode_ms.append((t1 - t0) * 1000)
        nv_infer_ms.append((t2 - t1) * 1000)

    n_nv = len(nv_decode_ms)
    return (cv2_decode_ms, cv2_infer_ms, n_cv2), (nv_decode_ms, nv_infer_ms, n_nv)


def print_table(header, rows):
    """Simple table printer."""
    col_widths = [max(len(str(row[i])) for row in [header] + rows) for i in range(len(header))]
    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
    print(fmt.format(*header))
    print(fmt.format(*["-" * w for w in col_widths]))
    for row in rows:
        print(fmt.format(*row))


def main():
    if not os.path.isfile(VIDEO_PATH):
        print(f"ERROR: VIDEO_PATH not found: {VIDEO_PATH}")
        print("Edit the VIDEO_PATH variable at the top of this script.")
        return

    # Get video info
    cap = cv2.VideoCapture(VIDEO_PATH)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = round(cap.get(cv2.CAP_PROP_FPS))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    print(f"Video: {os.path.basename(VIDEO_PATH)}")
    print(f"Resolution: {w}x{h} @ {fps}fps, {total} frames")
    print(f"Benchmarking {MAX_FRAMES} frames (after {WARMUP_FRAMES} warmup)\n")

    # --- Decode-only benchmark ---
    print("=" * 60)
    print("DECODE ONLY (no inference)")
    print("=" * 60)

    print("Running cv2.VideoCapture...")
    cv2_times = bench_cv2_decode(VIDEO_PATH, MAX_FRAMES)

    print("Running PyNvVideoCodec...")
    nv_times = bench_pynv_decode(VIDEO_PATH, MAX_FRAMES, h, w)

    print()
    print_table(
        ["Backend", "Frames", "Avg (ms)", "Median (ms)", "Min (ms)", "Max (ms)", "Total (s)"],
        [
            ["cv2", str(len(cv2_times)),
             f"{np.mean(cv2_times):.2f}", f"{np.median(cv2_times):.2f}",
             f"{np.min(cv2_times):.2f}", f"{np.max(cv2_times):.2f}",
             f"{np.sum(cv2_times)/1000:.3f}"],
            ["PyNvVC", str(len(nv_times)),
             f"{np.mean(nv_times):.2f}", f"{np.median(nv_times):.2f}",
             f"{np.min(nv_times):.2f}", f"{np.max(nv_times):.2f}",
             f"{np.sum(nv_times)/1000:.3f}"],
        ]
    )
    speedup = np.mean(cv2_times) / np.mean(nv_times) if np.mean(nv_times) > 0 else 0
    print(f"\nDecode speedup: {speedup:.2f}x")

    # --- Decode + inference benchmark ---
    print()
    print("=" * 60)
    print("DECODE + INFERENCE (full pipeline)")
    print("=" * 60)

    print("Setting up pose tracker...")
    pose_model, ModelClass, mode = setup_model_class_mode(POSE_MODEL, MODE)
    pose_tracker = setup_pose_tracker(ModelClass, det_frequency=1, mode=MODE,
                                       tracking=False, backend='onnxruntime', device='CUDA')

    # Warmup the pose tracker with a few frames
    cap = cv2.VideoCapture(VIDEO_PATH)
    for _ in range(3):
        ok, frame = cap.read()
        if ok:
            pose_tracker(frame)
    cap.release()

    print("Running both backends...")
    (cv2_dec, cv2_inf, n_cv2), (nv_dec, nv_inf, n_nv) = bench_with_inference(
        VIDEO_PATH, MAX_FRAMES, pose_tracker, h, w
    )

    cv2_total = [d + i for d, i in zip(cv2_dec, cv2_inf)]
    nv_total = [d + i for d, i in zip(nv_dec, nv_inf)]

    print()
    print_table(
        ["Backend", "Phase", "Avg (ms)", "Median (ms)", "Min (ms)", "Max (ms)"],
        [
            ["cv2", "decode", f"{np.mean(cv2_dec):.2f}", f"{np.median(cv2_dec):.2f}",
             f"{np.min(cv2_dec):.2f}", f"{np.max(cv2_dec):.2f}"],
            ["cv2", "infer", f"{np.mean(cv2_inf):.2f}", f"{np.median(cv2_inf):.2f}",
             f"{np.min(cv2_inf):.2f}", f"{np.max(cv2_inf):.2f}"],
            ["cv2", "TOTAL", f"{np.mean(cv2_total):.2f}", f"{np.median(cv2_total):.2f}",
             f"{np.min(cv2_total):.2f}", f"{np.max(cv2_total):.2f}"],
            ["", "", "", "", "", ""],
            ["PyNvVC", "decode", f"{np.mean(nv_dec):.2f}", f"{np.median(nv_dec):.2f}",
             f"{np.min(nv_dec):.2f}", f"{np.max(nv_dec):.2f}"],
            ["PyNvVC", "infer", f"{np.mean(nv_inf):.2f}", f"{np.median(nv_inf):.2f}",
             f"{np.min(nv_inf):.2f}", f"{np.max(nv_inf):.2f}"],
            ["PyNvVC", "TOTAL", f"{np.mean(nv_total):.2f}", f"{np.median(nv_total):.2f}",
             f"{np.min(nv_total):.2f}", f"{np.max(nv_total):.2f}"],
        ]
    )

    total_speedup = np.mean(cv2_total) / np.mean(nv_total) if np.mean(nv_total) > 0 else 0
    decode_speedup = np.mean(cv2_dec) / np.mean(nv_dec) if np.mean(nv_dec) > 0 else 0
    print(f"\nDecode speedup: {decode_speedup:.2f}x")
    print(f"End-to-end speedup: {total_speedup:.2f}x")
    print(f"\nWall time cv2:    {np.sum(cv2_total)/1000:.3f}s ({n_cv2} frames)")
    print(f"Wall time PyNvVC: {np.sum(nv_total)/1000:.3f}s ({n_nv} frames)")
    saved = np.sum(cv2_total) - np.sum(nv_total)
    print(f"Time saved:       {saved/1000:.3f}s ({saved/len(cv2_total):.1f}ms/frame)")


if __name__ == "__main__":
    main()
