# Audio Sync Test Script Specification

## Purpose

Test script to develop and validate audio-based multi-camera synchronisation for Go2Kin. Uses one existing set of 4× GoPro Hero 12 recordings. The script should plot every intermediate step so we can visually verify the algorithm before integrating into the main codebase.

Put the script in /tools/

## Input

- 4× MP4 files from GoPro Hero 12 cameras (or 4× WAV files if Raw Audio is available)
- File paths hardcoded at the top of the script as a list. Use the 4 video files in: "D:\Markerless_Projects\tests_Francois\sessions\test_full_pipeline\audio_sync_soft\video\" for now.
- Audio sample rate: 48000 Hz (assert this after loading)

## Recording protocol

- Two claps are performed at the start of the recording, separated by at least 0.3 seconds
- The system detects both claps, runs the sync pipeline independently on each, and compares results as a quality check

## Step 0: Load audio

- Extract audio from each MP4 using `ffmpeg` via subprocess, outputting mono 16-bit PCM WAV at 48 kHz: `ffmpeg -i input.MP4 -vn -ac 1 -ar 48000 -acodec pcm_s16le output.wav`
- If input is already WAV, load directly
- Load each WAV into a numpy array using `scipy.io.wavfile`
- Normalise each array to float64 in range [-1, 1]
- **Plot 1**: Raw waveform of all 4 tracks (4 subplots, shared x-axis in seconds), title each with the filename

## Step 1: Compute envelope

- For each audio track, compute the analytic signal using `scipy.signal.hilbert`
- Take the absolute value to get the amplitude envelope
- Smooth the envelope with a moving average filter of length 2400 samples (= 50 ms at 48 kHz). Use `np.convolve(envelope, np.ones(2400)/2400, mode='same')`
- **Plot 2**: Smoothed envelope of all 4 tracks (4 subplots, shared x-axis in seconds)

## Step 2: First derivative of envelope

- Compute the first derivative of each smoothed envelope using `np.diff`, prepending a zero so the array length is preserved: `np.concatenate(([0], np.diff(smoothed_envelope)))`
- We only care about positive derivatives (onset = rising edge), so clip negative values to zero: `derivative = np.maximum(derivative, 0)`
- **Plot 3**: Clipped first derivative of all 4 tracks (4 subplots, shared x-axis in seconds)

## Step 3: Detect two clap onsets in each track

- For each track, find the two most prominent peaks in the clipped derivative using `scipy.signal.find_peaks(derivative, distance=int(0.3 * 48000), height=threshold)` where `threshold` is 0.1× the maximum derivative value for that track
- From the returned peaks, select the **top 2 by height** (peak prominence)
- Sort these two peaks by sample index so that peak 0 = first clap, peak 1 = second clap
- If fewer than 2 peaks are found for any camera, print a warning and fall back to single-clap mode for that track
- **Print** for each camera: onset sample index and time (seconds) for both claps
- **Plot 4**: Same as Plot 2 (smoothed envelopes), but with two vertical dashed lines per track: red for clap 1, blue for clap 2

## Step 4: Identify reference camera and define crop windows

- The reference camera is the one with the **earliest** detected onset across clap 1 (smallest sample index for clap 1)
- Define **two** crop windows in samples, one per clap:
  - For clap `c` (c=0, 1):
    - `crop_start_c = onset_of_reference_camera_clap_c - int(0.200 * 48000)`  (200 ms before)
    - `crop_end_c = onset_of_reference_camera_clap_c + int(0.200 * 48000)`    (200 ms after)
    - Clamp `crop_start_c` to 0 if negative
    - Clamp `crop_end_c` to the minimum length of all audio tracks if it exceeds any
- Crop **all 4 raw audio tracks** (not envelopes) using the same `crop_start_c:crop_end_c` indices for each clap
- **Print**: reference camera index/filename, crop_start and crop_end for each clap, crop durations in ms
- **Plot 5**: Two rows of 4 subplots (row 1 = clap 1 crops, row 2 = clap 2 crops). Each subplot shows the cropped raw waveform for one camera. Shared x-axis in samples relative to crop_start. Mark the detected onset of each camera within the crop as a vertical red/blue dashed line.

## Step 5: Cross-correlation (run independently for each clap)

- For each clap (c=0, 1):
  - Designate the reference camera's cropped raw signal as `ref_signal`
  - For each of the other 3 cameras:
    - Compute cross-correlation: `cc = scipy.signal.correlate(target_cropped, ref_signal, mode='full', method='fft')`
    - Compute the lag array: `lags = np.arange(-(len(ref_signal)-1), len(target_cropped))`
    - Find the index of the maximum value in `cc`
    - The lag in samples at that index is `lag_samples = lags[peak_index]`
    - Apply **parabolic (quadratic) interpolation** for sub-sample precision:
      - Let `k = peak_index`, `y = cc`
      - `p = (y[k-1] - y[k+1]) / (2.0 * (y[k-1] - 2*y[k] + y[k+1]))`
      - `refined_lag = lag_samples + p`
      - Guard: only apply interpolation if `k > 0` and `k < len(cc) - 1`
    - Convert to time: `offset_seconds = refined_lag / 48000.0`
    - Convert to frames at a given FPS (default 100 fps): `offset_frames = offset_seconds * fps`
    - Record the peak CC value for later quality comparison
  - The reference camera has offset = 0 by definition
- **Plot 6**: Two rows of 3 subplots (row 1 = clap 1 CC functions, row 2 = clap 2 CC functions). X-axis in samples (lag), y-axis is CC value. Mark the peak with a red dot. Title each with the camera pair and the computed offset in ms.

## Step 6: Consistency check

- For each non-reference camera, compare the offset from clap 1 vs clap 2
- Compute the absolute difference in milliseconds: `diff_ms = abs(offset_clap1_ms - offset_clap2_ms)`
- Define consistency threshold: 20 ms (= 1 frame at 50 fps, sub-frame at 100 fps)
- If `diff_ms <= threshold`: **PASS**
- If `diff_ms > threshold`: **WARN** — flag this camera pair, print both offsets and the discrepancy
- **Print** the consistency check results for each camera
- If both claps pass: use the offset from whichever clap has the **higher peak CC value** (better signal quality), or optionally average them
- If one clap fails to detect (single-clap fallback): use the available clap's offset and print a warning

## Step 7: Verification overlay

- **Plot 7**: Overlay all 4 cropped raw waveforms (from the selected clap) on a single plot, shifting each target camera's waveform by its computed lag (in integer samples) so they should align. Use different colours with alpha=0.5. This provides a visual check that the clap transients are aligned after applying the offsets.

## Summary output

Print a summary table at the end:

```
Camera | Clap 1 Lag (ms) | Clap 1 CC | Clap 2 Lag (ms) | Clap 2 CC | Diff (ms) | Status | Final Lag (ms) | Final Lag (frames@100fps)
-------|-----------------|-----------|-----------------|-----------|-----------|--------|----------------|-------------------------
cam0*  |      0.00       |     —     |      0.00       |     —     |    0.00   |  REF   |      0.00      |          0.00
cam1   |      0.88       |   0.82    |      0.91       |   0.78    |    0.03   |  PASS  |      0.88      |          0.09
cam2   |     -0.31       |   0.75    |     -0.29       |   0.80    |    0.02   |  PASS  |     -0.29      |         -0.03
cam3   |      0.58       |   0.71    |      0.61       |   0.85    |    0.03   |  PASS  |      0.61      |          0.06
```

(* = reference camera. Final Lag uses the clap with the higher CC value.)

## Implementation notes

- Use `matplotlib.pyplot` for all plots. Use `plt.tight_layout()`. Save each figure as a PNG to the same directory as the script, named `sync_step_N.png`.
- Also display all plots with `plt.show()` at the end (after all figures are created).
- Use hardcoded paths at the top, clearly marked with a comment `# === CONFIGURE THESE ===`
- All file I/O for intermediate WAVs should go to a temp directory, cleaned up at the end
- Script should be a single file, no external dependencies beyond: numpy, scipy, matplotlib, subprocess (for ffmpeg)
- Target path: save the script wherever is convenient, we will run it manually

## Speed-of-sound compensation and the calibration steps

Speed-of-sound (ToF) compensation needs both the camera world positions and the sound-source world position. At ~340 m/s the residual error scales roughly as 3 ms per metre of difference in cam-to-clap distances between any two cameras — meaningful at 60 fps when one camera is much closer to the clap than another.

The calibration steps deliberately do **not** apply ToF compensation:

- **Extrinsic calibration**: camera positions are not yet known when the calibration video is synced (chicken-and-egg). Sync runs on raw clap onsets only. Practical guidance: clap near the centre of the camera volume so per-camera distance differences largely cancel.
- **Set Origin**: audio sync is skipped entirely. Because the charuco board is held static, per-camera frame-level alignment is unnecessary. The recorded videos are still trimmed to a common duration and frame-count-equalised so the downstream pipeline sees homogeneous inputs (`_run_calib_sync(..., skip_sync=True)`).

ToF compensation is applied for **trial recording** ([recording_tab.py](../code/GUI/recording_tab.py)), where the camera poses are already available from the loaded calibration and the sound-source position is read from the Recording tab's own UI fields. The Recording tab is the only place that owns the sound-source position; the Calibration tab does not store one.

### Reference re-baseline after compensation (Step 7)

The reference camera is initially chosen as the earliest *raw clap onset* (Step 4). ToF compensation (Step 6) subtracts each camera's differential sound-travel delay, which can make a **different** camera the genuinely earliest one — leaving that camera with a *negative* offset relative to the now-incorrect reference.

`compute_sync_offsets` therefore performs a **re-baseline** (Step 7) after compensation: the camera with the minimum compensated offset becomes the reference (offset 0), and every other camera's offset is shifted to `compensated_offset − min` so all front-trims are ≥ 0. The `REF` marker moves to this camera; the displaced old reference takes a normal `PASS` status. This is a no-op when no compensation is applied (raw offsets are already ≥ 0 with the onset-reference at the minimum). Because the per-reference constant cancels under the shift, the result is independent of which camera was the intermediate onset-reference.

Without this step, `trim_and_sync_videos` clamps the negative offset to zero (`max(0, round(offset*fps))`), silently mis-aligning the genuinely-earliest camera by up to a frame.

> Note: the `Clap1 Lag`/`Clap2 Lag` columns in the summary table remain raw onset lags relative to the *onset*-reference (diagnostic only) and are **not** re-baselined. The `REF` camera may therefore show a non-zero Clap1 Lag while its Final Lag is 0 — this is expected.
