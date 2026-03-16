"""
Project/session/trial/subject file hierarchy manager for Go2Kin.

Handles all CRUD operations for the data directory structure.
All data lives outside the Go2Kin repo at a configurable root path.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Characters not allowed in project/session/trial/subject names
_INVALID_CHARS = set('\\/:*?"<>|')


def _validate_name(name: str) -> None:
    """Raise ValueError if name is empty or contains invalid characters."""
    if not name or not name.strip():
        raise ValueError("Name cannot be empty")
    if any(c in _INVALID_CHARS for c in name):
        raise ValueError(f"Name contains invalid characters: {name}")


class ProjectManager:
    """Manages the project/session/trial/subject file hierarchy."""

    def __init__(self, data_root: str):
        self.data_root = Path(data_root)
        self.data_root.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # Project operations
    # =========================================================================

    def list_projects(self) -> list[str]:
        """Return sorted list of project folder names under data_root."""
        return sorted(d.name for d in self.data_root.iterdir() if d.is_dir())

    def create_project(self, name: str) -> Path:
        """Create project folder with subjects/, calibrations/, sessions/ subfolders."""
        _validate_name(name)
        project_path = self.data_root / name
        if project_path.exists():
            raise ValueError(f"Project already exists: {name}")
        for sub in ("subjects", "calibrations", "sessions"):
            (project_path / sub).mkdir(parents=True)
        logger.info(f"Created project: {project_path}")
        return project_path

    def get_project_path(self, name: str) -> Path:
        """Return path to project folder. Raises FileNotFoundError if missing."""
        project_path = self.data_root / name
        if not project_path.is_dir():
            raise FileNotFoundError(f"Project not found: {name}")
        return project_path

    # =========================================================================
    # Subject operations
    # =========================================================================

    def list_subjects(self, project: str) -> list[dict]:
        """Return list of parsed subject JSON dicts."""
        subjects_dir = self.get_project_path(project) / "subjects"
        result = []
        for f in sorted(subjects_dir.glob("*.json")):
            with open(f) as fh:
                result.append(json.load(fh))
        return result

    def create_subject(
        self,
        project: str,
        subject_id: str,
        initials: str,
        age: int,
        sex: str,
        height_m: float,
        mass_kg: float,
        notes: str = "",
    ) -> Path:
        """Create a subject JSON file. Returns path to the file."""
        _validate_name(subject_id)
        filepath = self.get_project_path(project) / "subjects" / f"{subject_id}.json"
        if filepath.exists():
            raise ValueError(f"Subject already exists: {subject_id}")
        data = {
            "subject_id": subject_id,
            "initials": initials,
            "age": age,
            "sex": sex,
            "height_m": height_m,
            "mass_kg": mass_kg,
            "notes": notes,
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Created subject: {filepath}")
        return filepath

    def get_subject(self, project: str, subject_id: str) -> dict:
        """Load and return subject JSON dict."""
        filepath = self.get_project_path(project) / "subjects" / f"{subject_id}.json"
        if not filepath.exists():
            raise FileNotFoundError(f"Subject not found: {subject_id}")
        with open(filepath) as f:
            return json.load(f)

    def update_subject(self, project: str, subject_id: str, **kwargs) -> None:
        """Update specified fields in a subject JSON file."""
        filepath = self.get_project_path(project) / "subjects" / f"{subject_id}.json"
        if not filepath.exists():
            raise FileNotFoundError(f"Subject not found: {subject_id}")
        with open(filepath) as f:
            data = json.load(f)
        data.update(kwargs)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    # =========================================================================
    # Calibration operations
    # =========================================================================

    def list_calibrations(self, project: str) -> list[str]:
        """Return sorted list of calibration names (stems of .json files)."""
        calib_dir = self.get_project_path(project) / "calibrations"
        return sorted(f.stem for f in calib_dir.glob("*.json"))

    def get_calibration_path(self, project: str, name: str, fmt: str = "json") -> Path:
        """Return path to calibration file (.json or .toml)."""
        return self.get_project_path(project) / "calibrations" / f"{name}.{fmt}"

    def save_calibration(self, project: str, name: str, calib_data: dict) -> Path:
        """Save calibration data as JSON and generate TOML for Pose2Sim.

        Args:
            project: Project name
            name: Calibration name (without extension)
            calib_data: Calibration dict (may be partial — intrinsics only)

        Returns:
            Path to the saved JSON file
        """
        calib_dir = self.get_project_path(project) / "calibrations"
        calib_dir.mkdir(parents=True, exist_ok=True)

        json_path = calib_dir / f"{name}.json"
        with open(json_path, "w") as f:
            json.dump(calib_data, f, indent=2)
        logger.info(f"Calibration saved: {json_path}")

        # Generate TOML if any cameras have extrinsic data
        toml_content = self._generate_toml_content(calib_data)
        if toml_content:
            toml_path = calib_dir / f"{name}.toml"
            with open(toml_path, "w") as f:
                f.write(toml_content)
            logger.info(f"TOML exported: {toml_path}")
        else:
            logger.warning("No cameras with extrinsic data — TOML not generated")

        return json_path

    def get_latest_calibration(self, project: str) -> str | None:
        """Return name of the most recently modified calibration, or None."""
        calib_dir = self.get_project_path(project) / "calibrations"
        json_files = list(calib_dir.glob("*.json"))
        if not json_files:
            return None
        newest = max(json_files, key=lambda f: f.stat().st_mtime)
        return newest.stem

    def get_calibration_age_days(self, project: str, name: str) -> int:
        """Return days since calibration file was last modified."""
        filepath = self.get_calibration_path(project, name, "json")
        if not filepath.exists():
            raise FileNotFoundError(f"Calibration not found: {name}")
        age_seconds = datetime.now().timestamp() - filepath.stat().st_mtime
        return int(age_seconds / 86400)

    def _generate_toml_content(self, calib_data: dict) -> str:
        """Generate Pose2Sim-compatible TOML from calibration dict.

        Only includes cameras that have both rotation and translation data.
        Returns empty string if no cameras have extrinsic data.
        """
        lines = []
        for cam_id_str, cam in calib_data.get("cameras", {}).items():
            if "rotation" not in cam or "translation" not in cam:
                continue
            R = np.array(cam["rotation"], dtype=np.float64)
            rvec = cv2.Rodrigues(R)[0].flatten()
            t = cam["translation"]

            lines.append(f"[cam_{cam_id_str}]")
            lines.append(f"cam_id = {cam_id_str}")
            lines.append(f"rotation_count = {cam.get('rotation_count', 0)}")
            lines.append(f"error = {cam['error']}")
            lines.append(f"grid_count = {cam.get('grid_count', 0)}")
            lines.append(f"fisheye = {'true' if cam.get('fisheye') else 'false'}")
            lines.append(f"size = {cam['size']}")
            lines.append(f"matrix = {cam['matrix']}")
            lines.append(f"distortions = {cam['distortions']}")
            lines.append(f"translation = {list(t)}")
            lines.append(f"rotation = {rvec.tolist()}")
            lines.append("")

        return "\n".join(lines)

    # =========================================================================
    # Session operations
    # =========================================================================

    def list_sessions(self, project: str) -> list[str]:
        """Return sorted list of session folder names."""
        sessions_dir = self.get_project_path(project) / "sessions"
        return sorted(d.name for d in sessions_dir.iterdir() if d.is_dir())

    def create_session(self, project: str, name: str) -> Path:
        """Create session folder. Returns path."""
        _validate_name(name)
        session_path = self.get_project_path(project) / "sessions" / name
        if session_path.exists():
            raise ValueError(f"Session already exists: {name}")
        session_path.mkdir(parents=True)
        logger.info(f"Created session: {session_path}")
        return session_path

    def get_session_path(self, project: str, name: str) -> Path:
        """Return session path. Raises FileNotFoundError if missing."""
        session_path = self.get_project_path(project) / "sessions" / name
        if not session_path.is_dir():
            raise FileNotFoundError(f"Session not found: {name}")
        return session_path

    # =========================================================================
    # Trial operations
    # =========================================================================

    def list_trials(self, project: str, session: str) -> list[str]:
        """Return sorted list of trial folder names within a session."""
        session_path = self.get_session_path(project, session)
        return sorted(d.name for d in session_path.iterdir() if d.is_dir())

    def create_trial(
        self,
        project: str,
        session: str,
        trial_name: str,
        subject_id: str,
        calibration_file: str,
        cameras_used: list[str],
    ) -> Path:
        """Create trial folder with video/, processed/ subdirs and trial.json."""
        _validate_name(trial_name)
        trial_path = self.get_session_path(project, session) / trial_name
        if trial_path.exists():
            raise ValueError(f"Trial already exists: {trial_name}")

        (trial_path / "video").mkdir(parents=True)
        (trial_path / "processed").mkdir(parents=True)

        now = datetime.now()
        trial_data = {
            "trial_name": trial_name,
            "session_name": session,
            "subject_id": subject_id,
            "calibration_file": calibration_file,
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "cameras_used": cameras_used,
            "synced": False,
            "processed": False,
        }

        with open(trial_path / "trial.json", "w") as f:
            json.dump(trial_data, f, indent=2)

        logger.info(f"Created trial: {trial_path}")
        return trial_path

    def get_trial(self, project: str, session: str, trial_name: str) -> dict:
        """Load and return trial.json as dict."""
        trial_path = self.get_session_path(project, session) / trial_name
        json_path = trial_path / "trial.json"
        if not json_path.exists():
            raise FileNotFoundError(f"Trial not found: {trial_name}")
        with open(json_path) as f:
            return json.load(f)

    def update_trial(self, project: str, session: str, trial_name: str, **kwargs) -> None:
        """Update specified fields in trial.json."""
        trial_path = self.get_session_path(project, session) / trial_name
        json_path = trial_path / "trial.json"
        if not json_path.exists():
            raise FileNotFoundError(f"Trial not found: {trial_name}")
        with open(json_path) as f:
            data = json.load(f)
        data.update(kwargs)
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)

    def get_trial_video_path(self, project: str, session: str, trial_name: str) -> Path:
        """Return path to trial's video/ folder."""
        return self.get_session_path(project, session) / trial_name / "video"

    def get_trial_synced_path(self, project: str, session: str, trial_name: str) -> Path:
        """Return path to trial's video/synced/ folder."""
        return self.get_session_path(project, session) / trial_name / "video" / "synced"

    def get_trial_processed_path(self, project: str, session: str, trial_name: str) -> Path:
        """Return path to trial's processed/ folder."""
        return self.get_session_path(project, session) / trial_name / "processed"

    # =========================================================================
    # Tree view
    # =========================================================================

    def get_project_tree(self, project: str) -> dict:
        """Return nested dict representing the full project structure."""
        sessions = {}
        for session_name in self.list_sessions(project):
            trials = self.list_trials(project, session_name)
            sessions[session_name] = {"trials": trials}

        return {
            "project": project,
            "sessions": sessions,
        }
