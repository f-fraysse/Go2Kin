# Tab 2 — Calibration

Multi-camera calibration using a printed charuco board: lens parameters (**intrinsic**),
camera positions and orientations (**extrinsic**), and the lab coordinate system
(**origin**). The algorithms are adapted from
[Caliscope](https://github.com/mprib/caliscope).

> 🚧 **TODO:** screenshot of the tab with each panel labelled.

## Charuco Board Config

Set board dimensions, square size (use the **measured** printed size) and ArUco
dictionary. **Save Board Image** exports a printable board image (default A1).

## Intrinsic Calibration

Per-camera lens calibration from a video of the board, using smart frame selection for
orientation and spatial coverage diversity. Procedure:
[Intrinsic calibration](../first-time-setup/06-intrinsic-calibration.md).

## LED Sync ROI

Only used with the **Light** sync method ([LED light sync](led-sync.md)). **Record LED clip
& set ROI** records a short clip on all cameras and opens a window where you click the LED
in each view; **Set ROI from folder…** does the same from an existing recording. The ROIs are
stored with the calibration (they depend on where the cameras are) and must be set before the
extrinsic recording, which is synced with the LED as well.

## Extrinsic Calibration

Multi-camera pose estimation from **synced** videos of the board moving through the
shared volume — PnP solving, outlier rejection, graph bridging, triangulation and bundle
adjustment. Browse to the trial's `synced/` folder and click **Calibrate Extrinsics**.
The recording is synced with the method selected in the bottom bar (claps or LED).

> 🚧 **TODO:** extrinsic quality metrics (RMSE etc.) are on the roadmap — document thresholds and a pass/fail heuristic once implemented.

## Set Origin

Stand the board **vertically, in portrait**, at the desired world origin (origin corner
**790 mm** above the floor). A short recording on all cameras is trimmed to a common
duration — audio sync is skipped, since the board is static — and the coordinate system
is aligned with a Umeyama similarity transform. Can be re-run after loading a saved
calibration to redefine the axes.

> 🚧 **TODO:** the 790 mm vertical offset is planned to become user-editable — update once it is.

## Save / Load

**Save Calibration** persists results to `config/calibration/calibration.json` and
auto-exports `camera_array_go2kin.toml` for Pose2Sim. **Load** restores a saved
calibration; the top-bar indicator reflects its age.
