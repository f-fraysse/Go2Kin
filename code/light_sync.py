"""
Light-based (LED flash) multi-camera video synchronisation.

An LED visible to all cameras is switched on for ~1 s shortly after recording
starts. For each video, ffmpeg decodes only the first few seconds and pipes a
small grayscale crop (the per-camera ROI around the LED) into Python; the LED
on/off edges are located in that 1-D brightness signal and used as sync events.

The result dict has the same contract as audio_sync.compute_sync_offsets
(offset_seconds / is_reference / status / final_offset_ms / offset_frames / fps)
so audio_sync.trim_and_sync_videos and create_stitched_preview are reused as-is.

Requires: ffmpeg + ffprobe (in PATH), numpy. See docs/light_sync_spec.md.
"""

import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from audio_sync import AudioSyncError, StepTimer, get_frame_rate


LIGHT_SEARCH_SECONDS = 6.0      # scan window from recording start
LIGHT_PULSE_SECONDS = 1.0       # LED on-time
PULSE_TOLERANCE_FRAMES = 3      # accepted deviation of measured pulse length
MIN_CONTRAST = 60               # grey levels, peak - baseline
BRIGHT_TOP_PIXELS = 16          # per-frame ROI statistic = mean of the N brightest pixels
LED_ROI_DEFAULT_SIZE = 80       # px, full-res square ROI
BASELINE_FRAMES = 10            # frames used for the LED-off baseline

GP_PATTERN = re.compile(r"_GP(\d+)\.", re.IGNORECASE)

# None = untested, True/False = result of the first -hwaccel cuda attempt.
_hwaccel_cuda_ok: Optional[bool] = None


class LightSyncError(AudioSyncError):
    """LED not detected / ROI missing. Subclass of AudioSyncError so existing
    ``except AudioSyncError`` branches in the GUI keep working."""
    pass


# ──────────────────────────────────────────────
# ffmpeg / ffprobe helpers
# ──────────────────────────────────────────────

def probe_video_size(video_path: str, ffprobe_path: str = "ffprobe") -> Tuple[int, int]:
    """Return (width, height) of the first video stream."""
    result = subprocess.run(
        [ffprobe_path, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", video_path],
        capture_output=True, text=True, timeout=10
    )
    parts = result.stdout.strip().split(",")
    if result.returncode != 0 or len(parts) < 2:
        raise LightSyncError(f"Failed to probe video size of {Path(video_path).name}")
    return int(parts[0]), int(parts[1])


def scale_roi(roi: Tuple[int, int, int, int],
              from_size: Optional[Tuple[int, int]],
              to_size: Tuple[int, int]) -> Tuple[int, int, int, int]:
    """Scale an (x, y, w, h) ROI defined on a from_size frame to a to_size frame
    and clamp it inside the frame. from_size None means "same as to_size"."""
    x, y, w, h = roi
    if from_size is not None and tuple(from_size) != tuple(to_size):
        sx = to_size[0] / from_size[0]
        sy = to_size[1] / from_size[1]
        x, y, w, h = round(x * sx), round(y * sy), round(w * sx), round(h * sy)
    fw, fh = to_size
    w = max(2, min(w, fw))
    h = max(2, min(h, fh))
    x = max(0, min(x, fw - w))
    y = max(0, min(y, fh - h))
    return int(x), int(y), int(w), int(h)


def _run_ffmpeg_pipe(args: List[str], ffmpeg_path: str, timeout: int) -> bytes:
    """Run ffmpeg with the rawvideo pipe args, trying NVDEC (-hwaccel cuda)
    first and falling back to CPU decoding. Returns raw stdout bytes."""
    global _hwaccel_cuda_ok
    base = [ffmpeg_path, "-hide_banner", "-loglevel", "error"]

    if _hwaccel_cuda_ok is not False:
        result = subprocess.run(base + ["-hwaccel", "cuda"] + args,
                                capture_output=True, timeout=timeout)
        if result.returncode == 0 and result.stdout:
            if _hwaccel_cuda_ok is None:
                print("light_sync: using ffmpeg -hwaccel cuda (NVDEC) decode")
            _hwaccel_cuda_ok = True
            return result.stdout
        if _hwaccel_cuda_ok is None:
            print("light_sync: -hwaccel cuda unavailable, falling back to CPU decode")
        _hwaccel_cuda_ok = False

    result = subprocess.run(base + args, capture_output=True, timeout=timeout)
    if result.returncode != 0 or not result.stdout:
        err = result.stderr.decode(errors="replace")[-300:]
        raise LightSyncError(f"ffmpeg decode failed: {err}")
    return result.stdout


def read_roi_signal(video_path: str, roi: Tuple[int, int, int, int],
                    seconds: float = LIGHT_SEARCH_SECONDS,
                    roi_size: Optional[Tuple[int, int]] = None,
                    ffmpeg_path: str = "ffmpeg") -> np.ndarray:
    """Per-frame brightness of the ROI over the first ``seconds`` of the video.

    roi is (x, y, w, h) in pixels of a frame of size roi_size (w, h); if the
    video has a different size the ROI is rescaled. Returns a float array with
    one value per decoded frame: the mean of the BRIGHT_TOP_PIXELS brightest
    pixels of the crop. A fixed pixel count (rather than a percentile or the
    mean) keeps the statistic independent of how large the LED blob is relative
    to the ROI: a 20 px blob in an 80x80 box moves the mean by only a few grey
    levels but its brightest 16 pixels are saturated.
    """
    vid_size = probe_video_size(video_path)
    if roi_size is not None and tuple(roi_size) != vid_size:
        print(f"  {Path(video_path).name}: video {vid_size[0]}x{vid_size[1]} differs from "
              f"ROI reference {roi_size[0]}x{roi_size[1]} — scaling ROI")
    x, y, w, h = scale_roi(roi, roi_size, vid_size)

    args = ["-i", video_path, "-t", f"{seconds:.3f}",
            "-vf", f"crop={w}:{h}:{x}:{y},format=gray",
            "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
    raw = _run_ffmpeg_pipe(args, ffmpeg_path, timeout=120)

    n_frames = len(raw) // (w * h)
    if n_frames == 0:
        raise LightSyncError(f"No frames decoded from {Path(video_path).name}")
    flat = np.frombuffer(raw[:n_frames * w * h], dtype=np.uint8).reshape(n_frames, w * h)
    k = min(BRIGHT_TOP_PIXELS, w * h)
    top = np.partition(flat, w * h - k, axis=1)[:, w * h - k:]
    return top.mean(axis=1).astype(float)


def sample_frames_for_roi(video_path: str, seconds: float = LIGHT_SEARCH_SECONDS,
                          fps_out: float = 4.0, width: int = 960,
                          ffmpeg_path: str = "ffmpeg") -> Tuple[List[np.ndarray], float]:
    """Decode reduced-size RGB frames at fps_out over the first ``seconds`` for the
    ROI-picking dialog. Returns (frames, scale) where scale = full_width / width so
    a click on a sampled frame maps back to full-resolution pixels. Sequential
    decode is deliberate: seeking re-decodes a whole GoPro GOP (~1 s) per seek.
    """
    vw, vh = probe_video_size(video_path)
    out_h = int(round(vh * width / vw))
    out_h -= out_h % 2
    args = ["-i", video_path, "-t", f"{seconds:.3f}",
            "-vf", f"fps={fps_out},scale={width}:{out_h}",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    raw = _run_ffmpeg_pipe(args, ffmpeg_path, timeout=120)

    frame_bytes = width * out_h * 3
    n = len(raw) // frame_bytes
    if n == 0:
        raise LightSyncError(f"No frames decoded from {Path(video_path).name}")
    arr = np.frombuffer(raw[:n * frame_bytes], dtype=np.uint8).reshape(n, out_h, width, 3)
    return [arr[i].copy() for i in range(n)], vw / width


# ──────────────────────────────────────────────
# Pulse detection (pure numpy)
# ──────────────────────────────────────────────

def detect_pulse(signal: np.ndarray, fps: float) -> dict:
    """Locate one LED pulse (off → on → off) in a per-frame brightness signal.

    Returns dict with on_frame / off_frame (first on frame, first off frame after
    it), sub-frame t_on / t_off (in frames, assuming exposure ≈ frame period),
    pulse_frames, contrast, baseline, peak. Raises LightSyncError if no pulse
    is found or it does not look like the LED.
    """
    sig = np.asarray(signal, dtype=float)
    if len(sig) < BASELINE_FRAMES + 2:
        raise LightSyncError(f"Signal too short ({len(sig)} frames)")

    baseline = float(np.median(sig[:BASELINE_FRAMES]))
    peak = float(sig.max())
    contrast = peak - baseline
    if contrast < MIN_CONTRAST:
        raise LightSyncError(
            f"LED not detected in ROI (contrast {contrast:.0f} < {MIN_CONTRAST} grey levels)")

    s = np.clip((sig - baseline) / contrast, 0.0, 1.0)
    above = s >= 0.5
    on = int(np.argmax(above))
    if on == 0:
        raise LightSyncError("LED already on at start of recording")

    below_after = ~above[on:]
    if not below_after.any():
        raise LightSyncError("LED never switches off within the search window")
    off = on + int(np.argmax(below_after))

    # Sub-frame edges: a partially lit frame gives the fraction of the exposure
    # during which the LED was on.
    if s[on] < 0.98:
        t_on = on + 1.0 - s[on]
    else:
        t_on = on - s[on - 1]
    if s[off] > 0.02:
        t_off = off + s[off]
    else:
        t_off = off - 1.0 + s[off - 1]

    pulse_frames = t_off - t_on
    expected = LIGHT_PULSE_SECONDS * fps
    if abs(pulse_frames - expected) > PULSE_TOLERANCE_FRAMES:
        raise LightSyncError(
            f"Brightness pulse of {pulse_frames:.1f} frames does not match the LED "
            f"({expected:.0f} ± {PULSE_TOLERANCE_FRAMES} frames)")

    return {
        "on_frame": on,
        "off_frame": off,
        "t_on": float(t_on),
        "t_off": float(t_off),
        "pulse_frames": float(pulse_frames),
        "contrast": contrast,
        "baseline": baseline,
        "peak": peak,
    }


# ──────────────────────────────────────────────
# ROI lookup
# ──────────────────────────────────────────────

def cam_id_from_filename(video_path: str) -> Optional[int]:
    """Camera number from the '_GP{N}.' filename suffix, or None."""
    m = GP_PATTERN.search(Path(video_path).name)
    return int(m.group(1)) if m else None


def resolve_rois_for_videos(video_paths: List[str],
                            rois_by_cam: Dict[int, dict]) -> Dict[str, dict]:
    """Map each video path to its camera's ROI entry {"roi": (x,y,w,h), "size": (w,h)}.

    rois_by_cam is keyed by camera number (from CalibrationTab.get_led_rois()).
    Raises LightSyncError if a filename has no _GP{N} tag or its camera has no ROI.
    """
    resolved = {}
    for vp in video_paths:
        cam_id = cam_id_from_filename(vp)
        if cam_id is None:
            raise LightSyncError(f"Cannot identify camera from filename: {Path(vp).name}")
        entry = (rois_by_cam or {}).get(cam_id)
        if not entry or not entry.get("roi"):
            raise LightSyncError(
                f"No LED ROI for GP{cam_id} — run 'Record LED clip & set ROI' "
                f"in the Calibration tab first")
        resolved[vp] = {"roi": tuple(entry["roi"]), "size": entry.get("size")}
    return resolved


# ──────────────────────────────────────────────
# Offsets, summary, acceptance
# ──────────────────────────────────────────────

def compute_light_sync_offsets(video_paths: List[str],
                               rois: Dict[str, dict],
                               output_dir: Optional[str] = None,
                               progress_callback: Optional[Callable] = None,
                               timer: Optional[StepTimer] = None,
                               seconds: float = LIGHT_SEARCH_SECONDS,
                               ) -> Dict[str, dict]:
    """Compute per-video sync offsets from the LED on-edge.

    rois: {video_path: {"roi": (x, y, w, h), "size": (w, h) | None}} — see
    resolve_rois_for_videos. Returns a dict keyed by video path compatible with
    audio_sync.trim_and_sync_videos, plus LED diagnostics.
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)

    n_cams = len(video_paths)
    filenames = [Path(vp).name for vp in video_paths]
    fps = get_frame_rate(video_paths[0])
    log(f"FPS: {fps:.0f} — scanning first {seconds:.1f}s for the LED pulse")

    # ── Step 0: decode ROI signals (parallel; ffmpeg releases the GIL) ──
    if timer: timer.mark("Step 0: Decode ROI signals")

    def _read(vp):
        entry = rois[vp]
        return read_roi_signal(vp, entry["roi"], seconds=seconds, roi_size=entry.get("size"))

    with ThreadPoolExecutor(max_workers=n_cams) as ex:
        signals = list(ex.map(_read, video_paths))
    for name, sig in zip(filenames, signals):
        log(f"  {name}: {len(sig)} frames decoded, ROI brightness "
            f"{sig.min():.0f}–{sig.max():.0f}")

    # ── Step 1: detect pulses ──
    if timer: timer.mark("Step 1: Detect pulses")
    pulses = []
    for name, sig in zip(filenames, signals):
        try:
            p = detect_pulse(sig, fps)
        except LightSyncError as e:
            raise LightSyncError(f"{name}: {e}") from None
        pulses.append(p)
        log(f"  {name}: LED on at frame {p['on_frame']} (t_on={p['t_on']:.2f}), "
            f"off at {p['off_frame']}, pulse {p['pulse_frames']:.1f} frames, "
            f"contrast {p['contrast']:.0f}")

    # ── Step 2: offsets vs the earliest camera ──
    if timer: timer.mark("Step 2: Offsets")
    ref = int(np.argmin([p["t_on"] for p in pulses]))
    t_on_ref = pulses[ref]["t_on"]
    t_off_ref = pulses[ref]["t_off"]

    results = {}
    for cam, vp in enumerate(video_paths):
        p = pulses[cam]
        offset_frames = int(round(p["t_on"] - t_on_ref))
        off_offset = int(round(p["t_off"] - t_off_ref))
        on_off_diff = off_offset - offset_frames
        offset_seconds = offset_frames / fps
        if cam == ref:
            status = "REF"
        elif abs(on_off_diff) > 1:
            status = "WARN"
        else:
            status = "PASS"
        results[vp] = {
            "offset_seconds": offset_seconds,
            "is_reference": cam == ref,
            "status": status,
            "final_offset_ms": offset_seconds * 1000.0,
            "offset_frames": offset_frames,
            "fps": fps,
            "on_frame": p["on_frame"],
            "off_frame": p["off_frame"],
            "t_on": p["t_on"],
            "t_off": p["t_off"],
            "pulse_frames": p["pulse_frames"],
            "contrast": p["contrast"],
            "on_off_diff_frames": on_off_diff,
        }

    # ── Summary + plot ──
    if timer: timer.mark("LED plot / summary")
    log("")
    log("=" * 60)
    log("Summary")
    log("=" * 60)
    for line in format_light_sync_summary(results).splitlines():
        log(line)

    if output_dir:
        synced_dir = Path(output_dir) / "synced"
        synced_dir.mkdir(exist_ok=True)
        plot_path = str(synced_dir / "sync_led_signal.png")
        save_led_signal_plot(signals, pulses, filenames, fps, plot_path)
        log(f"  Created: synced/sync_led_signal.png")

    return results


def format_light_sync_summary(results: Dict[str, dict]) -> str:
    """Multi-line camera/offset table (reference marked with '*')."""
    header = (f"{'Camera':<30} | {'On frame':>8} | {'t_on(fr)':>9} | {'Pulse(fr)':>9} | "
              f"{'Contrast':>8} | {'Offset(fr)':>10} | {'Final(ms)':>10} | {'On/Off':>6} | {'Status':>6}")
    lines = [header, "-" * len(header)]
    fps = None
    for vp, info in results.items():
        fps = info.get("fps", fps)
        name = Path(vp).name + ("*" if info.get("is_reference") else "")
        lines.append(
            f"{name:<30} | {info['on_frame']:>8d} | {info['t_on']:>9.2f} | "
            f"{info['pulse_frames']:>9.1f} | {info['contrast']:>8.0f} | "
            f"{info['offset_frames']:>+10d} | {info['final_offset_ms']:>+10.1f} | "
            f"{info['on_off_diff_frames']:>+6d} | {info['status']:>6}")
    lines.append("")
    lines.append("(* = reference camera; On/Off = off-edge offset minus on-edge offset, frames)")
    if fps is not None:
        lines.append(f"FPS for frame conversion: {fps:.0f}")
    return "\n".join(lines)


def evaluate_light_sync_acceptance(results: Dict[str, dict],
                                   max_offset_ms: float = 200.0
                                   ) -> Tuple[bool, List[str]]:
    """Decide whether a light sync is good enough to keep. All must hold:
      1. On- and off-edge offsets agree within 1 frame (non-reference cameras).
      2. No camera's offset vs reference exceeds max_offset_ms.
    (A missing pulse raises LightSyncError in compute_light_sync_offsets.)
    Returns (acceptable, reasons); reasons is empty iff acceptable.
    """
    reasons: List[str] = []
    for vp, info in results.items():
        if info.get("is_reference"):
            continue
        d = info.get("on_off_diff_frames", 0)
        if abs(d) > 1:
            reasons.append(
                f"{Path(vp).name}: LED on/off edges give offsets differing by {d:+d} frames")
    for vp, info in results.items():
        off = info.get("final_offset_ms", 0.0)
        if abs(off) > max_offset_ms:
            reasons.append(
                f"{Path(vp).name}: offset {off:+.1f} ms exceeds {max_offset_ms:.0f} ms limit")
    return (not reasons, reasons)


def save_led_signal_plot(signals: List[np.ndarray], pulses: List[dict],
                         filenames: List[str], fps: float, output_path: str) -> str:
    """One subplot per camera: ROI brightness, 50% threshold, on/off markers."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(signals)
    fig, axes = plt.subplots(n, 1, figsize=(14, 2.5 * n), sharex=True)
    if n == 1:
        axes = [axes]
    for ax, sig, p, name in zip(axes, signals, pulses, filenames):
        frames = np.arange(len(sig))
        ax.plot(frames, sig, linewidth=1.2, color="tab:blue")
        thr = p["baseline"] + 0.5 * p["contrast"]
        ax.axhline(thr, color="grey", linestyle=":", linewidth=1, label="50% threshold")
        ax.axvline(p["t_on"], color="red", linestyle="--", label=f"on {p['t_on']:.2f}")
        ax.axvline(p["t_off"], color="blue", linestyle="--", label=f"off {p['t_off']:.2f}")
        ax.set_title(name)
        ax.set_ylabel("ROI brightness")
        ax.legend(loc="upper right", fontsize=8)
    axes[-1].set_xlabel(f"Frame ({fps:.0f} fps)")
    fig.suptitle("LED sync signal")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path
