"""Tests for ProjectManager."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add code/ to path so we can import project_manager
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from project_manager import ProjectManager


class TestProjectManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.pm = ProjectManager(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    # ── Constructor ──────────────────────────────────────────────────────

    def test_init_creates_data_root(self):
        new_root = os.path.join(self.temp_dir.name, "nested", "data")
        pm = ProjectManager(new_root)
        self.assertTrue(Path(new_root).is_dir())

    # ── Project operations ───────────────────────────────────────────────

    def test_list_projects_empty(self):
        self.assertEqual(self.pm.list_projects(), [])

    def test_create_project(self):
        path = self.pm.create_project("my_project")
        self.assertTrue((path / "subjects").is_dir())
        self.assertTrue((path / "calibrations").is_dir())
        self.assertTrue((path / "sessions").is_dir())

    def test_create_project_duplicate_raises(self):
        self.pm.create_project("proj")
        with self.assertRaises(ValueError):
            self.pm.create_project("proj")

    def test_list_projects(self):
        self.pm.create_project("beta")
        self.pm.create_project("alpha")
        self.pm.create_project("gamma")
        self.assertEqual(self.pm.list_projects(), ["alpha", "beta", "gamma"])

    def test_get_project_path(self):
        self.pm.create_project("proj")
        path = self.pm.get_project_path("proj")
        self.assertTrue(path.is_dir())

    def test_get_project_path_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.pm.get_project_path("nonexistent")

    def test_invalid_project_name(self):
        with self.assertRaises(ValueError):
            self.pm.create_project("bad/name")
        with self.assertRaises(ValueError):
            self.pm.create_project("")

    # ── Subject operations ───────────────────────────────────────────────

    def test_create_subject(self):
        self.pm.create_project("proj")
        path = self.pm.create_subject("proj", "P01", "JD", 25, "M", 1.78, 75.0)
        self.assertTrue(path.exists())
        with open(path) as f:
            data = json.load(f)
        self.assertEqual(data["subject_id"], "P01")
        self.assertEqual(data["initials"], "JD")
        self.assertEqual(data["age"], 25)
        self.assertEqual(data["sex"], "M")
        self.assertAlmostEqual(data["height_m"], 1.78)
        self.assertAlmostEqual(data["mass_kg"], 75.0)
        self.assertEqual(data["notes"], "")

    def test_create_subject_with_notes(self):
        self.pm.create_project("proj")
        self.pm.create_subject("proj", "P02", "AB", 30, "F", 1.65, 60.0, notes="left knee injury")
        data = self.pm.get_subject("proj", "P02")
        self.assertEqual(data["notes"], "left knee injury")

    def test_create_subject_duplicate_raises(self):
        self.pm.create_project("proj")
        self.pm.create_subject("proj", "P01", "JD", 25, "M", 1.78, 75.0)
        with self.assertRaises(ValueError):
            self.pm.create_subject("proj", "P01", "JD", 25, "M", 1.78, 75.0)

    def test_list_subjects(self):
        self.pm.create_project("proj")
        self.pm.create_subject("proj", "P01", "JD", 25, "M", 1.78, 75.0)
        self.pm.create_subject("proj", "P02", "AB", 30, "F", 1.65, 60.0)
        subjects = self.pm.list_subjects("proj")
        self.assertEqual(len(subjects), 2)
        ids = [s["subject_id"] for s in subjects]
        self.assertIn("P01", ids)
        self.assertIn("P02", ids)

    def test_get_subject(self):
        self.pm.create_project("proj")
        self.pm.create_subject("proj", "P01", "JD", 25, "M", 1.78, 75.0)
        data = self.pm.get_subject("proj", "P01")
        self.assertEqual(data["subject_id"], "P01")

    def test_get_subject_missing_raises(self):
        self.pm.create_project("proj")
        with self.assertRaises(FileNotFoundError):
            self.pm.get_subject("proj", "P99")

    def test_update_subject(self):
        self.pm.create_project("proj")
        self.pm.create_subject("proj", "P01", "JD", 25, "M", 1.78, 75.0)
        self.pm.update_subject("proj", "P01", age=26, mass_kg=76.0)
        data = self.pm.get_subject("proj", "P01")
        self.assertEqual(data["age"], 26)
        self.assertAlmostEqual(data["mass_kg"], 76.0)
        # Unchanged fields preserved
        self.assertEqual(data["initials"], "JD")

    def test_update_subject_missing_raises(self):
        self.pm.create_project("proj")
        with self.assertRaises(FileNotFoundError):
            self.pm.update_subject("proj", "P99", age=30)

    # ── Calibration operations ───────────────────────────────────────────

    def _make_full_calib(self):
        """Return a minimal calibration dict with extrinsic data."""
        return {
            "charuco": {
                "columns": 5, "rows": 7,
                "board_height": 59.4, "board_width": 84.1,
                "dictionary": "DICT_4X4_50", "aruco_scale": 0.75,
                "inverted": False, "square_size_overide_cm": 11.7,
            },
            "cameras": {
                "1": {
                    "size": [3840, 2160],
                    "rotation_count": 0,
                    "error": 1.0,
                    "fisheye": False,
                    "ignore": False,
                    "matrix": [[2000, 0, 1920], [0, 2000, 1080], [0, 0, 1]],
                    "distortions": [0.01, -0.05, 0, 0, 0.05],
                    "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                    "translation": [0, 0, 5],
                    "grid_count": 20,
                },
            },
        }

    def _make_intrinsics_only_calib(self):
        """Return a calibration dict with intrinsics only (no rotation/translation)."""
        return {
            "charuco": {
                "columns": 5, "rows": 7,
                "board_height": 59.4, "board_width": 84.1,
                "dictionary": "DICT_4X4_50", "aruco_scale": 0.75,
                "inverted": False, "square_size_overide_cm": 11.7,
            },
            "cameras": {
                "1": {
                    "size": [3840, 2160],
                    "rotation_count": 0,
                    "error": 1.0,
                    "fisheye": False,
                    "ignore": False,
                    "matrix": [[2000, 0, 1920], [0, 2000, 1080], [0, 0, 1]],
                    "distortions": [0.01, -0.05, 0, 0, 0.05],
                    "grid_count": 20,
                },
            },
        }

    def test_save_calibration_full(self):
        self.pm.create_project("proj")
        calib = self._make_full_calib()
        json_path = self.pm.save_calibration("proj", "morning", calib)
        self.assertTrue(json_path.exists())
        # TOML should also exist
        toml_path = json_path.with_suffix(".toml")
        self.assertTrue(toml_path.exists())
        toml_text = toml_path.read_text()
        self.assertIn("[cam_1]", toml_text)

    def test_save_calibration_intrinsics_only(self):
        self.pm.create_project("proj")
        calib = self._make_intrinsics_only_calib()
        json_path = self.pm.save_calibration("proj", "intrinsics_only", calib)
        self.assertTrue(json_path.exists())
        # TOML should NOT exist (no extrinsic data)
        toml_path = json_path.with_suffix(".toml")
        self.assertFalse(toml_path.exists())

    def test_save_calibration_partial_null(self):
        """Calibration with null sections (intrinsics only, extrinsics null)."""
        self.pm.create_project("proj")
        calib = self._make_intrinsics_only_calib()
        calib["extrinsic"] = None
        calib["origin"] = None
        json_path = self.pm.save_calibration("proj", "partial", calib)
        # Should save and load correctly
        with open(json_path) as f:
            loaded = json.load(f)
        self.assertIsNone(loaded["extrinsic"])
        self.assertIsNone(loaded["origin"])

    def test_list_calibrations(self):
        self.pm.create_project("proj")
        self.pm.save_calibration("proj", "beta_calib", self._make_full_calib())
        self.pm.save_calibration("proj", "alpha_calib", self._make_full_calib())
        names = self.pm.list_calibrations("proj")
        self.assertEqual(names, ["alpha_calib", "beta_calib"])

    def test_get_calibration_path(self):
        self.pm.create_project("proj")
        self.pm.save_calibration("proj", "test_cal", self._make_full_calib())
        json_path = self.pm.get_calibration_path("proj", "test_cal", "json")
        toml_path = self.pm.get_calibration_path("proj", "test_cal", "toml")
        self.assertTrue(json_path.exists())
        self.assertTrue(toml_path.exists())

    def test_get_latest_calibration(self):
        self.pm.create_project("proj")
        self.assertIsNone(self.pm.get_latest_calibration("proj"))

        self.pm.save_calibration("proj", "old_cal", self._make_full_calib())
        # Set older mtime
        old_path = self.pm.get_calibration_path("proj", "old_cal")
        os.utime(old_path, (1000000, 1000000))

        self.pm.save_calibration("proj", "new_cal", self._make_full_calib())
        self.assertEqual(self.pm.get_latest_calibration("proj"), "new_cal")

    def test_get_calibration_age_days(self):
        self.pm.create_project("proj")
        self.pm.save_calibration("proj", "today", self._make_full_calib())
        age = self.pm.get_calibration_age_days("proj", "today")
        self.assertEqual(age, 0)

    def test_get_calibration_age_days_missing_raises(self):
        self.pm.create_project("proj")
        with self.assertRaises(FileNotFoundError):
            self.pm.get_calibration_age_days("proj", "nonexistent")

    # ── Session operations ───────────────────────────────────────────────

    def test_create_session(self):
        self.pm.create_project("proj")
        path = self.pm.create_session("proj", "2026-03-16-jumps")
        self.assertTrue(path.is_dir())

    def test_create_session_duplicate_raises(self):
        self.pm.create_project("proj")
        self.pm.create_session("proj", "sess")
        with self.assertRaises(ValueError):
            self.pm.create_session("proj", "sess")

    def test_list_sessions(self):
        self.pm.create_project("proj")
        self.pm.create_session("proj", "b_session")
        self.pm.create_session("proj", "a_session")
        self.assertEqual(self.pm.list_sessions("proj"), ["a_session", "b_session"])

    def test_get_session_path(self):
        self.pm.create_project("proj")
        self.pm.create_session("proj", "sess")
        path = self.pm.get_session_path("proj", "sess")
        self.assertTrue(path.is_dir())

    def test_get_session_path_missing_raises(self):
        self.pm.create_project("proj")
        with self.assertRaises(FileNotFoundError):
            self.pm.get_session_path("proj", "nonexistent")

    # ── Trial operations ─────────────────────────────────────────────────

    def test_create_trial(self):
        self.pm.create_project("proj")
        self.pm.create_session("proj", "sess")
        path = self.pm.create_trial(
            "proj", "sess", "jump_01", "P01", "2026-03-15_morning",
            ["cam1", "cam2", "cam3", "cam4"],
        )
        self.assertTrue((path / "video").is_dir())
        self.assertTrue((path / "processed").is_dir())
        self.assertTrue((path / "trial.json").exists())

        with open(path / "trial.json") as f:
            data = json.load(f)
        self.assertEqual(data["trial_name"], "jump_01")
        self.assertEqual(data["session_name"], "sess")
        self.assertEqual(data["subject_id"], "P01")
        self.assertEqual(data["calibration_file"], "2026-03-15_morning")
        self.assertEqual(data["cameras_used"], ["cam1", "cam2", "cam3", "cam4"])
        self.assertFalse(data["synced"])
        self.assertFalse(data["processed"])
        # date and time should be present
        self.assertIn("date", data)
        self.assertIn("time", data)

    def test_create_trial_no_calibration(self):
        """calibration_file='none' is valid."""
        self.pm.create_project("proj")
        self.pm.create_session("proj", "sess")
        path = self.pm.create_trial("proj", "sess", "trial_01", "P01", "none", ["cam1"])
        data = self.pm.get_trial("proj", "sess", "trial_01")
        self.assertEqual(data["calibration_file"], "none")

    def test_create_trial_duplicate_raises(self):
        self.pm.create_project("proj")
        self.pm.create_session("proj", "sess")
        self.pm.create_trial("proj", "sess", "t1", "P01", "none", ["cam1"])
        with self.assertRaises(ValueError):
            self.pm.create_trial("proj", "sess", "t1", "P01", "none", ["cam1"])

    def test_get_trial(self):
        self.pm.create_project("proj")
        self.pm.create_session("proj", "sess")
        self.pm.create_trial("proj", "sess", "t1", "P01", "cal1", ["cam1"])
        data = self.pm.get_trial("proj", "sess", "t1")
        self.assertEqual(data["trial_name"], "t1")

    def test_get_trial_missing_raises(self):
        self.pm.create_project("proj")
        self.pm.create_session("proj", "sess")
        with self.assertRaises(FileNotFoundError):
            self.pm.get_trial("proj", "sess", "nonexistent")

    def test_update_trial(self):
        self.pm.create_project("proj")
        self.pm.create_session("proj", "sess")
        self.pm.create_trial("proj", "sess", "t1", "P01", "cal1", ["cam1"])
        self.pm.update_trial("proj", "sess", "t1", synced=True)
        data = self.pm.get_trial("proj", "sess", "t1")
        self.assertTrue(data["synced"])
        self.assertFalse(data["processed"])  # unchanged

    def test_list_trials(self):
        self.pm.create_project("proj")
        self.pm.create_session("proj", "sess")
        self.pm.create_trial("proj", "sess", "b_trial", "P01", "none", ["cam1"])
        self.pm.create_trial("proj", "sess", "a_trial", "P01", "none", ["cam1"])
        self.assertEqual(self.pm.list_trials("proj", "sess"), ["a_trial", "b_trial"])

    def test_trial_video_path(self):
        self.pm.create_project("proj")
        self.pm.create_session("proj", "sess")
        self.pm.create_trial("proj", "sess", "t1", "P01", "none", ["cam1"])
        path = self.pm.get_trial_video_path("proj", "sess", "t1")
        self.assertTrue(path.is_dir())
        self.assertEqual(path.name, "video")

    def test_trial_synced_path(self):
        self.pm.create_project("proj")
        self.pm.create_session("proj", "sess")
        self.pm.create_trial("proj", "sess", "t1", "P01", "none", ["cam1"])
        path = self.pm.get_trial_synced_path("proj", "sess", "t1")
        # synced/ is not pre-created
        self.assertEqual(path.name, "synced")
        self.assertEqual(path.parent.name, "video")

    def test_trial_processed_path(self):
        self.pm.create_project("proj")
        self.pm.create_session("proj", "sess")
        self.pm.create_trial("proj", "sess", "t1", "P01", "none", ["cam1"])
        path = self.pm.get_trial_processed_path("proj", "sess", "t1")
        self.assertTrue(path.is_dir())
        self.assertEqual(path.name, "processed")

    # ── Tree view ────────────────────────────────────────────────────────

    def test_get_project_tree(self):
        self.pm.create_project("proj")
        self.pm.create_session("proj", "sess_a")
        self.pm.create_session("proj", "sess_b")
        self.pm.create_trial("proj", "sess_a", "t1", "P01", "none", ["cam1"])
        self.pm.create_trial("proj", "sess_a", "t2", "P01", "none", ["cam1"])
        self.pm.create_trial("proj", "sess_b", "t3", "P01", "none", ["cam1"])

        tree = self.pm.get_project_tree("proj")
        self.assertEqual(tree["project"], "proj")
        self.assertEqual(sorted(tree["sessions"].keys()), ["sess_a", "sess_b"])
        self.assertEqual(tree["sessions"]["sess_a"]["trials"], ["t1", "t2"])
        self.assertEqual(tree["sessions"]["sess_b"]["trials"], ["t3"])

    def test_get_project_tree_empty(self):
        self.pm.create_project("proj")
        tree = self.pm.get_project_tree("proj")
        self.assertEqual(tree["sessions"], {})


if __name__ == "__main__":
    unittest.main()
