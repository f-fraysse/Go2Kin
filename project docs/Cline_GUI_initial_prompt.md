Follow your custom instructions.
# Project Specification: Go2Kin - GUI for multi camera GoPro Control through USB 

## 1. Overview

This project is a research-focused Python application aimed at academics / lab users (not enterprise). The goals are:

- Implement multi-camera GoPro control through USB, using the GoPro HTTP API, through a tkinter GUI.
- Keep the implementation lean and simple.

## 2. Environment & Dependencies

We are working in Windows 11, Visual Studio Code, local project folder is D:\PythonProjects\Go2Kin. VS code terminal is Powershell.
We are working in a Conda environment named "Go2Kin" (Python 3.10).
We are using tkinter for the UI.
We are using openGoPro for HTTP control of cameras through USB.

python scripts and other files are in /code/ subfolder
recorded videos and other output will go in /output/
misc documentation is in /project docs/
---


## 3. GoPro API:
Implement multi-camera GoPro control through USB.
GoPro provides an API for camera control using HTTP protocol. This is accessible through USB connection.
Reference page for GoPro API: https://gopro.github.io/OpenGoPro/http

Some important info from the page:

The GoPro API allows developers to create apps and utilities that interact with and control a GoPro camera.
The GoPro API allows you to control and query the camera to:

Capture photo/video media
Get media list
Change settings
Get and set the date/time
Get camera status
Get media metadata (file size, width, height, duration, tags, etc)
and more!

USB connection
Open GoPro systems that utilize USB must support the Network Control Model (NCM) protocol. Connecting via USB requires the following steps:

Physically connect the camera's USB-C port to your system
Send HTTP command to enable wired USB control

Socket Address
USB
The socket address for USB connections is 172.2X.1YZ.51:8080 where XYZ are the last three digits of the camera's serial number.

The camera's serial number can be obtained in any of the following ways:

Reading the sticker inside the camera's battery enclosure
Camera UI: Preferences >> About >> Camera Info
Bluetooth Low Energy: By reading directly from Hardware Info
For example, if the camera's serial number is C0000123456789, the IP address for USB connections would be 172.27.189.51.

Alternatively, the IP address can be discovered via mDNS as the camera registers the _gopro-web service.

Commands
Using the Open GoPro API, a client can perform various command, control, and query operations.

Depending on the camera's state, it may not be ready to accept specific commands. This ready state is dependent on the System Busy and the Encoding Active status flags. For example:

System Busy flag is set while loading presets, changing settings, formatting sdcard
Encoding Active flag is set while capturing photo/video media
If the system is not ready, it should reject an incoming command; however, best practice is to always wait for the System Busy and Encode Active flags to be unset before sending messages other than camera status queries. For details regarding camera state, see the Get State Operation

Keep Alive
It is necessary to periodically send a keep-alive signal to maintain the connection.

Camera Control
In order to prevent undefined behavior between the camera and a connected app, simultaneous use of the camera and a connected app is discouraged. A third party client should use the Set Camera Control Status command to tell the camera that the client wishes to claim control of the camera.

Limitations
General

The camera will reject requests to change settings while encoding; for example, if Hindsight feature is active, the user can not change settings
Querying the value for a setting that is not associated with the current preset/core mode results in an undefined value. For example, the user should not try to query the current Photo Digital Lenses (FOV) value while in a video-based Preset.

The file /project docs/openGoPro api specs.json contains the full API specs and commands.


## 4. goproUSB class to encapsulate the API:

/code/goproUSB/goproUSB.py  defines the goproUSB class that wraps some API functionality.
/code/goproUSB/examples/ contains some examples showing how the goproUSB class is used. IN particular "goproRecordVideo_threeCameras.py" I have tested and verified it is working as intended.

We may need to extend goproUSB class to include more API commands.

## 5. General architecture and flow

The GUI will have three tabs:

Tab 1: camera settings. 
Allows to connect up to 4 cameras through USB. The four GoPros we have have following serial numbers, and associated “lab IDs” for them:
C3501326042700 = GoPro 1
C3501326054100 = GoPro 2
C3501326054460 = GoPro 3
C3501326062418 = GoPro 4
•	Grid of four panels showing:
•	Status indicator (red/green circle) updated via periodic keepAlive.
•	Current serial/IP, Edit Serial Number to enter a different camera serial number if needed.
•	Drop-downs for lens (Narrow, Linear, etc.), resolution (pre-populate with methods exposed in goproUSB.py: 1080p, 1440, 4K, etc.), and FPS (30 default). Selecting an option queues the corresponding API call.
•	Connect / Disconnect buttons call USBenable / USBdisable.
•	Defaults: populate with the four serials provided above and set initial settings (Narrow / 1080p / 30fps). Persist selections via a simple JSON config under Go2Kin/config/cameras.json so the UI loads them on launch.

Tab 2: live preview. 
Offers live preview (preview mode) for one camera at a time.
•	Camera selector listing currently “available” cameras.
•	Start/Stop buttons orchestrating preview mode for the selected camera.
•	video area where the preview is displayed.
I have not tested preview mode from the API. YOu should find relevant info in the API specs JSON file. See OGP_PREVIEW_STREAM_START in that file. Also see /project docs/live preview specs table.md.
I believe we are trying to use "USB - ViewFinder preview" mode since webcam preview and webcam mode are too limited.


Tab 3: recording. 
•	Directory selector (default D:\PythonProjects\Go2Kin\output) saved in the same config file.
•	Trial Name input field
•	Checklist or toggles for which cameras participate.
Here is a draft plan for flow, please check against API specs that the plan is sound:
•	Start button:
1.	For each selected controller, queue: ensure USB enabled, set mode/video/res/fps according to Tab 1 state, then shutterStart.
2.	Disable UI buttons while recording and show a timer.
3.	On start: compute trial_dir = save_dir / trial_name. If it already exists, append _001, _002, etc. automatically unless the user has manually overridden the name for this run. Store the last auto-generated base name and increment the numeric suffix when the user leaves the field untouched before the next recording.
•	Stop button:
1.	Issue shutterStop per camera.
2.	After stopping and downloading, each camera saves to trial_dir / f"{trial_name}_{camera_label}.mp4" (using the user-facing IDs “GP1”…“GP4”).
3.	After camBusy/encodingActive return false, call mediaDownloadLast to the chosen folder (spawn worker per camera). The module doesn’t currently delete files on the camera
4.	After stopping and downloading, each camera saves to trial_dir / f"{trial_name}_{camera_label}.mp4" (using the user-facing IDs “GP1”…“GP4”).
5.	Progress list showing each camera’s download status. Once downloads finish, optionally display a summary list of the saved files and expose a “Open Folder” button.
6. delete all media from cameras (i believe there is API function for this although I have not tested. See GPCAMERA_DELETE_ALL_FILES_ID in API specs)




