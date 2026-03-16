# ProjectManager Architecture

## Purpose

Go2Kin generates large volumes of data across multiple cameras, sessions, and participants. Previously, all output lived in a flat `output/` folder inside the repo. The `ProjectManager` introduces a structured file hierarchy that:

- Separates data from code (data lives at a configurable root path, e.g. `D:/Markerless_Projects/`)
- Organises recordings into projects, sessions, and trials
- Tracks participant metadata and calibration files alongside recordings
- Provides the foundation for Pose2Sim integration (each trial's `processed/` folder becomes the Pose2Sim staging area)

The module is GUI-agnostic — it handles only file/folder operations and JSON serialization. GUI integration happens in later phases.

## Configuration: go2kin_config.json

Located at the Go2Kin repo root. Created manually on first setup.

```json
{
    "data_root": "D:/Markerless_Projects",
    "gopro_serial_numbers": ["C3501326042700", "C3501326054100", "C3501326054460", "C3501326062418"]
}
```

| Field | Description |
|---|---|
| `data_root` | Root directory for all project data. ProjectManager creates it if missing. |
| `gopro_serial_numbers` | GoPro serial numbers (will replace `config/cameras.json` in a future phase). |

## Directory Structure

All paths below are relative to `data_root`:

```
{project}/
  subjects/
    {subject_id}.json         # Participant metadata
  calibrations/
    {name}.json               # Calibration data (Go2Kin internal format)
    {name}.toml               # Calibration data (Pose2Sim format, auto-generated)
  sessions/
    {session_name}/
      {trial_name}/
        trial.json            # Trial metadata
        video/                # Raw MP4 recordings from GoPros
          synced/             # Audio-synced trimmed videos (created by audio_sync)
        processed/            # Pose2Sim staging area and output
```

## JSON Schemas

### Subject (`subjects/{subject_id}.json`)

```json
{
    "subject_id": "P01",
    "initials": "JD",
    "age": 25,
    "sex": "M",
    "height_m": 1.78,
    "mass_kg": 75.0,
    "notes": ""
}
```

### Trial (`sessions/{session}/{trial}/trial.json`)

Created automatically when a trial is recorded. `date` and `time` are set to the moment of creation.

```json
{
    "trial_name": "jump_01",
    "session_name": "2026-03-16-netball_jumps",
    "subject_id": "P01",
    "calibration_file": "2026-03-15_morning",
    "date": "2026-03-16",
    "time": "10:34:22",
    "cameras_used": ["cam1", "cam2", "cam3", "cam4"],
    "synced": false,
    "processed": false
}
```

Notes:
- `calibration_file` references a name in `calibrations/` (without extension). Can be `"none"` if recording without calibration.
- `synced` and `processed` are updated by downstream operations via `update_trial()`.

### Calibration

Uses the existing Go2Kin calibration JSON format (charuco config + per-camera intrinsic/extrinsic data). See `code/calibration/persistence.py` for the authoritative schema. A calibration can be partial — cameras without `rotation`/`translation` keys represent intrinsics-only data.

## API Reference

### Constructor

```python
ProjectManager(data_root: str)
```

Creates `data_root` if it doesn't exist.

### Project Operations

| Method | Returns | Description |
|---|---|---|
| `list_projects()` | `list[str]` | Sorted project folder names |
| `create_project(name)` | `Path` | Creates project with `subjects/`, `calibrations/`, `sessions/` subdirs |
| `get_project_path(name)` | `Path` | Returns path; raises `FileNotFoundError` if missing |

### Subject Operations

| Method | Returns | Description |
|---|---|---|
| `list_subjects(project)` | `list[dict]` | All parsed subject JSON dicts |
| `create_subject(project, subject_id, initials, age, sex, height_m, mass_kg, notes="")` | `Path` | Creates `{subject_id}.json` |
| `get_subject(project, subject_id)` | `dict` | Loads subject JSON |
| `update_subject(project, subject_id, **kwargs)` | `None` | Merges kwargs into existing JSON |

### Calibration Operations

| Method | Returns | Description |
|---|---|---|
| `list_calibrations(project)` | `list[str]` | Sorted calibration names (file stems) |
| `get_calibration_path(project, name, fmt="json")` | `Path` | Path to `.json` or `.toml` file |
| `save_calibration(project, name, calib_data)` | `Path` | Saves JSON + auto-generates TOML |
| `get_latest_calibration(project)` | `str \| None` | Name of newest calibration (by mtime) |
| `get_calibration_age_days(project, name)` | `int` | Days since last modification |

### Session Operations

| Method | Returns | Description |
|---|---|---|
| `list_sessions(project)` | `list[str]` | Sorted session folder names |
| `create_session(project, name)` | `Path` | Creates session directory |
| `get_session_path(project, name)` | `Path` | Returns path; raises `FileNotFoundError` if missing |

### Trial Operations

| Method | Returns | Description |
|---|---|---|
| `list_trials(project, session)` | `list[str]` | Sorted trial folder names |
| `create_trial(project, session, trial_name, subject_id, calibration_file, cameras_used)` | `Path` | Creates trial dir with `video/`, `processed/`, and `trial.json` |
| `get_trial(project, session, trial_name)` | `dict` | Loads `trial.json` |
| `update_trial(project, session, trial_name, **kwargs)` | `None` | Merges kwargs into `trial.json` |
| `get_trial_video_path(project, session, trial_name)` | `Path` | Path to `video/` |
| `get_trial_synced_path(project, session, trial_name)` | `Path` | Path to `video/synced/` (not pre-created) |
| `get_trial_processed_path(project, session, trial_name)` | `Path` | Path to `processed/` |

### Tree View

```python
get_project_tree(project) -> dict
```

Returns a nested dict for GUI tree views:

```python
{
    "project": "netball_study",
    "sessions": {
        "2026-03-16-netball_jumps": {
            "trials": ["jump_01", "jump_02"]
        }
    }
}
```

## Design Decisions

### Data outside the repo

All project data lives at `data_root` (configured in `go2kin_config.json`), not inside the Go2Kin repo. This keeps the repo clean and avoids accidentally committing large video files. It also allows multiple Go2Kin installations to share the same data directory.

### Single flat class

`ProjectManager` is one class rather than separate `ProjectManager`, `SessionManager`, etc. The hierarchy is simple enough that splitting would add complexity without benefit. All methods are stateless (no cached state beyond `data_root`) — they read/write the filesystem directly.

### Inline TOML generation

The TOML export logic is inlined in `_generate_toml_content()` rather than calling the existing `tools/export_toml.py` via subprocess. Rationale:

- `export_toml.py` is a CLI script that reads from a file path — calling it requires writing JSON to disk first, then invoking subprocess, then cleaning up. The ProjectManager already has the data in memory.
- The TOML generation logic is ~20 lines. Inlining avoids subprocess overhead and path resolution fragility.
- The inlined version adds graceful handling of partial calibrations (cameras without extrinsics are skipped in TOML output).

The `cv2.Rodrigues` call requires `dtype=np.float64` explicitly, since JSON-sourced data (e.g. identity matrix `[[1,0,0],...]`) produces Python ints that OpenCV rejects.

### Name validation

Project, session, trial, and subject names are validated against Windows-illegal filename characters (`\/:*?"<>|`). This prevents filesystem errors and keeps paths portable.

### Error handling

- Duplicate creation raises `ValueError`
- Missing entities raise `FileNotFoundError`
- All methods use `pathlib.Path` for cross-platform path handling

## Tests

41 unit tests in `tests/test_project_manager.py`. Uses `tempfile.TemporaryDirectory` for isolation.

```
python tests/test_project_manager.py
```

Coverage includes: CRUD for all entities, duplicate/missing error cases, full and partial calibration save/load, TOML generation, tree view, name validation, and `calibration_file="none"` handling.
