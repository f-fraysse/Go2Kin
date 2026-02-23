# Active Context

## Current Work Focus

### Project Status: CORE FUNCTIONALITY DELIVERED ✅
Go2Kin multi-camera GoPro control system is fully operational with profile-driven settings management.

### Most Recent Work: Codebase Review & Cleanup (Feb 23, 2026)

**Bug Fixes Applied:**
- ✅ Fixed `setMaxLensOn()` bug (was sending option=0 instead of option=1)
- ✅ Fixed `setVideoLensesWide()` bug (was using Photo Lens setting ID 122 instead of Video Lens 121)
- ✅ Added sleep(0.5) and 60s timeout to `mediaDownloadLast()` encoding wait loop (was CPU-spinning)
- ✅ Added error handling to `camBusy()` and `encodingActive()` (fail-safe returns False on errors)
- ✅ Added `timeout=5` to ALL HTTP requests in goproUSB.py (prevents app hang on unresponsive camera)

**Design Improvements:**
- ✅ Deleted unused `config/app_settings.json` (was dead config causing confusion)
- ✅ Consolidated `previewStreamStart/Stop` into `streamStart(port)/streamStop()` (removed duplication)
- ✅ Updated default resolution from "1080p" to "1080" (matches settings reference format)
- ✅ Added Anti-Flicker 50Hz to `settings_on_connect` (correct for Australia)
- ✅ Updated `requirements.txt` with `opencv-python` and `Pillow`
- ✅ Updated `goproUSB/README.md` for HERO 12 compatibility

**Documentation Cleanup:**
- ✅ Cleaned up `progress.md` (removed duplicate phase sections)
- ✅ Updated `systemPatterns.md` (reflects actual architecture, not aspirational)
- ✅ Updated `techContext.md` (current project structure, dependencies, API details)
- ✅ Updated `activeContext.md` (this file)

## What's Complete

- **goproUSB.py**: Full camera control with timeouts, error handling, zoom, streaming
- **camera_profiles.py**: Profile management with reference caching
- **GUI**: 3-tab interface (Settings, Preview, Recording) fully functional
- **Settings on Connect**: Pro mode, Linear lens, GPS off, Hypersmooth off, 50Hz Anti-Flicker, etc.
- **Live Preview**: OpenCV-based with threaded capture, zoom controls
- **Recording**: Multi-camera synchronized workflow with auto-download and cleanup
- **Configuration**: Single `cameras.json` + per-camera profiles + per-model references

## Next Steps (Future Work)

### Near-term Candidates
1. **Move `connect_camera()` to background thread** — Currently blocks GUI for ~10 seconds. Show "Connecting..." indicator and disable buttons during connection.
2. **"Connect All" button** — Single click to connect all 4 cameras simultaneously.
3. **Dynamic camera selection in Recording tab** — Grey out checkboxes for disconnected cameras.
4. **User documentation** — Create user guide for research team.

### Longer-term Candidates
- "Apply to All" button for settings
- ISO/Exposure controls during live preview
- Recording readiness checks (prevent recording while cameras busy)
- Accurate timer start (after cameras confirm recording started)
- GUI layout optimization

## Important Patterns and Preferences

### Architecture
- **Keep it simple** — Research-focused, not enterprise
- **Profile-driven settings** — Reference defines options, profile tracks state
- **Single config file** — `cameras.json` for UI state, profiles for camera state
- **Error isolation** — One camera's failure shouldn't affect others

### API Usage
- **streamStart(port=8554)** / **streamStop()** — Consolidated stream methods
- **setSetting(id, option)** — Generic settings API (preferred over legacy convenience methods)
- **All requests timeout=5s** — Media downloads get 300s

### Known Quirks
- `deleteAllFiles()` uses legacy `/gp/gpControl/` endpoint (works, leave as-is)
- Settings 180 (System Video Mode) and 236 (Auto WiFi AP) not in discovery tool but applied on connect
- Preview forces 1080p/30fps/Linear — intentional for low-bandwidth positioning
- `sys.path.insert()` imports — functional but fragile, fix later
