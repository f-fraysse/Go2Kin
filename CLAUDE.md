# Go2Kin

Multi-camera GoPro control application for research. Controls up to 4 GoPro Hero 12 cameras via USB using the GoPro HTTP API, with a tkinter GUI.

## Dev Environment

- **OS**: Windows 11
- **Python**: 3.10 in Conda environment `Go2Kin` (`conda activate Go2Kin`)
- **IDE**: VSCode
- **Run**: `python code/go2kin.py`
- **Dependencies**: `pip install -r requirements.txt` (requests, opencv-python, Pillow)

## Project Structure

```
code/
  go2kin.py              # Entry point
  camera_profiles.py     # CameraProfileManager (profiles + settings references)
  GUI/
    __init__.py           # Exports Go2KinMainWindow
    main_window.py        # Go2KinMainWindow + LivePreviewCapture
  goproUSB/
    goproUSB.py           # GPcam class (camera HTTP API client)
config/
  cameras.json            # Main config (serials, settings, recording prefs)
  camera_profiles/        # Per-camera JSON profiles (profile_{serial}.json)
  settings_references/    # Per-model/firmware setting definitions
tools/
  discover_camera_settings.py  # Run once per model/firmware to generate reference
output/                   # Recording output directory
memory-bank/              # Legacy project documentation
```

## Architecture

- **GPcam** (`goproUSB.py`): HTTP client for one camera. IP derived from serial: `172.2X.1YZ.51:8080`
- **CameraProfileManager** (`camera_profiles.py`): Singleton managing per-camera profiles and per-model settings references
- **Go2KinMainWindow** (`GUI/main_window.py`): 3-tab tkinter GUI (Settings, Preview, Recording)
- **LivePreviewCapture** (`GUI/main_window.py`): Threaded OpenCV capture from UDP stream

## Hardware

4 GoPro Hero 12 cameras:
- C3501326042700 = GoPro 1
- C3501326054100 = GoPro 2
- C3501326054460 = GoPro 3
- C3501326062418 = GoPro 4

## Coding Conventions

- **Keep it simple** — research-focused, not enterprise. Avoid over-engineering.
- **Profile-driven settings** — references define available options, profiles track camera state, GUI populates from both
- **Error isolation** — one camera's failure must not affect others
- **Threading model**: GUI thread for display, ThreadPoolExecutor for multi-camera ops, background threads for status polling and frame capture
- **HTTP timeouts**: 5s for commands, 300s for media downloads
- **Settings via generic API**: prefer `setSetting(setting_id, option_id)` over legacy convenience methods

## GoPro API Essentials

```
# Connection
/gopro/camera/control/wired_usb?p=1    # Enable USB control
/gopro/camera/keep_alive               # Heartbeat (every 30s)

# Recording
/gopro/camera/shutter/start
/gopro/camera/shutter/stop

# Settings
/gopro/camera/setting?setting=X&option=Y

# Preview
/gopro/camera/stream/start?port=8554   # UDP stream
/gopro/camera/stream/stop

# Media
/gopro/media/list
/videos/DCIM/{dir}/{file}              # Download
/gp/gpControl/command/storage/delete/all  # Delete (legacy endpoint)
```

## Known Quirks

- `sys.path.insert()` used for imports — fragile but functional
- `deleteAllFiles()` uses legacy `/gp/gpControl/` endpoint — works, leave as-is
- Preview forces 1080p/30fps/Linear — intentional for low-bandwidth positioning
- Setting 236 (Auto WiFi AP) not in discovery tool but applied on connect
- `camBusy()`/`encodingActive()` return False on errors (fail-safe design)
- **GUI dropdown options are hardcoded for Hero 12 + 50Hz anti-flicker**: Resolution (1080, 2.7K, 4K) and FPS (25, 50, 100, 200) in `main_window.py` lines ~280/292. For different cameras or 60Hz anti-flicker, update these values. Invalid selections are caught at runtime (camera returns 403 with valid options popup).

## Known Issues / TODO

- **Low video quality on downloaded files**: Downloaded MP4s appear lower quality than expected for 1080p (low bitrate). Suspect the app may be downloading the GoPro's low-res preview file (LRV) instead of the full-quality MP4. To investigate: list SD card contents via `/gopro/media/list` before and after recording to see what files are created (MP4, LRV, THM, etc.), then check which file `mediaDownloadLast()` selects.
