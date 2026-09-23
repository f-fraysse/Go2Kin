# 7. Verify your setup

Run one short trial end-to-end to confirm everything works before a real collection.

1. **Calibrate extrinsics and set the origin** — follow the [regular workflow](../regular-use.md#calibrate) with the cameras in their working positions.
2. **Record a short trial** — a few seconds of movement, with **two loud hand claps within the first 3 seconds**. If you use [LED light sync](../gui/led-sync.md), set the LED ROI first (step 1 of the regular workflow) and trigger the LED instead of clapping.
3. **Check the sync** — the trial passed if no red *SYNC ISSUE* popup appeared. For a quick visual check, open `video/synced/stitched_videos.mp4` (2×2 grid preview) and `sync_onsets.png` (claps) or `sync_led_signal.png` (LED) in the trial folder.
4. **Process the trial** — Processing tab → tick the trial → **Process Selected**. Watch the log; pose estimation should report running on GPU (CUDA).
5. **Check the outputs** — confirm the kinematics results exist. *(🚧 TODO: list expected output files — .trc, .mot, scaled model, IK results — where they land, and what a "good" first result looks like.)*
6. **Optionally visualise** — open the trial in the [Visualisation tab](../gui/visualisation-tab.md) and eyeball the 2D/3D keypoint overlays.

If anything fails along the way, see [Known issues & tips](../troubleshooting.md).
