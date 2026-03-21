# Plan: Extract Preview & Recording Tabs from main_window.py

## Context
`main_window.py` is 1,842 lines. Four of six tabs (Project, Calibration, Processing, Visualisation) are already extracted to dedicated files. The remaining two — **Live Preview** and **Recording** — are still inline. Extracting them will make `main_window.py` significantly smaller and more maintainable, consistent with the existing pattern.

## Existing Pattern
All extracted tabs follow the same approach:
- Constructor receives `notebook`, shared state refs (cameras, config, project_manager), and **getter lambdas** for dynamic state
- Creates own `self.frame = ttk.Frame(notebook)` and adds to notebook
- All widget creation and logic encapsulated within the class
- Main window instantiates via `create_*_tab()` methods

## Step 1: Extract `PreviewTab` → `code/GUI/preview_tab.py`

**What moves out:**
- `create_live_preview_tab()` UI code (lines 323–399)
- `LivePreviewCapture` class (lines 28–109)
- All preview/zoom methods (~240 lines): `start_preview`, `stop_preview`, `cleanup_preview`, `update_video_display`, zoom methods (`zoom_increment`, `zoom_decrement`, `on_zoom_entry_enter`, `validate_zoom_input`, `apply_zoom_to_camera`, `update_zoom_display`, `sync_zoom_controls_from_camera`, `enable_zoom_controls`, `disable_zoom_controls`, `on_zoom_slider_release`)

**Constructor signature:**
```python
class PreviewTab:
    def __init__(self, notebook, cameras, camera_status, camera_profiles,
                 camera_references, save_camera_settings, is_recording):
```

**Dependencies to inject:**
- `cameras` dict, `camera_status` dict, `camera_profiles` dict, `camera_references` dict
- `save_camera_settings` callback
- `is_recording` lambda (to prevent preview during recording)
- Root window obtained via `notebook.winfo_toplevel()`

**Public API needed by main_window:**
- `update_preview_camera_dropdown()` — called when cameras connect/disconnect
- `cleanup_preview()` — called on app close
- `preview_active` property — checked by CalibrationTab and Recording logic

## Step 2: Extract `RecordingTab` → `code/GUI/recording_tab.py`

**What moves out:**
- `create_recording_tab()` UI code (lines 439–745)
- All recording methods (~300 lines): `toggle_recording`, `_start_recording`, `_stop_recording`, `recording_worker`, `start_camera_recording`, `stop_and_download`, `_auto_sync`, `start_timer`, `update_timer`, `refresh_recording_dropdowns`, `refresh_trial_tree`, `open_trial_folder`, `_on_new_participant`, `_on_calibration_selected`, `increment_trial_name`, `log_progress`, `reset_recording_ui`

**Constructor signature:**
```python
class RecordingTab:
    def __init__(self, notebook, config, cameras, camera_status, camera_serials,
                 project_manager, get_current_project, get_current_session,
                 save_camera_settings, load_camera_settings, save_config,
                 is_preview_active, is_calibration_recording):
```

**Dependencies to inject:**
- `cameras`, `camera_status`, `camera_serials` dicts
- `config` dict (resolution/FPS settings, last trial name)
- `project_manager` instance
- `get_current_project`, `get_current_session` lambdas (from ProjectTab)
- `save_camera_settings`, `load_camera_settings`, `save_config` callbacks
- `is_preview_active` lambda (mutual exclusion with preview)
- `is_calibration_recording` lambda (mutual exclusion with calibration recording)

**Public API needed by main_window:**
- `recording` property — checked by PreviewTab and CalibrationTab
- `refresh_recording_dropdowns()` — called when project/session changes
- `refresh_trial_tree()` — called after trial creation
- `log_progress(msg)` — used by CalibrationTab for shared progress display (verify this)

## Step 3: Update main_window.py

- Remove all extracted code (~540+ lines of methods, ~120 lines of UI)
- Replace `create_live_preview_tab()` and `create_recording_tab()` with tab instantiation (like existing pattern)
- Wire up cross-tab references via lambdas
- Update `__init__.py` exports if needed
- Move `LivePreviewCapture` class into `preview_tab.py`

## Step 4: Update CalibrationTab cross-references

CalibrationTab receives `is_recording` lambda — update to point to `RecordingTab.recording` instead of `main_window.recording`.

## Estimated reduction
main_window.py drops from ~1,842 lines to ~1,100–1,200 lines (~35% reduction).

## Verification
1. `python code/go2kin.py` — app launches, all 6 tabs visible
2. Preview tab: select camera, start/stop preview, zoom controls work
3. Recording tab: dropdowns populate, start/stop recording, timer works, trial tree updates
4. CalibrationTab recording still works (mutual exclusion guard intact)
5. Cross-tab interactions: preview blocked during recording and vice versa
6. App close: cleanup runs without errors
7. `python tests/test_project_manager.py` — existing tests pass

## Files to modify
- **Create:** `code/GUI/preview_tab.py`, `code/GUI/recording_tab.py`
- **Edit:** `code/GUI/main_window.py`, `code/GUI/__init__.py`
- **Possibly edit:** `code/GUI/calibration_tab.py` (if cross-tab lambda wiring changes)
