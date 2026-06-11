# 6. Intrinsic calibration

Intrinsic calibration measures each camera's **lens parameters**. It is done **per
camera** and only needs redoing if you **change the digital zoom** or swap to a different
camera model — not every session.

## Before you start

- Printed charuco board on a rigid mount ([equipment](../equipment.md)), with the **measured** printed square size.
- In **Calibration tab → Charuco Board Config**, enter the board dimensions, measured square size and ArUco dictionary. (**Save Board Image** here is also how you generate the printable board in the first place.)

## Record an intrinsics video for each camera

Record the board from a variety of **angles and distances**, covering different parts of
the frame.

> 🚧 **TODO:** concrete capture guidance — suggested duration, distance range, board orientations, plus an example clip.

> 🚧 **TODO:** document the exact recording procedure for intrinsics videos (recorded from within Go2Kin? which tab?) and where the files end up.

## Run the calibration

In **Calibration tab → Intrinsic Calibration**, browse to each camera's video and click
**Calibrate**. Smart frame selection picks frames for orientation and spatial coverage
diversity.

## Check and save

Intrinsic quality metrics are stored with the calibration.

> 🚧 **TODO:** what counts as a good result (e.g. RMSE threshold) and what to do when it's poor (more coverage, better lighting, re-print board…).

Click **Save Calibration** when done.
