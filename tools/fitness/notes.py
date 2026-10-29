"""Draft publishing notes: chapters, research cited, safety note and credits.

The draft is for the creator to edit and approve in the publishing step; it
is never posted automatically.
"""

from __future__ import annotations

from .common import write_json


DEFAULT_DISCLAIMER = ("Educational content, not personal medical or training advice. Holding tension raises blood pressure, "
                      "so keep breathing during every hold. Talk to a doctor before starting if you have high blood pressure, "
                      "heart disease or a joint injury, and stop if you feel sharp pain.")


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def _shared_prefix(tags: list[str]) -> int:
    """How many leading " · " items every heading shares (e.g. "Grip · Forearms", "Grip · Fingers" -> 1)."""
    parts = [t.split(" · ") for t in tags]
    count = 0
    while all(len(p) > count + 1 and p[count] == parts[0][count] for p in parts):
        count += 1
    return count


def draft(project) -> dict:
    scenes = {s["segment_id"]: s for s in project.storyboard["scenes"]}

    def label_of(scene):
        for key, field in (("badge", "title"), ("title", "text"), ("split", "title"), ("plan", "title"), ("table", "title")):
            if (scene.get(key) or {}).get(field):
                return scene[key][field]
        return None

    starts, cursor = {}, 0.0
    for segment in project.segments:
        starts[segment["id"]] = cursor
        cursor += project.state["audio"].get(segment["id"], {}).get("seconds", 0)

    def merged(items):  # merge chapters shorter than 10 s into the previous one
        chapters = []
        for start, label in items:
            if not (chapters and start - chapters[-1][0] < 10):
                chapters.append((start, label))
        return chapters

    # Chapters follow the heading tags when the video has them; the intro before the first heading belongs to it.
    sections = project.tag_sections()
    shared = _shared_prefix([s["tag"] for s in sections]) if len(sections) > 1 else 0
    headed = merged([(0.0 if i == 0 else starts[s["segment_id"]], " · ".join(s["tag"].split(" · ")[shared:]) or s["tag"])
                     for i, s in enumerate(sections)])
    # Otherwise one chapter per segment group (the id prefix before the first hyphen, e.g. "wall-setup" -> "wall").
    groups = []
    for segment in project.segments:
        group = segment["id"].split("-")[0]
        if not groups or groups[-1]["group"] != group:
            groups.append({"group": group, "start": starts[segment["id"]], "label": None})
        groups[-1]["label"] = groups[-1]["label"] or label_of(scenes[segment["id"]])
    grouped = merged([(g["start"], g["label"] or g["group"].replace("_", " ").capitalize()) for g in groups])
    # YouTube chapters need at least three, starting at 0:00, each at least 10 s long.
    valid = lambda c: len(c) >= 3 and c[0][0] == 0 and all(b[0] - a[0] >= 10 for a, b in zip(c, c[1:]))
    chapters = headed if valid(headed) else grouped
    usable = valid(chapters)
    claims = project.claims.get("claims", [])
    research = []
    for source in project.sources.get("sources", []):
        # Only what the paper reports; the channel's own interpretations stay out of the public notes.
        used = [c["text"].rstrip(". ") for c in claims if source["id"] in c["source_ids"] and c.get("kind") != "creator interpretation"]
        link = source["locator"].split(" (")[0]
        research.append(f"- {source.get('short') or source['title']}: {'; '.join(used)}. {link}" if used else f"- {source.get('short') or source['title']}. {link}")
    music = project.channel.get("music")
    credits = []
    if music and music.get("provider") == "lyria":
        credits.append(music.get("credit") or "Music: original instrumental made for this video with Google Lyria")
    elif music:  # a public credit line, never the internal provenance note
        source = music["provenance"]["source"]
        credits.append(music.get("credit") or ("Music: original instrumental made with Google Lyria" if "lyria" in source.lower()
                                               else f"Music: {source.split(' (')[0]}"))
    disclaimer = (project.channel.get("publishing") or {}).get("disclaimer") or DEFAULT_DISCLAIMER
    lines = ["<one-line hook in your own words>", ""]
    if usable:
        lines += ["Chapters", *[f"{_clock(t)} - {label}" for t, label in chapters], ""]
    lines += ["Research mentioned", *research, "", "Safety", disclaimer, ""]
    if credits:
        lines += ["Credits", *credits, ""]
    text = "\n".join(lines).rstrip() + "\n"
    target = project.path("render/description.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    result = {"path": str(target), "chapters": usable, "sources": len(research)}
    write_json(project.path("render/description.json"), result)
    return result
