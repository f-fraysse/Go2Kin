"""
Audio-based multi-camera video synchronisation.

Extracts audio from GoPro MP4 files, uses full cross-correlation
to find time offsets, and trims videos to sync.

Requires: ffmpeg (in PATH), numpy, scipy
"""

import io
import math
import subprocess
import wave
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from scipy.signal import correlate


SAMPLE_RATE = 48000  # GoPro native AAC rate
AUDIO_DURATION = 3.0  # seconds to analyse for cross-correlation sync


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


def detect_clap(audio: np.ndarray, sample_rate: int,
                threshold_factor: float = 3.0) -> Optional[int]:
    """
    Detect a hand clap transient in the audio signal.

    Returns sample index of the clap peak, or None if no clap found.
    Algorithm: envelope smoothing → threshold at N× background median → peak refinement.
    """
    # Compute envelope
    envelope = np.abs(audio)

    # Smooth with ~10ms rolling window
    window_size = int(sample_rate * 0.01)  # 480 samples at 48kHz
    kernel = np.ones(window_size) / window_size
    smoothed = np.convolve(envelope, kernel, mode="same")

    # Background noise level (median of smoothed envelope)
    background = np.median(smoothed)
    if background < 1e-6:
        background = 1e-6  # avoid division by zero in silent audio

    # Find first sample exceeding threshold
    threshold = background * threshold_factor
    candidates = np.where(smoothed > threshold)[0]

    if len(candidates) == 0:
        return None

    # Refine: find actual peak within 50ms window after first candidate
    first_hit = candidates[0]
    window_end = min(first_hit + int(sample_rate * 0.05), len(audio))
    peak_offset = np.argmax(np.abs(audio[first_hit:window_end]))

    return int(first_hit + peak_offset)


def find_offset_xcorr(ref_audio: np.ndarray, other_audio: np.ndarray,
                      sample_rate: int) -> tuple:
    """
    Find time offset between two audio signals using full cross-correlation.
    Returns (offset_seconds, peak_correlation) where offset is positive if
    other started recording earlier, and peak_correlation is normalised 0-1.
    """
    corr = correlate(other_audio, ref_audio, mode="full")
    peak_idx = np.argmax(np.abs(corr))
    # In 'full' mode, zero-lag is at index len(ref_audio) - 1
    offset_samples = peak_idx - (len(ref_audio) - 1)
    # Normalised peak correlation (0 to 1)
    norm = np.sqrt(np.sum(ref_audio**2) * np.sum(other_audio**2))
    peak_corr = float(abs(corr[peak_idx]) / max(norm, 1e-10))
    return offset_samples / sample_rate, peak_corr


def save_audio_waveform_plot(audio_data: Dict[str, np.ndarray],
                             sample_rate: int, output_dir: str) -> str:
    """
    Save a waveform plot of each camera's audio to output_dir/synced/audio_waveforms.png.
    Returns path to the saved image.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    synced_dir = Path(output_dir) / "synced"
    synced_dir.mkdir(exist_ok=True)

    n = len(audio_data)
    fig, axes = plt.subplots(n, 1, figsize=(14, 2.5 * n), sharex=True)
    if n == 1:
        axes = [axes]
    fig.suptitle(f"Audio Waveforms - First {AUDIO_DURATION:.0f} Seconds", fontsize=14)

    for i, (vp, audio) in enumerate(audio_data.items()):
        t = np.arange(len(audio)) / sample_rate
        axes[i].plot(t, audio, linewidth=0.3, color="steelblue")
        axes[i].set_ylabel(Path(vp).stem)
        axes[i].set_ylim(-1, 1)
        axes[i].grid(True, alpha=0.3)

    axes[-1].set_xlabel("Time (seconds)")
    plt.tight_layout()
    out_path = synced_dir / "audio_waveforms.png"
    plt.savefig(str(out_path), dpi=150)
    plt.close(fig)
    return str(out_path)


def compute_sync_offsets(video_paths: List[str],
                         output_dir: Optional[str] = None,
                         progress_callback: Optional[Callable] = None
                         ) -> Dict[str, dict]:
    """
    Compute sync offsets for a list of video files using full cross-correlation.

    Returns dict keyed by video path with:
      offset_seconds, is_reference
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)

    # Step 1: Extract audio from all cameras
    audio_data = {}
    for vp in video_paths:
        name = Path(vp).name
        log(f"Extracting audio: {name}")
        audio, sr = extract_audio(vp)
        audio_data[vp] = audio

    # Save waveform plot if output_dir provided
    if output_dir:
        log("Saving audio waveform plot...")
        save_audio_waveform_plot(audio_data, sr, output_dir)
        log("  Created: synced/audio_waveforms.png")

    # Step 2: Cross-correlate all cameras against first (arbitrary reference)
    ref_path = video_paths[0]
    ref_audio = audio_data[ref_path]
    ref_name = Path(ref_path).name
    log(f"Cross-correlating against reference: {ref_name}")

    raw_offsets = {}
    peak_correlations = {}
    for vp in video_paths:
        if vp == ref_path:
            raw_offsets[vp] = 0.0
            peak_correlations[vp] = 1.0
        else:
            offset, peak_corr = find_offset_xcorr(ref_audio, audio_data[vp], sr)
            raw_offsets[vp] = offset
            peak_correlations[vp] = peak_corr
            log(f"  {Path(vp).name}: offset {offset:.4f}s vs reference (correlation: {peak_corr:.3f})")

    # Step 3: Shift so minimum offset = 0 (latest-starting camera becomes reference)
    min_offset = min(raw_offsets.values())
    adjusted = {vp: off - min_offset for vp, off in raw_offsets.items()}

    # Identify the reference (the one with offset 0 after adjustment)
    ref_vp = min(adjusted, key=adjusted.get)
    log(f"Sync reference: {Path(ref_vp).name} (latest start)")

    results = {}
    for vp in video_paths:
        is_ref = (vp == ref_vp)
        results[vp] = {
            "offset_seconds": adjusted[vp],
            "is_reference": is_ref,
            "peak_correlation": peak_correlations[vp],
        }
        if not is_ref:
            log(f"  {Path(vp).name}: trim {adjusted[vp]:.4f}s from start")

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

    # Generate timestamps.csv
    fps = get_frame_rate(output_files[0])
    num_cameras = len(output_files)
    csv_path = synced_dir / "timestamps.csv"
    log(f"Generating timestamps.csv ({min_frames} frames x {num_cameras} cameras, {fps:.2f} fps)...")
    with open(csv_path, "w", newline="") as f:
        f.write("cam_id,frame_time\n")
        for frame_idx in range(min_frames):
            frame_time = frame_idx / fps
            for cam_id in range(1, num_cameras + 1):
                f.write(f"{cam_id},{frame_time:.8f}\n")
    log(f"  Created: timestamps.csv")

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
