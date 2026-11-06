"""Upload pack text + thumbnails for a Pixar episode (the 1080p file itself is `kidzone pixar --phase package`).

  kidzone upload <episode.toml> [--text] [--thumbs]      (default: both; existing files are kept unless --force)

text    upload/upload_text.md: title, description (chapters + lyrics), tags. The writer LLM drafts the title, the intro
        paragraph and the tags; chapters and lyrics come straight from the shot list, so they are always exact.
thumbs  upload/thumb_<shot>.jpg: three keyframes with the title lettered on them (CoreText, so Hindi shapes correctly)
        and the channel badge bottom-left (YouTube covers the bottom-right with the duration).
"""

import json
import re
import subprocess
import tempfile
import tomllib
from pathlib import Path

from . import pixar
from .core import IMAGE_ENV, ROOT, chat_json, log

from .paths import BRAND, BRAND_TOOLS, rel  # noqa: E402
from . import paths  # noqa: E402
ICON = BRAND / "final/yt_icon_800.png"
XFADE = 0.3   # the intro crossfades into the episode (pipeline/tools/brand/add_intro.sh)
PLAYLISTS = {"en": "English Rhymes", "hi": "हिंदी बालगीत", "bhakti": "Bal Bhakti"}
FILL = ["#FFC21A", "#14C3BE", "#FF4FA3"]

WRITER = """You write YouTube upload text for "Gaana Gaadi", a kids' song channel (English nursery rhymes, Hindi बालगीत,
Bal Bhakti) with Pixar-style 3D animation for toddlers and preschoolers (ages 1-6). The video is MADE FOR KIDS.
Rules: warm, simple, factual; no clickbait, no ALL CAPS sentences, no promises of learning outcomes; at most 2 emoji in the title;
title ≤ 90 characters and ends with "| Gaana Gaadi"; the description intro is 2-3 short sentences naming the characters and
what happens; for Hindi songs write the title in Hindi first, then a short English part; tags are lowercase search phrases
parents type (12-16 of them), including the song name in both scripts for Hindi songs. thumb_lines: the song name split into
1-3 short lines for big thumbnail lettering (in the song's language)."""
SCHEMA = {"type": "object", "properties": {
    "title": {"type": "string"}, "intro": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}},
    "hashtags": {"type": "array", "items": {"type": "string"}}, "thumb_lines": {"type": "array", "items": {"type": "string"}}},
    "required": ["title", "intro", "tags", "hashtags", "thumb_lines"]}


def _rel(p: Path) -> str:
    return rel(p)


def mmss(t: float) -> str:
    t = int(round(t))
    return f"{t // 60:02d}:{t % 60:02d}"


def intro_seconds(ep: pixar.Episode) -> float:
    """How much the project's intro clip shifts everything in the intro version (its length minus the crossfade)."""
    clip = pixar.project_intro(ep)
    return max(0.0, pixar._probe_seconds(clip) - XFADE) if clip else 0.0


def chapters(ep: pixar.Episode, min_gap: float = 10.0, offset: float = 0.0, first: str | None = None) -> list[tuple[float, str]]:
    """YouTube chapters: first at 00:00, each ≥ 10 s long. A new chapter starts at a lyric line that differs from the last chapter's.
    offset = intro length for the version that opens with the intro (its first chapter is then the channel's name)."""
    out: list[tuple[float, str]] = [(0.0, first or ep.spec["episode"]["title"])]
    lyr = {s["id"]: (s.get("lyric") or "").strip() for s in ep.spec["shot"]}
    seen: set[str] = set()
    for s in ep.shots:
        line = lyr.get(s.id, "")
        t = s.start + offset
        if not line or line in seen or t - out[-1][0] < min_gap:
            continue
        seen.add(line)
        out.append((t, line.rstrip(",.;")))
    end = ep.shots[-1].start + ep.shots[-1].dur + offset
    if len(out) > 1 and end - out[-1][0] < min_gap:
        out.pop()
    return out


def lyrics_block(ep: pixar.Episode) -> str:
    lines, prev = [], None
    for s in ep.spec["shot"]:
        ln = (s.get("lyric") or "").strip()
        if ln and ln != prev:
            lines.append(ln)
        prev = ln
    return "\n".join(lines)


CHAPTER_LINE = re.compile(r"^(\d{2}):(\d{2}) (.*)$")
CHAPTERS_ORIGINAL = "Chapters: original file"   # in the header of upload_text.md written since the intro became optional


def intro_offset(ep: pixar.Episode) -> float:
    """How far the intro version shifts the episode: as recorded when it was made, else the project's clip."""
    return float((pixar.intro_record(ep) or {}).get("seconds") or intro_seconds(ep))


def description_for(ep: pixar.Episode, text: dict, with_intro: bool) -> str:
    """The description with chapter times for the chosen file. The stored chapters are shifted (never recomputed, so hand
    edits and the text of a published video survive). Texts from before the intro became optional were written for the
    intro version."""
    stored = 0.0 if CHAPTERS_ORIGINAL in text.get("meta", "") or not pixar.project_intro(ep) and not pixar.intro_record(ep) else intro_offset(ep)
    target = intro_offset(ep) if with_intro else 0.0
    delta = target - stored
    lines = text["description"].split("\n")
    rows = [i for i, ln in enumerate(lines) if CHAPTER_LINE.match(ln)]
    if abs(delta) < 0.05 or not rows:
        return text["description"]
    proj = paths.projects().get(ep.spec["episode"].get("project") or paths.default_project(), {})
    out, last = [], None
    for k, i in enumerate(rows):
        m = CHAPTER_LINE.match(lines[i])
        t = int(m.group(1)) * 60 + int(m.group(2))
        if k == 0:   # 00:00 stays; it names the channel in the intro version and the song in the original
            out.append((i, f"00:00 {(proj.get('name') or 'Intro') + '!' if with_intro else ep.spec['episode']['title']}"))
            last = 0.0
            continue
        t = max(0.0, t + delta)
        if t - last < 10:   # YouTube wants chapters at least 10 s long
            out.append((i, None))
            continue
        out.append((i, f"{mmss(t)} {m.group(3)}"))
        last = t
    new = dict(out)
    return "\n".join(new[i] if i in new else ln for i, ln in enumerate(lines) if not (i in new and new[i] is None))


def parse_text(md: str) -> dict:
    """Read an upload_text.md back: {title, description, tags, meta}."""
    sec = {m.group(1).split("(")[0].strip().lower(): m.group(2).strip()
           for m in re.finditer(r"^## ([^\n]+)\n(.*?)(?=^## |\Z)", md, re.M | re.S)}
    meta = md.split("## ", 1)[0]
    return {"title": sec.get("title", ""), "description": sec.get("description", ""), "tags": sec.get("tags", ""), "meta": meta.strip()}


def write_text(ep: pixar.Episode, force: bool = False, chat=chat_json) -> Path:
    up = ep.dir / "upload"
    up.mkdir(exist_ok=True)
    out = up / "upload_text.md"
    if out.exists() and not force:
        log("upload", f"{_rel(out)} exists (use --force to redo)")
        return out
    e = ep.spec["episode"]
    lang = e.get("lang", "en")
    reg = pixar._registry()
    cast = sorted({c for s in ep.shots for c in s.key.cast if c in reg.get("cast", {})}, key=lambda c: -sum(c in s.key.cast for s in ep.shots))
    who = ", ".join(f"{c.split('_')[0].capitalize()} ({reg['cast'][c]['ref']})" for c in cast[:6])
    scenes = ", ".join(dict.fromkeys(s.key.scene.replace("_", " ") for s in ep.shots))
    lyr = lyrics_block(ep)
    user = f"Song: {e['title']} (language: {lang}).\nCharacters: {who}.\nPlaces: {scenes}.\nLyrics:\n{lyr[:1500]}"
    log("upload", "asking the writer model for title, intro and tags …")
    d = chat(WRITER, user, SCHEMA, temperature=0.5)
    proj = paths.projects().get(e.get("project") or paths.default_project(), {})
    playlist = e.get("playlist") or proj.get("playlists", {}).get(lang) or PLAYLISTS.get(lang, "English Rhymes")
    chap = "\n".join(f"{mmss(t)} {name}" for t, name in chapters(ep))
    channel = proj.get("name", "")
    tags = ", ".join(dict.fromkeys([t.strip().lower() for t in d["tags"] if t.strip()] + ([channel.lower()] if channel else [])))
    hashtags = " ".join("#" + re.sub(r"\W+", "", h.lstrip("#")) for h in d["hashtags"][:3] if re.sub(r"\W+", "", h))
    subscribe = proj.get("subscribe", {}).get(lang) or (f"Subscribe to {channel} for new songs!" if channel else "")
    text = f"""# {e['title']} ({lang.upper()}): upload text

File: {ep.output.stem}_1080p.mp4 · {CHAPTERS_ORIGINAL} · Thumbnail: thumbnail.jpg
Audience: Yes, made for kids · AI use: YES (the song is AI-generated music and is the main focus of the video) · Playlist: {playlist}
Category: Education · Language: {'Hindi' if lang == 'hi' else 'English'} · Visibility: Unlisted first → Public

## Title (≤100 chars)

{d['title'].strip()[:100]}

## Description

{d['intro'].strip()}

{chap}

🎵 Lyrics
{lyr}

{subscribe}

{hashtags}

## Tags

{tags}
"""
    out.write_text(text)
    (up / "thumb_lines.json").write_text(json.dumps(d["thumb_lines"][:3], ensure_ascii=False))
    log("upload", f"upload text → {_rel(out)}")
    return out


# ---------------------------------------------------------------- thumbnails

THUMB_PY = r'''
import sys
from PIL import Image, ImageDraw, ImageFilter
art, out, icon, *lines = sys.argv[1:]
W, H = 1280, 720
bg = Image.open(art).convert("RGBA").resize((W, H), Image.LANCZOS)
wash = Image.new("RGBA", (W, H)); ImageDraw.Draw(wash).ellipse((-300, -160, 680, 600), fill=(255, 255, 255, 120))
bg = Image.alpha_composite(bg, wash.filter(ImageFilter.GaussianBlur(70)))
parts = [Image.open(p).convert("RGBA") for p in lines]
parts = [p.crop(p.getbbox()) for p in parts]   # text.swift pads for ascenders; stack the visible letters
# one scale for every line (the widest fits 560 px, the block fits 330 px high) so the title reads as one unit
gap = 14
k = min(1.0, 560 / max(p.width for p in parts), 300 / sum(p.height + gap for p in parts))
parts = [p.resize((int(p.width * k), int(p.height * k)), Image.LANCZOS) for p in parts]
block_w = max(p.width for p in parts)
y = 28
for p in parts:
    x = 30 + (block_w - p.width) // 2
    a = p.split()[3]
    shadow = Image.new("RGBA", p.size, (27, 42, 107, 255)); shadow.putalpha(a)   # navy extrusion like the channel art
    bg.alpha_composite(shadow, (x + 3, y + int(10 * k)))
    bg.alpha_composite(p, (x, y)); y += p.height + int(gap * k) + int(10 * k)
if icon:   # your channel icon in the corner (assets/brand/final/yt_icon_800.png in your content folder)
    ic = Image.open(icon).convert("RGBA").resize((150, 150), Image.LANCZOS)
    m = Image.new("L", (600, 600)); ImageDraw.Draw(m).ellipse((0, 0, 599, 599), fill=255); ic.putalpha(m.resize((150, 150), Image.LANCZOS))
    ring = Image.new("RGBA", (162, 162)); ImageDraw.Draw(ring).ellipse((0, 0, 161, 161), fill="white")
    bg.alpha_composite(ring, (28, H - 190)); bg.alpha_composite(ic, (34, H - 184))
bg.convert("RGB").save(out, quality=92)
'''


def _letter(text: str, size: int, fill: str, out: Path) -> None:
    subprocess.run(["swift", str(BRAND_TOOLS / "text.swift"), str(BRAND_TOOLS / "fonts/Baloo2-800.ttf"), str(size), fill, "#FFFFFF", "0.09", text, str(out)],
                   check=True, capture_output=True)


def pick_art(ep: pixar.Episode, n: int = 3) -> list[Path]:
    """Keyframes with the most characters, spread over the song (approved ones first when reviewed)."""
    from .studio import review
    rv = review.load(ep.dir)["keys"]
    have = [s for s in ep.shots if (ep.keys_dir / f"{s.key.name}.png").exists()]
    score = lambda s: (rv.get(s.id, {}).get("decision") == "approved", len(s.key.cast), not s.sing)
    ranked = sorted(have, key=score, reverse=True)
    picked: list[pixar.Shot] = []
    for s in ranked:   # not three neighbours of the same moment
        if all(abs(s.start - p.start) > 8 for p in picked):
            picked.append(s)
        if len(picked) == n:
            break
    return [ep.keys_dir / f"{s.key.name}.png" for s in picked]


def make_thumbs(ep: pixar.Episode, force: bool = False) -> list[Path]:
    up = ep.dir / "upload"
    up.mkdir(exist_ok=True)
    lf = up / "thumb_lines.json"
    lines = json.loads(lf.read_text()) if lf.exists() else [ep.spec["episode"]["title"]]
    arts = pick_art(ep)
    if not arts:
        log("upload", "no keyframes yet: no thumbnails")
        return []
    made = []
    with tempfile.TemporaryDirectory() as tmp:
        pngs = []
        for i, ln in enumerate(lines[:3]):
            p = Path(tmp) / f"l{i}.png"
            _letter(ln, 150 if len(lines) > 1 else 170, FILL[i % 3], p)
            pngs.append(str(p))
        script = Path(tmp) / "thumb.py"
        script.write_text(THUMB_PY)
        for art in arts:
            out = up / f"thumb_{art.stem.removesuffix('_a')}.jpg"
            if out.exists() and not force:
                made.append(out)
                continue
            subprocess.run(["uv", "run", "--project", str(IMAGE_ENV), "python", str(script), str(art), str(out),
                            str(ICON) if ICON.exists() else "", *pngs], check=True, capture_output=True)
            print(f"key thumb {out.name}", flush=True)
            made.append(out)
    log("upload", f"thumbnails: {', '.join(p.name for p in made)}")
    return made


def main(args) -> None:
    ep = pixar.load(paths.find_spec(args.spec))
    both = not args.text and not args.thumbs
    if args.text or both:
        write_text(ep, args.force)
    if args.thumbs or both:
        make_thumbs(ep, args.force)


def state_path(ep_dir: Path) -> Path:
    return ep_dir / "upload" / "upload.toml"


def load_state(ep_dir: Path) -> dict:
    p = state_path(ep_dir)
    return tomllib.loads(p.read_text()) if p.exists() else {}


def save_state(ep_dir: Path, st: dict) -> dict:
    p = state_path(ep_dir)
    p.parent.mkdir(exist_ok=True)
    lines = ["# Upload choices made in the Rhymeworks studio (safe to edit by hand)."]
    if st.get("thumbnail"):
        lines.append(f"thumbnail = {json.dumps(st['thumbnail'], ensure_ascii=False)}")
    lines.append(f"checks = [{', '.join(json.dumps(c) for c in st.get('checks', []))}]")
    p.write_text("\n".join(lines) + "\n")
    return load_state(ep_dir)
