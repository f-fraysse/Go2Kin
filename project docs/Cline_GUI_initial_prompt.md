Follow your custom instructions.
# Project Specification: Go2Kin - GoPro Control + Future Mocap Pipeline

## 1. Overview

This project is a research-focused Python application for biomechanics markerless motion capture, aimed at academics / lab users (not enterprise). The goals are:

- Keep the implementation relatively lean and hackable.
- Prioritise clarity over enterprise-grade robustness.
- Maintain a clear separation of major steps in the pipeline.

Long-term, the project will provide a PyQt-based GUI that covers:

- Part 1 — Camera handling (GoPro control)
- Part 2 — Calibration
- Part 3 — Post-processing synchronisation
- Part 4 — Detection & pose estimation
- Part 5 — Triangulation & 3D reconstruction
- Part 6 — Kinematic analysis / joint angles

All of this should live in a single repo, with a modular internal structure.

## 2. Environment & Dependencies

We are working in Windows 11, Visual Studio Code, local project folder is D:\PythonProjects\Go2Kin. VS code terminal is Powershell.
We are working in a Conda environment named "Go2Kin" (Python 3.10)
Some packages are already installed in the conda environment (e.g. PyQT6), we can add more if needed. Trying to limit dependencies overall. Ask before installing packages.

---

## 3. Repository Structure & Separation by Parts

The repo should reflect the major pipeline parts, even if most folders are initially empty.

```text
Go2Kin/
    src/
        go2kin/
            __init__.py
            config.py

            # Part 1 — Camera handling
            gopro/
                __init__.py
                multi_camera_controller.py   # Stage 1: HERO12 control
            # Part 2 — Calibration
            calibration/
                __init__.py
                # later: calibration tools (e.g., checkerboard, wand)

            # Part 3 — Post-processing synchronisation
            sync/
                __init__.py
                # later: audio/video/timecode-based sync

            # Part 4 — Detection & Pose estimation (RTMDet + RTMPose)
	We have most of the pipeline working in a different repo, will provide source code when the time comes
            pipeline/
                __init__.py
                hpe/
                    __init__.py
                    # later: detector, pose estimator, batch runners

            # Part 5 — Triangulation & 3D reconstruction
            reconstruction/
                __init__.py
                # later: triangulation, 3D reconstruction, smoothing

            # Part 6 — Kinematics / joint angles
            kinematics/
                __init__.py
                # later: joint angle computation, summary metrics

            # GUI
            ui/
                __init__.py
                main_window.py       # main PyQt window
                preview_widget.py    # optional: preview component

    .env.example
    requirements.txt
    README.md
    SPECIFICATION.md   # (this file, optional)
```

## 4. Current scope (Stage 1):
Implement multi-camera GoPro control through USB using the goproUSB repo with a minimal PyQt GUI.
goproUSB is a subfolder within the main project folder (Go2Kin). It contains:
goproUSB.py provides functionality to control and set up gopros.
goproRecordVideo_threeCameras.py provides an example to trigger recording from three cameras at once, and downloading the video files from each camera.
I have tested this script and confirmed it is working.

Here’s a draft of basic UI layout and functionality:

Architecture

•	GPcamController: thin wrapper around each GPcam instance holding serial, derived IP, status flags, and queued actions (mode/lens/res/fps). Keeps all HTTP calls off the UI thread using QThreadPool + QRunnable or QtConcurrent.run.
•	CameraManager: tracks up to four controllers, exposes signals like statusChanged, recordingStarted, downloadFinished, and manages shared tasks (bulk start/stop recording, download directory, etc.).
•	Main window hosts a QTabWidget with three tabs described below.

Functionality 

Tab 1: camera settings. Allows to connect up to 4 cameras through USB. The four GoPros we have have following serial numbers, and associated “lab IDs” for them:
C3501326042700 = GoPro 1
C3501326054100 = GoPro 2
C3501326054460 = GoPro 3
C3501326062418 = GoPro 4
•	Grid of four panels (one per lab ID) showing:
•	Status indicator (QLabel with red/green pixmap) updated via periodic keepAlive or getState.
•	Current serial/IP, Edit Serial Number… button opens QInputDialog; on save, controller re-initializes GPcam.
•	Drop-downs for lens (Narrow, Linear, etc.), resolution (pre-populate with methods exposed in goproUSB.py: 1080p, 1440, 4K, etc.), and FPS (30 default). Selecting an option queues the corresponding API call in a worker.
•	Connect / Disconnect buttons call USBenable / USBdisable.
•	Defaults: populate with the four serials you provided and set initial settings (Narrow / 1080p / 30fps). Persist selections via a simple JSON config under Go2Kin/config/cameras.json so the UI rehydrates on launch.

Tab 2: live preview. 
•	Camera selector (QComboBox) listing currently “available” controllers.
•	Start/Stop buttons orchestrating webcam mode:
1.	Ensure other cameras are either idle or explicitly kept in USB control mode (per the note in goproUSB.py you must disable wired control before webcam commands).
2.	Call USBdisable, then webcamStart, retrieve the preview URL (likely http://<ip>:8080/live/amba.m3u8 or similar), and feed it into a QWebEngineView (since PyQt6 supports it) or a custom QLabel updated by an ffmpeg subprocess piping frames. Keep it minimal: QWebEngineView.load(QUrl(stream_url)).
3.	Stop button calls webcamStop followed by USBenable so the camera returns to control mode.
•	Big central widget reserved for the preview; later you can overlay keypoints by drawing on top or swapping the widget entirely.

Tab 3: recording. 
•	Directory selector (default D:\PythonProjects\Go2Kin\output) saved in the same config file.
•	Trial Name input field
•	Checklist or toggles for which cameras participate.
•	Start button:
1.	For each selected controller, queue: ensure USB enabled, set mode/video/res/fps according to Tab 1 state, then shutterStart.
2.	Disable UI buttons while recording and show a timer.
3.	On start: compute trial_dir = save_dir / trial_name. If it already exists, append _001, _002, etc. automatically unless the user has manually overridden the name for this run. Store the last auto-generated base name and increment the numeric suffix when the user leaves the field untouched before the next recording.
•	Stop button:
1.	Issue shutterStop per camera.
2.	After stopping and downloading, each camera saves to trial_dir / f"{trial_name}_{camera_label}.mp4" (using the user-facing IDs “GP1”…“GP4”).
3.	After camBusy/encodingActive return false, call mediaDownloadLast to the chosen folder (spawn worker per camera). The module doesn’t currently delete files on the camera, so add a helper that hits /gopro/camera/command/storage/delete_last (if supported) or list & delete via /gopro/media/delete/file. If the firmware lacks delete endpoints over wired control, we’ll have to leave files in place or implement card cleanup separately.
4.	After stopping and downloading, each camera saves to trial_dir / f"{trial_name}_{camera_label}.mp4" (using the user-facing IDs “GP1”…“GP4”).
5.	Progress list showing each camera’s download status. Once downloads finish, optionally display a summary list of the saved files and expose a “Open Folder” button.




