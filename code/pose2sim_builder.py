"""
Build Pose2Sim project directories from Go2Kin trials.

Creates the expected Pose2Sim folder structure from Go2Kin's project/session/trial
hierarchy (calibration, videos, Config.toml).
"""

import logging
import os
import re
import shutil


from pathlib import Path

logger = logging.getLogger(__name__)

# Path to the Config.toml template shipped with Go2Kin
_TEMPLATE_PATH = Path(__file__).parent.parent / "config" / "pose2sim_config_template.toml"

# Files to skip when copying synced videos
_SKIP_FILES = {"stitched_videos.mp4", "timestamps.csv", "audio_waveforms.png"}


def build_pose2sim_project(project_manager, project, session, trial_name):
    """Stage a Pose2Sim-compatible directory for a Go2Kin trial.

    Args:
        project_manager: ProjectManager instance
        project: Project name
        session: Session name
        trial_name: Trial name

    Returns:
        Path to the staging directory ([trial]/processed/)

    Raises:
        ValueError: If validation fails (missing videos, calibration, subject data)
    """
    pm = project_manager
    log = print

    # 1. Load trial data
    trial = pm.get_trial(project, session, trial_name)

    # 2. Validate inputs
    # Check synced videos
    synced_path = pm.get_trial_synced_path(project, session, trial_name)
    if not synced_path.exists():
        raise ValueError(f"Synced video folder does not exist: {synced_path}")

    video_files = [f for f in synced_path.iterdir()
                   if f.suffix.lower() == ".mp4" and f.name not in _SKIP_FILES]
    if not video_files:
        raise ValueError(f"No synced MP4 files found in {synced_path}")

    # Check calibration
    calib_name = trial.get("calibration_file", "none")
    if not calib_name or calib_name == "none":
        raise ValueError(f"Trial '{trial_name}' has no calibration file assigned")

    calib_toml = pm.get_calibration_path(project, calib_name, fmt="toml")
    if not calib_toml.exists():
        raise ValueError(f"Calibration TOML not found: {calib_toml}")

    # Check subject
    subject_id = trial.get("subject_id", "")
    if not subject_id:
        raise ValueError(f"Trial '{trial_name}' has no subject assigned")

    try:
        subject = pm.get_subject(project, subject_id)
    except FileNotFoundError:
        raise ValueError(f"Subject '{subject_id}' not found in project '{project}'")

    height = subject.get("height_m")
    mass = subject.get("mass_kg")
    if height is None or mass is None:
        raise ValueError(
            f"Subject '{subject_id}' missing height_m ({height}) or mass_kg ({mass})"
        )

    log(f"Validated: {len(video_files)} videos, calibration '{calib_name}', "
        f"subject '{subject_id}' ({height}m, {mass}kg)")

    # 3. Create staging directory
    processed_path = pm.get_trial_processed_path(project, session, trial_name)
    calib_dir = processed_path / "calibration"
    videos_dir = processed_path / "videos"
    calib_dir.mkdir(parents=True, exist_ok=True)
    videos_dir.mkdir(parents=True, exist_ok=True)

    # 4. Copy calibration TOML
    dest_calib = calib_dir / "Calib.toml"
    shutil.copy2(str(calib_toml), str(dest_calib))
    log(f"Copied calibration to {dest_calib.name}")

    # 5. Link or copy synced videos
    use_symlink = True
    for vf in video_files:
        dest = videos_dir / vf.name
        if dest.exists():
            dest.unlink()
        if use_symlink:
            try:
                os.symlink(str(vf), str(dest))
            except OSError:
                use_symlink = False
                log("Symlinks not available, falling back to file copy")
                shutil.copy2(str(vf), str(dest))
        else:
            shutil.copy2(str(vf), str(dest))

    method = "symlinked" if use_symlink else "copied"
    log(f"{method.capitalize()} {len(video_files)} video files")

    # 6. Generate Config.toml from template
    if not _TEMPLATE_PATH.exists():
        raise ValueError(f"Config.toml template not found at {_TEMPLATE_PATH}")

    template = _TEMPLATE_PATH.read_text(encoding="utf-8")

    # Substitute participant values
    template = re.sub(
        r"^participant_height\s*=\s*.*$",
        f"participant_height = '{height}'",
        template, count=1, flags=re.MULTILINE
    )
    template = re.sub(
        r"^participant_mass\s*=\s*.*$",
        f"participant_mass = {mass}",
        template, count=1, flags=re.MULTILINE
    )

    config_path = processed_path / "Config.toml"
    config_path.write_text(template, encoding="utf-8")
    log("Generated Config.toml")

    return processed_path
