"""
Re-run audio sync on an already-recorded trial.

The GUI only syncs automatically straight after recording, so this CLI lets you
re-sync an existing trial's video/ folder with the current audio_sync code
(e.g. after a fix to the trimming logic). It imports and calls the real
audio_sync functions rather than reimplementing the algorithm.

Usage:
    python tools/resync_trial.py "<...>/<trial>/video"

If no path is given, defaults to the walk02 test trial below.

Note: no speed-of-sound compensation is applied here (the standalone tool has no
calibration / sound-source context). Offsets are computed from raw clap onsets
only. Use the Recording tab for compensated sync.
"""

import sys
from pathlib import Path

# Import the real audio_sync module from code/ (matches repo import style)
CODE_DIR = Path(__file__).resolve().parent.parent / "code"
sys.path.insert(0, str(CODE_DIR))

from audio_sync import (  # noqa: E402
    compute_sync_offsets,
    trim_and_sync_videos,
    create_stitched_preview,
    AudioSyncError,
)

DEFAULT_VIDEO_DIR = (
    r"D:\Markerless_Projects\tests_Francois\sessions\Charlotte_Pilot1\180_turn01\video"
)


def main():
    video_dir = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VIDEO_DIR)
    if not video_dir.is_dir():
        print(f"ERROR: not a directory: {video_dir}")
        sys.exit(1)

    # Raw MP4s live directly in video/ (the synced/ subfolder is excluded by glob)
    video_paths = sorted(str(p) for p in video_dir.glob("*.MP4"))
    if len(video_paths) < 2:
        print(f"ERROR: need at least 2 raw .MP4 files in {video_dir}, "
              f"found {len(video_paths)}")
        sys.exit(1)

    print(f"Re-syncing {len(video_paths)} videos in {video_dir}")
    for vp in video_paths:
        print(f"  {Path(vp).name}")

    log = lambda msg: print(f"  {msg}")  # noqa: E731

    try:
        offsets = compute_sync_offsets(
            video_paths, output_dir=str(video_dir), progress_callback=log
        )
        print("\nTrimming videos (frame-accurate re-encode)...")
        trim_and_sync_videos(
            video_paths, offsets, str(video_dir), progress_callback=log
        )
        print("\nCreating stitched preview...")
        create_stitched_preview(str(video_dir / "synced"), progress_callback=log)
    except AudioSyncError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    print(f"\nDone. Synced files in {video_dir / 'synced'}")


if __name__ == "__main__":
    main()
