# Go2Kin GUI Redesign — Implementation Plan

## Context

The current Go2Kin GUI has 6 tabs with a Project tab that should become a persistent top bar, no shared components between tabs, inline log widgets with broken piping, and two tabs (Recording, Live Preview) still inlined in `main_window.py`. The redesign plan in `docs/go2kin_ui_redesign.md` defines the target state. This implementation plan breaks it into sessions that each produce a **launchable, manually testable app**.

## Session Overview

| # | What | Testable outcome |
|---|------|-----------------|
| 0 | Prep: log cleanup + extract inline tabs | App launches, all output in terminal, no GUI log boxes |
| 1 | Top bar + remove Project tab | Top bar with cascading dropdowns, Project tab gone |
| 2 | Bottom bar + log placeholder | Manual/Speaker radio, log placeholder panel visible |
| 3 | Recording tab redesign (+ build shared trial list) | Big record button, countdown, trial list on right side |
| 4 | Calibration tab redesign | Collapsible pipeline, one-button extrinsic flow |
| 5 | Processing tab redesign | Flat trial list with shared component, big Process button |
| 6 | Visualisation + Live Preview | Shared trial list in Vis, zoom warning in Preview |

---

## Session 0: Prep — Log Cleanup + Extract Inline Tabs

**Goal**: Remove all GUI log widgets. Extract Recording and Live Preview tabs into own files. Pure refactor — identical behavior, cleaner structure.

### Step 0a: Log cleanup (DO FIRST)

**`code/GUI/main_window.py`** — Recording tab inline:
- Remove `progress_frame` + `progress_text` (lines 547-560)
- Remove `log_progress()` method (line 1911)
- Replace all `self.log_progress(msg)` calls with `print(msg)` and `self.log_progress(msg, "warning")` with `print(f"WARNING: {msg}")`

**`code/GUI/processing_tab.py`**:
- Remove `log_frame` (lines 97-115), `log()` method (line 222), `log_progress()` method (line 235), `_clear_log()` method (line 266), `_progress_marks` state (line 37)
- Remove Clear Log button (lines 101-104)
- Replace `self.log(...)` → `print(...)` (~20 call sites)
- Replace `log_callback=self.log` → `log_callback=print` in pose2sim_builder calls
- Replace `progress_callback=self.log_progress` → `progress_callback=lambda key, msg: print(msg)`

**User test**: Launch app. Recording and Processing tabs have no log text boxes. All output appears in the terminal window. Everything else works as before.

### Step 0b: Extract LivePreviewTab

**Create `code/GUI/live_preview_tab.py`**:
- Move `LivePreviewCapture` class (lines 30-112)
- Create `LivePreviewTab` class with all preview UI + methods:
  - UI: `create_live_preview_tab` (lines 349-425)
  - Methods: `start_preview`, `stop_preview`, `update_preview_camera_dropdown`, `update_video_display`, `cleanup_preview`, all zoom methods (lines 1177-1530ish)
- Constructor: `LivePreviewTab(notebook, cameras, camera_status, camera_serials)`

**Update `code/GUI/main_window.py`**:
- `create_live_preview_tab()` → import + instantiate `LivePreviewTab`
- `cleanup_preview()` → delegate to `self.live_preview_tab.cleanup_preview()`

### Step 0c: Extract RecordingTab

**Create `code/GUI/recording_tab.py`**:
- Move all recording UI (lines 471-579) and logic methods:
  - `toggle_recording`, `_start_recording`, `_stop_recording`, `recording_worker`
  - `_auto_sync`, `refresh_recording_dropdowns`, `_update_calibration_age_label`
  - `_on_calibration_selected`, `refresh_trial_tree`, `_clear_trial_tree`
  - `_on_new_participant`, `open_trial_folder`, `start_camera_recording`, `stop_and_download`
  - `start_timer`, `update_timer`, `reset_recording_ui`, `increment_trial_name`
- Move `self.recording` bool, `self._current_trial_info`, `self._last_trial_video_dir` state into RecordingTab
- Constructor receives callbacks: `project_manager, cameras, camera_status, camera_serials, config, get_current_project, get_current_session, is_calib_recording, run_rec_delay, start_bar_timer, stop_bar_timer, play_sync_sound, save_camera_settings, save_app_config, get_calibration_tab`

**Update `code/GUI/main_window.py`**:
- `create_recording_tab()` → import + instantiate `RecordingTab`
- `is_recording` property → delegate to `self.recording_tab.recording`
- `_on_tab_changed` stays in main_window but calls `self.recording_tab.refresh_recording_dropdowns()` etc.

**User test**: Launch app. All 6 tabs work identically to before. Recording works. Preview works. File structure is now modular.

---

## Session 1: Persistent Top Bar + Remove Project Tab

**Create `code/GUI/top_bar.py`** — new `TopBar` class:
- Constructor: `TopBar(parent, project_manager, app_config, save_config_callback, on_selection_changed)`
- Widgets:
  - Project combobox + "+" button
  - Session combobox + "+" button
  - Participant combobox + "+" button
  - Calibration status label (name + age: "initial — 3d")
  - Gear button → opens management dialog (subject table from ProjectTab, calibration management)
- Cascading enablement: no project → session/participant disabled
- Methods: `get_current_project()`, `get_current_session()`, `get_current_participant()`, `refresh()`, `_restore_last_selection()`
- `on_selection_changed` callback notifies main_window which propagates to tabs

**Modify `code/GUI/main_window.py`**:
- In `create_widgets()`: create TopBar frame packed above notebook
- Remove `create_project_tab()` call
- Tab order: Live Preview | Calibration | Recording | Processing | Visualisation
- `get_current_project()` / `get_current_session()` delegate to `self.top_bar`
- Update all lambdas passed to tabs: `lambda: self.project_tab.get_current_project()` → `lambda: self.top_bar.get_current_project()`
- `_on_tab_changed`: update tab index references (or use name-based lookup)

**Delete or archive `code/GUI/project_tab.py`** — migrate subject table UI into gear dialog within TopBar.

**User test**: Launch app. Top bar visible. Create project via "+", then session, then participant — cascading enablement works. Gear icon opens management. Selection persists on restart. No Project tab. All other tabs still work.

---

## Session 2: Bottom Bar Updates + Log Placeholder

**Modify `code/GUI/main_window.py`** — `create_camera_bottom_bar()`:
- Replace `sync_sound_checkbox` with `ttk.Radiobutton` pair: "Manual" / "Speaker", bound to `self.sync_method_var = tk.StringVar(value="manual")`
- Update `_play_sync_sound` to check `sync_method_var.get() == "speaker"`

**Modify `code/GUI/main_window.py`** — add log placeholder:
- New frame between notebook and camera bar
- Pack order: camera bar (BOTTOM), log panel (BOTTOM), notebook (BOTH expand)
- Static `tk.Text`, 3-4 lines, disabled, showing "Output is shown in the terminal"
- Three filter labels (Cal / Rec / Proc) — visual only

**User test**: Launch app. Bottom bar shows Manual/Speaker radio buttons. Log placeholder visible between tabs and camera bar. Recording still works with correct sync mode.

---

## Session 3: Shared Trial List + Recording Tab Redesign

### Build shared component

**Create `code/GUI/components/__init__.py`** (empty)

**Create `code/GUI/components/session_trials_list.py`** — `SessionTrialsList`:
- Constructor: `SessionTrialsList(parent, project_manager, get_project, get_session, extra_columns=None, on_select=None, on_delete=None)`
- Base columns: Trial Name, Sync Status (✅/🟡)
- `extra_columns`: list of (name, width) tuples for tab-specific columns
- `ttk.Treeview` with scrollbar, Delete button
- Methods: `refresh()`, `get_selected()`, `select_trial(name)`, `set_extra_data(trial_name, col, value)`
- Sync status from `trial.json` → `synced` field
- Tag-based coloring for status indicators

### Redesign Recording tab

**Rewrite `code/GUI/recording_tab.py`**:
- Layout: left panel (trial setup + big record) | right panel (SessionTrialsList)
- **Trial name**: large Entry with bigger font (14pt+), prominent
- **Record button**: `tk.Button` (not ttk), ~80px tall, grey idle / red recording
- **Countdown**: 5-second countdown display before recording starts (large centered text)
- **Recording state**: red button with "STOP", red timer "02:34", visual tab-wide state change
- **Trial setup**: participant dropdown, calibration dropdown with age hint, camera checkboxes, sound source X/Y/Z (shown only if sync method == "manual")
- **Post-recording**: auto-sync, trial appears in list, trial name auto-advances
- Remove: Open Trial Folder button

**User test**: Launch app → Recording tab. Big record button visible. Connect cameras, set trial name, record. Countdown appears, button turns red, timer shows. Stop → videos download, sync runs, trial appears in list with ✅/🟡. Trial name advances. Delete trial from list works.

---

## Session 4: Calibration Tab Redesign

**Rewrite `code/GUI/calibration_tab.py`** — UI layout only, preserve all backend calibration logic.

### Collapsible section helper
Simple widget: clickable header with arrow (▸/▾), content frame that shows/hides, status line visible when collapsed.

### Layout (left column, top to bottom)
1. **Load/Save bar**: Load, Save buttons + calibration name
2. **Charuco Board Config**: collapsed by default, status "Board: 7x5, 11.7cm"
3. **Intrinsics**: collapsed by default, status "4/4 cameras, RMSE < 0.8px". Per-camera Record/Browse/Calibrate when expanded.
4. **Extrinsics**: always visible. Single "Calibrate Extrinsics" button → countdown → record → stop → download → sync → calibrate. Sound source X/Y/Z inline. Status indicator.
5. **Set Origin**: enabled after extrinsics. Same one-button flow. Sound source inline.
6. **Apply**: enabled after all steps. Auto-saves with timestamp. Updates top bar.

### Right column
3D camera plot (existing matplotlib embed). Updates after extrinsic and origin steps.

### Automated extrinsic flow
Background thread: countdown → start recording → user clicks Stop → download → audio sync → run extrinsic calibration → display result. If sync fails → warning popup. If quality poor → amber/red indicator. Auto-delete temp videos on success.

**User test**: Launch app → Calibration tab. Pipeline layout visible. Charuco/Intrinsics collapsed with status. Run extrinsic calibration end-to-end. Set Origin enables after. Apply commits calibration, top bar updates.

---

## Session 5: Processing Tab Redesign

**Rewrite `code/GUI/processing_tab.py`**:
- Replace grouped treeview with `SessionTrialsList` (from Session 3), adding "Processing" extra column
- Shows current session only (session from top bar)
- Processing status: ⚫ Pending | 🔄 Processing | ✅ Processed | ❌ Failed
- Select All / Deselect All / Delete buttons above list
- Large "PROCESS SELECTED" button (colored, prominent)
- `ttk.Progressbar` + step label below ("pose detection 2/4 cameras")
- Event-driven refresh: bind to `<<TrialRecorded>>` and `<<TrialProcessed>>` virtual events

**User test**: Launch app → Processing tab. Flat list of current session trials. Select trials, click Process. Progress bar updates. Status changes to Processed.

---

## Session 6: Visualisation + Live Preview

**Modify `code/GUI/visualisation_tab.py`**:
- see /docs/go2kin_ui_redesign.md, "Visualisation Tab" section
- Project/session from top bar, no local dropdowns
- `on_select` triggers video load

**Modify `code/GUI/live_preview_tab.py`**:
- Add persistent warning label below zoom controls: bold orange text "Changing zoom requires recalibrating intrinsics"

**User test**: Launch app. Visualisation uses shared trial list — select trial, video loads. Preview shows zoom warning.

---

## Cross-Session Communication

Tabs communicate via:
1. **Constructor-injected callables** (existing pattern, preserved)
2. **Virtual events** on root (new):
   - `<<ProjectChanged>>` / `<<SessionChanged>>` — fired by TopBar
   - `<<TrialRecorded>>` — fired by RecordingTab
   - `<<TrialProcessed>>` — fired by ProcessingTab
3. **Direct method calls** for sync queries: `top_bar.get_current_project()`

---

## Progress Log

### Session 0a — 2026-03-25 ✅
- Completed: Log cleanup in main_window.py and processing_tab.py. Removed all GUI log widgets (Progress Log in Recording tab, Log in Processing tab). Replaced ~54 self.log_progress() calls and ~15 self.log() calls with print(). Removed _LogForwarder, _StreamRedirector, and related infrastructure from pose2sim_builder.py. Removed log_callback/progress_callback params from build_pose2sim_project() and run_pose2sim_pipeline(). Removed use_custom_logging override so Pose2Sim handles its own logging.
- Deviations: Had to also clean up pose2sim_builder.py — passing print as log_callback caused infinite recursion because _StreamRedirector replaced sys.stdout. Resolved by removing all log redirection infrastructure (no longer needed without GUI log widgets).
- State: App launches, no GUI log boxes. All output in terminal including Pose2Sim logging. Processing works end-to-end.

### Session 0b/0c — 2026-03-25 ✅
- Completed: Extracted LivePreviewTab and RecordingTab from main_window.py into own files.
  - Created `code/GUI/live_preview_tab.py` with `LivePreviewCapture` + `LivePreviewTab` classes (all preview UI, zoom controls, streaming logic).
  - Created `code/GUI/recording_tab.py` with `RecordingTab` class (all recording UI, trial management, sync sound, bar timer, auto-sync).
  - main_window.py reduced from 1922 to 816 lines. All 6 tabs now in separate files.
  - Updated cross-references: `update_camera_status()` delegates checkbox/dropdown updates, `on_closing()` delegates to both tabs, `_on_tab_changed()` uses frame-based identification, `save_camera_settings()` reads trial name from recording_tab, `create_calibration_tab()` uses lazy lambdas for recording callbacks.
  - Removed unused imports from main_window.py: cv2, PIL, queue, sounddevice, numpy, concurrent.futures.
- Deviations: None. Followed plan exactly.
- State: App launches, all 6 tabs work identically to before. File structure is now fully modular. 41 unit tests pass.

### Session 1 — 2026-03-25 ✅
- Completed: Persistent top bar replaces Project tab.
  - Created `code/GUI/top_bar.py` with `TopBar` class: Project/Session/Participant dropdowns with cascading enablement, "+" buttons for creating new entities (project/session name dialogs, full subject form for participant), calibration status indicator (colored circle: green <1d, amber 1+d, red none), "Manage" button opening modal subject table dialog, auto-restore of last selection on launch.
  - Modified `code/GUI/main_window.py`: replaced `create_project_tab()` with `create_top_bar()`, updated all lambda callbacks from `self.project_tab` to `self.top_bar`, added `get_current_participant()`, wired `on_calibration_saved` callback. Tab order now 5 tabs: Live Preview, Calibration, Recording, Processing, Visualisation.
  - Modified `code/GUI/calibration_tab.py`: added `on_calibration_saved` callback parameter, called after save and load to refresh top bar calibration indicator.
  - `code/GUI/project_tab.py` kept as unused reference (no longer imported).
- Deviations: None. Followed plan exactly.
- State: App launches, top bar visible with cascading dropdowns. Project tab gone. All 5 tabs work. Last selection auto-restores on launch. 41 unit tests pass.

### Session 2 — 2026-03-25 ✅
- Completed: Bottom bar updates + log placeholder.
  - Modified `code/GUI/main_window.py`: replaced disabled sync sound checkbox with Manual/Speaker radio buttons bound to `self.sync_method_var` (StringVar, default "manual"). Added `create_log_panel()` method: `ttk.LabelFrame` with [Cal][Rec][Proc] filter labels (visual only) and disabled `tk.Text` placeholder showing "Output is shown in the terminal". Pack order: camera bar (BOTTOM), log panel (BOTTOM), top bar (TOP), notebook (BOTH expand).
  - Modified `code/GUI/recording_tab.py`: renamed constructor param `sync_sound_enabled` → `sync_method_var`. Updated `_play_sync_sound()` to check `sync_method_var.get() != "speaker"` instead of `sync_sound_enabled.get()`.
- Deviations: None. Followed plan exactly.
- State: App launches, log placeholder visible above camera bar, Manual/Speaker radio buttons in camera bar. All 5 tabs work. 41 unit tests pass.

### Session 3 — 2026-03-25 ✅
- Completed: Shared trial list component + Recording tab redesign.
  - Created `code/GUI/components/` package with `session_trials_list.py`: reusable `SessionTrialsList` widget with 5 columns (Trial, Participant, Sync, Calib, Processed), checkbox selection (unicode ☐/☑), Select All/Deselect All/Delete Selected buttons. Queries ProjectManager directly via callbacks.
  - Added `delete_trial()` method to `code/project_manager.py` (shutil.rmtree with confirmation in UI).
  - Rewrote `code/GUI/recording_tab.py` UI: removed participant/calibration dropdowns (now in top bar), removed Open Trial Folder button, removed old session→trial tree. New layout: SessionTrialsList at top, big trial name entry (Arial 14), camera checkboxes, sound source X/Y/Z fields (persisted to app_config, wired into auto-sync), large green tk.Button RECORD that turns red/STOP during recording, large timer display. All backend logic preserved unchanged.
  - Added `get_current_participant` callback to RecordingTab constructor, wired from main_window via top bar.
  - Added `on_selection_changed` callback to TopBar — fires when project or session changes, triggers `_refresh_active_tab()` in main_window to refresh whichever tab is currently visible (recording, processing, or visualisation).
  - Added visualisation tab refresh to `_on_tab_changed()`.
- Deviations: Sound source fields always visible (manual mode assumed for now; speaker mode bottom bar fields deferred). TopBar callback added to fix live refresh (not in original Session 3 plan but needed for correct behavior).
- State: App launches, recording tab has new cockpit layout. Session trials list refreshes on tab switch and on top bar project/session change. 41 unit tests pass.

### Session 3b — 2026-03-25 ✅
- Completed: SessionTrialsList visual overhaul — colored status indicators + date column + sort order.
  - Replaced `ttk.Treeview` with `tk.Canvas` + scrollable `tk.Frame` to enable per-cell colored text (tkinter's GDI renderer doesn't support color emoji in Treeview value columns).
  - Sync/Cal/Proc columns now show colored `●` (U+25CF) circles: green = OK, red = not synced/failed, grey = pending/none. No text, just circles.
  - Added "Date" column (between Trial and Participant) showing `YYYY-MM-DD HH:MM` from `trial.json` date+time fields.
  - Trials sorted newest-first by date+time.
  - Alternating row backgrounds (white/light grey), green highlight on checked rows.
  - Column headers left-aligned. Fixed-width columns for Date, Participant, Sync, Cal, Proc; Trial column stretches.
  - Same public API preserved (`refresh()`, `get_checked_trials()`, `frame`) — no caller changes needed.
- Deviations: Header alignment required placing header inside the canvas interior frame (same grid as data rows). Circles kept at font size 16 (larger sizes stretch row height too much).
- State: App launches, Recording tab shows colored status circles and date column. Newest trials on top. Processing tab will reuse same component in Session 5.

### Session 4 — 2026-03-25 ✅
- Completed: Calibration tab redesign with pipeline layout.
  - Created `code/GUI/components/collapsible_section.py`: reusable `CollapsibleSection` widget with clickable header (▸/▾ arrow), colored status circle indicator, status text. Used for Charuco and Intrinsic sections.
  - Rewrote `code/GUI/calibration_tab.py` UI: pipeline layout with Load/Save bar at top, collapsible Charuco Board Config and Intrinsic Calibration sections (with live status), always-visible Extrinsic Calibration and Set Origin sections, new Apply Calibration button at bottom.
  - One-button automated flows for extrinsic and origin: click → 5s countdown → record → user clicks Stop → download → audio sync → calibrate/set-origin → update 3D viewer. Auto-deletes temp videos on success.
  - Sound source X/Y/Z fields moved inline into Extrinsic and Origin sections (shared variables, no standalone section). Fields read silently before sync — no explicit Set/Clear buttons.
  - Apply Calibration button: auto-saves with timestamp name (`calibration_YYYY-MM-DD-HH-MM.json`), updates top bar. Separates "got a result" from "commit the result".
  - Pipeline state management: buttons enable/disable based on calibration progress (intrinsics → extrinsics → origin → apply). Status indicators show green/amber/red based on RMSE quality.
  - Added `sync_method_var` parameter to CalibrationTab constructor, wired from main_window.py.
  - All backend calibration logic preserved unchanged (charuco, intrinsic, extrinsic, origin, sync, 3D viewer, save/load, auto-load).
- Deviations from plan:
  - Removed Browse Folder fallback buttons (not needed — simplified UI).
  - Removed camera selection checkboxes for extrinsic/origin — now uses all connected cameras automatically.
  - Renamed "Calibrate Extrinsics" → "Calibrate". Unified button sizes across Calibrate, Set Origin, Apply.
  - Centred sound source fields and action buttons in each section for visual alignment.
  - Removed redundant `run_rec_delay()` call from multi-record worker (was blocking before cameras started; the 5s countdown already serves this purpose). Added print() logging to match Recording tab's terminal output pattern.
  - Fixed STOP button not working: buttons were left in `state="disabled"` from countdown phase when switching to STOP mode.
- State: App launches, calibration tab functional with pipeline layout. Automated extrinsic and origin flows work end-to-end. 41 unit tests pass.

### Session 5 — 2026-03-26 ✅
- Completed: Processing tab redesign with shared SessionTrialsList and pipeline progress indicators.
  - Rewrote `code/GUI/processing_tab.py`: replaced custom Treeview with `SessionTrialsList` (identical appearance/position to Recording tab). Added pipeline progress section with 5 step labels (Calibration, Pose Estimation, Triangulation, Filtering, Kinematics) each with grey/green circle indicator. Large green "PROCESS SELECTED" button (same style as Recording tab's RECORD) toggles to red "CANCEL" during processing. Context label shows current trial + progress count.
  - Pipeline execution now inline (replaced `run_pose2sim_pipeline` delegation) so step circles update in real-time after each step completes.
  - Updated `code/GUI/main_window.py`: changed `refresh_tree()` → `refresh()` in `_refresh_active_tab()`.
- Deviations: Pipeline steps displayed horizontally (not vertically) to keep the layout compact. Pipeline execution inlined rather than delegating to `run_pose2sim_pipeline()` to enable per-step UI updates.
- State: App launches, processing tab has shared trial list matching recording tab. Pipeline steps show grey/green progress. 41 unit tests pass.

### Session 6 — 2026-03-26 ✅
- Completed: Visualisation tab redesign + Live Preview zoom warning.
  - Rewrote `code/GUI/visualisation_tab.py`: removed project/session dropdowns and all related methods (`_populate_projects`, `_on_project_selected`, `_populate_sessions`, `_on_session_selected`, `_populate_trials`, `_clear_trial_list`, `_on_trial_selected`). Replaced with shared `SessionTrialsList` component in left sidebar. Trial selection via `on_select` callback. Project/session now read from top bar via `get_current_project()`/`get_current_session()` getters (~15 replacements). Added `refresh()` public method that clears video and refreshes trial list.
  - Modified `code/GUI/live_preview_tab.py`: added persistent bold orange warning label "⚠ Changing zoom requires recalibrating intrinsics" between control bar and video area.
  - Modified `code/GUI/main_window.py`: changed `_refresh_active_tab()` to call `visualisation_tab.refresh()` instead of `visualisation_tab._populate_projects()`.
- Deviations: None. Followed plan exactly.
- State: App launches, visualisation tab uses shared SessionTrialsList with colored status circles. No project/session dropdowns. Live Preview shows zoom warning. 41 unit tests pass.

### TODO (future sessions)
