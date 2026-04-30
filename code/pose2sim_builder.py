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

# Match the camera id in synced video filenames like "trial_001_GP3.mp4"
_VIDEO_CAM_RE = re.compile(r"_GP(\d+)\.(?:mp4|MP4)$")

# Anchored TOML section header — won't match a stray '[' inside an array value
_TOML_SECTION_RE = re.compile(r"^\[([A-Za-z0-9_]+)\]\s*$")


def _natural_sort_key(s):
    """Match Pose2Sim's common.natural_sort_key (used by its video glob)."""
    return [int(c) if c.isdigit() else c.lower()
            for c in re.split(r"(\d+)", str(s))]


def _filter_calibration_toml(src_toml, dest_toml, video_files):
    """Write a calibration TOML containing only the [cam_N] sections whose N
    appears in the staged video filenames, ordered to match the natural sort
    of those video basenames (which is how Pose2Sim globs them).

    Source of truth is the on-disk video filenames, not trial.json["cameras_used"]:
    a camera missing after sync should not appear in calibration even if it
    was nominally part of the trial.

    Returns the list of camera ids written, in output order.
    Raises ValueError if any video's camera id has no matching section in
    the calibration TOML, or if no video matches the expected naming pattern.
    """
    text = Path(src_toml).read_text(encoding="utf-8")

    # Split TOML into section blocks keyed by header (e.g. "cam_1").
    # Anything before the first section header is discarded — Go2Kin's calibration
    # TOMLs have no preamble.
    blocks = {}
    current_header = None
    current_lines = []
    for line in text.splitlines(keepends=True):
        m = _TOML_SECTION_RE.match(line.rstrip("\r\n"))
        if m:
            if current_header is not None:
                blocks[current_header] = "".join(current_lines)
            current_header = m.group(1)
            current_lines = [line]
        elif current_header is not None:
            current_lines.append(line)
    if current_header is not None:
        blocks[current_header] = "".join(current_lines)

    # Pair each video with its camera id, dropping any that don't match the pattern.
    matched = []
    for vf in video_files:
        m = _VIDEO_CAM_RE.search(vf.name)
        if m:
            matched.append((int(m.group(1)), vf))
    if not matched:
        raise ValueError(
            f"No videos in {video_files[0].parent if video_files else '?'} matched "
            f"the expected '_GP<N>.mp4' naming pattern."
        )

    matched.sort(key=lambda pair: _natural_sort_key(pair[1].name))

    cam_section_names = sorted(k for k in blocks if k.startswith("cam_"))
    out_chunks = []
    cam_ids = []
    for cid, vf in matched:
        key = f"cam_{cid}"
        if key not in blocks:
            raise ValueError(
                f"Trial uses camera {cid} (from video '{vf.name}') but calibration "
                f"'{Path(src_toml).stem}' has no [{key}] section. Calibration "
                f"contains: {cam_section_names}."
            )
        out_chunks.append(blocks[key])
        cam_ids.append(cid)

    Path(dest_toml).write_text("".join(out_chunks), encoding="utf-8")
    return cam_ids


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

    # 4. Stage calibration TOML, filtered to the cameras present in this trial
    dest_calib = calib_dir / "Calib.toml"
    cam_ids = _filter_calibration_toml(calib_toml, dest_calib, video_files)
    log(f"Staged calibration for cameras {cam_ids} -> {dest_calib.name}")

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
