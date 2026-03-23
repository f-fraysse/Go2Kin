"""
Audio-based multi-camera video synchronisation.

Extracts audio from GoPro MP4 files, detects clap onsets using
Hilbert envelope + derivative threshold crossing, and trims videos to sync.

Requires: ffmpeg (in PATH), numpy, scipy
"""

import io
import math
import subprocess
import wave
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from scipy.signal import hilbert


SAMPLE_RATE = 48000  # GoPro native AAC rate
AUDIO_DURATION = 3.0  # seconds to analyse for onset detection
SMOOTHING_WINDOW = 240  # 5 ms at 48 kHz
CLAP_COOLDOWN_SECONDS = 0.3  # minimum gap between claps
PEAK_HEIGHT_FACTOR = 0.2  # threshold = 20% of max derivative


class AudioSyncError(Exception):
    """Custom exception for audio sync failures."""
    pass


def check_ffmpeg(ffmpeg_path: str = "ffmpeg") -> bool:
    """Verify ffmpeg is available."""
    try:
        result = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_audio_track(video_path: str, ffprobe_path: str = "ffprobe") -> bool:
    """Check whether a video file contains an audio track."""
    result = subprocess.run(
        [ffprobe_path, "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", video_path],
        capture_output=True, text=True, timeout=10
    )
    return "audio" in result.stdout


def get_video_duration(video_path: str, ffprobe_path: str = "ffprobe") -> float:
    """Get video duration in seconds using ffprobe."""
    result = subprocess.run(
        [ffprobe_path, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", video_path],
        capture_output=True, text=True, timeout=10
    )
    return float(result.stdout.strip())


def get_frame_count(video_path: str, ffprobe_path: str = "ffprobe") -> int:
    """Count video frames using ffprobe container metadata."""
    result = subprocess.run(
        [ffprobe_path, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=nb_frames", "-of", "csv=p=0", video_path],
        capture_output=True, text=True, timeout=30
    )
    count_str = result.stdout.strip()
    if result.returncode != 0 or not count_str or count_str == "N/A":
        # Fallback: decode-count (slower but always accurate)
        result = subprocess.run(
            [ffprobe_path, "-v", "error", "-count_frames",
             "-select_streams", "v:0",
             "-show_entries", "stream=nb_read_frames",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, timeout=120
        )
        count_str = result.stdout.strip()
    if not count_str:
        raise AudioSyncError(
            f"Failed to count frames in {Path(video_path).name}"
        )
    return int(count_str)


def get_frame_rate(video_path: str, ffprobe_path: str = "ffprobe") -> float:
    """Get video frame rate using ffprobe."""
    result = subprocess.run(
        [ffprobe_path, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", video_path],
        capture_output=True, text=True, timeout=10
    )
    # r_frame_rate returns as fraction e.g. "50/1"
    rate_str = result.stdout.strip()
    if "/" in rate_str:
        num, den = rate_str.split("/")
        return float(num) / float(den)
    return float(rate_str)


def extract_audio(video_path: str, duration: float = AUDIO_DURATION,
                  ffmpeg_path: str = "ffmpeg") -> Tuple[np.ndarray, int]:
    """
    Extract first `duration` seconds of audio as mono float32 numpy array.
    Uses ffmpeg pipe to avoid temp files.
    Returns (samples_array, sample_rate).
    """
    proc = subprocess.run(
        [ffmpeg_path, "-i", video_path, "-t", str(duration),
         "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "wav", "-"],
        capture_output=True, timeout=30
    )
    if proc.returncode != 0:
        raise AudioSyncError(
            f"Failed to extract audio from {Path(video_path).name}: "
            f"{proc.stderr.decode(errors='replace')[-200:]}"
        )

    wav_data = io.BytesIO(proc.stdout)
    with wave.open(wav_data, "rb") as wf:
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
        # 16-bit PCM → float32 normalised to [-1, 1]
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    return samples, SAMPLE_RATE


# ──────────────────────────────────────────────
# Onset detection algorithm
# ──────────────────────────────────────────────

def compute_envelope(audio: np.ndarray,
                     smoothing_window: int = SMOOTHING_WINDOW) -> np.ndarray:
    """Hilbert envelope with moving-average smoothing."""
    analytic = hilbert(audio)
    env = np.abs(analytic)
    kernel = np.ones(smoothing_window) / smoothing_window
    return np.convolve(env, kernel, mode="same")


def compute_derivative(envelope: np.ndarray) -> np.ndarray:
    """First derivative of envelope, clipped to positive only (rising edges)."""
    deriv = np.concatenate(([0], np.diff(envelope)))
    return np.maximum(deriv, 0)


def detect_onsets(derivative: np.ndarray, sample_rate: int,
                  peak_height_factor: float = PEAK_HEIGHT_FACTOR,
                  clap_cooldown_seconds: float = CLAP_COOLDOWN_SECONDS
                  ) -> Tuple[int, Optional[int]]:
    """
    Detect one or two clap onsets via threshold crossing on the derivative.

    Returns (clap1_sample_idx, clap2_sample_idx_or_None).
    Raises AudioSyncError if no clap found.
    """
    threshold = peak_height_factor * derivative.max()
    cooldown = int(clap_cooldown_seconds * sample_rate)

    # Clap 1: first threshold crossing
    clap1 = None
    for j in range(len(derivative)):
        if derivative[j] > threshold:
            clap1 = j
            break
    if clap1 is None:
        raise AudioSyncError("No clap onset detected — threshold never crossed")

    # Clap 2: first threshold crossing after cooldown
    clap2 = None
    for j in range(clap1 + cooldown, len(derivative)):
        if derivative[j] > threshold:
            clap2 = j
            break

    return clap1, clap2


def save_onset_plot(audio_tracks: List[np.ndarray],
                    envelopes: List[np.ndarray],
                    onsets: List[Tuple[int, Optional[int]]],
                    filenames: List[str],
                    sample_rate: int,
                    output_path: str) -> str:
    """
    Save onset detection summary plot (raw waveform + envelope + onset markers).
    Cropped to 0.3s before first clap to 0.3s after last clap.
    Returns path to saved image.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n_cams = len(audio_tracks)

    # Compute crop bounds across all tracks
    all_clap1 = [o[0] for o in onsets]
    all_clap2 = [o[1] for o in onsets if o[1] is not None]
    earliest = min(all_clap1)
    latest = max(all_clap2) if all_clap2 else max(all_clap1)

    crop_start = max(0, earliest - int(0.3 * sample_rate))
    crop_end = min(max(len(a) for a in audio_tracks),
                   latest + int(0.3 * sample_rate))

    fig, axes = plt.subplots(n_cams, 1, figsize=(14, 2.5 * n_cams), sharex=True)
    if n_cams == 1:
        axes = [axes]

    for i in range(n_cams):
        audio = audio_tracks[i]
        env = envelopes[i]
        t = np.arange(len(audio)) / sample_rate

        axes[i].plot(t, audio, linewidth=0.3, color="grey", alpha=0.3)
        axes[i].plot(t[:len(env)], env, linewidth=1.5, color="tab:blue")

        c1, c2 = onsets[i]
        axes[i].axvline(c1 / sample_rate, color="red", linestyle="--", label="Clap 1")
        if c2 is not None:
            axes[i].axvline(c2 / sample_rate, color="blue", linestyle="--", label="Clap 2")

        axes[i].set_title(filenames[i])
        axes[i].set_ylabel("Envelope")
        axes[i].legend(loc="upper right", fontsize=8)

    axes[-1].set_xlabel("Time (s)")
    axes[0].set_xlim(crop_start / sample_rate, crop_end / sample_rate)
    fig.suptitle("Detected Clap Onsets")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def compute_sync_offsets(video_paths: List[str],
                         output_dir: Optional[str] = None,
                         progress_callback: Optional[Callable] = None
                         ) -> Dict[str, dict]:
    """
    Compute sync offsets using envelope onset detection (dual-clap with
    consistency check). FPS read from first video via ffprobe.

    Returns dict keyed by video path with:
      offset_seconds, is_reference, status
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)

    n_cams = len(video_paths)
    filenames = [Path(vp).name for vp in video_paths]

    # Get FPS from first video
    fps = get_frame_rate(video_paths[0])
    log(f"Video FPS: {fps:.0f}")

    # ── Step 0: Load audio ──
    log("=" * 60)
    log("Step 0: Load audio")
    log("=" * 60)

    audio_tracks = []
    for i, vp in enumerate(video_paths):
        audio, sr = extract_audio(vp)
        audio_tracks.append(audio)
        log(f"  {filenames[i]}: {len(audio)} samples, {len(audio)/sr:.2f}s")

    # ── Step 1: Compute envelope ──
    log("")
    log("=" * 60)
    log("Step 1: Compute envelope")
    log("=" * 60)

    envelopes = []
    for i, audio in enumerate(audio_tracks):
        env = compute_envelope(audio)
        envelopes.append(env)
        log(f"  {filenames[i]}: envelope max = {env.max():.4f}")

    # ── Step 2: First derivative ──
    log("")
    log("=" * 60)
    log("Step 2: First derivative of envelope")
    log("=" * 60)

    derivatives = []
    for i, env in enumerate(envelopes):
        deriv = compute_derivative(env)
        derivatives.append(deriv)
        log(f"  {filenames[i]}: derivative max = {deriv.max():.6f}")

    # ── Step 3: Detect clap onsets ──
    log("")
    log("=" * 60)
    log("Step 3: Detect clap onsets")
    log("=" * 60)

    onsets = []
    for i, deriv in enumerate(derivatives):
        try:
            c1, c2 = detect_onsets(deriv, sr)
        except AudioSyncError:
            raise AudioSyncError(
                f"{filenames[i]}: no clap onset detected — "
                f"ensure a clear clap is audible in the first {AUDIO_DURATION:.0f} seconds"
            )
        onsets.append((c1, c2))
        t1 = c1 / sr
        if c2 is not None:
            t2_str = f"{c2 / sr:.4f}s (sample {c2})"
        else:
            t2_str = "N/A"
            log(f"  WARNING: {filenames[i]} — clap 2 not found, single-clap fallback")
        log(f"  {filenames[i]}: clap1 = {t1:.4f}s (sample {c1}), clap2 = {t2_str}")

    # ── Step 4: Compute offsets from onset times ──
    log("")
    log("=" * 60)
    log("Step 4: Compute offsets from onset times")
    log("=" * 60)

    # Determine available claps
    available_claps = [0]
    if all(o[1] is not None for o in onsets):
        available_claps.append(1)
    else:
        log("  WARNING: Not all cameras have 2 claps — single-clap mode")

    # Per clap: ref = camera with earliest onset
    offsets_by_clap = {i: {} for i in range(n_cams)}
    ref_cams = {}

    for c in available_claps:
        clap_indices = [o[c] for o in onsets]
        ref = int(np.argmin(clap_indices))
        ref_cams[c] = ref
        log(f"  Clap {c+1} reference: {filenames[ref]} (onset at sample {onsets[ref][c]})")

        for cam in range(n_cams):
            offset_samples = onsets[cam][c] - onsets[ref][c]
            offset_ms = offset_samples / (sr / 1000.0)
            offset_frames = offset_ms / (1000.0 / fps)
            offsets_by_clap[cam][c] = {
                "offset_samples": offset_samples,
                "offset_ms": offset_ms,
                "offset_frames": offset_frames,
            }
            if cam != ref:
                log(f"    {filenames[cam]}: {offset_samples:+d} samples = "
                    f"{offset_ms:+.3f} ms = {offset_frames:+.3f} frames@{fps:.0f}fps")

    # ── Step 5: Consistency check ──
    log("")
    log("=" * 60)
    log("Step 5: Consistency check")
    log("=" * 60)

    consistency_threshold_ms = 1000.0 / fps  # 1 frame
    log(f"  Threshold: {consistency_threshold_ms:.1f} ms (1 frame at {fps:.0f} fps)")

    ref_cam = ref_cams[0]
    final_offsets = {}

    for cam in range(n_cams):
        if cam == ref_cam:
            final_offsets[cam] = {"offset_ms": 0.0, "offset_frames": 0.0, "status": "REF"}
            continue

        o1 = offsets_by_clap[cam][0]["offset_ms"]
        if len(available_claps) == 2:
            o2 = offsets_by_clap[cam][1]["offset_ms"]
            diff_ms = abs(o1 - o2)
            status = "PASS" if diff_ms <= consistency_threshold_ms else "WARN"
            if status == "WARN":
                log(f"  WARNING: {filenames[cam]} — clap1={o1:+.3f}ms, clap2={o2:+.3f}ms, "
                    f"diff={diff_ms:.3f}ms > {consistency_threshold_ms:.1f}ms")
            log(f"  {filenames[cam]}: clap1={o1:+.3f}ms, clap2={o2:+.3f}ms, "
                f"diff={diff_ms:.3f}ms -> {status}, final={o1:+.3f}ms")
        else:
            status = "PASS (1 clap)"
            log(f"  {filenames[cam]}: single clap offset = {o1:+.3f} ms")

        final_offsets[cam] = {
            "offset_ms": o1,
            "offset_frames": o1 / (1000.0 / fps),
            "status": status,
        }

    # ── Summary table ──
    log("")
    log("=" * 60)
    log("Summary")
    log("=" * 60)

    header = (f"{'Camera':<30} | {'Clap1 Lag(ms)':>13} | {'Clap2 Lag(ms)':>13} | "
              f"{'Diff(ms)':>9} | {'Status':>12} | {'Final Lag(ms)':>14} | {'Final(frames)':>14}")
    log(header)
    log("-" * len(header))

    for cam in range(n_cams):
        name = filenames[cam]
        if cam == ref_cam:
            name += "*"

        o1 = offsets_by_clap[cam][0]["offset_ms"]
        if len(available_claps) == 2:
            o2 = offsets_by_clap[cam][1]["offset_ms"]
            diff = abs(o1 - o2)
            o2_str = f"{o2:+.3f}"
            diff_str = f"{diff:.3f}"
        else:
            o2_str = "--"
            diff_str = "--"

        fo = final_offsets[cam]
        row = (f"{name:<30} | {o1:>+13.3f} | {o2_str:>13} | "
               f"{diff_str:>9} | {fo['status']:>12} | {fo['offset_ms']:>+14.3f} | "
               f"{fo['offset_frames']:>+14.3f}")
        log(row)

    log(f"\n(* = reference camera, clap 1 used for final offset)")
    log(f"FPS for frame conversion: {fps:.0f}")

    # Save onset plot
    if output_dir:
        synced_dir = Path(output_dir) / "synced"
        synced_dir.mkdir(exist_ok=True)
        plot_path = str(synced_dir / "sync_onsets.png")
        log("Saving onset plot...")
        save_onset_plot(audio_tracks, envelopes, onsets, filenames, sr, plot_path)
        log(f"  Created: synced/sync_onsets.png")

    # Build return dict keyed by video path
    # Convert clap1-based offsets to seconds for trimming
    results = {}
    for cam, vp in enumerate(video_paths):
        fo = final_offsets[cam]
        is_ref = (cam == ref_cam)
        offset_seconds = fo["offset_ms"] / 1000.0
        results[vp] = {
            "offset_seconds": offset_seconds,
            "is_reference": is_ref,
            "status": fo["status"],
        }

    return results


def trim_and_sync_videos(video_paths: List[str], offsets: Dict[str, dict],
                         output_dir: str, ffmpeg_path: str = "ffmpeg",
                         progress_callback: Optional[Callable] = None
                         ) -> List[str]:
    """
    Trim videos: align starts (by offset) and trim ends (to shortest common duration).
    Uses ffmpeg stream copy (no re-encoding).
    Returns list of output file paths.
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)

    synced_dir = Path(output_dir) / "synced"
    synced_dir.mkdir(exist_ok=True)

    # Compute common duration (shortest remaining after start trim)
    remaining_durations = []
    for vp in video_paths:
        total = get_video_duration(vp)
        offset = offsets[vp]["offset_seconds"]
        remaining = total - offset
        remaining_durations.append(remaining)
        log(f"  {Path(vp).name}: total={total:.2f}s, offset={offset:.4f}s, remaining={remaining:.2f}s")

    common_duration = min(remaining_durations)
    log(f"Common duration: {common_duration:.2f}s")

    # Trim each video
    output_files = []
    for vp in video_paths:
        info = offsets[vp]
        out_path = synced_dir / Path(vp).name
        offset = info["offset_seconds"]

        cmd = [
            ffmpeg_path, "-y",
            "-ss", f"{offset:.6f}",
            "-i", vp,
            "-t", f"{common_duration:.6f}",
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            str(out_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise AudioSyncError(
                f"ffmpeg trim failed for {Path(vp).name}: {result.stderr[-300:]}"
            )

        ref_marker = " (reference)" if info["is_reference"] else ""
        log(f"  Created: {Path(vp).name}{ref_marker}")
        output_files.append(str(out_path))

    # Frame equalization: ensure all files have identical frame counts
    log("Verifying frame counts...")
    frame_counts = {}
    for out_path in output_files:
        count = get_frame_count(out_path)
        frame_counts[out_path] = count
        log(f"  {Path(out_path).name}: {count} frames")

    min_frames = min(frame_counts.values())
    max_frames = max(frame_counts.values())

    if min_frames != max_frames:
        log(f"Frame mismatch ({min_frames}-{max_frames}), equalising to {min_frames} frames...")
        for out_path in output_files:
            if frame_counts[out_path] > min_frames:
                temp_path = Path(out_path).with_suffix(".tmp.mp4")
                cmd = [
                    ffmpeg_path, "-y",
                    "-i", out_path,
                    "-frames:v", str(min_frames),
                    "-c", "copy",
                    str(temp_path)
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    raise AudioSyncError(
                        f"Frame equalization failed for {Path(out_path).name}: "
                        f"{result.stderr[-300:]}"
                    )
                Path(out_path).unlink()
                temp_path.rename(out_path)
                log(f"  {Path(out_path).name}: trimmed {frame_counts[out_path]} -> {min_frames}")
    else:
        log(f"All files have {min_frames} frames")

    return output_files


def create_stitched_preview(synced_dir: str, ffmpeg_path: str = "ffmpeg",
                            progress_callback: Optional[Callable] = None) -> str:
    """
    Create a grid preview video from synced files (2 or more).
    Each input is downscaled to 480x480, arranged in an auto-sized grid.
    Returns path to the stitched file.
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)

    synced_path = Path(synced_dir)
    mp4_files = sorted(
        f for f in synced_path.glob("*.mp4")
        if f.name.lower() != "stitched_videos.mp4"
    )

    if len(mp4_files) < 2:
        raise AudioSyncError(
            f"Need at least 2 synced files for stitching, found {len(mp4_files)}"
        )

    output_path = synced_path / "stitched_videos.mp4"
    n = len(mp4_files)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    cell_size = 480
    log(f"Creating {cols}x{rows} stitched preview ({n} files)...")

    # Build ffmpeg command with xstack filter
    cmd = [ffmpeg_path, "-y"]
    for f in mp4_files:
        cmd.extend(["-i", str(f)])
    # Add black filler inputs for empty grid cells
    pad_count = cols * rows - n
    for _ in range(pad_count):
        cmd.extend(["-f", "lavfi", "-i",
                     f"color=black:s={cell_size}x{cell_size}:d=1"])

    total_inputs = n + pad_count
    # Scale real inputs, build xstack layout
    parts = []
    for i in range(n):
        parts.append(f"[{i}:v]scale={cell_size}:{cell_size}[v{i}]")
    for i in range(n, total_inputs):
        parts.append(f"[{i}:v]copy[v{i}]")

    stack_inputs = "".join(f"[v{i}]" for i in range(total_inputs))
    layout_parts = []
    for i in range(total_inputs):
        r, c = divmod(i, cols)
        layout_parts.append(f"{c * cell_size}_{r * cell_size}")
    layout = "|".join(layout_parts)

    parts.append(f"{stack_inputs}xstack=inputs={total_inputs}:layout={layout}[out]")
    filter_str = ";".join(parts)

    cmd.extend([
        "-filter_complex", filter_str,
        "-map", "[out]",
        "-an",  # no audio needed for preview
        "-c:v", "mpeg4",
        "-q:v", "5",
        str(output_path)
    ])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise AudioSyncError(
            f"ffmpeg stitching failed: {result.stderr[-300:]}"
        )

    log(f"  Created: stitched_videos.mp4")
    return str(output_path)
