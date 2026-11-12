import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "workflow.py"
spec = importlib.util.spec_from_file_location("workflow", MODULE)
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.call("init")
        self.profile = w.read_json(self.root / "workflow.json")
        self.profile["assets"].update(cover_width=32, cover_height=48)
        self.profile["publish"].update(enabled=True, authorization_reference="Explicit test-only authorization",
                                        platforms={"alpha": "@example-alpha", "beta": "@example-beta"})
        self.save_profile()
        self.write("media/video.mp4", b"synthetic unit-test bytes; media probe is mocked")
        self.write("assets/cover.png", b"synthetic image fixture")
        self.write("assets/caption.txt", "A useful result. #Example")
        self.write_json("assets/qa.json", {"reviewer": "test reviewer", "observed_at": w.now(),
                       "video_reviewed": True, "caption_reviewed": True, "cover_reviewed": True,
                       "notes": "Unit test attestation, not real media review"})
        self.probe = patch.object(w, "media", return_value={"width": 32, "height": 48,
                                                          "duration_seconds": 1, "full_decode": True})
        self.probe.start()
        self.addCleanup(self.probe.stop)

    def call(self, *values):
        return w.run(w.parser().parse_args(["--root", str(self.root), *values]))

    def save_profile(self):
        w.atomic_json(self.root / "workflow.json", self.profile)

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)

    def write_json(self, relative, data):
        self.write(relative, json.dumps(data))

    def make_job(self, identifier="demo", *, complete=True, video="media/video.mp4"):
        self.call("create", identifier, "--title", "Demo", "--brief", "A task and a result")
        self.call("start", identifier)
        self.call("video", identifier, "--path", video, "--final", "--approval-reference", "Test fixture approved")
        if complete:
            self.assets(identifier)
        return self.call("show", identifier)

    def assets(self, identifier="demo"):
        return self.call("assets", identifier, "--caption", "assets/caption.txt", "--cover", "assets/cover.png",
                         "--qa", "assets/qa.json")

    def future(self, days=7):
        return (datetime.now(timezone.utc) + timedelta(days=days)).replace(
            hour=19 if (datetime.now(timezone.utc) + timedelta(days=days)).weekday() >= 5 else 12,
            minute=30, second=0, microsecond=0).isoformat()

    def begin(self, identifier="demo", platform="alpha", at=None):
        return self.call("begin-submit", identifier, platform, "--at", at or self.future())

    def confirm(self, platform="alpha", identifier="demo", post_id="example-post"):
        record = self.call("show", identifier)["platforms"][platform]
        proof = {"observed_at": w.now(), "observer": "test", "note": "Synthetic offline evidence",
                 "post_id": post_id, "account": record["account"], "scheduled_at": record["scheduled_at"],
                 "visibility": "public"}
        self.write_json("evidence/" + platform + ".json", proof)
        return self.call("confirm", identifier, platform, "--attempt", record["attempts"][-1]["id"],
                         "--post-id", post_id, "--account", record["account"], "--at", record["scheduled_at"],
                         "--visibility", "public", "--evidence", "evidence/" + platform + ".json")

    def test_real_stage_progression_and_profile_snapshot(self):
        job = self.make_job()
        self.assertEqual(job["state"], "ready")
        self.assertEqual(set(self.call("verify", "demo")), {"video", "caption", "cover", "qa"})
        self.profile["publish"]["platforms"]["alpha"] = "@changed"
        self.save_profile()
        self.assertEqual(self.call("show", "demo")["platforms"]["alpha"]["account"], "@example-alpha")

    def test_duplicate_video_and_baseline_are_rejected(self):
        self.make_job()
        self.write("media/renamed.mp4", (self.root / "media/video.mp4").read_bytes())
        with self.assertRaisesRegex(w.WorkflowError, "Duplicate"):
            self.make_job("copy", video="media/renamed.mp4")
        self.write("media/old.mp4", b"old content")
        self.call("exclude", "--path", "media/old.mp4", "--reason", "Already published")
        with self.assertRaisesRegex(w.WorkflowError, "baseline"):
            self.make_job("old", video="media/old.mp4")

    def test_mutated_asset_blocks_submission_without_partial_write(self):
        self.make_job()
        before = (self.root / ".video-workflow/state.json").read_bytes()
        self.write("assets/caption.txt", "Changed after handoff")
        with self.assertRaisesRegex(w.WorkflowError, "changed"):
            self.begin()
        self.assertEqual(before, (self.root / ".video-workflow/state.json").read_bytes())

    def test_uncertain_attempt_cannot_resubmit_and_assets_are_frozen(self):
        self.make_job()
        self.begin()
        with self.assertRaises(w.WorkflowError):
            self.begin()
        with self.assertRaisesRegex(w.WorkflowError, "submission attempt"):
            self.assets()

    def test_independent_platform_completion_and_idempotent_confirmation(self):
        self.make_job()
        self.begin()
        first = self.confirm()
        self.assertEqual(first["state"], "publishing")
        self.assertEqual(first["platforms"]["beta"]["state"], "ready")
        with self.assertRaises(w.WorkflowError):
            self.begin()
        self.begin(platform="beta")
        finished = self.confirm("beta", post_id="second-post")
        self.assertEqual(finished["state"], "scheduled")
        self.assertEqual(self.confirm("beta", post_id="second-post"), finished)

    def test_reconciliation_requires_all_online_surfaces_and_latest_attempt(self):
        self.make_job()
        job = self.begin()
        record = job["platforms"]["alpha"]
        attempt = record["attempts"][-1]["id"]
        report = {"observed_at": w.now(), "observer": "test", "note": "Offline fixture",
                  "absent": True, "account": record["account"], "checked": ["scheduled"]}
        self.write_json("evidence/absence.json", report)
        args = ("reconcile-absent", "demo", "alpha", "--attempt", attempt,
                "--evidence", "evidence/absence.json")
        with self.assertRaisesRegex(w.WorkflowError, "drafts"):
            self.call(*args)
        report["checked"] += ["published", "drafts"]
        self.write_json("evidence/absence.json", report)
        self.assertEqual(self.call(*args)["platforms"]["alpha"]["state"], "ready")
        newer = self.begin()["platforms"]["alpha"]["attempts"][-1]["id"]
        self.assertNotEqual(attempt, newer)
        with self.assertRaisesRegex(w.WorkflowError, "Attempt ID"):
            self.call(*args)

    def test_daily_cap_and_account_pending_attempt(self):
        self.make_job()
        self.write("media/second.mp4", b"different final content")
        self.make_job("second", video="media/second.mp4")
        self.begin()
        with self.assertRaisesRegex(w.WorkflowError, "pending"):
            self.begin(identifier="second", at=self.future(8))
        self.confirm()
        with self.assertRaisesRegex(w.WorkflowError, "occupied"):
            self.begin(identifier="second")
        suggested = self.call("slot", "second", "alpha")["suggested_at"]
        self.assertGreater(w.instant(suggested).date(), w.instant(self.future()).date())

    def test_publishing_disabled_does_not_allow_attempt(self):
        self.profile["publish"]["enabled"] = False
        self.save_profile()
        self.make_job()
        with self.assertRaisesRegex(w.WorkflowError, "disabled"):
            self.begin()

    def test_cover_caption_and_qa_checks(self):
        self.profile["assets"].update(required_hashtags=["#Example"], caption_max_utf16=30)
        self.save_profile()
        self.make_job(complete=False)
        self.write("assets/caption.txt", "#ExampleExtra")
        with self.assertRaisesRegex(w.WorkflowError, "hashtag"):
            self.assets()
        self.write("assets/caption.txt", "#Example " + "😀" * 12)
        with self.assertRaisesRegex(w.WorkflowError, "UTF-16"):
            self.assets()
        self.write("assets/caption.txt", "#Example")
        with patch.object(w, "media", return_value={"width": 48, "height": 32}):
            with self.assertRaisesRegex(w.WorkflowError, "dimensions"):
                self.assets()
        report = w.read_json(self.root / "assets/qa.json")
        report["video_reviewed"] = False
        self.write_json("assets/qa.json", report)
        with self.assertRaisesRegex(w.WorkflowError, "review"):
            self.assets()

    def test_handoff_preserves_sent_state(self):
        self.make_job()
        with self.assertRaisesRegex(w.WorkflowError, "sending"):
            self.call("handoff", "demo", "--stage", "publisher", "--state", "sent", "--reference", "msg-1")
        self.call("handoff", "demo", "--stage", "publisher", "--state", "sending", "--reference", "worker")
        self.call("handoff", "demo", "--stage", "publisher", "--state", "sent", "--reference", "msg-1")
        with self.assertRaisesRegex(w.WorkflowError, "already sent"):
            self.call("handoff", "demo", "--stage", "publisher", "--state", "sending", "--reference", "worker")

    def test_handoff_receipt_is_idempotent_after_stage_advances(self):
        self.make_job(complete=False)
        self.call("handoff", "demo", "--stage", "assets", "--state", "sending", "--reference", "editor")
        self.call("handoff", "demo", "--stage", "assets", "--state", "sent", "--reference", "message")
        self.assets()
        again = self.call("handoff", "demo", "--stage", "assets", "--state", "sent", "--reference", "message")
        self.assertEqual(again["state"], "ready")
        self.assertEqual(again["handoffs"]["assets"]["reference"], "message")

    def test_simulation_is_marked_in_project_and_job(self):
        with tempfile.TemporaryDirectory() as other:
            args = ["--root", other]
            result = w.run(w.parser().parse_args([*args, "init", "--simulation"]))
            self.assertEqual(result["execution_mode"], "simulation")
            job = w.run(w.parser().parse_args([*args, "create", "fixture", "--title", "Fixture", "--brief", "Offline only"]))
            self.assertEqual(job["execution_mode"], "simulation")

    def test_ambiguous_and_nonexistent_daily_times_are_rejected(self):
        try:
            tz = w.ZoneInfo("America/New_York")
        except w.ZoneInfoNotFoundError:
            self.skipTest("IANA timezone data unavailable")
        for day, clock in ((datetime(2026, 3, 8).date(), "02:30"), (datetime(2026, 11, 1).date(), "01:30")):
            with self.assertRaisesRegex(w.WorkflowError, "DST"):
                w.wall_slot(day, clock, tz)

    def test_path_escape_and_symlinks(self):
        project = w.Project(self.root)
        for path in ("../outside.mp4", str(self.root.parent / "outside.mp4")):
            with self.assertRaises(w.WorkflowError):
                project.asset(path)
        try:
            (self.root / "link").symlink_to(self.root / "media", target_is_directory=True)
        except OSError:
            return  # Windows without symlink privilege still tests traversal above.
        with self.assertRaisesRegex(w.WorkflowError, "Symlinks"):
            project.asset("link/video.mp4")

    def test_process_lock_and_atomic_write_failure_preserve_state(self):
        project = w.Project(self.root)
        with project.lock():
            result = subprocess.run([sys.executable, str(MODULE), "--root", str(self.root),
                                     "create", "other", "--title", "Other", "--brief", "test"],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("lock", result.stderr)
        original = project.state_path.read_bytes()
        with patch.object(os, "replace", side_effect=OSError("simulated write failure")):
            with self.assertRaises(OSError):
                project.save({"schema_version": 1, "jobs": {}, "exclusions": []})
        self.assertEqual(project.state_path.read_bytes(), original)
        self.assertEqual(list(project.folder.glob(".write-*")), [])

    def test_confirm_rejects_stale_evidence(self):
        self.make_job()
        job = self.begin()
        record = job["platforms"]["alpha"]
        proof = {"observed_at": "2000-01-01T00:00:00+00:00", "observer": "test", "note": "Old evidence",
                 "account": "@example-alpha", "post_id": "p", "visibility": "public",
                 "scheduled_at": record["scheduled_at"]}
        self.write_json("evidence/old.json", proof)
        with self.assertRaisesRegex(w.WorkflowError, "predates"):
            self.call("confirm", "demo", "alpha", "--attempt", record["attempts"][-1]["id"],
                      "--post-id", "p", "--account", "@example-alpha", "--at", record["scheduled_at"],
                      "--visibility", "public", "--evidence", "evidence/old.json")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg not installed")
class MediaIntegrationTests(unittest.TestCase):
    def test_generated_video_and_image_decode_and_corrupt_video_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video, image = root / "generated.mp4", root / "generated.png"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                            "color=c=blue:s=64x96:r=10", "-f", "lavfi", "-i", "sine=frequency=440",
                            "-t", "0.6", "-c:v", "mpeg4", "-c:a", "aac", str(video)], check=True)
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                            "color=c=orange:s=32x48", "-frames:v", "1", "-threads", "1", str(image)], check=True)
            self.assertTrue(w.media(video, video=True)["full_decode"])
            self.assertEqual(w.media(image, video=False), {"width": 32, "height": 48})
            video.write_bytes(b"not a video")
            with self.assertRaisesRegex(w.WorkflowError, "probe or decode"):
                w.media(video, video=True)


if __name__ == "__main__":
    unittest.main()
