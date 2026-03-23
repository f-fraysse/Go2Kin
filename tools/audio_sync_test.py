"""
Audio Sync Test Script
Develops and validates envelope-based dual-clap multi-camera synchronisation.
See docs/audio_sync_spec.md for full specification.
"""

import subprocess
import tempfile
import shutil
import os
import sys
import numpy as np
import scipy.io.wavfile as wavfile
from scipy.signal import hilbert
import matplotlib.pyplot as plt
from pathlib import Path

# === CONFIGURE THESE ===
VIDEO_DIR = Path(r"D:\Markerless_Projects\tests_Francois\sessions\test_full_pipeline\audio_sync_soft\video")
VIDEO_FILES = [
    VIDEO_DIR / "audio_sync_soft_GP1.MP4",
    VIDEO_DIR / "audio_sync_soft_GP2.MP4",
    VIDEO_DIR / "audio_sync_soft_GP3.MP4",
    VIDEO_DIR / "audio_sync_soft_GP4.MP4",
]
SAMPLE_RATE = 48000
FPS = 100
FFMPEG = r"D:\Miniconda3\envs\Go2Kin\Library\bin\ffmpeg"
SCRIPT_DIR = Path(__file__).parent
SMOOTHING_WINDOW = 240  # 5 ms at 48 kHz
CLAP_COOLDOWN = int(0.4 * SAMPLE_RATE)  # 0.4s between claps
PEAK_HEIGHT_FACTOR = 0.3


def extract_audio_to_wav(video_path, output_wav):
    """Extract mono 16-bit PCM WAV at 48 kHz from MP4."""
    cmd = [
        FFMPEG, "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-acodec", "pcm_s16le", str(output_wav),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ffmpeg error for {video_path}:\n{result.stderr}")
        sys.exit(1)


def load_audio(wav_path):
    """Load WAV, normalise to float64 [-1, 1]. Assert sample rate."""
    sr, data = wavfile.read(wav_path)
    assert sr == SAMPLE_RATE, f"Expected {SAMPLE_RATE} Hz, got {sr} Hz"
    return data.astype(np.float64) / 32768.0


def save_fig(fig, name):
    fig.savefig(SCRIPT_DIR / name, dpi=150)
    print(f"  Saved {name}")


# ──────────────────────────────────────────────
# Step 0: Load audio
# ──────────────────────────────────────────────
print("=" * 60)
print("Step 0: Load audio")
print("=" * 60)

tmp_dir = tempfile.mkdtemp(prefix="audio_sync_")
audio_tracks = []
filenames = []

for vf in VIDEO_FILES:
    assert vf.exists(), f"File not found: {vf}"
    wav_path = os.path.join(tmp_dir, vf.stem + ".wav")
    if str(vf).lower().endswith(".wav"):
        wav_path = str(vf)
    else:
        extract_audio_to_wav(vf, wav_path)
    audio = load_audio(wav_path)
    audio_tracks.append(audio)
    filenames.append(vf.name)
    print(f"  {vf.name}: {len(audio)} samples, {len(audio)/SAMPLE_RATE:.2f}s")

n_cams = len(audio_tracks)

# Plot 1: Raw waveforms
fig1, axes1 = plt.subplots(n_cams, 1, figsize=(14, 8), sharex=True)
for i, (audio, name) in enumerate(zip(audio_tracks, filenames)):
    t = np.arange(len(audio)) / SAMPLE_RATE
    axes1[i].plot(t, audio, linewidth=0.3)
    axes1[i].set_title(name)
    axes1[i].set_ylabel("Amplitude")
axes1[-1].set_xlabel("Time (s)")
fig1.suptitle("Step 0: Raw Waveforms")
plt.tight_layout()
save_fig(fig1, "sync_step_0.png")

# ──────────────────────────────────────────────
# Step 1: Compute envelope
# ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("Step 1: Compute envelope")
print("=" * 60)

envelopes = []
kernel = np.ones(SMOOTHING_WINDOW) / SMOOTHING_WINDOW
for i, audio in enumerate(audio_tracks):
    analytic = hilbert(audio)
    env = np.abs(analytic)
    env_smooth = np.convolve(env, kernel, mode="same")
    envelopes.append(env_smooth)
    print(f"  {filenames[i]}: envelope max = {env_smooth.max():.4f}")

# Plot 2: Raw waveform + smoothed envelope overlay
fig2, axes2 = plt.subplots(n_cams, 1, figsize=(14, 8), sharex=True)
for i, (env, name) in enumerate(zip(envelopes, filenames)):
    t = np.arange(len(audio_tracks[i])) / SAMPLE_RATE
    axes2[i].plot(t, audio_tracks[i], linewidth=0.3, color="grey", alpha=0.3, label="Raw")
    axes2[i].plot(t[:len(env)], env, linewidth=1.5, color="tab:blue", label="Envelope")
    axes2[i].set_title(name)
    axes2[i].set_ylabel("Amplitude")
    axes2[i].legend(loc="upper right", fontsize=8)
axes2[-1].set_xlabel("Time (s)")
fig2.suptitle("Step 1: Raw Waveform + Smoothed Envelope")
plt.tight_layout()
save_fig(fig2, "sync_step_1.png")

# ──────────────────────────────────────────────
# Step 2: First derivative of envelope
# ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("Step 2: First derivative of envelope")
print("=" * 60)

derivatives = []
for i, env in enumerate(envelopes):
    deriv = np.concatenate(([0], np.diff(env)))
    deriv = np.maximum(deriv, 0)
    derivatives.append(deriv)
    print(f"  {filenames[i]}: derivative max = {deriv.max():.6f}")

# Plot 3: Clipped first derivative
fig3, axes3 = plt.subplots(n_cams, 1, figsize=(14, 8), sharex=True)
for i, (deriv, name) in enumerate(zip(derivatives, filenames)):
    t = np.arange(len(deriv)) / SAMPLE_RATE
    axes3[i].plot(t, deriv, linewidth=0.5)
    axes3[i].set_title(name)
    axes3[i].set_ylabel("Derivative")
axes3[-1].set_xlabel("Time (s)")
fig3.suptitle("Step 2: Clipped First Derivative")
plt.tight_layout()
save_fig(fig3, "sync_step_2.png")

# ──────────────────────────────────────────────
# Step 3: Detect two clap onsets in each track
# ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("Step 3: Detect clap onsets")
print("=" * 60)

onsets = []  # list of (clap1_idx, clap2_idx) or (clap1_idx, None)
for i, deriv in enumerate(derivatives):
    threshold = PEAK_HEIGHT_FACTOR * deriv.max()

    # Clap 1: first threshold crossing
    clap1 = None
    for j in range(len(deriv)):
        if deriv[j] > threshold:
            clap1 = j
            break
    if clap1 is None:
        print(f"  ERROR: {filenames[i]} — no threshold crossing found!")
        sys.exit(1)

    # Clap 2: first threshold crossing after cooldown
    clap2 = None
    search_start = clap1 + CLAP_COOLDOWN
    for j in range(search_start, len(deriv)):
        if deriv[j] > threshold:
            clap2 = j
            break
    if clap2 is None:
        print(f"  WARNING: {filenames[i]} — clap 2 not found, single-clap fallback")

    onsets.append((clap1, clap2))
    t1 = clap1 / SAMPLE_RATE
    t2_str = f"{clap2 / SAMPLE_RATE:.4f}s (sample {clap2})" if clap2 is not None else "N/A"
    print(f"  {filenames[i]}: clap1 = {t1:.4f}s (sample {clap1}), clap2 = {t2_str}")

# Plot 4: Envelopes with onset markers
fig4, axes4 = plt.subplots(n_cams, 1, figsize=(14, 8), sharex=True)
for i, (env, name) in enumerate(zip(envelopes, filenames)):
    t = np.arange(len(audio_tracks[i])) / SAMPLE_RATE
    axes4[i].plot(t, audio_tracks[i], linewidth=0.3, color="grey", alpha=0.3)
    axes4[i].plot(t[:len(env)], env, linewidth=1.5, color="tab:blue")
    c1, c2 = onsets[i]
    axes4[i].axvline(c1 / SAMPLE_RATE, color="red", linestyle="--", label="Clap 1")
    if c2 is not None:
        axes4[i].axvline(c2 / SAMPLE_RATE, color="blue", linestyle="--", label="Clap 2")
    axes4[i].set_title(name)
    axes4[i].set_ylabel("Envelope")
    axes4[i].legend(loc="upper right", fontsize=8)
axes4[-1].set_xlabel("Time (s)")
fig4.suptitle("Step 3: Detected Clap Onsets")
plt.tight_layout()
save_fig(fig4, "sync_step_3.png")

# ──────────────────────────────────────────────
# Step 4: Compute offsets from onset times
# ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("Step 4: Compute offsets from onset times")
print("=" * 60)

# Determine which claps are available (need all cameras to have clap c)
available_claps = [0]
if all(o[1] is not None for o in onsets):
    available_claps.append(1)
else:
    print("  WARNING: Not all cameras have 2 claps -- single-clap mode")

# Per clap: ref = camera with earliest onset, compute offsets
offsets = {i: {} for i in range(n_cams)}  # {cam: {clap: {offset_samples, offset_ms, offset_frames}}}
ref_cams = {}  # {clap: ref_cam_idx}

for c in available_claps:
    clap_indices = [o[c] for o in onsets]
    ref = int(np.argmin(clap_indices))
    ref_cams[c] = ref
    print(f"  Clap {c+1} reference: {filenames[ref]} (onset at sample {onsets[ref][c]})")

    for cam in range(n_cams):
        offset_samples = onsets[cam][c] - onsets[ref][c]
        offset_ms = offset_samples / 48.0
        offset_frames = offset_ms / (1000.0 / FPS)
        offsets[cam][c] = {
            "offset_samples": offset_samples,
            "offset_ms": offset_ms,
            "offset_frames": offset_frames,
        }
        if cam != ref:
            print(f"    {filenames[cam]}: {offset_samples:+d} samples = {offset_ms:+.3f} ms = {offset_frames:+.3f} frames@{FPS}fps")

# ──────────────────────────────────────────────
# Step 5: Consistency check
# ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("Step 5: Consistency check")
print("=" * 60)

consistency_threshold_ms = 1000.0 / FPS  # 1 frame at target FPS
print(f"  Threshold: {consistency_threshold_ms:.1f} ms (1 frame at {FPS} fps)")

# Use clap 1's reference camera as the overall reference
ref_cam = ref_cams[0]
final_offsets = {}

for cam in range(n_cams):
    if cam == ref_cam:
        final_offsets[cam] = {"offset_ms": 0.0, "offset_frames": 0.0, "status": "REF"}
        continue

    o1 = offsets[cam][0]["offset_ms"]
    if len(available_claps) == 2:
        o2 = offsets[cam][1]["offset_ms"]
        diff_ms = abs(o1 - o2)

        if diff_ms <= consistency_threshold_ms:
            status = "PASS"
        else:
            status = "WARN"
            print(f"  WARNING: {filenames[cam]} -- clap1={o1:+.3f}ms, clap2={o2:+.3f}ms, "
                  f"diff={diff_ms:.3f}ms > {consistency_threshold_ms:.1f}ms")

        # Use clap 1 if both pass, otherwise use whichever is available
        chosen_ms = o1
        print(f"  {filenames[cam]}: clap1={o1:+.3f}ms, clap2={o2:+.3f}ms, "
              f"diff={diff_ms:.3f}ms -> {status}, final={chosen_ms:+.3f}ms")
    else:
        chosen_ms = o1
        status = "PASS (1 clap)"
        print(f"  {filenames[cam]}: single clap offset = {chosen_ms:+.3f} ms")

    final_offsets[cam] = {
        "offset_ms": chosen_ms,
        "offset_frames": chosen_ms / (1000.0 / FPS),
        "status": status,
    }

# ──────────────────────────────────────────────
# Summary table
# ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("Summary")
print("=" * 60)

header = (f"{'Camera':<30} | {'Clap1 Lag(ms)':>13} | {'Clap2 Lag(ms)':>13} | "
          f"{'Diff(ms)':>9} | {'Status':>8} | {'Final Lag(ms)':>14} | {'Final(frames)':>14}")
sep = "-" * len(header)
print(header)
print(sep)

for cam in range(n_cams):
    name = filenames[cam]
    if cam == ref_cam:
        name += "*"

    o1 = offsets[cam][0]["offset_ms"]
    if len(available_claps) == 2:
        o2 = offsets[cam][1]["offset_ms"]
        diff = abs(o1 - o2)
        o2_str = f"{o2:+.3f}"
        diff_str = f"{diff:.3f}"
    else:
        o2_str = "--"
        diff_str = "--"

    fo = final_offsets[cam]
    row = (f"{name:<30} | {o1:>+13.3f} | {o2_str:>13} | "
           f"{diff_str:>9} | {fo['status']:>8} | {fo['offset_ms']:>+14.3f} | {fo['offset_frames']:>+14.3f}")
    print(row)

print(f"\n(* = reference camera, clap 1 used for final offset)")
print(f"FPS for frame conversion: {FPS}")

# Cleanup temp files
shutil.rmtree(tmp_dir, ignore_errors=True)
print(f"\nCleaned up temp directory: {tmp_dir}")

# Show all plots
print("\nDisplaying plots...")
plt.show()
