"""Fitness explainer workflow CLI.

  setup | doctor
  channel init | voices | sample | character | select | add-reference | review | approve
  init | status | reference | skeleton | research | originality | review | approve | notes
  produce (= audio + poses + sheets + storyboard) | build (= visuals + preview + check) | render
  audio | poses | sheet | stills | storyboard | visuals | preview | check

Read .agents/skills/fitness-explainer/SKILL.md for the gated process.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fitness import assemble, audio, notes, poses, providers, qa, reference, research, scenes  # noqa: E402
from fitness import channel as channel_profile  # noqa: E402
from fitness import project as projects  # noqa: E402
from fitness.common import CHANNEL_DIR, ROOT, RUNTIME, FitnessError, secret_present, which  # noqa: E402

SAMPLE_TEXT = ("Your tendons adapt slower than your muscles. Hold this position for thirty seconds, "
               "breathe, and feel the load build up around the knee.")


def setup(_args) -> None:
    npm = which("npm")
    if not npm or not which("node") or not which("ffmpeg"):
        raise FitnessError("Node.js, npm and FFmpeg are required: run setup/setup.ps1")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if not (RUNTIME / "package.json").exists():
        (RUNTIME / "package.json").write_text('{"private":true}\n', encoding="utf-8")
    if not (RUNTIME / "node_modules/playwright").is_dir():
        subprocess.run([npm, "install", "--no-audit", "--no-fund", "playwright@1"], cwd=RUNTIME, check=True)
    subprocess.run([str(RUNTIME / "node_modules/.bin/playwright.cmd"), "install", "chromium"], cwd=RUNTIME, check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r",
                    str(ROOT / "config/fitness/requirements.txt")], check=True)
    print(f"Fitness render runtime ready: {RUNTIME}")


def doctor(_args) -> None:
    rows = []
    for name in ("GENMAX_API_KEY", "GEMINI_API_KEY"):
        rows.append(("OK" if secret_present(name) else "ACTION", name, "present locally (not remotely validated)" if secret_present(name) else "missing: run setup/configure.ps1"))
    for binary in ("node", "ffmpeg", "ffprobe"):
        rows.append(("OK" if which(binary) else "ACTION", binary, "found" if which(binary) else "missing: run setup/setup.ps1"))
    rows.append(("OK" if (RUNTIME / "node_modules/playwright").is_dir() else "ACTION", "render runtime", str(RUNTIME)))
    try:
        providers.codex_script()
        codex = which("codex") or os.environ.get("CODEX_BIN")
        result = subprocess.run([codex, "login", "status"], capture_output=True, text=True, timeout=30) if codex else None
        status = (result.stdout + result.stderr) if result else ""  # codex prints the status on stderr
        logged_in = "Logged in" in status
        rows.append(("OK" if logged_in else "ACTION", "Codex images",
                     "Codex CLI logged in (ChatGPT plan)" if logged_in else
                     ("not logged in: double-click 4-Dang-nhap-Codex.cmd; Gemini backup is used meanwhile" if codex else
                      "Codex CLI missing: run 1-Cai-dat.cmd; Gemini backup is used meanwhile")))
    except (FitnessError, OSError, subprocess.SubprocessError) as exc:
        rows.append(("ACTION", "Codex images", f"{exc}; Gemini backup is used"))
    try:
        channel = channel_profile.load()
        rows.append(("OK", "channel profile", str(channel_profile.PROFILE)))
        try:
            rows.append(("OK", "voice provider", channel_profile.voice_provider(channel)))
        except FitnessError as exc:
            rows.append(("ACTION", "voice provider", str(exc)))
        for character_id in channel["characters"]:
            try:
                count = len(channel_profile.references(channel, character_id))
                rows.append(("OK", f"character {character_id}", f"{count} reference image(s)"))
            except FitnessError as exc:
                rows.append(("ACTION", f"character {character_id}", str(exc)))
        rows.append(("OK" if channel_profile.approval_current(channel) else "ACTION", "channel approval",
                     "current" if channel_profile.approval_current(channel) else "missing or stale"))
    except FitnessError as exc:
        rows.append(("ACTION", "channel profile", str(exc)))
    for row in rows:
        print(" | ".join(row))
    print("Local checks only. No API call, generation or publishing performed.")


# -- channel ------------------------------------------------------------------

def channel_cmd(args) -> None:
    if args.channel_action == "init":
        print(channel_profile.init())
        return
    channel = channel_profile.load()
    if args.channel_action == "voices":
        for voice in providers.genmax_voices(args.search, args.limit)[:args.limit]:
            languages = ",".join(sorted({v.get("language_id", "") for v in voice.get("verified_languages", [])}))
            print(f"{voice.get('voice_id')} | {voice.get('name')} | {voice.get('gender')}/{voice.get('age')}/{voice.get('accent')} | "
                  f"{voice.get('use_case')} | {languages} | {voice.get('preview_url', '')}")
    elif args.channel_action == "sample":
        folder = CHANNEL_DIR / "voice-samples"
        folder.mkdir(parents=True, exist_ok=True)
        text = args.text or SAMPLE_TEXT
        if args.gemini_voice:
            config = channel["voice"]["gemini"]
            pcm = providers.gemini_speech(config["model"], text, args.gemini_voice, config.get("style", ""))
            raw = folder / f"gemini-{args.gemini_voice}.pcm"
            raw.write_bytes(pcm)
            target = raw.with_suffix(".mp3")
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1",
                            "-i", str(raw), "-b:a", "128k", str(target)], check=True)
            raw.unlink()
        else:
            if not args.voice_id:
                raise FitnessError("--voice-id is required (or --gemini-voice)")
            config = {**channel["voice"]["genmax"], "voice_id": args.voice_id}
            if args.model_id:
                config["model_id"] = args.model_id
            task = providers.genmax_submit(text, config)
            print(f"Genmax task {task} submitted; waiting")
            result = providers.genmax_wait(task)
            target = folder / f"genmax-{args.voice_id}.mp3"
            target.write_bytes(providers.genmax_download(result["result"]["audio_url"]))
            print(f"credits_deducted={result.get('credits_deducted')}")
        print(target.resolve())
    elif args.channel_action == "character":
        for name, path, info in poses.character_candidates(channel, args.id, args.candidates):
            print(f"{name}: {path} {info['warnings'] or ''}")
        print(CHANNEL_DIR / "characters" / args.id / "candidates.png")
    elif args.channel_action == "select":
        poses.select_character(channel, args.character, args.candidate)
        print("\n".join(map(str, channel_profile.references(channel, args.character))))
    elif args.channel_action == "add-reference":
        print(channel_profile.add_reference(channel, args.character, Path(args.image), args.label))
    elif args.channel_action == "review":
        voice = channel_profile.voice_config(channel)
        print(f"Channel: {channel['name']}\nPalette: {channel['palette']}\nDefault character: {channel['default_character']}")
        for character_id, spec in channel["characters"].items():
            print(f"- {character_id}: {spec['description']}\n  signature: {spec.get('signature')}")
            for reference in channel_profile.references(channel, character_id):
                print(f"  reference: {reference}")
        print(f"Voice (default {channel['voice'].get('default')}): {voice}")
        for preset_id, preset in channel_profile.voice_presets(channel).items():
            print(f"  preset {preset_id}: {preset['name']} ({preset['voice_id']})")
        print(f"Music: {channel.get('music')}")
        print(f"sha256={channel_profile.record_review(channel)}")
    elif args.channel_action == "approve":
        channel_profile.approve(channel, args.expected_sha256, args.decision)
        print("Channel approval recorded")


# -- project ------------------------------------------------------------------

def init_cmd(args) -> None:
    print(projects.init(args.project, args.title, args.aspect, args.voice, args.tag))


def status_cmd(args) -> None:
    project = projects.Project(args.project)
    print(f"{project.name}: {project.brief['title']} [{project.brief['aspect']} {project.size[0]}x{project.size[1]} @{project.size[2]}fps]")
    for gate in projects.GATES:
        approval = project.state["approvals"].get(gate)
        current = project.approved(gate)
        print(f"  {gate:8} {'approved' if current else ('STALE' if approval else 'pending')}")
    for segment in project.segments:
        sid = segment["id"]
        a, s = project.state["audio"].get(sid), project.state["scenes"].get(sid)
        pending = project.state.get("audio_tasks", {}).get(sid)
        print(f"  - {sid}: audio={'%.2fs' % a['seconds'] if a else ('task ' + pending.get('status', '?') if pending else '-')} "
              f"scene={'yes' if s else '-'}")
    for pose_id in project.used_poses():
        record = project.state["poses"].get(pose_id)
        print(f"  pose {pose_id}: {record['path'] if record else '-'} {(record or {}).get('warnings') or ''}")
    for name in ("preview", "final"):
        output = project.state["outputs"].get(name)
        if output:
            print(f"  {name}: {project.path(output['path'])} ({output['seconds']}s, {output['bytes'] // 1024} KiB)")
    credits = sum(r.get("credits") or 0 for r in project.state["audio"].values())
    images = {}
    for pose_id, record in project.state["poses"].items():
        provider = (record.get("made_by") or {}).get("provider", "gemini")
        images[provider] = images.get(provider, 0) + project.state.get("pose_takes", {}).get(pose_id, 1)
    drawn = ", ".join(f"{name} {count}" for name, count in sorted(images.items())) or "none"
    print(f"  spent: Genmax credits {credits} (current narration), images {drawn} (incl. retakes; content-changed redraws not counted)")
    missing = poses.missing_layout(project) if project.state["poses"] else []
    if missing:
        print(f"  layout.json still needs tendon positions: {', '.join(missing)}")


def review_cmd(args) -> None:
    project = projects.Project(args.project)
    for earlier in projects.GATES[:projects.GATES.index(args.gate)]:
        project.require(earlier)
    sha = project.gate_digest(args.gate)
    lines = [f"# {project.brief['title']} — {args.gate} review", ""]
    if args.gate == "content":
        tag = project.brief.get("tag")
        lines += [f"Aspect {project.brief['aspect']}; audience: {project.brief.get('audience', '')}",
                  f"Pinned tag (top-left on every scene): {tag}" if tag else "Pinned tag: MISSING - set brief.tag (e.g. 'Tendons · Full guide · At home · No gym') before approval",
                  "", "## Script and scenes", ""]
        for segment in project.segments:
            scene = project.scene_for(segment["id"])
            lines += [f"### {segment['id']}", segment["text"], ""]
            if segment.get("delivery"):
                lines.append(f"*Delivery:* {segment['delivery']}")
            visual = {k: v for k, v in scene.items() if k != "segment_id"}
            lines += [f"*Visual:* {visual}", ""]
        lines += ["## Poses", *[f"- {k}: {v['prompt']}" for k, v in project.storyboard["poses"].items()], "",
                  "## Claims", *[f"- {c['id']}: {c['text']} ({', '.join(c['source_ids'])})" for c in project.claims["claims"]], "",
                  "## Sources", *[f"- {s['id']}: {s['title']} — {s['locator']}" for s in project.sources["sources"]]]
        if project.path("reference/analysis.json").is_file():
            ref = reference.read_json(project.path("reference/analysis.json"))
            check = reference.originality(project) if project.path("reference/transcript.json").is_file() else None
            lines += ["", f"Reference: {ref.get('title')} ({ref.get('url') or 'local file'}), {ref.get('duration')} s, {len(ref['chapters'])} chapters",
                      ("Wording overlap with the reference: " + (f"{check['coverage']:.0%} of words, longest shared run "
                       f"{check['longest_shared_words']} words" + ("" if check["ok"] else " - REWRITE before approval")) if check and ref.get("words")
                       else "Wording overlap: no reference transcript")]
        checked = {r["id"]: r for r in (project.state.get("source_check") or {}).get("results", [])}
        lines += ["", "Source check (Crossref): " + (", ".join(f"{k} {v['status']}" for k, v in checked.items()) if checked
                                                  else "not run; run `research --project ...`")]
    elif args.gate == "media":
        voice = channel_profile.voice_config(project.channel, project.voice_preset)
        lines += [f"Voice: {voice['service']} {voice.get('voice_id') or voice.get('voice_name')}",
                  f"Narration for listening (all segments, joined as in the video): {assemble.narration_review(project)}", ""]
        for segment in project.segments:
            record = project.state["audio"][segment["id"]]
            lines.append(f"- {segment['id']}: {project.path(record['path'])} ({record['speech_seconds']:.2f}s speech, {record['seconds']:.2f}s slot)")
        lines += ["", f"Pose sheet: {poses.sheet(project)}"]
        board = project.path("review/storyboard.png")
        if board.is_file():
            lines.append(f"Storyboard (every scene after each beat): {board}")
        for pose_id in project.used_poses():
            record = project.state["poses"][pose_id]
            lines.append(f"- {pose_id}: {project.path(record['path'])} {record.get('warnings') or ''}")
    else:
        preview = project.state["outputs"]["preview"]
        report = qa.check(project, "preview")
        lines += [f"Draft preview: {project.path(preview['path'])} ({preview['seconds']}s, {preview['bytes'] // 1024} KiB)",
                  "Same timing and mix as the final; lower resolution only.",
                  f"Measured: {report['integrated_lufs']} LUFS, peak {report['true_peak_dbfs']} dBFS, "
                  f"music between scenes {report['gap_mean_volume_db']} dB; frames: {report['frames']}",
                  *[f"Note: {n}" for n in report["notes"]]]
    lines += ["", f"sha256: {sha}"]
    project.record_review(args.gate, sha)
    target = project.path(f"review/{args.gate}.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWritten: {target}")


def approve_cmd(args) -> None:
    project = projects.Project(args.project)
    project.approve(args.gate, args.expected_sha256, args.decision)
    print(f"{args.gate} approval recorded")


def reference_cmd(args) -> None:
    project = projects.Project(args.project)
    if args.describe:
        print(reference.describe(project))
        return
    report = reference.ingest(project, url=args.url, video=args.video and Path(args.video), subs=args.subs and Path(args.subs),
                              transcribe=args.transcribe)
    print(f"{report['title']} | {report['duration']} s | {report['words']} words ({report['wpm']} wpm) | transcript: {report['transcript_source']}")
    if report.get('caption_error'):
        print(f"  captions unavailable now ({report['caption_error'][-120:].strip()}); rerun later, or pass --subs / --transcribe")
    for chapter in report["chapters"]:
        print(f"  {chapter['start']:6.0f}s {chapter['seconds']:5.0f}s {chapter['words']:4d} words | {chapter['title']}")
    for item in report["cited"]:
        lead = research.lookup(item["citation"], item["journal"], item["says"])
        hint = f" -> lead: {lead['title']} ({lead['journal']}, {lead['year']}) doi:{lead['doi']}" if lead else " -> no lead found"
        print(f"  cited: {item['citation']} ({item['journal']}): {item['says']}{hint}")
    if report.get("keyframes"):
        frames = report["keyframes"]
        print(f"  illustration frames: {frames['frames']} kept ({frames['dropped']} black/duplicate dropped) from {frames['source']}")
        print(f"  sheets: {', '.join(frames['sheets'])}")
    if report.get("keyframes_error"):
        print(f"  frames unavailable: {report['keyframes_error']}")
    print(f"analysis: {project.path('reference/analysis.json')}")


def skeleton_cmd(args) -> None:
    result = reference.skeleton(projects.Project(args.project), args.seconds, args.frames)
    for row in result["rows"]:
        times = ", ".join(f"{f['t']:.0f}s" for f in row["frames"])
        print(f"  {row['target_seconds']:5.1f}s ~{row['target_words']:3d} words {row['segments']} seg | {row['chapter']} "
              f"(ref {row['reference_seconds']} s){' | frames ' + times if times else ''}")
    print(f"sheet: {result['sheet'] or 'no frames yet: run `reference --url` (storyboard) or `reference --video <file>`'}")


def originality_cmd(args) -> None:
    result = reference.originality(projects.Project(args.project))
    print(f"coverage {result['coverage']:.1%}, longest shared run {result['longest_shared_words']} words -> {'ok' if result['ok'] else 'REWRITE'}")
    for segment in result["segments"]:
        for run in segment["shared"]:
            print(f"  {segment['id']}: \"{run}\"")


def notes_cmd(args) -> None:
    result = notes.draft(projects.Project(args.project))
    print(f"{result['path']} (chapters: {'yes' if result['chapters'] else 'no'}, sources: {result['sources']})")


def research_cmd(args) -> None:
    for result in research.verify(projects.Project(args.project)):
        print(f"{result['id']}: {result['status']} - {result['detail']}")


def _beats_report(project) -> None:
    for segment in project.segments:
        if segment["id"] in project.state["audio"]:
            beats, count = audio.beats(project, segment), len(audio.sentences(segment["text"]))
            flag = "" if len(beats) == count else "  <- differs from sentence count: check `at` overrides"
            print(f"  {segment['id']}: beats {beats} | sentences: {count}{flag}")


def produce_cmd(args) -> None:
    """After content approval: narration, poses, pose sheets and (when layout is complete) the storyboard."""
    project = projects.Project(args.project)
    print(f"narration: {', '.join(audio.generate(project, wait_seconds=args.wait_seconds)) or 'all current'}")
    _beats_report(project)
    print(f"poses: {', '.join(poses.generate(project, jobs=args.jobs, wait_seconds=args.wait_seconds)) or 'all current'}")
    print(f"pose sheet: {poses.sheet(project)} (grid copy: {project.path('review/poses-grid.png')})")
    missing = poses.missing_layout(project)
    if missing:
        print(f"next: set layout.json tendon positions for {', '.join(missing)} using the grid sheet, then run `storyboard`")
    else:
        print(f"storyboard: {scenes.storyboard(project, jobs=args.jobs)}")


def storyboard_cmd(args) -> None:
    print(scenes.storyboard(projects.Project(args.project), jobs=args.jobs))


def build_cmd(args) -> None:
    """After media approval: render scenes, assemble the draft preview and measure it."""
    project = projects.Project(args.project)
    print(f"rendered: {', '.join(scenes.render(project, jobs=args.jobs)) or 'all current'}")
    record = assemble.preview(project)
    print(f"preview: {project.path(record['path'])} {record['seconds']}s {record['bytes'] // 1024} KiB")
    _print_check(qa.check(project, "preview"))


def _print_check(report: dict) -> None:
    print(f"  {report['width']}x{report['height']} {report['seconds']}s | {report['integrated_lufs']} LUFS | peak {report['true_peak_dbfs']} dBFS"
          f" | music between scenes {report['gap_mean_volume_db']} dB")
    print(f"  frames: {report['frames']}")
    for note in report["notes"]:
        print(f"  note: {note}")


def check_cmd(args) -> None:
    _print_check(qa.check(projects.Project(args.project), args.output))


def audio_cmd(args) -> None:
    project = projects.Project(args.project)
    if args.reconcile:
        for note in audio.reconcile(project):
            print(note)
        return
    done = audio.generate(project, only=args.only, wait_seconds=args.wait_seconds)
    print(f"generated: {', '.join(done) or 'nothing (all current)'}")
    _beats_report(project)


def poses_cmd(args) -> None:
    project = projects.Project(args.project)
    if args.reconcile_batch:
        print(poses.reconcile_batch(project))
        return
    if args.recrop:
        print(f"re-cropped from Codex originals: {', '.join(poses.recrop(project)) or 'nothing'}")
        print(poses.sheet(project))
        return
    done = poses.generate(project, only=args.only, retake=args.retake, jobs=args.jobs, wait_seconds=args.wait_seconds)
    print(f"generated: {', '.join(done) or 'nothing (all current)'}")
    print(poses.sheet(project))


def sheet_cmd(args) -> None:
    print(poses.sheet(projects.Project(args.project)))


def stills_cmd(args) -> None:
    project = projects.Project(args.project)
    for path in scenes.stills(project, args.scene, [float(t) for t in args.at.split(",")]):
        print(path)


def visuals_cmd(args) -> None:
    project = projects.Project(args.project)
    done = scenes.render(project, only=args.only, jobs=args.jobs)
    print(f"rendered: {', '.join(done) or 'nothing (all current)'}")


def preview_cmd(args) -> None:
    record = assemble.preview(projects.Project(args.project))
    print(f"{record['path']} {record['seconds']}s {record['bytes'] // 1024} KiB")


def render_cmd(args) -> None:
    project = projects.Project(args.project)
    record = assemble.final(project)
    print(f"{project.path(record['path'])} {record['seconds']}s sha256={record['sha256']}")
    print(project.path("render/delivery.json"))
    _print_check(qa.check(project, "final"))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup").set_defaults(func=setup)
    sub.add_parser("doctor").set_defaults(func=doctor)

    channel = sub.add_parser("channel")
    channel.set_defaults(func=channel_cmd)
    actions = channel.add_subparsers(dest="channel_action", required=True)
    actions.add_parser("init")
    voices = actions.add_parser("voices")
    voices.add_argument("--search")
    voices.add_argument("--limit", type=int, default=30)
    sample = actions.add_parser("sample")
    sample.add_argument("--voice-id")
    sample.add_argument("--model-id")
    sample.add_argument("--gemini-voice")
    sample.add_argument("--text")
    character = actions.add_parser("character")
    character.add_argument("--id", required=True, help="character id in channel.json")
    character.add_argument("--candidates", type=int, default=3)
    select = actions.add_parser("select")
    select.add_argument("--character", required=True)
    select.add_argument("--candidate", required=True)
    reference = actions.add_parser("add-reference")
    reference.add_argument("--character", required=True)
    reference.add_argument("--image", required=True)
    reference.add_argument("--label")
    actions.add_parser("review")
    approve = actions.add_parser("approve")
    approve.add_argument("--expected-sha256", help="digest printed by `channel review` (default: the last review)")
    approve.add_argument("--decision", required=True)

    def with_project(name, func, **extra):
        command = sub.add_parser(name)
        command.add_argument("--project", required=True)
        command.set_defaults(func=func)
        return command

    init = with_project("init", init_cmd)
    init.add_argument("--title", required=True)
    init.add_argument("--aspect", required=True, choices=sorted(projects.ASPECTS))
    init.add_argument("--voice", help="voice preset from channel voice.presets (default: the channel default)")
    init.add_argument("--tag", help='pinned top-left title line, e.g. "Tendons · Full guide · At home · No gym"')
    with_project("status", status_cmd)
    review = with_project("review", review_cmd)
    review.add_argument("--gate", required=True, choices=projects.GATES)
    with_project("research", research_cmd)
    ref = with_project("reference", reference_cmd)
    ref.add_argument("--url", help="YouTube URL: metadata, chapters, description and captions (no media download)")
    ref.add_argument("--video", help="video file the creator downloaded: scene keyframes for illustration study")
    ref.add_argument("--subs", help="caption file (.vtt/.srt) if the video has no usable captions")
    ref.add_argument("--transcribe", action="store_true", help="no captions: transcribe --video with Genmax (paid)")
    ref.add_argument("--describe", action="store_true", help="describe extracted keyframes with Gemini (paid, small)")
    skeleton = with_project("skeleton", skeleton_cmd)
    skeleton.add_argument("--seconds", type=float, required=True)
    skeleton.add_argument("--frames", type=int, default=4, help="illustration frames per chapter")
    with_project("originality", originality_cmd)
    with_project("notes", notes_cmd)
    approve = with_project("approve", approve_cmd)
    approve.add_argument("--gate", required=True, choices=projects.GATES)
    approve.add_argument("--expected-sha256", help="digest printed by `review` (default: the last review of this gate)")
    approve.add_argument("--decision", required=True)
    audio_parser = with_project("audio", audio_cmd)
    audio_parser.add_argument("--only")
    audio_parser.add_argument("--reconcile", action="store_true")
    audio_parser.add_argument("--wait-seconds", type=int, default=300)
    poses_parser = with_project("poses", poses_cmd)
    poses_parser.add_argument("--only")
    poses_parser.add_argument("--retake")
    poses_parser.add_argument("--jobs", type=int, default=2)
    poses_parser.add_argument("--recrop", action="store_true", help="re-crop Codex poses from Codex's kept originals (free)")
    poses_parser.add_argument("--reconcile-batch", action="store_true", help="resolve a Gemini batch submit with unknown outcome")
    poses_parser.add_argument("--wait-seconds", type=int, default=900, help="how long to wait for a Gemini batch before returning")
    produce = with_project("produce", produce_cmd)
    produce.add_argument("--jobs", type=int, default=2)
    produce.add_argument("--wait-seconds", type=int, default=300)
    with_project("storyboard", storyboard_cmd).add_argument("--jobs", type=int, default=2)
    with_project("build", build_cmd).add_argument("--jobs", type=int, default=2)
    with_project("check", check_cmd).add_argument("--output", choices=("preview", "final"), default="preview")
    with_project("sheet", sheet_cmd)
    stills = with_project("stills", stills_cmd)
    stills.add_argument("--scene", required=True)
    stills.add_argument("--at", required=True, help="comma-separated seconds")
    visuals = with_project("visuals", visuals_cmd)
    visuals.add_argument("--only")
    visuals.add_argument("--jobs", type=int, default=2)
    with_project("preview", preview_cmd)
    with_project("render", render_cmd)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except (FitnessError, OSError, KeyError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"fitness: {exc}", file=sys.stderr)
        sys.exit(1)
