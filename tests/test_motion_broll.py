"""Deterministic bridge tests; no user media or network required."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/motion_broll.py"
SPEC = importlib.util.spec_from_file_location("motion_broll", MODULE_PATH)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class MotionBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        (self.project / "edit/transcripts").mkdir(parents=True)
        (self.project / "motion/out").mkdir(parents=True)
        self.edl = {
            "version": 1,
            "sources": {"camera": str(self.project / "input/camera.mp4")},
            "ranges": [
                {"source": "camera", "start": 10, "end": 12},
                {"source": "camera", "start": 20, "end": 22},
            ],
            "overlays": [{"file": "animations/existing.mp4", "start_in_output": 0, "duration": 1}],
        }
        bridge.write_json(self.project / "edit/edl.json", self.edl)
        bridge.write_json(self.project / "edit/transcripts/camera.json", {
            "words": [
                {"type": "word", "start": 10.2, "end": 10.6, "text": "First"},
                {"type": "word", "start": 11.8, "end": 12.2, "text": "cut"},
                {"type": "word", "start": 20.1, "end": 20.5, "text": "Second"},
                {"type": "audio_event", "start": 20.6, "end": 21, "text": "[laugh]"},
            ]
        })

    def prepare_plan(self):
        bridge.timeline(self.project)
        (self.project / "edit/base.mp4").touch()
        (self.project / "motion/out/01.mp4").touch()
        bridge.write_json(self.project / "motion/plan.json", {
            "video": "../edit/base.mp4",
            "fps": "30/1",
            "clips": [{"id": "01", "in": 2.1, "out": 3.5, "kind": "full", "file": "out/01.mp4"}],
        })

    def test_timeline_retimes_words_across_cuts(self):
        path, count = bridge.timeline(self.project)
        self.assertEqual(count, 3)
        srt = path.read_text(encoding="utf-8")
        self.assertIn("00:00:00,200 --> 00:00:00,600\nFirst", srt)
        self.assertIn("00:00:01,800 --> 00:00:02,000\ncut", srt)
        self.assertIn("00:00:02,100 --> 00:00:02,500\nSecond", srt)
        self.assertNotIn("[laugh]", srt)

    @patch.object(bridge, "probe_video")
    def test_attach_preserves_original_edl_and_overlays(self, probe):
        self.prepare_plan()
        probe.side_effect = [
            {"width": 1920, "height": 1080, "duration": 4.0, "pix_fmt": "yuv420p"},
            {"width": 1920, "height": 1080, "duration": 1.5, "pix_fmt": "yuv420p"},
        ]
        result = bridge.attach(self.project)
        output = json.loads(result.read_text(encoding="utf-8"))
        self.assertEqual(len(output["overlays"]), 2)
        self.assertEqual(output["overlays"][1]["file"], "../motion/out/01.mp4")
        self.assertEqual(bridge.read_json(self.project / "edit/edl.json"), self.edl)

    @patch.object(bridge, "probe_video")
    def test_attach_rejects_short_render(self, probe):
        self.prepare_plan()
        probe.side_effect = [
            {"width": 1920, "height": 1080, "duration": 4.0, "pix_fmt": "yuv420p"},
            {"width": 1920, "height": 1080, "duration": 1.0, "pix_fmt": "yuv420p"},
        ]
        with self.assertRaisesRegex(ValueError, "shorter"):
            bridge.attach(self.project)

    def test_attach_rejects_stale_cut(self):
        self.prepare_plan()
        self.edl["ranges"][0]["end"] = 11.5
        bridge.write_json(self.project / "edit/edl.json", self.edl)
        with self.assertRaisesRegex(ValueError, "EDL changed"):
            bridge.attach(self.project)


if __name__ == "__main__":
    unittest.main()
