"""Offline tests for the fitness explainer workflow; providers are simulated.

The end-to-end test renders real frames with Playwright/FFmpeg when the kit's
render runtime is installed (`fitness_video.py setup`); no API is called.
"""

import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import wave
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="fitness-test-"))
os.environ["FITNESS_PROJECTS_DIR"] = str(TMP / "projects")
os.environ["FITNESS_LOCAL_DIR"] = str(TMP / "local")
os.environ.setdefault("FITNESS_RUNTIME_DIR", str(ROOT / "local/fitness-runtime"))
os.environ["GENMAX_API_KEY"] = "test-key-not-real"
sys.path.insert(0, str(ROOT / "tools"))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from fitness import assemble, audio, imaging, notes, poses, providers, qa, reference, research, scenes  # noqa: E402
from fitness import channel as channel_profile  # noqa: E402
from fitness import project as projects  # noqa: E402
from fitness.common import FitnessError, file_hash, probe, read_json, write_json  # noqa: E402

HAS_RENDER = (Path(os.environ["FITNESS_RUNTIME_DIR"]) / "node_modules/playwright").is_dir() and shutil.which("ffmpeg")


def figure_png(size=(600, 800), shorts_rgb=(250, 125, 35), mark=False) -> bytes:
    w, h = size
    rng = np.random.default_rng(7)
    a = rng.integers(0, 14, (h, w, 3)).astype(np.uint8)
    yy, xx = np.mgrid[0:h, 0:w]
    body = ((xx - w / 2) / (w * .18)) ** 2 + ((yy - h * .42) / (h * .3)) ** 2 < 1
    a[body] = [176, 172, 168]
    a[body & (xx % 9 < 2)] = [70, 70, 70]
    shorts = (abs(xx - w / 2) < w * .17) & (yy > h * .6) & (yy < h * .72)
    a[shorts] = shorts_rgb
    if mark:  # a small grey mark far from the subject, like a provider sparkle
        a[h - 40:h - 20, w - 40:w - 20] = [150, 150, 150]
    buffer = io.BytesIO()
    Image.fromarray(a).save(buffer, format="PNG")
    return buffer.getvalue()


def speech_mp3() -> bytes:
    target = TMP / "speech.mp3"
    if not target.exists():
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "aevalsrc=0.3*sin(2*PI*220*t)*(lt(t\\,1)+gt(t\\,1.6)*lt(t\\,2.6)):s=24000:d=2.8",
                        "-c:a", "libmp3lame", "-b:a", "64k", str(target)], check=True)
    return target.read_bytes()


def make_channel():
    if not channel_profile.PROFILE.exists():
        channel_profile.init()
        channel = read_json(channel_profile.PROFILE)
        channel["voice"]["presets"] = {"test": {"voice_id": "voice-test", "name": "Test"}, "other": {"voice_id": "voice-2", "name": "Other"}}
        channel["voice"]["default"] = "test"
        channel["image"] = {"provider": "gemini", "fallback": None, "model": "gemini-3.1-flash-image", "size": "1K"}  # never call Codex from tests
        channel["characters"]["bulk"] = {"name": "Bulk", "description": "huge bodybuilder in a black tank top", "references": [], "signature": None}
        write_json(channel_profile.PROFILE, channel)
        for character_id, colour in (("hero", (250, 125, 35)), ("bulk", (90, 90, 90))):
            source = TMP / f"{character_id}-source.png"
            source.write_bytes(figure_png(shorts_rgb=colour, mark=True))
            channel_profile.add_reference(channel, character_id, source, "front")
        channel_profile.approve(channel, channel_profile.channel_digest(channel), "test approval")
    return channel_profile.load()


def make_project(name: str):
    make_channel()
    directory = projects.init(name, "Wall Hold Test", "9:16")
    write_json(directory / "research/sources.json", {"sources": [{"id": "s1", "title": "Tendon study", "short": "Study 2020", "locator": "https://example.org/study"}]})
    write_json(directory / "research/claims.json", {"claims": [{"id": "c1", "text": "Isometrics load tendons", "source_ids": ["s1"]}]})
    write_json(directory / "script.json", {"segments": [
        {"id": "hook", "text": "Your tendons adapt slower. Here is why.", "delivery": "punchy"},
        {"id": "hold", "text": "Slide down the wall. Hold for thirty seconds."},
    ]})
    write_json(directory / "storyboard.json", {
        "poses": {"wall-sit": {"prompt": "wall sit, thighs parallel to the floor, side view"}},
        "scenes": [
            {"segment_id": "hook", "title": {"text": "Tendons adapt slower", "accent": [{"word": "tendons", "color": "highlight"}]},
             "text": [{"text": "Here is why", "beat": 1}]},
            {"segment_id": "hold", "pose": "wall-sit", "tendons": ["knee"], "jitter": 0.7,
             "badge": {"kicker": "HOLD 1", "title": "The wall hold"},
             "timer": {"count": 30, "beat": 1}, "warning": {"text": "Stop if your knee hurts", "beat": 1},
             "bars": {"items": [{"label": "Tendon load", "value": 0.6, "display": "+60%", "claim_id": "c1"}], "beat": 0, "until_beat": 1},
             "text": [{"text": "Slide down the wall", "accent": [{"word": "wall", "color": "signature"}]}, {"text": "Hold 30 seconds"}]},
        ],
    })
    write_json(directory / "layout.json", {"poses": {"wall-sit": {"tendons": {"knee": {"x": .5, "y": .6, "rx": .06}}, "focus": [.5, .6]}}, "scenes": {}})
    return projects.Project(name)


def approve(project, gate):
    project.approve(gate, project.gate_digest(gate), "looks good")


class ImagingTests(unittest.TestCase):
    def test_black_is_clamped_and_shorts_take_signature_colour(self):
        raw, out = TMP / "raw.png", TMP / "out.png"
        raw.write_bytes(figure_png())
        info = imaging.process(raw, out, ["#FF5722"])
        a = np.asarray(Image.open(out).convert("RGB")).astype(int)
        self.assertEqual(a[:20, :20].max(), 0, "noisy near-black background must become pure #000")
        self.assertGreater(info["signature_fraction"]["#FF5722"], 0.01)
        h, w = a.shape[:2]
        shorts = a[int(h * .64), int(w / 2)]
        self.assertGreater(shorts[0], shorts[1] * 2.2)  # orange-red, re-tinted
        body = a[int(h * .4), int(w / 2 + 3)]
        self.assertEqual(len(set(body.tolist())), 1, "ink stays grayscale")

    def test_blue_signature_is_matched_by_hue_and_monochrome_has_no_tint(self):
        raw, out = TMP / "raw-blue.png", TMP / "out-blue.png"
        raw.write_bytes(figure_png(shorts_rgb=(17, 86, 217)))
        info = imaging.process(raw, out, ["#1A66FF"])
        a = np.asarray(Image.open(out).convert("RGB")).astype(int)
        h, w = a.shape[:2]
        r, g, b = a[int(h * .64), int(w / 2)]
        self.assertGreater(b, r * 3)
        self.assertGreater(info["signature_fraction"]["#1A66FF"], 0.01)
        imaging.process(raw, out, [])
        a = np.asarray(Image.open(out).convert("RGB")).astype(int)
        self.assertTrue((a[..., 0] == a[..., 2]).all(), "no signature means fully grayscale")


class CharacterTests(unittest.TestCase):
    def test_reference_import_crops_to_the_subject(self):
        channel = make_channel()
        reference = channel_profile.references(channel, "hero")[0]
        with Image.open(reference) as image:
            self.assertLess(image.width, 600 * .6, "distant corner mark is cropped away")

    def test_multi_character_pose_sends_every_reference(self):
        project = make_project("cast-test")
        project.storyboard["poses"]["duo"] = {"prompt": "standing side by side", "characters": ["hero", "bulk"]}
        project.storyboard["scenes"][0]["pose"] = "duo"
        self.assertEqual(len(poses.pose_references(project, "duo")), 2)
        prompt = poses.pose_prompt(project, "duo")
        self.assertIn("the bulk character (reference image 2)", prompt)
        self.assertIn("hero character's shorts", prompt)
        self.assertEqual(poses.pose_signatures(project, "duo"), ["#FF5722"])


class GateTests(unittest.TestCase):
    def test_content_approval_goes_stale_when_script_changes(self):
        project = make_project("gate-test")
        approve(project, "content")
        self.assertTrue(project.approved("content"))
        project.script["segments"][0]["text"] = "Changed line."
        self.assertFalse(project.approved("content"))
        with self.assertRaises(FitnessError):
            project.approve("content", "0" * 64, "ok")

    def test_voice_preset_switch_keeps_content_but_changes_narration(self):
        project = make_project("voice-test")
        approve(project, "content")
        before = project.audio_fingerprint(project.segments[0])
        project.brief["voice"] = "other"
        self.assertTrue(project.approved("content"))
        self.assertNotEqual(before, project.audio_fingerprint(project.segments[0]))
        self.assertEqual(channel_profile.voice_config(project.channel, "other")["voice_id"], "voice-2")
        project.brief["voice"] = "missing"
        with self.assertRaises(FitnessError):
            project.audio_fingerprint(project.segments[0])

    def test_approve_uses_last_review_and_rejects_later_edits(self):
        project = make_project("shorthand-test")
        with self.assertRaises(FitnessError):
            project.approve("content", None, "ok")  # nothing presented yet
        project.record_review("content", project.gate_digest("content"))
        project.script["segments"][1]["text"] = "Edited after the review."
        with self.assertRaises(FitnessError):
            project.approve("content", None, "ok")

    def test_source_check_resolves_dois(self):
        project = make_project("research-test")
        project.sources["sources"][0]["locator"] = "https://doi.org/10.1000/xyz123"
        project.sources["sources"][0]["title"] = "Smith J. Tendon study of loading. J Test. 2020"
        reply = unittest.mock.Mock(status_code=200, ok=True)
        reply.json.return_value = {"message": {"title": ["Tendon study of loading"], "issued": {"date-parts": [[2020]]}, "container-title": ["J Test"]}}
        with patch.object(research.requests, "get", return_value=reply) as get:
            result = research.verify(project)[0]
        self.assertIn("10.1000/xyz123", get.call_args.args[0])
        self.assertEqual(result["status"], "ok")

    def test_bars_require_a_sourced_claim(self):
        project = make_project("claim-test")
        project.storyboard["scenes"][1]["bars"]["items"][0]["claim_id"] = "missing"
        with self.assertRaises(FitnessError):
            project.content_digest()


class ImageProviderTests(unittest.TestCase):
    def test_codex_output_is_cropped_to_the_requested_aspect(self):
        def fake_run(arguments, **_):
            out = Path(arguments[arguments.index("--out") + 1])
            Image.new("RGB", (1536, 1024), (0, 0, 0)).save(out)
            self.assertEqual(arguments[arguments.index("--aspect") + 1], "3:2")
            self.assertEqual(arguments.count("--ref"), 2)
            return subprocess.CompletedProcess(arguments, 0, b'{"path": "x", "agent_credits": 0.1}\n', b"")
        with patch.object(providers, "codex_script", return_value=Path("codex_image.mjs")), patch("subprocess.run", side_effect=fake_run):
            data, meta = providers.codex_image("a pose", [Path("a.png"), Path("b.png")], "16:9")
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.size, (1536, 864))
        self.assertEqual(meta["agent_credits"], 0.1)

    def test_gemini_backs_up_codex(self):
        config = {"provider": "codex", "fallback": "gemini"}
        with patch.object(providers, "codex_image", side_effect=FitnessError("not logged in")), \
                patch.object(providers, "gemini_image", return_value=b"png") as gemini:
            data, meta = providers.generate_image(config, "a pose", [], "1:1")
        self.assertEqual((data, meta["provider"]), (b"png", "gemini"))
        self.assertIn("not logged in", meta["fallback_reason"])
        gemini.assert_called_once()
        with patch.object(providers, "codex_image", side_effect=FitnessError("refused")), \
                patch.object(providers, "gemini_image", side_effect=FitnessError("quota")):
            with self.assertRaises(FitnessError):
                providers.generate_image(config, "a pose", [], "1:1")

    def test_gateway_uses_image_host_and_never_falls_back_after_a_timeout(self):
        buffer = io.BytesIO()
        Image.new("RGB", (1536, 1024), (0, 0, 0)).save(buffer, format="PNG")
        ok = unittest.mock.Mock(status_code=200)
        ok.json.return_value = {"data": [{"b64_json": base64.b64encode(buffer.getvalue()).decode()}]}
        config = {"provider": "gateway", "fallback": "gemini", "gateway_base": "https://apithat.dev/v1"}
        with patch.object(providers, "secret", return_value="sk-test"), \
                patch.object(providers.requests, "post", return_value=ok) as post:
            data, meta = providers.generate_image(config, "a pose", [], "16:9")
        self.assertEqual(post.call_args.args[0], "https://api.apithat.dev/v1/images/generations")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "gpt-image-2.5-sunburst")
        self.assertEqual((meta["provider"], meta["native"]), ("gateway", [1536, 1024]))
        for outcome in (providers.requests.ReadTimeout(), unittest.mock.Mock(status_code=524)):
            with patch.object(providers, "secret", return_value="sk-test"), \
                    patch.object(providers.requests, "post", side_effect=[outcome] if isinstance(outcome, Exception) else None,
                                 return_value=outcome), \
                    patch.object(providers, "gemini_image") as gemini:
                with self.assertRaises(providers.UncertainOutcome):
                    providers.generate_image(config, "a pose", [], "16:9")
            gemini.assert_not_called()


class GeminiBatchTests(unittest.TestCase):
    def setUp(self):
        # The in-memory channel switches to batch mode; keep the shared test channel approval untouched.
        patcher = patch.object(channel_profile, "require_approved", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def batch_project(self, name):
        project = make_project(name)
        project.storyboard["poses"]["calf"] = {"prompt": "calf raise hold"}
        project.storyboard["scenes"][0]["pose"] = "calf"
        project.storyboard["scenes"][0].pop("title", None)
        write_json(project.dir / "storyboard.json", project.storyboard)
        project = projects.Project(name)
        project.channel["image"] = {"provider": "gemini", "batch": True, "model": "gemini-3.1-flash-image", "size": "1K"}
        approve(project, "content")
        return project

    @staticmethod
    def finished(keys, missing=()):
        items = [{"metadata": {"key": k}, "response": {"candidates": [{"content": {"parts": [
            {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(figure_png()).decode()}}]}}]}}
            for k in keys if k not in missing]
        items += [{"metadata": {"key": k}, "error": {"message": "blocked"}} for k in missing]
        return {"name": "batches/1", "metadata": {"state": "BATCH_STATE_SUCCEEDED"}, "done": True,
                "response": {"inlinedResponses": {"inlinedResponses": items}}}

    def test_pending_batch_is_polled_not_resubmitted(self):
        project = self.batch_project("batch-resume")
        with patch.object(providers, "gemini_batch_submit", return_value="batches/1") as submit, \
                patch.object(providers, "gemini_batch_get", return_value={"name": "batches/1", "metadata": {"state": "BATCH_STATE_RUNNING"}}):
            with self.assertRaises(poses.BatchPending):
                poses.generate(project, wait_seconds=0)
        self.assertEqual(project.state["image_batch"]["name"], "batches/1")
        request = submit.call_args.args[1]["calf"]
        self.assertEqual(request["generationConfig"]["imageConfig"]["imageSize"], "1K")
        self.assertEqual(request["contents"][0]["parts"][0]["inlineData"]["mimeType"], "image/jpeg", "references are shrunk for the batch")
        with patch.object(providers, "gemini_batch_submit") as submit, \
                patch.object(providers, "gemini_batch_get", return_value=self.finished(["calf", "wall-sit"])):
            poses.generate(project, wait_seconds=0)
            submit.assert_not_called()
        self.assertEqual({r["made_by"]["mode"] for r in project.state["poses"].values()}, {"batch"})
        self.assertNotIn("image_batch", project.state)

    def test_failed_batch_items_fall_back_to_interactive_calls(self):
        project = self.batch_project("batch-fallback")
        with patch.object(providers, "gemini_batch_submit", return_value="batches/1"), \
                patch.object(providers, "gemini_batch_get", return_value=self.finished(["calf", "wall-sit"], missing=["calf"])), \
                patch.object(providers, "gemini_image", return_value=figure_png()) as interactive:
            poses.generate(project, wait_seconds=0)
        self.assertEqual(interactive.call_count, 1)
        self.assertEqual(project.state["poses"]["calf"]["made_by"]["batch_fallback"], "blocked")
        self.assertEqual(project.state["poses"]["wall-sit"]["made_by"]["mode"], "batch")

    def test_uncertain_batch_submit_is_reconciled(self):
        project = self.batch_project("batch-uncertain")
        with patch.object(providers, "gemini_batch_submit", side_effect=providers.UncertainOutcome("timeout")):
            with self.assertRaises(providers.UncertainOutcome):
                poses.generate(project, wait_seconds=0)
        with patch.object(providers, "gemini_batch_submit") as submit:
            with self.assertRaises(FitnessError):
                poses.generate(project, wait_seconds=0)
            submit.assert_not_called()
        display = project.state["image_batch"]["display_name"]
        with patch.object(providers, "gemini_batch_list", return_value=[{"name": "batches/9", "metadata": {"displayName": display}}]):
            self.assertIn("batches/9", poses.reconcile_batch(project))
        self.assertEqual(project.state["image_batch"]["name"], "batches/9")


class GenmaxResumeTests(unittest.TestCase):
    def test_interrupted_poll_resumes_the_same_task(self):
        project = make_project("resume-test")
        approve(project, "content")
        done = {"status": "completed", "result": {"audio_url": "https://api.genmax.io/audio/a.mp3"}}
        with patch.object(providers, "genmax_submit", side_effect=["task-1", "task-2"]) as submit, \
                patch.object(providers, "genmax_wait", side_effect=[FitnessError("still processing"), done, done]) as wait, \
                patch.object(providers, "genmax_download", return_value=speech_mp3()):
            with self.assertRaises(FitnessError):
                audio.generate(project)
            self.assertEqual(project.state["audio_tasks"]["hook"]["task_id"], "task-1")
            audio.generate(project)
        self.assertEqual([c.args[0] for c in submit.call_args_list], ["Your tendons adapt slower. Here is why.", "Slide down the wall. Hold for thirty seconds."])
        self.assertEqual(wait.call_args_list[1].args[0], "task-1")
        self.assertEqual(project.state["audio"]["hook"]["task_id"], "task-1")
        _, _, fps = project.size
        seconds = project.state["audio"]["hook"]["seconds"]
        self.assertAlmostEqual(seconds * fps, round(seconds * fps), places=6)
        self.assertEqual(len(audio.beats(project, project.segments[0])), 2)

    def test_uncertain_submit_is_reconciled_not_resent(self):
        project = make_project("uncertain-test")
        approve(project, "content")
        with patch.object(providers, "genmax_submit", side_effect=providers.UncertainOutcome("timeout")):
            with self.assertRaises(providers.UncertainOutcome):
                audio.generate(project, only="hook")
        with patch.object(providers, "genmax_submit") as submit:
            with self.assertRaises(FitnessError):
                audio.generate(project, only="hook")
            submit.assert_not_called()
        history = [{"id": "found-7", "text": "Your tendons adapt slower. Here is why.", "created_at": "2999-01-01T00:00:00Z"}]
        with patch.object(providers, "genmax_history", return_value=history):
            self.assertIn("adopted Genmax task found-7", audio.reconcile(project)[0])
        done = {"status": "completed", "result": {"audio_url": "https://x/a.mp3"}}
        with patch.object(providers, "genmax_submit") as submit, patch.object(providers, "genmax_wait", return_value=done) as wait, \
                patch.object(providers, "genmax_download", return_value=speech_mp3()):
            audio.generate(project, only="hook")
            submit.assert_not_called()
            self.assertEqual(wait.call_args.args[0], "found-7")


def fake_media(project):
    done = {"status": "completed", "result": {"audio_url": "https://x/a.mp3"}}
    with patch.object(providers, "genmax_submit", side_effect=["t-a", "t-b"]), patch.object(providers, "genmax_wait", return_value=done), \
            patch.object(providers, "genmax_download", return_value=speech_mp3()):
        audio.generate(project)


YT_VTT = """WEBVTT
Kind: captions

00:00:00.000 --> 00:00:02.000
Have<00:00:00.400><c> you</c><00:00:00.800><c> ever</c><00:00:01.200><c> noticed</c>

00:00:02.000 --> 00:00:02.010
Have you ever noticed

00:00:02.010 --> 00:00:04.000
skinny<00:00:02.400><c> guys</c><00:00:02.800><c> [music]</c><00:00:03.000><c> are&#39;</c><00:00:03.300><c> strong</c>
"""


class ReferenceTests(unittest.TestCase):
    def make(self, name):
        project = make_project(name)
        folder = reference.folder(project)
        write_json(folder / "info.json", {"title": "Ref", "duration": 40, "url": "https://youtu.be/x",
                                          "chapters": [{"start_time": 0, "end_time": 10, "title": "Hook"},
                                                       {"start_time": 10, "end_time": 40, "title": "Hold 1"}],
                                          "description": "Research mentioned: Kubo et al. 2001 (J Appl Physiol: holds made tendons stiffer); "
                                                         "Moritani & deVries 1979 (Am J Phys Med: early gains are neural)."})
        words = "your tendons adapt slower than muscles so slide down the wall and hold it".split()
        write_json(folder / "transcript.json", {"words": [{"t": 12 + i, "w": w} for i, w in enumerate(words)]})
        return project

    def test_youtube_captions_skip_rolling_repeats_and_noise(self):
        words = [w["w"] for w in reference.parse_captions(YT_VTT)]
        self.assertEqual(words, ["Have", "you", "ever", "noticed", "skinny", "guys", "are'", "strong"])
        plain = reference.parse_captions("1\n00:00:01,000 --> 00:00:03,000\nHold the wall\n")
        self.assertEqual([round(w["t"], 2) for w in plain], [1.0, 1.67, 2.33])

    def test_analysis_skeleton_and_citations(self):
        project = self.make("ref-analysis")
        report = reference.analyse(project)
        self.assertEqual([c["words"] for c in report["chapters"]], [0, 14])
        self.assertEqual([c["citation"] for c in report["cited"]], ["Kubo et al. 2001", "Moritani & deVries 1979"])
        rows = reference.skeleton(project, 60)["rows"]
        self.assertEqual([r["target_seconds"] for r in rows], [15.0, 45.0])

    def test_originality_flags_copied_runs(self):
        project = self.make("ref-originality")
        project.script["segments"][1]["text"] = "So slide down the wall and hold it for thirty seconds."
        result = reference.originality(project)
        self.assertFalse(result["ok"])
        self.assertIn("so slide down the wall and hold it", result["segments"][1]["shared"][0])
        project.script["segments"][1]["text"] = "Back against a wall, sink until your knees bend, then stay there."
        self.assertTrue(reference.originality(project)["ok"])

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg missing")
    def test_keyframes_follow_cuts_and_describe_is_cached(self):
        project = self.make("ref-frames")
        video = TMP / "ref-source.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "smptebars=s=320x180:d=2",
                        "-f", "lavfi", "-i", "rgbtestsrc=s=320x180:d=2", "-f", "lavfi", "-i", "mandelbrot=s=320x180:r=25", "-t", "18",
                        "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0", "-r", "25", str(video)], check=True)
        info = read_json(reference.folder(project) / "info.json")
        info["source_file"] = "source.mp4"
        shutil.copyfile(video, reference.folder(project) / "source.mp4")
        write_json(reference.folder(project) / "info.json", info)
        result = reference.keyframes(project)
        frames = read_json(reference.folder(project) / "frames.json")["frames"]
        self.assertIn("scene cuts", result["source"])
        self.assertGreaterEqual(len(frames), 3)
        self.assertTrue(any(f["t"] > 6 for f in frames), "long scenes get filler frames")
        answer = [{"hud": ["timer_ring"], "our_template": "timer"}] * len(frames)
        with patch.object(providers, "gemini_json", return_value=answer) as ask:
            summary = reference.describe(project, batch=len(frames))
            self.assertEqual(summary["hud_counts"], {"timer_ring": len(frames)})
            reference.describe(project, batch=len(frames))
        self.assertEqual(ask.call_count, 1, "already described frames are not sent again")

    def test_storyboard_frames_are_filtered_and_feed_the_skeleton(self):
        project = self.make("ref-storyboard")
        # 3x3 sprite, 4 s per tile: two identical red tiles, one black tile, the rest distinct patterns.
        tiles = [(200, 30, 30), (200, 30, 30), (0, 0, 0), (30, 200, 30), (30, 30, 200), (220, 220, 40), (240, 120, 20), (90, 90, 90), (10, 160, 160)]
        sprite = Image.new("RGB", (192, 108))
        for k, colour in enumerate(tiles):
            tile = Image.new("RGB", (64, 36), colour)
            if k != 2:  # patterned like real frames; tiles 0 and 1 stay identical
                ImageDraw.Draw(tile).rectangle([8, 8, 8 + max(k, 1) * 5, 28], fill=(255, 255, 255))
            sprite.paste(tile, ((k % 3) * 64, (k // 3) * 36))
        buffer = io.BytesIO()
        sprite.save(buffer, format="PNG")
        info = read_json(reference.folder(project) / "info.json")
        info["storyboard"] = {"width": 64, "height": 36, "rows": 3, "columns": 3, "fragments": [{"url": "https://i.ytimg.com/sb/x.jpg", "duration": 36}]}
        write_json(reference.folder(project) / "info.json", info)
        reply = unittest.mock.Mock(content=buffer.getvalue())
        reply.raise_for_status.return_value = None
        with patch("requests.get", return_value=reply):
            result = reference.storyboard_frames(project)
        self.assertEqual((result["frames"], result["dropped"]), (7, 2))
        reference.analyse(project)
        skeleton = reference.skeleton(project, 60, frames_per_chapter=2)
        self.assertEqual([len(r["frames"]) for r in skeleton["rows"]], [1, 2])  # hook keeps one: duplicate + black dropped
        self.assertTrue(Path(skeleton["sheet"]).is_file())

    def test_publish_notes_list_sources_and_safety(self):
        project = make_project("notes-test")
        text = Path(notes.draft(project)["path"]).read_text(encoding="utf-8")
        self.assertIn("Research mentioned", text)
        self.assertIn("Study 2020: Isometrics load tendons", text)
        self.assertIn("keep breathing", text)


@unittest.skipUnless(HAS_RENDER, "render runtime not installed (fitness_video.py setup)")
class EndToEndTests(unittest.TestCase):
    def test_landscape_layout_renders_inspection_stills(self):
        make_channel()
        projects.init("landscape-test", "Landscape", "16:9")
        source = projects.Project("e2e-layout-source") if (TMP / "projects/e2e-layout-source").exists() else make_project("e2e-layout-source")
        for name in ("research/sources.json", "research/claims.json", "script.json", "storyboard.json", "layout.json"):
            shutil.copyfile(source.dir / name, TMP / "projects/landscape-test" / name)
        project = projects.Project("landscape-test")
        approve(project, "content")
        fake_media(project)
        with patch.object(providers, "gemini_image", return_value=figure_png()):
            poses.generate(project)
        self.assertEqual(poses.pose_aspect(project, "wall-sit"), "1:1")
        stills = scenes.stills(project, "hold", [0.6, 2.4]) + scenes.stills(project, "hook", [2.0])
        self.assertTrue(all(p.is_file() for p in stills))
        with Image.open(stills[0]) as frame:
            self.assertEqual(frame.size, (1920, 1080))

    def test_pinned_tag_in_both_aspects(self):
        for aspect, name in (("16:9", "tag-wide"), ("9:16", "tag-tall")):
            make_channel()
            source = projects.Project("e2e-layout-source") if (TMP / "projects/e2e-layout-source").exists() else make_project("e2e-layout-source")
            projects.init(name, "Tag", aspect)
            for f in ("research/sources.json", "research/claims.json", "script.json", "storyboard.json", "layout.json"):
                shutil.copyfile(source.dir / f, TMP / "projects" / name / f)
            brief = read_json(TMP / "projects" / name / "brief.json")
            brief["tag"] = "Grip · Full guide · At home · No gym"
            write_json(TMP / "projects" / name / "brief.json", brief)
            project = projects.Project(name)
            approve(project, "content")
            fake_media(project)
            with patch.object(providers, "gemini_image", return_value=figure_png()):
                poses.generate(project)
            config = scenes.scene_config(project, project.segments[1])
            self.assertEqual(config["tag"], "Grip · Full guide · At home · No gym")
            self.assertNotIn("tagFrom", config, "one heading for the whole video stays static")
            self.assertTrue(scenes.stills(project, "hold", [1.0])[0].is_file())

    def test_heading_tags_change_per_main_idea(self):
        make_channel()
        directory = projects.init("headings-test", "Headings", "16:9", tag="Grip · Forearms · At home")
        write_json(directory / "research/sources.json", {"sources": []})
        write_json(directory / "research/claims.json", {"claims": []})
        ids = ("intro", "fingers", "card", "plan")
        write_json(directory / "script.json", {"segments": [{"id": s, "text": "One short line. Then another."} for s in ids]})
        write_json(directory / "storyboard.json", {"poses": {"wall-sit": {"prompt": "wall sit"}}, "scenes": [
            {"segment_id": "intro", "pose": "wall-sit"},
            {"segment_id": "fingers", "pose": "wall-sit", "tag": "Grip · Fingers · At home"},
            {"segment_id": "card", "title": {"text": "Your plan"}, "tag": False},
            {"segment_id": "plan", "pose": "wall-sit", "tag": "Grip · Weekly plan"}]})
        write_json(directory / "layout.json", {"poses": {}, "scenes": {}})
        project = projects.Project("headings-test")
        self.assertEqual([s["segment_id"] for s in project.tag_sections()], ["intro", "fingers", "plan"])
        tags = project.tags()
        self.assertEqual([tags[i]["from"] for i in ids], [None, "Grip · Forearms · At home", None, ""])
        self.assertIsNone(tags["card"]["text"])
        approve(project, "content")
        done = {"status": "completed", "result": {"audio_url": "https://x/a.mp3"}}
        with patch.object(providers, "genmax_submit", side_effect=lambda text, voice: "t"), patch.object(providers, "genmax_wait", return_value=done), \
                patch.object(providers, "genmax_download", return_value=speech_mp3()):
            audio.generate(project)
        with patch.object(providers, "gemini_image", return_value=figure_png()):
            poses.generate(project, jobs=1)
        self.assertEqual(scenes.scene_config(project, project.segments[1])["tagFrom"], "Grip · Forearms · At home")
        self.assertNotIn("tagFrom", scenes.scene_config(project, project.segments[0]))
        mid, after = scenes.stills(project, "fingers", [0.2, 1.5])
        with Image.open(mid) as a, Image.open(after) as b:
            corner = (0, 0, 700, 120)
            self.assertNotEqual(a.crop(corner).tobytes(), b.crop(corner).tobytes(), "the heading is mid-swap at 0.2 s")
        self.assertTrue(scenes.stills(project, "plan", [0.2])[0].is_file())
        for segment_id in ids:
            project.state["audio"][segment_id]["seconds"] = 12.0
        text = Path(notes.draft(project)["path"]).read_text(encoding="utf-8")
        self.assertIn("0:00 - Forearms · At home\n0:12 - Fingers · At home\n0:36 - Weekly plan", text)
        project.storyboard["scenes"][1]["tag"] = 7
        with self.assertRaises(FitnessError):
            project.validate_content()

    def test_new_templates_render(self):
        make_channel()
        directory = projects.init("templates-test", "Templates", "16:9")
        write_json(directory / "research/sources.json", {"sources": [{"id": "s1", "title": "Study", "short": "Study 2020", "locator": "doi:10.1/x"}]})
        write_json(directory / "research/claims.json", {"claims": [{"id": "c1", "text": "Holds beat reps", "source_ids": ["s1"]}]})
        write_json(directory / "script.json", {"segments": [{"id": s, "text": "One short line. Then another."} for s in ("inset", "split", "plan", "table")]})
        write_json(directory / "storyboard.json", {
            "poses": {"wall-sit": {"prompt": "wall sit"}, "engine": {"kind": "illustration", "prompt": "an engine and a rope", "colours": ["highlight"]}},
            "scenes": [
                {"segment_id": "inset", "pose": "wall-sit", "labels": [{"text": "Tendon = the rope", "x": .5, "y": .2, "color": "highlight"}],
                 "marks": [{"type": "x", "x": .8, "y": .3}], "inset": {"pose": "engine", "label": "Thigh to knee tendon", "spots": ["knee"], "beat": 0},
                 "meter": {"label": "Effort", "value": 7, "beat": 1}, "text": [{"text": "Muscle is the engine"}]},
                {"segment_id": "split", "split": {"title": "Same total work", "beat": 0,
                                                    "left": {"label": "Leg 1", "title": "50 x fast", "pose": "wall-sit", "value": "+0%", "color": "highlight", "claim_id": "c1"},
                                                    "right": {"label": "Leg 2", "title": "20 s holds", "pose": "wall-sit", "value": "+57%", "color": "accent", "claim_id": "c1"}}},
                {"segment_id": "plan", "plan": {"title": "The whole plan", "sub": "3-4 days a week", "items": [{"pose": "wall-sit", "label": "Wall hold"}] * 4}},
                {"segment_id": "table", "table": {"title": "Your wall hold", "rows": [{"left": "Under 30 s", "right": "Every session", "color": "highlight"},
                                                                                    {"left": "2 min +", "right": "Strong", "color": "accent"}]}},
            ]})
        write_json(directory / "layout.json", {"poses": {"wall-sit": {"tendons": {"knee": {"x": .5, "y": .6, "rx": .06}}},
                                                         "engine": {"tendons": {"knee": {"x": .5, "y": .5, "rx": .08}}}}, "scenes": {}})
        project = projects.Project("templates-test")
        self.assertEqual(project.used_poses(), ["engine", "wall-sit"])
        approve(project, "content")
        done = {"status": "completed", "result": {"audio_url": "https://x/a.mp3"}}
        with patch.object(providers, "genmax_submit", side_effect=lambda text, voice: "t"), patch.object(providers, "genmax_wait", return_value=done), \
                patch.object(providers, "genmax_download", return_value=speech_mp3()):
            audio.generate(project)
        with patch.object(providers, "gemini_image", return_value=figure_png()) as image:
            poses.generate(project, jobs=1)
        prompts = {call.args[1] for call in image.call_args_list}
        self.assertTrue(any("engine and a rope" in p and "vivid red" in p for p in prompts), "illustration prompt keeps its accent colour")
        board = scenes.storyboard(project)
        self.assertTrue(board.is_file())
        with Image.open(board) as sheet:
            self.assertGreater(sheet.width, 1000)

    def test_transitions_glow_and_hud_panels_render(self):
        make_channel()
        directory = projects.init("motion-test", "Motion", "16:9")
        write_json(directory / "research/sources.json", {"sources": [{"id": "s1", "title": "Study", "short": "Study", "locator": "doi:10.1/x"}]})
        write_json(directory / "research/claims.json", {"claims": []})
        write_json(directory / "script.json", {"segments": [{"id": s, "text": "One short line. Then another."} for s in ("hook", "hold", "ease", "end")]})
        write_json(directory / "storyboard.json", {
            "poses": {"wall-sit": {"prompt": "wall sit"}},
            "scenes": [
                {"segment_id": "hook", "impact": True, "title": {"text": "The ten second test", "accent": [{"word": "test", "color": "highlight"}]}},
                {"segment_id": "hold", "pose": "wall-sit", "holdbar": {"label": "Feet up, start the timer", "beat": 0, "run_at": 0.2, "speed": 4, "stop_at": 1.6},
                 "dose": {"main": "20-30s x 3", "sets": 3, "beat": 0}},
                {"segment_id": "ease", "transition": "swipe", "pose": "wall-sit", "switch": {"steps": [
                    {"side": "easy", "text": "Toes lightly touching", "at": 0.1}, {"side": "hard", "text": "Knees further out", "accent": [{"word": "further", "color": "highlight"}], "at": 1.0}]}},
                {"segment_id": "end", "pose": "wall-sit", "angle": {"label": "Legs level", "accent": [{"word": "level", "color": "highlight"}], "steps": [{"deg": 0, "at": 0.4}], "beat": 0},
                 "text": [{"text": "Stay light", "accent": [{"word": "light", "color": "accent"}]}]},
            ]})
        write_json(directory / "layout.json", {"poses": {"wall-sit": {"tendons": {}}}, "scenes": {}})
        project = projects.Project("motion-test")
        approve(project, "content")
        done = {"status": "completed", "result": {"audio_url": "https://x/a.mp3"}}
        with patch.object(providers, "genmax_submit", side_effect=lambda text, voice: "t"), patch.object(providers, "genmax_wait", return_value=done), \
                patch.object(providers, "genmax_download", return_value=speech_mp3()):
            audio.generate(project)
        with patch.object(providers, "gemini_image", return_value=figure_png()):
            poses.generate(project, jobs=1)
        # Exits mirror the next entry: blur only into a blur scene, sharp into impact/swipe.
        seg = {s["id"]: s for s in project.segments}
        self.assertEqual(scenes.transition(project, seg["hook"]), {"in": "impact", "out": "blur"})
        self.assertEqual(scenes.transition(project, seg["hold"]), {"in": "blur", "out": "none"})
        self.assertEqual(scenes.transition(project, seg["ease"]), {"in": "swipe", "out": "blur"})
        config = scenes.scene_config(project, seg["hold"])
        self.assertTrue(config["holdbar"]["stop_at"] == 1.6 and config["dose"]["sets"] == 3)
        shots = scenes.stills(project, "hook", [0.03, 0.25, 1.0]) + scenes.stills(project, "hold", [0.05, 1.0, 2.0]) \
            + scenes.stills(project, "ease", [0.1, 0.5, 1.6]) + scenes.stills(project, "end", [1.2])
        self.assertTrue(all(p.is_file() for p in shots))
        with Image.open(shots[0]) as flash, Image.open(shots[2]) as settled:
            self.assertGreater(np.asarray(flash.convert("L")).mean(), np.asarray(settled.convert("L")).mean() + 60, "impact frame is inverted to white")
        keep = os.environ.get("FITNESS_TEST_KEEP")
        if keep:
            Path(keep).mkdir(parents=True, exist_ok=True)
            for p in shots:
                shutil.copy(p, Path(keep) / p.name)
        # Sound effects: a pack built from the creator's files, cues placed from the same scene configs.
        from fitness import sfx as sfx_effects, music as music_beds
        pack = TMP / "mh-pack"
        for cue, (name, _) in sfx_effects.MISTER_HORSE.items():
            target = pack / f"{name}.wav"
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=0.6", str(target)], check=True)
        project.channel["sfx"] = {"pack": "sfx-test", "gain_db": 0}  # in memory only: the shared channel approval stays valid
        self.assertEqual(len(sfx_effects.build_pack(project.channel, pack)), len(sfx_effects.MISTER_HORSE))
        timeline = sfx_effects.events(project)
        cues = {e["cue"] for e in timeline}
        self.assertTrue({"impact-bass-2", "click", "error", "whoosh"} <= cues, cues)
        self.assertTrue(all(b["t"] - a["t"] >= sfx_effects.DEDUPE for a, b in zip(timeline, timeline[1:])))
        track = sfx_effects.build_track(project)
        with wave.open(str(track)) as w:
            samples = np.frombuffer(w.readframes(w.getnframes()), "<i2").reshape(-1, 2)
        hit = timeline[0]
        self.assertGreater(np.abs(samples[int(hit["t"] * 48000): int(hit["t"] * 48000) + 4800]).max(), 1000)
        # Music: a new bed per video, refused when another video used the same style, checked for dropouts.
        project.channel["music"] = {"provider": "lyria", "gain_db": -18, "duck": False}
        project.brief["music"] = {"prompt": "dark ticking clock tension", "bpm": 108}

        async def fake_stream(output, seconds, spec, gap=None):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=110:duration={seconds:.2f}",
                            "-ac", "2", "-ar", "48000", str(output)], check=True)
            return seconds
        with patch.object(music_beds, "_stream", fake_stream):
            record = music_beds.generate(project)
            self.assertTrue(project.path(record["path"]).is_file())
            self.assertEqual(music_beds.bed(project), (project.path("audio/bgm.wav"), False))
            projects.init("motion-test-2", "Motion 2", "16:9")
            twin = projects.Project("motion-test-2")
            twin.channel["music"] = project.channel["music"]
            twin.brief["music"] = dict(project.brief["music"])
            for s in project.segments:
                twin.state["audio"][s["id"]] = project.state["audio"][s["id"]]
            with self.assertRaises(FitnessError):
                music_beds.generate(twin)  # same style as motion-test
        with tempfile.TemporaryDirectory() as work:
            seconds = sum(project.state["audio"][s["id"]]["seconds"] for s in project.segments)
            mix = assemble._mix(project, Path(work), seconds)
            self.assertGreater(probe(mix)["duration"], seconds - 0.1)
        silent = TMP / "gap.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=110:duration=10", "-af",
                        "volume=enable='between(t,4,6)':volume=0", str(silent)], check=True)
        self.assertTrue(music_beds.dropouts(silent))
        project.storyboard["scenes"][1]["timer"] = {"count": 10, "beat": 1}
        write_json(project.dir / "storyboard.json", project.storyboard)
        with self.assertRaises(FitnessError):
            scenes.scene_config(projects.Project("motion-test"), seg["hold"])  # dose and timer share a corner

    def test_gated_render_produces_matching_delivery(self):
        project = make_project("e2e-test")
        approve(project, "content")
        fake_media(project)
        with patch.object(providers, "gemini_image", return_value=figure_png()) as image:
            poses.generate(project)
            self.assertEqual(len(image.call_args.args[2]), 1, "the character reference is sent with the prompt")
        with self.assertRaises(FitnessError):
            scenes.render(project)  # media not approved yet
        poses.sheet(project)
        self.assertTrue(project.path("review/poses-grid.png").is_file())
        board = scenes.storyboard(project)
        self.assertTrue(board.is_file())
        approve(project, "media")
        self.assertEqual(sorted(scenes.render(project, jobs=2)), ["hold", "hook"])
        assemble.preview(project)
        report = qa.check(project, "preview")
        self.assertEqual((report["width"], report["height"]), (720, 1280))
        self.assertLess(abs(report["integrated_lufs"] + 14), 1.5)
        with self.assertRaises(FitnessError):
            assemble.final(project)  # render gate pending
        # Approval without retyping the digest binds to the last review and refuses changed files.
        project.record_review("render", project.gate_digest("render"))
        project.approve("render", None, "ok")
        record = assemble.final(project)
        final = project.path(record["path"])
        info = probe(final)
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        self.assertEqual((video["width"], video["height"]), (1080, 1920))
        expected = sum(project.state["audio"][s["id"]]["seconds"] for s in project.segments)
        self.assertAlmostEqual(info["duration"], expected, delta=0.1)
        delivery = json.loads(project.path("render/delivery.json").read_text(encoding="utf-8"))
        self.assertEqual(delivery["sha256"], file_hash(final))
        # Moving a tendon glow re-renders only that scene and invalidates the render approval.
        project.layout["poses"]["wall-sit"]["tendons"]["knee"]["x"] = .45
        self.assertFalse(project.approved("render"))
        self.assertTrue(project.approved("media"))


def tearDownModule():
    if not os.environ.get("FITNESS_KEEP_TEST_OUTPUT"):
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
