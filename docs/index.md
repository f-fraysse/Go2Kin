# Go2Kin

!!! note "Work in progress"
    Go2Kin and this manual are under active development. Sections marked 🚧 **TODO** still need content.

Go2Kin is an integrated markerless motion capture pipeline for **up to 4 USB-wired GoPro
cameras**, run from a single desktop GUI. It covers the full workflow of a traditional
marker-based lab (e.g. Vicon Nexus) — camera setup, calibration, synchronised recording,
pose estimation and 3D kinematics in OpenSim — without markers.

Go2Kin is designed for **indoor motion capture labs**, and several deliberate design
choices follow from that setting:

- **USB-wired cameras** (not WiFi) — reliable connection, control and file transfer to a single PC.
- **Audio-based synchronisation** using hand claps — simple and robust indoors, but unlikely to work well outdoors or in noisy environments.
- A **familiar lab structure** — project → session → participant → trial, mirroring conventional mocap workflows.

Under the hood, the pipeline runs: camera connection & control (Open GoPro HTTP API over
USB) → multi-camera calibration (adapted from [Caliscope](https://github.com/mprib/caliscope))
→ recording → audio sync → pose estimation, triangulation and filtering
([Pose2Sim](https://github.com/perfanalytics/pose2sim), RTMlib) → kinematics (OpenSim).

Developed and tested with the **GoPro Hero 12 Black** on **Windows 11**; any GoPro
supporting the HTTP API (Hero 9 or later) should work.

> 🚧 **TODO:** embed the demo video (GoPro footage + OpenSim output side by side).

## How this manual is organised

- **[Equipment](equipment.md)** — what you need before you start.
- **[First-time setup](first-time-setup/index.md)** — install, configure and verify Go2Kin once, on a new PC or in a new lab.
- **[Regular use](regular-use.md)** — the routine for a normal data-collection session.
- **[GUI reference](gui/index.md)** — what every part of the interface does.
- **[Known issues & tips](troubleshooting.md)** — fixes, workarounds and FAQ.
