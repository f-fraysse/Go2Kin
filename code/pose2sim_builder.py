"""
Build Pose2Sim project directories from Go2Kin trials and run the pipeline.

Creates the expected Pose2Sim folder structure from Go2Kin's project/session/trial
hierarchy, then runs pose estimation, triangulation, filtering, and kinematics.
"""

import logging
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Regex to strip ANSI escape codes (cursor movement, colors, etc.)
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
# Extract tqdm description key (text before ":  NN%")
_TQDM_KEY_RE = re.compile(r'^(.*?):\s+\d+%')

# Path to the Config.toml template shipped with Go2Kin
_TEMPLATE_PATH = Path(__file__).parent.parent / "config" / "pose2sim_config_template.toml"

# Files to skip when copying synced videos
_SKIP_FILES = {"stitched_videos.mp4", "timestamps.csv", "audio_waveforms.png"}


def build_pose2sim_project(project_manager, project, session, trial_name,
                           log_callback=None):
    """Stage a Pose2Sim-compatible directory for a Go2Kin trial.

    Args:
        project_manager: ProjectManager instance
        project: Project name
        session: Session name
        trial_name: Trial name
        log_callback: Optional callable(str) for status messages

    Returns:
        Path to the staging directory ([trial]/processed/)

    Raises:
        ValueError: If validation fails (missing videos, calibration, subject data)
    """
    pm = project_manager
    log = log_callback or (lambda msg: None)

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

    # Enable custom logging so Pose2Sim doesn't hijack Go2Kin's logging
    template = re.sub(
        r"^use_custom_logging\s*=\s*.*$",
        "use_custom_logging = true",
        template, count=1, flags=re.MULTILINE
    )

    config_path = processed_path / "Config.toml"
    config_path.write_text(template, encoding="utf-8")
    log("Generated Config.toml")

    return processed_path


class _LogForwarder(logging.Handler):
    """Logging handler that forwards records to a callback and terminal."""

    def __init__(self, callback, terminal_stream=None):
        super().__init__()
        self.callback = callback
        self.terminal_stream = terminal_stream

    def emit(self, record):
        try:
            msg = self.format(record)
            self.callback(msg)
            if self.terminal_stream:
                self.terminal_stream.write(msg + "\n")
                self.terminal_stream.flush()
        except Exception:
            pass


class _StreamRedirector:
    """Redirects a stream (stdout/stderr) to a callback, with tqdm awareness."""

    _THROTTLE_INTERVAL = 0.15  # max ~7 GUI updates/sec per progress bar

    def __init__(self, callback, progress_callback, original):
        self.callback = callback
        self.progress_callback = progress_callback
        self.original = original
        self._last_progress_times = {}  # per-key throttle timestamps

    def write(self, text):
        # Always pass through to terminal unmodified
        if self.original:
            self.original.write(text)

        if not text or not text.strip():
            return

        # Strip ANSI escape codes for GUI processing (cursor-up, colors, etc.)
        clean = _ANSI_RE.sub('', text)
        if not clean.strip():
            return

        # Detect tqdm: any \r in the cleaned text indicates progress bar updates
        if "\r" in clean:
            # Split on \r, process each non-empty segment as a progress line
            segments = clean.split("\r")
            now = time.time()
            for seg in segments:
                line = seg.strip()
                if not line:
                    continue
                # Extract key from tqdm description (e.g. "Processing dancing_GP2.mp4")
                m = _TQDM_KEY_RE.match(line)
                key = m.group(1).strip() if m else "_progress"
                # Per-key throttle
                last = self._last_progress_times.get(key, 0)
                if now - last >= self._THROTTLE_INTERVAL:
                    self._last_progress_times[key] = now
                    if self.progress_callback:
                        self.progress_callback(key, line)
        else:
            # Normal output — forward each non-empty line
            for line in clean.splitlines():
                cleaned = line.strip()
                if cleaned:
                    self.callback(cleaned)

    def flush(self):
        if self.original:
            self.original.flush()


def run_pose2sim_pipeline(processed_path, log_callback=None,
                          progress_callback=None, stop_event=None):
    """Run the Pose2Sim pipeline on a prepared directory.

    Args:
        processed_path: Path to the processed/ directory with Config.toml
        log_callback: Optional callable(str) for log messages (appends new line)
        progress_callback: Optional callable(key, msg) for progress updates (replaces line by key)
        stop_event: Optional threading.Event to request stop between steps

    Returns:
        True on success, False on failure or stop
    """
    log = log_callback or (lambda msg: None)
    # Fallback: if no progress_callback, just append via log_callback (ignore key)
    progress = progress_callback or (lambda key, msg: log(msg))
    original_cwd = os.getcwd()
    handler = None
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    try:
        os.chdir(str(processed_path))

        # Set up log forwarding
        if log_callback:
            handler = _LogForwarder(log_callback, terminal_stream=old_stderr)
            handler.setLevel(logging.DEBUG)
            logging.getLogger().addHandler(handler)
            sys.stdout = _StreamRedirector(log_callback, progress, old_stdout)
            sys.stderr = _StreamRedirector(log_callback, progress, old_stderr)

        # Import Pose2Sim (submodule at code/pose2sim/)
        pose2sim_path = str(Path(__file__).parent / "pose2sim")
        if pose2sim_path not in sys.path:
            sys.path.insert(0, pose2sim_path)

        from Pose2Sim import Pose2Sim as P2S

        # Run pipeline steps individually for stop-event granularity
        steps = [
            ("Calibration", P2S.calibration),
            ("Pose Estimation", P2S.poseEstimation),
            ("Triangulation", P2S.triangulation),
            ("Filtering", P2S.filtering),
            ("Kinematics", P2S.kinematics),
        ]

        for step_name, step_fn in steps:
            if stop_event and stop_event.is_set():
                log(f"Pipeline stopped before {step_name}")
                return False

            log(f"--- Starting {step_name} ---")
            try:
                step_fn()
            except Exception as e:
                log(f"ERROR in {step_name}: {e}")
                logger.exception(f"Pose2Sim {step_name} failed")
                return False

        log("Pipeline completed successfully")
        return True

    except Exception as e:
        log(f"Pipeline error: {e}")
        logger.exception("Pose2Sim pipeline failed")
        return False

    finally:
        os.chdir(original_cwd)
        if handler:
            logging.getLogger().removeHandler(handler)
        sys.stdout = old_stdout
        sys.stderr = old_stderr
