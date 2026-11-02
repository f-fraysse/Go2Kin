"""Tests for stored sync offsets: building the trial.json "sync" block and
applying it to Pose2Sim pose JSONs (pose/ -> pose-sync/)."""

import sys
import tempfile
import unittest
from pathlib import Path

# Add code/ to path so we can import the modules under test
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from audio_sync import offsets_to_trial_sync
from pose2sim_builder import apply_sync_offsets


class TestOffsetsToTrialSync(unittest.TestCase):

    def test_light_style_results(self):
        results = {
            r"C:\x\trial_GP1.mp4": {"offset_seconds": 3 / 200, "is_reference": False, "fps": 200.0},
            r"C:\x\trial_GP2.mp4": {"offset_seconds": 0.0, "is_reference": True, "fps": 200.0},
            r"C:\x\trial_GP4.MP4": {"offset_seconds": 5 / 200, "is_reference": False, "fps": 200.0},
        }
        sync = offsets_to_trial_sync(results)
        self.assertEqual(sync["fps"], 200.0)
        self.assertEqual(sync["reference_cam"], 2)
        self.assertEqual(sync["offset_frames"], {"1": 3, "2": 0, "4": 5})

    def test_fractional_audio_offsets_round(self):
        results = {
            "a_GP1.mp4": {"offset_seconds": 0.0, "is_reference": True, "fps": 50.0},
            "a_GP2.mp4": {"offset_seconds": 0.029, "is_reference": False, "fps": 50.0},  # 1.45 fr
            "a_GP3.mp4": {"offset_seconds": 0.031, "is_reference": False, "fps": 50.0},  # 1.55 fr
        }
        self.assertEqual(offsets_to_trial_sync(results)["offset_frames"],
                         {"1": 0, "2": 1, "3": 2})


class TestApplySyncOffsets(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.processed = Path(self.temp_dir.name)
        # 2 cameras x 10 raw frames of pose JSON, contents = raw frame index
        for cam in (1, 2):
            d = self.processed / "pose" / f"trial_GP{cam}_json"
            d.mkdir(parents=True)
            for i in range(10):
                (d / f"trial_GP{cam}_{i:06d}.json").write_text(str(i))

    def tearDown(self):
        self.temp_dir.cleanup()

    def _synced(self, cam):
        d = self.processed / "pose-sync" / f"trial_GP{cam}_json"
        return {int(f.stem.split("_")[-1]): int(f.read_text()) for f in d.glob("*.json")}

    def test_shift_and_drop(self):
        apply_sync_offsets(self.processed, {2: 3})
        # GP1 (no offset) unchanged: synced s == raw s
        self.assertEqual(self._synced(1), {i: i for i in range(10)})
        # GP2: raw frames 0-2 dropped, synced s == raw s + 3
        self.assertEqual(self._synced(2), {s: s + 3 for s in range(7)})
        # pose/ itself is untouched
        self.assertEqual(len(list((self.processed / "pose" / "trial_GP2_json").glob("*.json"))), 10)

    def test_rerun_replaces_stale_output(self):
        apply_sync_offsets(self.processed, {2: 3})
        (self.processed / "pose-associated").mkdir()
        apply_sync_offsets(self.processed, {})  # legacy / zero offsets
        self.assertEqual(self._synced(2), {i: i for i in range(10)})
        self.assertFalse((self.processed / "pose-associated").exists())

    def test_no_pose_folders_raises(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(ValueError):
                apply_sync_offsets(empty, {})


if __name__ == "__main__":
    unittest.main()
