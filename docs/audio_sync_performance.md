# Audio Sync Performance & Diagnostics

Notes from a June 2026 investigation into post-recording wall-clock time on the
Recording tab. Covers the built-in timing diagnostic, where the time actually goes,
and an important environment gotcha (CrowdStrike) that makes the *first* sync of a
session look much slower than it is.

## Built-in per-step timing table

`audio_sync.py` carries a small `StepTimer` (created in `recording_tab.py`'s record
worker, threaded through `compute_sync_offsets` / `trim_and_sync_videos` /
`create_stitched_preview`). After every Recording-tab trial sync it prints a table to
the terminal:

```
======================================================
Sync step timing
======================================================
Step                                     |  Time (s)
------------------------------------------------------
1. Download                              |     6.064
2. Audio checks / prep                   |     2.127
Step 0: Load audio                       |     1.897
Step 1: Compute envelope                 |     0.025
Step 2: First derivative of envelope     |     0.003
Step 3: Detect clap onsets               |     0.014
Step 4: Compute offsets from onset times |     0.000
Step 5: Consistency check                |     0.000
Step 6: Speed-of-sound compensation      |     0.000
Onset plot / summary                     |     0.476
10a. Frame count + common                |     0.202
10b. Re-encode (trim)                    |    23.516
11. Verifying frame counts               |     0.158
12. Stitched preview                     |     4.510
------------------------------------------------------
TOTAL                                    |    38.994
======================================================
```

It is always-on (a research-tool diagnostic), **Recording tab only** — the
calibration sync path (`_run_calib_sync`) is not instrumented. The `timer` parameters
are optional/defaulted, so calibration call sites are unaffected.

## Where the time goes (warm run, 4× 1080p100, ~10 s clip)

Total ~39 s, dominated by the trim re-encode:

| Step | Time | Notes |
|---|---|---|
| 10b. Re-encode (trim) | ~23.5 s | **The floor.** Frame-accurate `hevc_nvenc` re-encode. Stream-copy can't trim sub-GOP (GoPro keyframes ~1 s apart, offsets are ms), so each video must be decoded and re-cut. Only lever is the NVENC preset (quality trade-off) or risky parallel-NVENC. Left as-is. |
| 1. Download | ~6 s | Already parallel (4 cameras concurrent, `ThreadPoolExecutor`). Limited by per-camera USB transfer. |
| 12. Stitched preview | ~4.5 s | Single `mpeg4` encode of the 2×2 grid. |
| 2. Audio checks / prep | ~2 s | `check_ffmpeg` + `check_audio_track` ×4 (ffprobe). |
| Step 0. Load audio | ~1.9 s | `extract_audio` ×4 — **now parallelised** (was ~7.6 s sequential). |
| ffprobe steps (10a, 11) | ~0.4 s | Frame counting; fast once warm. |
| Onset detection (Steps 1–6) | ~0 s | Pure numpy; negligible. |

### Optimisation applied

The 4 `extract_audio` calls (Step 0) were run sequentially (~1.9 s each ≈ 7.6 s).
They are now extracted **4-wide** with `ThreadPoolExecutor` (`ex.map` preserves order;
ffmpeg releases the GIL during `subprocess.run`): **7.6 s → ~1.9 s**.

### Ideas investigated and rejected

- **`ffprobe -count_packets` instead of `-count_frames`** for frame counting — pointless.
  The `nb_frames` container-metadata fast path is already ~45 ms; the slow decode
  fallback isn't being hit. `get_frame_count` left unchanged (exact counts required).
- **Use the small LGPL ffprobe/ffmpeg for non-encode work** — pointless. The 131 MB
  NVENC build launches in ~46 ms once warm; it is not the bottleneck.

## Gotcha: the first sync of a session looks ~25 s slower (CrowdStrike Falcon)

On this lab machine, the **first** ffmpeg/ffprobe spawn in a process pays ~2 s while
CrowdStrike Falcon (the corporate EDR) scans the 131 MB binary image; the verdict is
then cached and subsequent calls are ~45 ms. A *cold* sync therefore shows inflated
ffprobe-heavy steps:

| Step | Cold (first sync) | Warm |
|---|---|---|
| 2. Audio checks / prep | ~11 s | ~2 s |
| 10a. Frame count | ~9.5 s | ~0.2 s |
| 11. Verifying frame counts | ~8 s | ~0.16 s |

This is an **environment cost, not application code** — accepted as a once-per-session
hit. If it ever needs eliminating, the route is an IT-managed CrowdStrike exclusion for
the ffmpeg binaries / data folder, not a code change.

## Benchmarking caveat

When measuring ffmpeg/ffprobe launch time, **use PowerShell (or run the real app), not
a Git-Bash shell.** The Bash environment adds a bogus ~1.95 s per spawn of the large
NVENC binary (a sandbox/wrapper artifact) that the real PowerShell/Python launch path
does not pay. Trusting the Bash number led, briefly, to a wrong root-cause diagnosis.
