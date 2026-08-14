# Go2Kin

- **[Equipment](equipment.md)**
- **[First-time setup](first-time-setup/index.md)**
- **[Regular use](regular-use.md)**
- **[GUI reference](gui/index.md)**
- **[Known issues & tips](troubleshooting.md)**

!!! note "Work in progress"
    Go2Kin and this manual are under active development.
Go2Kin is an integrated markerless motion capture pipeline for up to 4 USB-wired GoPro
cameras, run from a single desktop GUI. 

It covers the full workflow of a traditional
marker-based lab (e.g. Vicon Nexus): 
- camera connection and setup (Open GoPro HTTP API over USB),
- camera calibration (adapted from [Caliscope](https://github.com/mprib/caliscope)),
- recording and auto-sync in post processing (audio based),
- pose estimation (RTMpose), triangulation, filtering, interpolation ([Pose2Sim](https://github.com/perfanalytics/pose2sim)),
-  3D kinematics (OpenSim).

The code was designed to be modular so blocks can be swapped in/out; e.g. change the camera connection/handling block to use different cameras / conenction method (e.g. WiFi), change pose estimtion to use e.g. some vision transformer instead of CNN-based method, etc.

It is also designed mainly for **indoor labs**, and several design choices follow from that setting:

- USB-wired cameras for simple reliable connection, 
- Audio-based synchronisation using hand claps - simple and robust indoors,

Developed and tested with the **GoPro Hero 12 Black** on **Windows 11**; any GoPro
supporting the HTTP API (Hero 9 or later) should work.


