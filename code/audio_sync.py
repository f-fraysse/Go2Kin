"""
Audio-based multi-camera video synchronisation.

Extracts audio from GoPro MP4 files, detects hand clap transients,
cross-correlates to find time offsets, and trims videos to sync.

Requires: ffmpeg (in PATH), numpy, scipy
"""

import io
import struct
import subprocess
import wave
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from scipy.signal import correlate


SAMPLE_RATE = 48000  # GoPro native AAC rate
AUDIO_DURATION = 5.0  # seconds to analyse for clap detection


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
                threshold_factor: float = 5.0) -> Optional[int]:
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


def cross_correlate_claps(audio_ref: np.ndarray, audio_other: np.ndarray,
                          clap_ref: int, clap_other: int,
                          sample_rate: int,
                          window_ms: float = 200.0) -> int:
    """
    Find precise sample offset between two audio signals using cross-correlation.
    Returns offset in samples (positive = other's clap is later in its file).
    """
    half_window = int(sample_rate * window_ms / 1000.0 / 2)

    # Extract windows around each clap
    ref_start = max(0, clap_ref - half_window)
    ref_end = min(len(audio_ref), clap_ref + half_window)
    ref_window = audio_ref[ref_start:ref_end]

    other_start = max(0, clap_other - half_window)
    other_end = min(len(audio_other), clap_other + half_window)
    other_window = audio_other[other_start:other_end]

    # Cross-correlate
    corr = correlate(other_window, ref_window, mode="full")
    peak_idx = np.argmax(np.abs(corr))

    # Convert correlation peak index to sample offset
    # In 'full' mode, zero-lag is at index len(ref_window) - 1
    offset_from_corr = peak_idx - (len(ref_window) - 1)

    # Total offset: rough offset from clap positions + fine correction from correlation
    rough_offset = clap_other - clap_ref
    # The correlation offset refines the rough estimate
    fine_offset = (other_start + offset_from_corr) - ref_start

    return fine_offset


def compute_sync_offsets(video_paths: List[str],
                         progress_callback: Optional[Callable] = None
                         ) -> Dict[str, dict]:
    """
    Compute sync offsets for a list of video files.

    Returns dict keyed by video path with:
      clap_sample, clap_time_seconds, offset_seconds, is_reference
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)

    # Step 1: Extract audio and detect claps
    clap_data = {}
    for vp in video_paths:
        name = Path(vp).name
        log(f"Extracting audio: {name}")
        audio, sr = extract_audio(vp)

        log(f"Detecting clap: {name}")
        clap_sample = detect_clap(audio, sr)
        if clap_sample is None:
            raise AudioSyncError(
                f"No clap detected in {name}. "
                f"Ensure a hand clap occurs in the first {AUDIO_DURATION:.0f} seconds."
            )

        clap_time = clap_sample / sr
        log(f"  {name}: clap at {clap_time:.3f}s")
        clap_data[vp] = {
            "audio": audio,
            "clap_sample": clap_sample,
            "clap_time_seconds": clap_time,
        }

    # Step 2: Reference = earliest clap (smallest clap_sample)
    ref_path = min(clap_data, key=lambda p: clap_data[p]["clap_sample"])
    ref_clap = clap_data[ref_path]["clap_sample"]
    ref_name = Path(ref_path).name
    log(f"Reference camera: {ref_name} (earliest clap at {clap_data[ref_path]['clap_time_seconds']:.3f}s)")

    # Step 3: Cross-correlate each non-reference against reference for precision
    ref_audio = clap_data[ref_path]["audio"]
    results = {}

    for vp in video_paths:
        data = clap_data[vp]
        if vp == ref_path:
            results[vp] = {
                "clap_sample": data["clap_sample"],
                "clap_time_seconds": data["clap_time_seconds"],
                "offset_seconds": 0.0,
                "is_reference": True,
            }
        else:
            # Cross-correlate for precise offset
            precise_offset_samples = cross_correlate_claps(
                ref_audio, data["audio"],
                ref_clap, data["clap_sample"],
                sr
            )
            offset_seconds = precise_offset_samples / sr
            # Offset should be positive (other cameras started earlier)
            offset_seconds = max(0.0, offset_seconds)

            results[vp] = {
                "clap_sample": data["clap_sample"],
                "clap_time_seconds": data["clap_time_seconds"],
                "offset_seconds": offset_seconds,
                "is_reference": False,
            }
            log(f"  {Path(vp).name}: trim {offset_seconds:.4f}s from start")

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

    return output_files


def create_stitched_preview(synced_dir: str, ffmpeg_path: str = "ffmpeg",
                            progress_callback: Optional[Callable] = None) -> str:
    """
    Create a 2x2 grid preview video from 4 synced files.
    Each input is downscaled to 480x480, producing a 960x960 output.
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

    if len(mp4_files) != 4:
        raise AudioSyncError(
            f"Expected 4 synced files for stitching, found {len(mp4_files)}"
        )

    output_path = synced_path / "stitched_videos.mp4"
    log("Creating 2x2 stitched preview...")

    # Build ffmpeg command with xstack filter
    # Each input scaled to 480x480, arranged in 2x2 grid
    cmd = [ffmpeg_path, "-y"]
    for f in mp4_files:
        cmd.extend(["-i", str(f)])

    filter_str = (
        "[0:v]scale=480:480[v0];"
        "[1:v]scale=480:480[v1];"
        "[2:v]scale=480:480[v2];"
        "[3:v]scale=480:480[v3];"
        "[v0][v1][v2][v3]xstack=inputs=4:layout=0_0|480_0|0_480|480_480[out]"
    )

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
