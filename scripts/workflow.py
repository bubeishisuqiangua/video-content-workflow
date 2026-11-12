#!/usr/bin/env python3
"""Local workflow ledger. Does not render, download, message, or publish."""

import argparse
import copy
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class WorkflowError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise WorkflowError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def instant(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        raise WorkflowError("Expected a timezone-aware ISO timestamp") from None
    require(result.tzinfo is not None and result.utcoffset() is not None,
            "Timestamp must include a timezone offset")
    return result


def read_json(path):
    with path.open(encoding="utf-8-sig") as handle:
        return json.load(handle)


def atomic_json(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reject_link(path):
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode) and not
            (getattr(info, "st_file_attributes", 0) &
             getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)),
            "Symlinks and reparse points are not supported in project paths")


class Project:
    def __init__(self, root):
        self.root = Path(os.path.abspath(root))
        require(self.root.is_dir(), "Project root must be an existing directory")
        reject_link(self.root)
        self.folder = self.root / ".video-workflow"
        self.state_path = self.folder / "state.json"

    def safe(self, value, *, file=True):
        path = Path(value)
        require(".." not in path.parts, "Parent traversal is not allowed")
        path = path if path.is_absolute() else self.root / path
        try:
            relative = path.relative_to(self.root)
        except ValueError:
            raise WorkflowError("File must be inside the project root") from None
        current = self.root
        for part in relative.parts:
            current = current / part
            if current.exists() or current.is_symlink():
                reject_link(current)
        if file:
            require(path.is_file() and path.stat().st_size > 0,
                    "Expected a nonempty regular project file")
        return path

    def asset(self, value, extensions=None):
        path = self.safe(value)
        if extensions:
            require(path.suffix.lower() in extensions, "Unsupported file extension")
        return {"path": path.relative_to(self.root).as_posix(),
                "sha256": sha256(path), "bytes": path.stat().st_size}

    @contextmanager
    def lock(self):
        self.safe(self.folder, file=False)
        self.folder.mkdir(exist_ok=True)
        lockpath = self.safe(self.folder / "lock", file=False)
        with lockpath.open("a+b") as handle:
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise WorkflowError("Another workflow command holds the project lock") from None
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def load(self):
        state = read_json(self.safe(self.state_path))
        require(state.get("schema_version") == 1, "Unsupported ledger version")
        return state

    def save(self, state):
        self.safe(self.state_path, file=False)
        atomic_json(self.state_path, state)


def media(path, *, video):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True, text=True, check=True)
        metadata = json.loads(result.stdout)
        streams = [s for s in metadata.get("streams", []) if s.get("codec_type") == "video"]
        require(streams, "No video/image stream found")
        stream = streams[0]
        facts = {"width": int(stream["width"]), "height": int(stream["height"])}
        require(facts["width"] > 0 and facts["height"] > 0, "Invalid media dimensions")
        if video:
            duration = float(metadata.get("format", {}).get("duration", 0))
            require(duration > 0, "Video has no positive duration")
            # Decode every audio/video stream, not merely a representative frame.
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(path),
                            "-map", "0:v", "-map", "0:a?", "-f", "null", "-"],
                           capture_output=True, check=True)
            facts.update(duration_seconds=duration, full_decode=True)
        return facts
    except FileNotFoundError:
        raise WorkflowError("Install FFmpeg and ffprobe and add them to PATH") from None
    except (subprocess.CalledProcessError, ValueError, KeyError):
        raise WorkflowError("Media probe or decode failed; inspect the source file") from None


def profile_check(profile):
    require(profile.get("schema_version") == 1, "Unsupported profile version")
    publish = profile["publish"]
    require(publish["max_per_day"] == 1, "This version supports exactly one video per day")
    require(isinstance(publish["enabled"], bool), "publish.enabled must be a boolean")
    for name, account in publish["platforms"].items():
        require(re.fullmatch(r"[a-z][a-z0-9_-]{0,40}", name), "Invalid platform key")
        require(isinstance(account, str) and account.strip(), "Each platform needs an exact account")
    for key in ("weekday_time", "weekend_time"):
        require(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", publish[key]), "Invalid schedule time")
    require(isinstance(profile["assets"]["caption_max_utf16"], int) and
            profile["assets"]["caption_max_utf16"] > 0, "Invalid caption limit")
    for key in ("cover_width", "cover_height"):
        require(isinstance(profile["assets"][key], int) and profile["assets"][key] > 0,
                "Cover dimensions must be positive integers")


def zone(job):
    try:
        return ZoneInfo(job["profile"]["publish"]["timezone"])
    except ZoneInfoNotFoundError:
        raise WorkflowError("Unknown/unavailable IANA timezone; Windows may need tzdata") from None


def wall_slot(day, clock, tz):
    naive = datetime.fromisoformat(str(day) + "T" + clock)
    candidate = naive.replace(tzinfo=tz)
    require(candidate.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) == naive and
            candidate.utcoffset() == candidate.replace(fold=1).utcoffset(),
            "Daily time is ambiguous/nonexistent at a DST transition; choose a different time")
    return candidate


def job_for(state, identifier):
    require(identifier in state["jobs"], "Unknown job ID")
    return state["jobs"][identifier]


def platform_for(job, name):
    require(name in job["platforms"], "Platform is not a target of this job")
    return job["platforms"][name]


def verify(project, job):
    require(job.get("assets") and all(k in job["assets"] for k in ("video", "caption", "cover", "qa")),
            "Job has no verified final asset set")
    for saved in job["assets"].values():
        actual = project.asset(saved["path"])
        require(actual["sha256"] == saved["sha256"] and actual["bytes"] == saved["bytes"],
                "Asset changed after verification; preserve prior files and create a revision")
    return job["assets"]


def evidence(project, path, started):
    item = project.asset(path, {".json"})
    report = read_json(project.safe(path))
    require(isinstance(report, dict), "Evidence must be a JSON object")
    require(report.get("observer") and report.get("note"), "Evidence needs observer and note")
    require(instant(report.get("observed_at")) >= instant(started), "Evidence predates this attempt")
    return item, report


def same_account_records(state, name, account):
    for job in state["jobs"].values():
        record = job["platforms"].get(name)
        if record and record["account"] == account:
            yield job, record


def event(job, action, **details):
    job["events"].append({"at": now(), "action": action, **details})


def run(args):
    if args.command == "init":
        Path(args.root).mkdir(parents=True, exist_ok=True)
    project = Project(args.root)
    with project.lock():
        if args.command == "init":
            config = project.safe("workflow.json", file=False)
            require(not project.state_path.exists() and not config.exists(),
                    "Project already initialized or profile exists; no files overwritten")
            template = Path(__file__).resolve().parent.parent / "assets" / "profile.example.json"
            atomic_json(config, read_json(template))
            mode = "simulation" if args.simulation else "live-recording"
            project.save({"schema_version": 1, "execution_mode": mode, "jobs": {}, "exclusions": []})
            return {"project": str(project.root), "profile": str(config), "execution_mode": mode}

        state = project.load()
        if args.command == "create":
            require(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}", args.id), "Invalid job ID")
            require(args.id not in state["jobs"], "Job already exists; resume it instead")
            profile = read_json(project.safe("workflow.json"))
            profile_check(profile)
            job = {"id": args.id, "title": args.title, "brief": args.brief,
                   "state": "planned", "execution_mode": state["execution_mode"],
                   "created_at": now(), "profile": copy.deepcopy(profile),
                   "assets": {}, "handoffs": {}, "events": [],
                   "platforms": {name: {"account": account, "state": "ready", "attempts": []}
                                 for name, account in profile["publish"]["platforms"].items()}}
            state["jobs"][args.id] = job
            event(job, "created")
        elif args.command == "exclude":
            item = project.asset(args.path, {".mp4", ".mov", ".webm", ".mkv"})
            require(not any(j.get("assets", {}).get("video", {}).get("sha256") == item["sha256"]
                            for j in state["jobs"].values()), "Video is already attached to a job")
            if not any(e["sha256"] == item["sha256"] for e in state["exclusions"]):
                state["exclusions"].append({**item, "reason": args.reason, "at": now()})
            project.save(state)
            return item
        else:
            job = job_for(state, args.id)
            if args.command == "show":
                return job
            if args.command == "verify":
                return verify(project, job)
            if args.command == "start":
                require(job["state"] == "planned", "Only a planned job can start production")
                job["state"] = "producing"
                event(job, "production_started")
            elif args.command == "video":
                require(args.final and args.approval_reference.strip(),
                        "Final video requires --final and an actual approval/policy reference")
                item = project.asset(args.path, {".mp4", ".mov", ".webm", ".mkv"})
                if job["assets"].get("video"):
                    old = job["assets"]["video"]
                    require(item["sha256"] == old["sha256"] and item["path"] == old["path"],
                            "Final video is immutable; create an explicit revision job")
                    return job
                require(job["state"] in {"planned", "producing"}, "Wrong stage for video")
                require(not any(e["sha256"] == item["sha256"] for e in state["exclusions"]),
                        "Video matches excluded/baseline content")
                require(not any(other["id"] != args.id and
                                other["assets"].get("video", {}).get("sha256") == item["sha256"]
                                for other in state["jobs"].values()), "Duplicate video content")
                facts = media(project.safe(args.path), video=True)
                # Detect a local edit during the long media check.
                require(project.asset(args.path) == item, "Video changed during validation")
                job["assets"]["video"] = item
                job["video_facts"] = facts
                job["final_approval_reference"] = args.approval_reference
                job["state"] = "awaiting_assets"
                event(job, "final_video_attached")
            elif args.command == "assets":
                require(not any(p["attempts"] for p in job["platforms"].values()),
                        "Cannot replace assets after a submission attempt")
                require(job["state"] in {"awaiting_assets", "ready"}, "Wrong stage for assets")
                video = job["assets"].get("video")
                require(video and project.asset(video["path"]) == video, "Final video changed")
                caption = project.asset(args.caption, {".txt"})
                cover = project.asset(args.cover, {".png", ".jpg", ".jpeg", ".webp"})
                qa = project.asset(args.qa, {".json"})
                require(len({i["path"] for i in (video, caption, cover, qa)}) == 4,
                        "Assets must be distinct files")
                text = project.safe(args.caption).read_text(encoding="utf-8-sig")
                rules = job["profile"]["assets"]
                require(text.strip() and len(text.encode("utf-16-le")) // 2 <= rules["caption_max_utf16"],
                        "Caption is empty or exceeds the configured UTF-16 limit")
                tags = set(re.findall(r"(?<!\w)#[\w]+", text, re.UNICODE))
                require(all(tag in tags for tag in rules["required_hashtags"]), "Missing required hashtag")
                facts = media(project.safe(args.cover), video=False)
                require((facts["width"], facts["height"]) == (rules["cover_width"], rules["cover_height"]),
                        "Cover dimensions do not match the job profile")
                report = read_json(project.safe(args.qa))
                require(report.get("reviewer") and report.get("notes"), "QA requires reviewer and notes")
                instant(report.get("observed_at"))
                require(all(report.get(key) is True for key in
                            ("video_reviewed", "caption_reviewed", "cover_reviewed")),
                        "Complete the actual video/caption/cover review first")
                for item in (video, caption, cover, qa):
                    require(project.asset(item["path"]) == item, "Asset changed during validation")
                job["assets"] = {"video": video, "caption": caption, "cover": cover, "qa": qa}
                job["state"] = "ready"
                event(job, "assets_verified")
            elif args.command == "handoff":
                previous = job["handoffs"].get(args.stage)
                if previous and previous["state"] == "sent":
                    require(args.state == "sent" and previous["reference"] == args.reference,
                            "Handoff already sent; inspect target before any retry")
                    return job
                allowed = job["state"] == "awaiting_assets" if args.stage == "assets" else job["state"] == "ready"
                require(allowed, "Job is not ready for this handoff stage")
                if args.stage == "publisher":
                    verify(project, job)
                require(args.state == "sending" or previous and previous["state"] == "sending",
                        "Record sending before recording sent")
                job["handoffs"][args.stage] = {"state": args.state, "reference": args.reference, "at": now()}
                event(job, "handoff_" + args.state, stage=args.stage)
            elif args.command in {"slot", "begin-submit", "confirm", "reconcile-absent"}:
                record = platform_for(job, args.platform)
                tz = zone(job)
                if args.command == "slot":
                    require(record["state"] == "ready", "Platform already has a submission attempt")
                    boundary = datetime.now(tz)
                    if args.after:
                        boundary = max(boundary, instant(args.after).astimezone(tz))
                    for _, other in same_account_records(state, args.platform, record["account"]):
                        if other["state"] in {"submitting", "scheduled"}:
                            boundary = max(boundary, instant(other["scheduled_at"]).astimezone(tz))
                    candidate = boundary.date()
                    while True:
                        key = "weekend_time" if candidate.weekday() >= 5 else "weekday_time"
                        timestamp = wall_slot(candidate, job["profile"]["publish"][key], tz)
                        if timestamp > boundary:
                            return {"platform": args.platform, "account": record["account"],
                                    "suggested_at": timestamp.isoformat(), "online_verified": False}
                        candidate += timedelta(days=1)
                if args.command == "begin-submit":
                    verify(project, job)
                    policy = job["profile"]["publish"]
                    require(job["state"] in {"ready", "publishing"} and record["state"] == "ready", "Platform is not ready")
                    require(policy["enabled"] is True and policy["authorization_reference"].strip(),
                            "Publishing disabled or no user authorization reference recorded")
                    planned = instant(args.at).astimezone(tz)
                    require(planned > datetime.now(tz), "Scheduled timestamp must be in the future")
                    key = "weekend_time" if planned.weekday() >= 5 else "weekday_time"
                    require(planned.strftime("%H:%M") == policy[key] and planned.second == 0 and planned.microsecond == 0,
                            "Timestamp does not match the configured daily slot")
                    wall_slot(planned.date(), policy[key], tz)
                    for other_job, other in same_account_records(state, args.platform, record["account"]):
                        require(other["state"] != "submitting", "Reconcile the account's pending attempt first")
                        if other_job["id"] != args.id and other["state"] == "scheduled":
                            require(instant(other["scheduled_at"]).astimezone(tz).date() != planned.date(),
                                    "Daily slot is already occupied in the local ledger")
                    attempt = {"id": uuid.uuid4().hex, "started_at": now(), "scheduled_at": planned.isoformat(),
                               "authorization_reference": policy["authorization_reference"]}
                    record["attempts"].append(attempt)
                    record.update(state="submitting", scheduled_at=planned.isoformat())
                    job["state"] = "publishing"
                    event(job, "submission_started", platform=args.platform, attempt=attempt["id"])
                else:
                    require(record["attempts"] and record["attempts"][-1]["id"] == args.attempt,
                            "Attempt ID does not match the latest attempt")
                    attempt = record["attempts"][-1]
                    if args.command == "confirm" and record["state"] == "scheduled":
                        require(record["post_id"] == args.post_id and record["account"] == args.account and
                                instant(record["scheduled_at"]) == instant(args.at) and args.visibility == "public",
                                "Existing scheduled record differs; no automatic revision")
                        return job
                    require(record["state"] == "submitting", "No unresolved submission to reconcile")
                    proof, report = evidence(project, args.evidence, attempt["started_at"])
                    require(report.get("account") == record["account"], "Evidence has a different account")
                    if args.command == "confirm":
                        verify(project, job)
                        require(args.account == record["account"] and args.visibility == "public",
                                "Account or public visibility does not match")
                        require(instant(args.at) == instant(record["scheduled_at"]), "Scheduled time differs")
                        require(report.get("post_id") == args.post_id and report.get("visibility") == "public" and
                                instant(report.get("scheduled_at")) == instant(args.at), "Evidence fields differ")
                        require(not any(other_job["id"] != args.id and other.get("post_id") == args.post_id
                                        for other_job, other in same_account_records(state, args.platform, args.account)),
                                "Post ID already belongs to another job")
                        attempt.update(result="scheduled", evidence=proof)
                        record.update(state="scheduled", post_id=args.post_id, visibility="public", evidence=proof)
                        if all(p["state"] == "scheduled" for p in job["platforms"].values()):
                            job["state"] = "scheduled"
                        event(job, "schedule_verified", platform=args.platform, post_id=args.post_id)
                    else:
                        require(report.get("absent") is True and
                                {"scheduled", "published", "drafts"}.issubset(set(report.get("checked", []))),
                                "Absence evidence must include scheduled, published, and drafts")
                        attempt.update(result="reconciled_absent", evidence=proof)
                        record["state"] = "ready"
                        record.pop("scheduled_at", None)
                        job["state"] = "ready" if all(p["state"] == "ready" for p in job["platforms"].values()) else "publishing"
                        event(job, "absence_verified", platform=args.platform)
        project.save(state)
        return job


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--root", required=True, help="Separate project root")
    subs = result.add_subparsers(dest="command", required=True)
    init = subs.add_parser("init")
    init.add_argument("--simulation", action="store_true", help="Label all records as offline simulation; no live actions allowed")
    create = subs.add_parser("create")
    create.add_argument("id")
    create.add_argument("--title", required=True)
    create.add_argument("--brief", required=True)
    exclude = subs.add_parser("exclude")
    exclude.add_argument("--path", required=True)
    exclude.add_argument("--reason", required=True)
    for command in ("start", "show", "verify", "video", "assets", "handoff", "slot", "begin-submit", "confirm", "reconcile-absent"):
        sub = subs.add_parser(command)
        sub.add_argument("id")
        if command == "video":
            sub.add_argument("--path", required=True)
            sub.add_argument("--final", action="store_true")
            sub.add_argument("--approval-reference", required=True)
        elif command == "assets":
            for flag in ("caption", "cover", "qa"):
                sub.add_argument("--" + flag, required=True)
        elif command == "handoff":
            sub.add_argument("--stage", choices=("assets", "publisher"), required=True)
            sub.add_argument("--state", choices=("sending", "sent"), required=True)
            sub.add_argument("--reference", required=True)
        elif command in {"slot", "begin-submit", "confirm", "reconcile-absent"}:
            sub.add_argument("platform")
            if command == "slot":
                sub.add_argument("--after")
            elif command == "begin-submit":
                sub.add_argument("--at", required=True)
            else:
                sub.add_argument("--attempt", required=True)
                sub.add_argument("--evidence", required=True)
                if command == "confirm":
                    for flag in ("post-id", "account", "at"):
                        sub.add_argument("--" + flag, required=True)
                    sub.add_argument("--visibility", choices=("public",), required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
        return 0
    except (WorkflowError, OSError, ValueError, KeyError, TypeError) as error:
        # Do not echo arbitrary provider responses, subprocess logs, or secrets.
        message = str(error) if isinstance(error, WorkflowError) else type(error).__name__ + ": check local files/profile"
        print(json.dumps({"error": message}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
