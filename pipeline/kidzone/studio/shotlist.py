"""Shot list editing for episode.toml, format-preserving: only the lines that change are rewritten, so comments,
section headers and the order of other lines stay exactly as a person wrote them.

Each [[shot]] block holds single-line `field = value` entries (values may carry a trailing `# comment`, which is kept).
Every write is checked twice before it reaches disk: it must parse as TOML and resolve with the Pixar engine
(unknown {tokens} or scenes are refused), so the studio can never leave a spec that `kidzone pixar` can't run.
"""

import json
import os
import re
import tempfile
import tomllib
from pathlib import Path

from .. import pixar
from .specedit import _shot_block

FIELDS = ("lyric", "scene", "seed", "key", "motion", "feel", "sing", "end", "lines", "frames", "clip_seed")
ORDER = ("id", "lyric", "seed", "clip_seed", "scene", "sing", "end", "lines", "frames", "feel", "key", "motion")   # for new lines
SHOT_HDR = re.compile(r"^\[\[shot\]\]\s*$", re.M)
ID_RE = re.compile(r"^s\d{2,3}[a-z]?$")


class SpecError(ValueError):
    """The edit would leave a spec the engine can't run (message is shown to the user)."""


# ---------------------------------------------------------------- values

def toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)   # JSON strings are valid TOML basic strings
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {toml_value(x)}" for k, x in v.items()) + " }"
    raise TypeError(f"can't write {type(v).__name__} to TOML")


def _split_comment(rest: str) -> tuple[str, str]:
    """'"a # b"   # note' → ('"a # b"', '   # note'): the first # that is outside a string starts the comment."""
    q = None
    i = 0
    while i < len(rest):
        c = rest[i]
        if q:
            if c == "\\" and q == '"':
                i += 2
                continue
            if c == q:
                q = None
        elif c in "\"'":
            q = c
        elif c == "#":
            j = i
            while j > 0 and rest[j - 1] in " \t":
                j -= 1
            return rest[:j], rest[j:]
        i += 1
    return rest.rstrip(), ""


def set_field(block: str, field: str, value) -> str:
    """Set/replace/remove (value None) one `field = …` line inside a [[shot]] block."""
    m = re.search(rf"^{re.escape(field)}\s*=(.*)$", block, re.M)
    if value is None:
        if not m:
            return block
        end = m.end() + (1 if block[m.end():m.end() + 1] == "\n" else 0)
        return block[:m.start()] + block[end:]
    line = f"{field} = {toml_value(value)}"
    if m:
        _, comment = _split_comment(m.group(1))
        return block[:m.start()] + line + comment + block[m.end():]
    # new line: put it after the last existing field that comes before it in ORDER (keeps blocks tidy)
    before = ORDER[:ORDER.index(field)] if field in ORDER else ORDER
    anchor = None
    for f in before:
        fm = re.search(rf"^{re.escape(f)}\s*=.*$", block, re.M)
        if fm and (anchor is None or fm.end() > anchor):
            anchor = fm.end()
    if anchor is None:   # no id line?! append at the end of the block's fields
        body = block.rstrip("\n")
        return body + "\n" + line + block[len(body):]
    return block[:anchor] + "\n" + line + block[anchor:]


# ---------------------------------------------------------------- read

def read(spec: Path) -> dict:
    data = tomllib.loads(spec.read_text())
    shots = []
    for sh in data.get("shot", []):
        shots.append({"id": sh["id"], **{f: sh.get(f) for f in FIELDS}})
    for s in shots:
        s["sing"] = bool(s["sing"])
    return {"episode": data.get("episode", {}), "song": data.get("song", {}), "vars": data.get("vars", {}), "shots": shots}


# ---------------------------------------------------------------- write (validated)

def _check_and_write(spec: Path, text: str) -> None:
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise SpecError(f"not valid TOML: {e}") from None
    fd, tmp = tempfile.mkstemp(prefix=".episode.", suffix=".toml", dir=spec.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        try:
            pixar.load(tmp)
        except KeyError as e:
            raise SpecError(str(e).strip("'\"")) from None
        except Exception as e:  # noqa: BLE001 - anything the engine rejects
            raise SpecError(f"{type(e).__name__}: {e}") from None
        os.replace(tmp, spec)   # atomic: readers never see a half-written spec
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _blocks(text: str) -> list[tuple[int, int]]:
    starts = [m.start() for m in SHOT_HDR.finditer(text)]
    return list(zip(starts, starts[1:] + [len(text)]))


def _own_span(text: str, shot: str) -> tuple[int, int]:
    """Span of a shot's own lines: its header and fields, without the comments/blank lines after it
    (those are usually the section header of the NEXT shot, e.g. `# ---- verse 2 ----`)."""
    a, b = _shot_block(text, shot)
    m = re.search(r"\n(?:[ \t]*#[^\n]*\n|[ \t]*\n)*\Z", text[a:b])
    return a, a + (m.start() + 1 if m else b - a)


def _clean_fields(fields: dict) -> dict:
    out = {}
    for k, v in fields.items():
        if k not in FIELDS:
            raise SpecError(f"unknown shot field '{k}'")
        if k in ("key", "motion", "lyric", "feel") and isinstance(v, str):
            v = " ".join(v.split()) if k != "lyric" else v.strip()   # one line in the file
            if k in ("lyric", "feel") and not v:
                v = None
        if k == "end" and v not in (None, "same") and not (isinstance(v, dict) and "key" in v and "seed" in v):
            raise SpecError('end must be "same", { seed, key } or empty')
        if k in ("seed", "clip_seed", "lines", "frames") and v is not None:
            v = int(v)
        if k == "sing":
            v = True if v else None   # only written when true
        out[k] = v
    return out


def update(spec: Path, shot: str, fields: dict) -> dict:
    fields = _clean_fields(fields)
    text = spec.read_text()
    a, b = _shot_block(text, shot)
    block = text[a:b]
    for k, v in fields.items():
        block = set_field(block, k, v)
    _check_and_write(spec, text[:a] + block + text[b:])
    return next(s for s in read(spec)["shots"] if s["id"] == shot)


def next_id(ids: list[str]) -> str:
    nums = [int(re.match(r"s(\d+)", i).group(1)) for i in ids if re.match(r"s(\d+)", i)]
    return f"s{(max(nums) + 1) if nums else 0:02d}"


def _render_block(sid: str, fields: dict) -> str:
    lines = ["[[shot]]", f"id = {toml_value(sid)}"]
    for f in ORDER[1:]:
        if fields.get(f) is not None:
            lines.append(f"{f} = {toml_value(fields[f])}")
    return "\n".join(lines) + "\n\n"


def add(spec: Path, after: str | None = None, copy_of: str | None = None, fields: dict | None = None) -> dict:
    """New shot after `after` (default: at the end), optionally a copy of `copy_of` with a fresh seed."""
    text = spec.read_text()
    data = read(spec)
    ids = [s["id"] for s in data["shots"]]
    sid = next_id(ids)
    base: dict = {}
    if copy_of:
        src = next((s for s in data["shots"] if s["id"] == copy_of), None)
        if not src:
            raise SpecError(f"no shot {copy_of}")
        base = {k: v for k, v in src.items() if k in FIELDS and k not in ("clip_seed",)}
        if not after:
            after = copy_of
    else:
        scene = data["shots"][-1]["scene"] if data["shots"] else next(iter(pixar._registry()["scenes"]))
        base = {"scene": scene, "key": "", "motion": ""}
    seeds = [s["seed"] or 0 for s in data["shots"]]
    base["seed"] = (max(seeds) + 1) if seeds else 100
    if fields:
        base.update(_clean_fields(fields))
    new = _render_block(sid, base)
    if after:
        if after not in ids:
            raise SpecError(f"no shot {after}")
        _, cut = _own_span(text, after)
        out = text[:cut].rstrip("\n") + "\n\n" + new + text[cut:].lstrip("\n")
    else:
        out = text.rstrip("\n") + "\n\n" + new
    _check_and_write(spec, out.rstrip("\n") + "\n")
    return next(s for s in read(spec)["shots"] if s["id"] == sid)


def delete(spec: Path, shot: str) -> None:
    text = spec.read_text()
    a, b = _own_span(text, shot)
    if len(_blocks(text)) == 1:
        raise SpecError("an episode needs at least one shot")
    out = text[:a] + text[b:]
    _check_and_write(spec, re.sub(r"\n{3,}", "\n\n", out))


def move(spec: Path, shot: str, before: str | None) -> None:
    """Move a shot so it comes just before `before` (None = to the end). Its own lines move with it, comments too."""
    text = spec.read_text()
    a, b = _own_span(text, shot)
    block = text[a:b].rstrip("\n") + "\n\n"
    rest = text[:a] + text[b:]
    if before:
        c, _ = _shot_block(rest, before)
        lead = re.search(r"(?:^[ \t]*(?:#[^\n]*)?\n)*\Z", rest[:c], re.M)   # the comments above `before` stay with it
        c = lead.start() if lead else c
        out = rest[:c].rstrip("\n") + "\n\n" + block + rest[c:].lstrip("\n")
    else:
        out = rest.rstrip("\n") + "\n\n" + block
    _check_and_write(spec, re.sub(r"\n{3,}", "\n\n", out).rstrip("\n") + "\n")


# ---------------------------------------------------------------- new episode

def slug_ok(slug: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{1,60}", slug))


def new_episode(ep_dir: Path, title: str, lang: str, lines: list[str], line_seconds: float, project: str, scene: str,
                lyrics_text: str = "", bpm: int | None = None) -> Path:
    """episodes/<slug>/episode.toml with one (empty) shot per lyric line. The song comes later (song/master_<lang>.wav)."""
    if ep_dir.exists():
        raise SpecError(f"episodes/{ep_dir.name} already exists")
    stem = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:40] or ep_dir.name.replace("-", "_")
    head = [
        f"# {title}: Pixar-style episode spec (made in the Rhymeworks studio; safe to edit by hand).",
        "# Tokens: {gopu} {minu} {bus} … (assets/registry.toml), {name} ([vars]), {keep:bus} in motion prompts.",
        "",
        "[episode]",
        f"title = {toml_value(title)}",
        f"lang = {toml_value(lang)}",
        f"output = {toml_value(f'{stem}_{lang}.mp4')}",
        f"project = {toml_value(project)}",
        "",
        "[render]                             # defaults: 1280×720, seed 7",
        "",
        "[song]",
        f"audio = {toml_value(f'song/master_{lang}.wav')}         # mastered song (made in the Song step)",
        f"vocals = {toml_value(f'song/vox_{lang}.wav')}           # isolated vocal for lip-sync shots",
        f"line_seconds = {line_seconds!r}",
        *([f"bpm = {int(bpm)}"] if bpm else []),
        "",
        "[vars]",
        'sit = "sitting properly on the seat cushion like a child on a chair, knees at the front edge of the seat, lower legs hanging down"',
        "",
    ]
    blocks = [_render_block(f"s{i:02d}", {"lyric": ln.strip() or None, "seed": 100 + i, "scene": scene, "key": "", "motion": ""})
              for i, ln in enumerate(lines or [""])]
    ep_dir.mkdir(parents=True)
    spec = ep_dir / "episode.toml"
    try:
        spec.write_text("\n".join(head) + "\n" + "".join(blocks).rstrip("\n") + "\n")
        pixar.load(spec)
    except Exception:
        import shutil
        shutil.rmtree(ep_dir)
        raise
    if lyrics_text.strip():   # the full lyrics with [Verse]/[Chorus] tags, for the Song step
        (ep_dir / "song").mkdir(exist_ok=True)
        (ep_dir / "song" / f"lyrics_{lang}.txt").write_text(lyrics_text.strip() + "\n")
    return spec


def replace_shots(spec: Path, plan: list[dict]) -> None:
    """Replace every [[shot]] with `plan` ([{lyric, lines, …}]). Prompts already written are carried over to the new shot
    with the same lyric (in order), so re-timing a song never throws away work."""
    text = spec.read_text()
    old = read(spec)["shots"]
    pool = [s for s in old if (s["key"] or "").strip()]
    first = SHOT_HDR.search(text)
    head = text[:first.start()] if first else text
    scene = old[0]["scene"] if old else next(iter(pixar._registry()["scenes"]))
    blocks = []
    for i, p in enumerate(plan):
        keep = next((s for s in pool if p.get("lyric") and s.get("lyric") == p["lyric"]), None)
        if keep:
            pool.remove(keep)
        f = {"lyric": p.get("lyric"), "seed": 100 + i, "scene": (keep or {}).get("scene") or scene,
             "lines": p["lines"] if p.get("lines", 1) != 1 else None,
             "key": (keep or {}).get("key") or "", "motion": (keep or {}).get("motion") or "",
             "sing": True if keep and keep.get("sing") else None, "end": (keep or {}).get("end")}
        blocks.append(_render_block(f"s{i:02d}", f))
    _check_and_write(spec, head.rstrip("\n") + "\n\n" + "".join(blocks).rstrip("\n") + "\n")
