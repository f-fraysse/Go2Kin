# Audio Sync Rework Plan

## Background

The current audio sync (`code/audio_sync.py`) uses GCC-PHAT cross-correlation on the first 3 seconds of audio. Offset accuracy is inconsistent — see CLAUDE.md known issues.

A new onset-based algorithm was developed and validated in `tools/audio_sync_test.py`:
- Hilbert envelope + 5ms moving average smoothing
- Clipped first derivative (positive only = rising edges)
- Threshold crossing detection (30% of peak derivative, 0.4s cooldown between claps)
- Dual-clap consistency check (threshold = 1 frame at target FPS)
- Offsets computed directly from onset sample differences (no cross-correlation)

This approach proved more robust and consistent than GCC-PHAT. The plan below describes how to integrate it into Go2Kin and extend it with automatic sync sound playback and speed-of-sound compensation.

## Phase 1: Automatic sync sound playback

### Goal
Eliminate manual clapping by having the computer play two clap sounds through speakers automatically after recording starts.

### Implementation
- **Bottom bar of GUI** (`GUI/main_window.py`): Add a "Sync Sound" checkbox, positioned to the left of the existing "Delay" controls.
- **Behaviour**: When checked, 1 second after recording starts, play two clap sounds through the speakers. The claps should be loud, short transients (e.g. 10ms impulse or a short WAV file) separated by ~0.5 seconds.
- **Trigger points**: Recording tab shutter start, and Calibration tab extrinsic/origin Record buttons — all places where multi-camera recording is initiated.
- **Audio playback**: Use a simple method (e.g. `winsound`, `playsound`, or `sounddevice`) to play the sync sound. Must not block the recording thread.
- **Sync sound file**: Ship a short WAV file in `config/` (or generate programmatically — two sharp impulses).

### Feasibility test
Record a few trials with speaker-generated claps. Run `tools/audio_sync_test.py` on the recordings to verify the onset detection works with speaker audio (which may have different frequency content / attack profile than hand claps).

## Phase 2: Validate with real recordings

Manual step — no code changes needed. Record several trials with the sync sound feature enabled and run `tools/audio_sync_test.py` to confirm onset detection works reliably with speaker-generated claps.

## Phase 3: Speed-of-sound compensation

### Goal
Account for the physical delay between the sync sound leaving the speaker and arriving at each camera's microphone. At 340 m/s, a 3-metre distance introduces ~8.8 ms of delay. If cameras are at different distances from the speaker, this creates a systematic offset that should be subtracted from the measured audio offsets.

### Implementation
- **Calibration tab** (`GUI/calibration_tab.py`): Add a "Set Sound Source Position" section, below or near the Set Origin controls.
  - Three entry fields: X, Y, Z coordinates in metres (in the calibration coordinate system).
  - A button to confirm / update the position.
  - Display the sound source position in the 3D viewer as a thick black cross marker.
- **Persistence**: Save the sound source position in the calibration JSON (alongside camera positions).
- **Offset compensation** (in the sync algorithm):
  1. After computing raw audio offsets (Step 5 of the onset algorithm), load camera positions from calibration and the sound source position.
  2. For each camera, compute the Euclidean distance to the sound source.
  3. Compute the sound travel time: `travel_time_ms = distance_m / 340.0 * 1000.0`
  4. The natural offset for each camera (relative to the reference camera) is: `natural_offset_ms = travel_time_to_cam - travel_time_to_ref`
  5. Subtract the natural offset from the measured audio offset to get the true recording delay: `true_offset_ms = measured_offset_ms - natural_offset_ms`
  6. Print both raw and compensated offsets for transparency.

### Notes
- Speed of sound assumed constant at 340 m/s (room temperature). Could make configurable but not worth it initially.
- Requires a completed calibration (camera positions known) and a known sound source position. If either is missing, skip compensation and use raw offsets with a warning.
- The compensation is small (typically < 10 ms for indoor setups with cameras < 5m from speaker) but matters at high frame rates (100+ fps).

## Phase 4: Replace production audio sync

Once phases 1-3 are validated:
- Replace the GCC-PHAT algorithm in `code/audio_sync.py` with the onset-based approach.
- Wire in the speed-of-sound compensation (optional, only when calibration + sound source position are available).
- Keep the existing trim/sync/stitch pipeline unchanged — only the offset computation changes.
- Update CLAUDE.md to remove the "audio sync offset accuracy" known issue.
