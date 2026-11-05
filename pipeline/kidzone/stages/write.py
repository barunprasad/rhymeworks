"""Write stage: brief + show bible → bilingual song + storyboard (Gemma 4 via Ollama, structured output).

The model writes; a repair pass then enforces what the renderer can actually do (known cast, allowed
actions, known scenes, defined props), so creative slips get corrected instead of failing the run.
"""

import json

from ..core import Episode, chat_json, log, slugify, wait_ollama_unloaded, write_json
from ..models import EpisodeBrief, PropDef, Storyboard

SYSTEM = """You are the head writer and storyboard artist of an original preschool music show.
Write ONE original song episode and its storyboard as JSON.

Song rules:
- Original lyrics only. Never copy or imitate existing songs (no Baby Shark, no nursery-rhyme melodies or famous hooks).
- Simple words for the age band, short lines (4–9 sung syllables), lots of repetition, a catchy chorus that repeats at least twice.
- Clear rhymes in English. Hindi is written natively in Devanagari: natural, singable Hindi a parent would sing (not a word-for-word
  translation), with a similar syllable count to the English line so both fit the same melody. Same number of lines in both.
- Teach the learning goal explicitly and concretely (name the things, count them, show them).

Storyboard rules (per line):
- singers: cast ids who sing the line (use call-and-response when the show premise suggests it).
- shot: wide (everyone), medium or close (on `focus`, a cast id). Vary shots; choruses are mostly wide.
- actions: for on-screen cast, pick ONLY from that character's allowed actions.
- props: things that pop onto the screen on this line to TEACH (e.g. the fruit being named, the number being counted). Each prop id
  must be defined in `props` with a short visual description of ONE object (e.g. "a single red apple"). Use labels for numbers/words.
- scene: one of the show's scene ids per section. Change scene at most once or twice.
Return only JSON."""


def schema(cast_ids: list[str], scene_ids: list[str]) -> dict:
    s = Storyboard.model_json_schema()
    # Constrain ids at the decoder level where possible.
    s["$defs"]["Section"]["properties"]["scene"] = {"type": "string", "enum": scene_ids}
    return s


def bible(show: dict, brief: EpisodeBrief) -> str:
    cast = [c for c in show["cast"] if not brief.cast or c["id"] in brief.cast]
    scenes = [s for s in show["scenes"] if not brief.scenes or s["id"] in brief.scenes]
    n_lines = max(10, min(28, round(brief.duration_sec / 4.2)))
    lines = [
        f"SHOW: {show['title']} — {show['premise']}",
        "CAST (id: name — description — allowed actions):",
        *[f"- {c['id']}: {c['name']['en']} — {c['description']} — actions: {', '.join(c['actions'])}" for c in cast],
        "SCENES (id — description):",
        *[f"- {s['id']} — {s['description']}" for s in scenes],
        "",
        f"BRIEF: topic = {brief.topic}; learning goal = {brief.learning_goal}; age = {brief.age_band}; mood = {brief.mood}; repetition = {brief.repetition}.",
        f"Length: about {n_lines} sung lines in total (~{brief.duration_sec} s), structured as intro, verses and a repeated chorus, outro.",
    ]
    if brief.must_include:
        lines.append(f"Must include: {', '.join(brief.must_include)}.")
    if brief.avoid:
        lines.append(f"Avoid: {', '.join(brief.avoid)}.")
    if brief.lyrics and (brief.lyrics.en or brief.lyrics.hi):
        lines.append("Use these lyrics EXACTLY as written (keep wording and line order; only add the storyboard):")
        if brief.lyrics.en:
            lines.append("EN:\n" + brief.lyrics.en)
        if brief.lyrics.hi:
            lines.append("HI:\n" + brief.lyrics.hi)
    return "\n".join(lines)


def repair(sb: Storyboard, show: dict, brief: EpisodeBrief) -> tuple[Storyboard, list[str]]:
    notes: list[str] = []
    cast = {c["id"]: c for c in show["cast"]}
    allowed_cast = set(brief.cast) if brief.cast else set(cast)
    scenes = {s["id"] for s in show["scenes"]}
    default_scene = (brief.scenes or [show["scenes"][0]["id"]])[0]
    # Props the model referenced but forgot to define: define them from their id, unless the id is something
    # that must not be a pop-up prop (text, icons, faces, effects, cast, or a show's blocklist e.g. deities).
    blocked = {"text", "icon", "face", "confetti", "logo", "emoji", "symbol", "smile", "image of", "flying", *show.get("prop_blocklist", []), *cast}
    referenced = {p.id for sec in sb.sections for ln in sec.lines for p in ln.props}
    for pid in sorted(referenced - {p.id for p in sb.props}):
        words = pid.lower().replace("-", "_").split("_")
        if any(b in words or b in pid.lower() for b in blocked):
            continue
        sb.props.append(PropDef(id=pid, description=f"a single {' '.join(words)}"))
        notes.append(f"auto-defined prop {pid!r}")
    # Defined props are filtered by the same rules (by id and description) — e.g. no deity faces as pop-ups.
    keep = []
    for p in sb.props:
        hay = f"{p.id} {p.description}".lower()
        if any(b in hay for b in blocked):
            notes.append(f"removed prop {p.id!r} ({p.description})")
        else:
            keep.append(p)
    sb.props = keep
    prop_ids = {p.id for p in sb.props}
    for sec in sb.sections:
        if sec.scene not in scenes:
            notes.append(f"scene {sec.scene!r} → {default_scene}")
            sec.scene = default_scene
        for ln in sec.lines:
            ln.singers = [s for s in ln.singers if s in allowed_cast] or [sorted(allowed_cast)[0]]
            if ln.focus and ln.focus not in allowed_cast:
                ln.focus = ln.singers[0]
            if ln.shot != "wide" and not ln.focus:
                ln.focus = ln.singers[0]
            fixed = []
            for a in ln.actions:
                if a.who not in allowed_cast:
                    continue
                if a.action not in cast[a.who]["actions"]:
                    notes.append(f"{a.who}: action {a.action!r} → {cast[a.who]['actions'][0]}")
                    a.action = cast[a.who]["actions"][0]
                fixed.append(a)
            ln.actions = fixed
            missing = [p.id for p in ln.props if p.id not in prop_ids]
            if missing:
                notes.append(f"dropped undefined props {missing}")
            ln.props = [p for p in ln.props if p.id in prop_ids][:5]
            ln.hi = ln.hi.strip() or ln.en
    sb.props = sb.props[:10]
    return sb, notes


KINDS = {"intro": "intro", "verse": "verse", "chorus": "chorus", "bridge": "bridge", "outro": "outro", "hook": "chorus", "pre-chorus": "bridge",
         "instrumental": "interlude", "interlude": "interlude", "music": "interlude", "solo": "interlude"}


def parse_lyrics(text: str) -> list[tuple[str, list[str]]]:
    """'[Verse]\nline\nline\n\n[Chorus]…' → [(kind, [lines])]."""
    sections: list[tuple[str, list[str]]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            kind = KINDS.get(line[1:-1].strip().lower().split()[0], "verse")
            sections.append((kind, []))
        else:
            if not sections:
                sections.append(("verse", []))
            if sections[-1][0] == "interlude":
                sections.append(("verse", []))
            sections[-1][1].append(line)
    return [(k, ls) for k, ls in sections if ls or k == "interlude"]  # interludes are tag-only


def enforce_lyrics(sb: Storyboard, brief: EpisodeBrief) -> Storyboard:
    """Brief-supplied lyrics win: rebuild the section/line skeleton from them and attach the model's per-line
    storyboard (singers, shot, actions, props, English gloss) by position."""
    primary = brief.lyrics.hi or brief.lyrics.en
    parsed = parse_lyrics(primary)
    other = parse_lyrics(brief.lyrics.en if brief.lyrics.hi else "") if brief.lyrics.en and brief.lyrics.hi else None
    model_lines = sb.lines()
    model_secs = sb.sections
    flat_other = [ln for _, ls in other for ln in ls] if other else []
    new_sections, k = [], 0
    for si, (kind, lines) in enumerate(parsed):
        scene = model_secs[min(si, len(model_secs) - 1)].scene if model_secs else ""
        out_lines = []
        for text in lines:
            src = model_lines[k % len(model_lines)] if model_lines else None
            data = src.model_dump() if src else {"singers": [], "en": "", "hi": ""}
            if brief.lyrics.hi:
                data["hi"] = text
                data["en"] = flat_other[k] if k < len(flat_other) else (data.get("en") or text)
            else:
                data["en"] = text
                data["hi"] = data.get("hi") or text
            out_lines.append(data)
            k += 1
        new_sections.append({"kind": kind, "scene": scene, "lines": out_lines})
    return Storyboard.model_validate({**sb.model_dump(), "sections": new_sections})


def run(ep: Episode, brief: EpisodeBrief, show: dict) -> Storyboard:
    out = ep.path("storyboard.json")
    if out.exists():
        return Storyboard.model_validate_json(out.read_text())
    cast_ids = [c["id"] for c in show["cast"] if not brief.cast or c["id"] in brief.cast]
    scene_ids = [s["id"] for s in show["scenes"] if not brief.scenes or s["id"] in brief.scenes]
    log("write", f"Gemma writing '{brief.topic}' for {show['title']} …")
    last_err = None
    for attempt in range(3):
        try:
            raw = chat_json(SYSTEM, bible(show, brief), schema(cast_ids, scene_ids), temperature=0.8 if attempt == 0 else 0.6)
            sb = Storyboard.model_validate(raw)
            if len(sb.lines()) < 6:
                raise ValueError(f"only {len(sb.lines())} lines")
            break
        except Exception as e:  # noqa: BLE001 — retry on any malformed generation
            last_err = e
            log("write", f"attempt {attempt + 1} rejected: {e}")
    else:
        raise RuntimeError(f"writer failed: {last_err}")
    wait_ollama_unloaded()
    if brief.lyrics and (brief.lyrics.hi or brief.lyrics.en):
        sb = enforce_lyrics(sb, brief)
        log("write", f"using brief lyrics verbatim ({len(sb.lines())} lines)")
    sb, notes = repair(sb, show, brief)
    for n in notes:
        log("write", f"repair: {n}")
    write_json(out, json.loads(sb.model_dump_json()))
    log("write", f"'{sb.title.en}' — {len(sb.sections)} sections, {len(sb.lines())} lines, {len(sb.props)} props")
    return sb


def default_slug(brief: EpisodeBrief) -> str:
    return brief.slug or slugify(f"{brief.show}-{brief.topic}")
