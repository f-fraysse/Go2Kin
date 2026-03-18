# Phase 4: Pose2Sim Processing Tab

## Context

Read `redesign_plan_16_03_2026_updated.md` for the full redesign plan. Completed so far:
- Phase 1: `code/project_manager.py` (ProjectManager class)
- Phase 1b: Project tab in GUI (project/session selection, subject management)
- Phase 2a: Camera settings bottom bar
- Phase 2b: Recording tab rework (new file structure, auto-sync, trial.json)
- Phase 3: Calibration tab rework (record buttons, save/load to project path)

All infrastructure is in place. Trials are saved to `[project]/sessions/[session]/[trial]/` with video files in `video/synced/`, calibration files in `[project]/calibrations/`, and subject data in `[project]/subjects/`. Each trial has a `trial.json` with `subject_id` and `calibration_file` references.

Pose2Sim is installed as a git submodule at `code/pose2sim/` and available via `from Pose2Sim import Pose2Sim`.

This phase adds a new "Processing" tab that runs the Pose2Sim pipeline on recorded trials.

## What Pose2Sim needs

Pose2Sim expects a specific directory structure and a `Config.toml` file. It operates on relative paths from within the project directory. The pipeline steps are:

```python
from Pose2Sim import Pose2Sim
Pose2Sim.calibration()
Pose2Sim.poseEstimation()
Pose2Sim.triangulation()
Pose2Sim.filtering()
Pose2Sim.kinematics()
```

Each function reads `Config.toml` from the current working directory. The expected folder structure for a single trial is:

```
[pose2sim_project]/
├── calibration/
│   └── Calib.toml              # calibration file
├── videos/
│   ├── cam1.mp4                # synced video files
│   ├── cam2.mp4
│   ├── cam3.mp4
│   └── cam4.mp4
├── Config.toml                 # pipeline configuration
├── pose/                       # created by poseEstimation
├── pose-3d/                    # created by triangulation
└── kinematics/                 # created by kinematics
```

For reference, a working example of this structure exists at `D:\PythonProjects\Go2Kin\code\pose2sim\Pose2Sim\example_trial`. This folder contains all output after the pose2sim pipeline has been run. I have run the pose2sim pipeline manually from this folder by running main_entry.py, confirmed working. Use this as reference for the expected Config.toml format and output structure.

## What to build

### 1. Project builder module

Create `code/pose2sim_builder.py` with a function that stages a Pose2Sim project for a given trial.

```python
def build_pose2sim_project(
    project_manager: ProjectManager,
    project: str,
    session: str,
    trial_name: str
) -> Path:
```

This function:

1. **Reads trial.json** to get `subject_id` and `calibration_file`
2. **Validates inputs:**
   - Synced video files exist in `[trial]/video/synced/`
   - Calibration file exists (check `calibration_file` is not `"none"` and the `.toml` file exists in `[project]/calibrations/`)
   - Subject file exists and has `height_m` and `mass_kg`
   - If any validation fails, raise a clear error message
3. **Creates staging directory** at `[trial]/processed/` reproducing the Pose2Sim structure:
   ```
   [trial]/processed/
   ├── calibration/
   │   └── Calib.toml
   ├── videos/
   │   ├── xxxx_GP1.mp4 (symlink or copy)
   │   ├── xxxx_GP2.mp4
   │   ├── xxxx_GP3.mp4
   │   └── xxxx_GP4.mp4
   └── Config.toml
   ```
4. **Calibration file:** Copy the `.toml` calibration file from `[project]/calibrations/` into `processed/calibration/` (Pose2Sim expects this location). Use a file copy, not symlink.
5. **Video files:** Try to create symlinks from `[trial]/video/synced/*.mp4` into `processed/videos/`. If symlinks fail (Windows permissions), fall back to copying the files. Log which method was used.
6. **Config.toml:** Generate a `Config.toml` file with:
   - Participant height and mass from subject.json
   - All other parameters set to  defaults (use the working Config.toml from `D:\PythonProjects\Go2Kin\code\pose2sim\Pose2Sim\example_trial\Config.toml` as the template — copy it into the Go2Kin repo at `config/pose2sim_config_template.toml` as a reference)
   - For now, only `participant_height` and `participant_mass` are populated dynamically. Everything else uses template defaults.
7. **Returns** the path to the staging directory (`[trial]/processed/`)

### 2. Pipeline runner

Create a function in `code/pose2sim_builder.py` (or a separate `code/pose2sim_runner.py`) that runs the pipeline:

```python
def run_pose2sim_pipeline(
    processed_path: Path,
    log_callback: callable = None
) -> bool:
```

This function:

1. Changes working directory to `processed_path` (Pose2Sim requires this)
2. Redirects Pose2Sim's logging/print output to `log_callback` if provided (for GUI display). Pose2Sim uses Python's `logging` module — capture its log output. Also capture stdout/stderr as Pose2Sim may print directly.
3. Calls each step in sequence:
   ```python
   Pose2Sim.calibration()
   Pose2Sim.poseEstimation()
   Pose2Sim.triangulation()
   Pose2Sim.filtering()
   Pose2Sim.kinematics()
   ```
4. If any step fails, logs the error and stops (do not continue to next step)
5. Restores the original working directory after completion (use try/finally)
6. Returns `True` on success, `False` on failure

### 3. Processing tab GUI

Create `code/GUI/processing_tab.py` with a new tab added to the Notebook.

**Layout:**

**Top section — Trial selection:**
- Tree view (`ttk.Treeview`) showing sessions and trials for the current project
- Populated from `project_manager.get_project_tree(current_project)`
- Top-level items: session names
- Under each session: trial names
- Checkboxes for each trial (use treeview with checkbutton pattern, or a separate checkbox column)
- "Select All" / "Deselect All" buttons
- Option to select/deselect all trials within a session (clicking session checkbox toggles all its trials)
- Refresh when project changes in the Project tab

**Middle section — Log output:**
- Scrollable text widget (same style as Recording tab log)
- Displays Pose2Sim terminal output in real time as the pipeline runs
- Clear button to reset the log

**Bottom section — Controls:**
- "Process Selected" button: runs the pipeline on all checked trials
- For batch processing: processes trials sequentially (one at a time)
- Button is disabled while processing is running
- "Stop" button to cancel processing (stops after current trial completes, does not interrupt mid-step)

**Processing flow when user clicks "Process Selected":**

1. For each selected trial:
   a. Display "Setting up [trial_name]..." in log
   b. Call `build_pose2sim_project()` to stage files
   c. If staging fails (missing calibration, missing videos, etc.), log the error, skip this trial, continue to next
   d. Display "Processing [trial_name]..." in log
   e. Call `run_pose2sim_pipeline()` with a callback that writes to the log widget
   f. On success: update `trial.json` with `processed: true` via `project_manager.update_trial()`
   g. On failure: log the error, continue to next trial
2. After all trials: display summary (X of Y trials processed successfully)

**Threading:** The pipeline is long-running (minutes per trial). Run it in a background thread so the GUI stays responsive. The log callback must update the text widget safely from the background thread (use `widget.after()` or a queue).

### 4. Wire into main window

Modify `code/GUI/main_window.py` to:
- Add the Processing tab to the Notebook (after Recording, before or after Calibration — use a sensible tab order: Project, Preview, Calibration, Recording, Processing)
- Pass `ProjectManager` and reference to Project tab to the Processing tab

### 5. Config template

Copy the working `Config.toml` from `D:\PythonProjects\Go2Kin\code\pose2sim\Pose2Sim\example_trial` into the Go2Kin repo at `config/pose2sim_config_template.toml`. The project builder reads this template and substitutes participant-specific values. This template file is committed to the repo.

If this file does not exist or is not accessible, create a minimal Config.toml based on the Pose2Sim demo Config.toml available in the pose2sim submodule at `D:\PythonProjects\Go2Kin\code\pose2sim\Pose2Sim\example_trial`.

## What NOT to do

- Do NOT modify any Pose2Sim source code (it's a submodule — treat as read-only)
- Do NOT modify the Project tab, Recording tab, Calibration tab, Preview tab, or camera bottom bar
- Do NOT expose Config.toml options in the GUI beyond participant height and mass (future work)
- Do NOT implement structured progress display with tick marks and metrics (future work — for now just stream log output)
- Do NOT implement file management / video deletion after processing (future work)
- Do NOT modify `project_manager.py` unless a small addition is needed (e.g. a missing helper method)

## File locations

- New files: `code/GUI/processing_tab.py`, `code/pose2sim_builder.py`, `config/pose2sim_config_template.toml`
- Modify: `code/GUI/main_window.py` (add Processing tab)
- Reference: `code/project_manager.py` (all file operations)
- Reference: `code/GUI/project_tab.py` (get current project)
- Reference: `code/pose2sim/Pose2Sim/Demo_SinglePerson/Config.toml` (template reference)
- Reference: `D:\PythonProjects\pose2sim\Pose2Sim\test_messing\` (working example of pipeline output)

## Testing

After implementation, verify manually:
- Open Processing tab → tree view shows sessions and trials for current project
- Select a trial with valid synced videos, calibration, and subject → click Process → pipeline runs, log output streams in real time
- Check `[trial]/processed/` folder contains expected Pose2Sim output structure (pose/, pose-3d/, kinematics/)
- `trial.json` updated with `processed: true` after success
- Select a trial with missing calibration → clear error message, trial skipped
- Select a trial with missing synced videos → clear error message, trial skipped
- Select multiple trials → processes sequentially, summary at end
- GUI stays responsive during processing (can switch tabs, scroll log)
- Stop button works (waits for current trial to finish, then stops)
- Switch project in Project tab → tree view refreshes
