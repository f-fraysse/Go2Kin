"""Tests for light_sync (LED pulse detection) and the led_roi persistence round-trip."""

import sys
import unittest
from pathlib import Path

import numpy as np

# Add code/ to path so we can import light_sync
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

import light_sync  # noqa: E402
from light_sync import (  # noqa: E402
    LightSyncError, detect_pulse, evaluate_light_sync_acceptance, scale_roi,
    resolve_rois_for_videos, cam_id_from_filename,
)

FPS = 100.0


def make_signal(on=150, length=600, pulse=100, baseline=20.0, peak=220.0,
                on_frac=None, off_frac=None):
    """Synthetic per-frame brightness: baseline, then LED on for `pulse` frames.

    on_frac: brightness fraction of the first (partially lit) on frame.
    off_frac: brightness fraction of the first (partially lit) off frame.
    """
    sig = np.full(length, baseline)
    sig[on:on + pulse] = peak
    if on_frac is not None:
        sig[on] = baseline + on_frac * (peak - baseline)
    if off_frac is not None:
        sig[on + pulse] = baseline + off_frac * (peak - baseline)
    return sig


class TestDetectPulse(unittest.TestCase):

    def test_clean_pulse(self):
        r = detect_pulse(make_signal(), FPS)
        self.assertEqual(r["on_frame"], 150)
        self.assertEqual(r["off_frame"], 250)
        self.assertAlmostEqual(r["t_on"], 150.0, places=3)
        self.assertAlmostEqual(r["t_off"], 250.0, places=3)
        self.assertAlmostEqual(r["pulse_frames"], 100.0, places=3)
        self.assertGreater(r["contrast"], light_sync.MIN_CONTRAST)

    def test_partial_edge_frames(self):
        # First on frame lit for 70% of its exposure -> LED turned on 0.3 frames in
        # First off frame lit for 30% -> LED turned off 0.3 frames into it
        r = detect_pulse(make_signal(on_frac=0.7, off_frac=0.3), FPS)
        self.assertEqual(r["on_frame"], 150)
        self.assertAlmostEqual(r["t_on"], 150.3, delta=0.05)
        self.assertAlmostEqual(r["t_off"], 250.3, delta=0.05)

    def test_partial_edge_below_threshold(self):
        # 30%-lit frame is below the 50% threshold: on_frame is the next frame but
        # t_on still recovers the sub-frame instant from the preceding partial frame.
        r = detect_pulse(make_signal(on_frac=0.3), FPS)
        self.assertEqual(r["on_frame"], 151)
        self.assertAlmostEqual(r["t_on"], 150.7, delta=0.05)

    def test_no_pulse_raises(self):
        with self.assertRaises(LightSyncError):
            detect_pulse(np.full(600, 20.0) + np.random.default_rng(0).normal(0, 2, 600), FPS)

    def test_low_contrast_raises(self):
        with self.assertRaises(LightSyncError):
            detect_pulse(make_signal(baseline=100.0, peak=140.0), FPS)

    def test_short_pulse_raises(self):
        with self.assertRaises(LightSyncError):
            detect_pulse(make_signal(pulse=50), FPS)

    def test_long_pulse_raises(self):
        with self.assertRaises(LightSyncError):
            detect_pulse(make_signal(pulse=120), FPS)

    def test_already_on_raises(self):
        with self.assertRaises(LightSyncError):
            detect_pulse(make_signal(on=0), FPS)

    def test_no_off_edge_raises(self):
        with self.assertRaises(LightSyncError):
            detect_pulse(make_signal(on=550, pulse=100, length=600), FPS)

    def test_pulse_within_tolerance(self):
        r = detect_pulse(make_signal(pulse=102), FPS)
        self.assertAlmostEqual(r["pulse_frames"], 102.0, places=3)


class TestAcceptance(unittest.TestCase):

    @staticmethod
    def _result(offset_frames, on_off_diff=0, ref=False, fps=100.0):
        return {
            "offset_seconds": offset_frames / fps,
            "is_reference": ref,
            "status": "REF" if ref else ("WARN" if abs(on_off_diff) > 1 else "PASS"),
            "final_offset_ms": offset_frames / fps * 1000.0,
            "offset_frames": offset_frames,
            "fps": fps,
            "on_frame": 150 + offset_frames,
            "off_frame": 250 + offset_frames,
            "t_on": 150.0 + offset_frames,
            "t_off": 250.0 + offset_frames,
            "pulse_frames": 100.0,
            "contrast": 200.0,
            "on_off_diff_frames": on_off_diff,
        }

    def test_pass(self):
        results = {"a_GP1.mp4": self._result(0, ref=True),
                   "a_GP2.mp4": self._result(3, on_off_diff=1),
                   "a_GP3.mp4": self._result(-2)}
        ok, reasons = evaluate_light_sync_acceptance(results)
        self.assertTrue(ok)
        self.assertEqual(reasons, [])

    def test_on_off_disagree(self):
        results = {"a_GP1.mp4": self._result(0, ref=True),
                   "a_GP2.mp4": self._result(3, on_off_diff=2)}
        ok, reasons = evaluate_light_sync_acceptance(results)
        self.assertFalse(ok)
        self.assertIn("GP2", reasons[0])

    def test_offset_too_large(self):
        results = {"a_GP1.mp4": self._result(0, ref=True),
                   "a_GP2.mp4": self._result(25)}  # 250 ms at 100 fps
        ok, reasons = evaluate_light_sync_acceptance(results, max_offset_ms=200.0)
        self.assertFalse(ok)
        self.assertIn("exceeds", reasons[0])

    def test_reference_diff_ignored(self):
        results = {"a_GP1.mp4": self._result(0, on_off_diff=5, ref=True)}
        ok, _ = evaluate_light_sync_acceptance(results)
        self.assertTrue(ok)


class TestRoiHelpers(unittest.TestCase):

    def test_scale_roi_4k_to_27k(self):
        roi = scale_roi((1812, 402, 80, 80), (3840, 2160), (2704, 1520))
        self.assertEqual(roi, (1276, 283, 56, 56))

    def test_scale_roi_same_size(self):
        self.assertEqual(scale_roi((10, 20, 80, 80), None, (1920, 1080)), (10, 20, 80, 80))

    def test_scale_roi_clamped(self):
        self.assertEqual(scale_roi((1900, 1070, 80, 80), None, (1920, 1080)),
                         (1840, 1000, 80, 80))

    def test_cam_id_from_filename(self):
        self.assertEqual(cam_id_from_filename("D:/x/trial_001_GP3.MP4"), 3)
        self.assertIsNone(cam_id_from_filename("stitched_videos.mp4"))

    def test_resolve_rois(self):
        rois = {1: {"roi": (1, 2, 80, 80), "size": (1920, 1080)}}
        out = resolve_rois_for_videos(["t_GP1.mp4"], rois)
        self.assertEqual(out["t_GP1.mp4"]["roi"], (1, 2, 80, 80))
        with self.assertRaises(LightSyncError):
            resolve_rois_for_videos(["t_GP2.mp4"], rois)
        with self.assertRaises(LightSyncError):
            resolve_rois_for_videos(["nocam.mp4"], rois)


class TestLedRoiPersistence(unittest.TestCase):

    def test_round_trip(self):
        from calibration.data_types import CameraData
        from calibration.persistence import _camera_data_to_dict, _dict_to_camera_data

        cam = CameraData(cam_id=2, size=(3840, 2160), led_roi=(1812, 402, 80, 80))
        d = _camera_data_to_dict(cam)
        self.assertEqual(d["led_roi"], [1812, 402, 80, 80])
        back = _dict_to_camera_data(2, d)
        self.assertEqual(back.led_roi, (1812, 402, 80, 80))

        cam_none = CameraData(cam_id=1, size=(1920, 1080))
        d2 = _camera_data_to_dict(cam_none)
        self.assertNotIn("led_roi", d2)
        self.assertIsNone(_dict_to_camera_data(1, d2).led_roi)

    def test_erase_clears_roi(self):
        from calibration.data_types import CameraData
        cam = CameraData(cam_id=1, size=(1920, 1080), led_roi=(1, 1, 80, 80))
        cam.erase_calibration_data()
        self.assertIsNone(cam.led_roi)


if __name__ == "__main__":
    unittest.main()
