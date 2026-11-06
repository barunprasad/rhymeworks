"""Auto-checks: hints that point the reviewer at likely mistakes. They never approve or reject anything.

Movement (instant, no model): every clip, computed when the studio lists it. LTX sometimes returns an almost still
video; the mean change between neighbouring frames (64×36 grey, 4 fps) below FROZEN_STEP means "barely moves".

Pictures (`kidzone check <episode.toml> --stage keys|clips`, a queued job, ~2 s per picture with the writer model):
the local vision-capable writer model counts each character the shot should have, plus any extras, and lists clear
drawing mistakes (extra hands, melted faces, floating characters). Keyframes are checked as they are; clips at five
moments (start, ¼, ½, ¾, end). Results go to episodes/<slug>/checks.json, keyed by output file and its mtime, so a
redone shot is checked again and an unchanged one is skipped.
"""

import base64
import json
import os
import subprocess
import tomllib
import urllib.request
from pathlib import Path

from . import pixar
from .core import OLLAMA, WRITER_MODEL
from .paths import REGISTRY

FROZEN_STEP = 1.5
W, H = 64, 36
STAGES = ("keys", "clips")


# ---------------------------------------------------------------- movement

def motion(clip: Path) -> dict:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(clip), "-vf", f"fps=4,scale={W}:{H},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    n = W * H
    frames = [raw[i:i + n] for i in range(0, len(raw) - n + 1, n)]
    if len(frames) < 2:
        return {"step": 0.0, "frozen": True}
    diff = lambda a, b: sum(abs(x - y) for x, y in zip(a, b)) / n
    step = sum(diff(a, b) for a, b in zip(frames, frames[1:])) / (len(frames) - 1)
    return {"step": round(step, 2), "frozen": step < FROZEN_STEP}


_motion_cache: dict[tuple[str, float], dict] = {}


def motion_cached(clip: Path) -> dict | None:
    if not clip.exists():
        return None
    k = (str(clip), clip.stat().st_mtime)
    if k not in _motion_cache:
        _motion_cache[k] = motion(clip)
    return _motion_cache[k]


# ---------------------------------------------------------------- pictures

def _path(ep_dir: Path) -> Path:
    return ep_dir / "checks.json"


def load(ep_dir: Path) -> dict:
    p = _path(ep_dir)
    try:
        data = json.loads(p.read_text()) if p.exists() else {}
    except (ValueError, OSError):   # a damaged file only means "not checked yet"
        data = {}
    return {st: data.get(st, {}) for st in STAGES}


def _save(ep_dir: Path, data: dict) -> None:
    tmp = _path(ep_dir).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    os.replace(tmp, _path(ep_dir))   # never a half-written file


def fresh(entry: dict | None, f: Path) -> bool:
    return bool(entry) and f.exists() and abs(entry.get("mtime", 0) - f.stat().st_mtime) < 1e-3


def _names(cast: list[str], reg: dict) -> list[tuple[str, str]]:
    """(display name, description) for the listed cast; props (kites, buses) aren't counted."""
    people = reg.get("cast", {})
    return [(c.replace("_", " ").split(" ")[0].title(), people[c]["ref"]) for c in dict.fromkeys(cast) if c in people]


def ask(image: bytes, cast: list[tuple[str, str]]) -> dict:
    ids = [f"c{i + 1}" for i in range(len(cast))]
    schema = {"type": "object", "required": ["counts", "extra", "problems"], "properties": {
        "counts": {"type": "object", "properties": {i: {"type": "integer"} for i in ids}, "required": ids},
        "extra": {"type": "integer"}, "problems": {"type": "array", "items": {"type": "string"}}}}
    listing = "\n".join(f"{i}: {ref}" for i, (_, ref) in zip(ids, cast)) or "(nobody)"
    q = ("This is one frame from a children's cartoon. The characters that belong in it:\n" + listing +
         "\n\ncounts: how many times each listed character appears in THIS frame (0 if out of frame; 2 if the same character "
         "is drawn twice). extra: how many other people or animals are clearly visible in the foreground that are not in the "
         "list (ignore small background crowds). problems: only clear drawing mistakes a parent would notice: extra arms, hands "
         "or legs, a melted or distorted face, a body merged with another, a character floating in the air with no reason, "
         "garbled writing. Jumping, flying kites and birds in the sky are fine. Empty list if none.")
    body = {"model": WRITER_MODEL, "stream": False, "think": False, "keep_alive": "60s", "format": schema,
            "options": {"temperature": 0},
            "messages": [{"role": "user", "content": q, "images": [base64.b64encode(image).decode()]}]}
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.loads(json.load(r)["message"]["content"])
    counts = out.get("counts") or {}
    return {"counts": {name: int(counts.get(i, 0)) for i, (name, _) in zip(ids, cast)},
            "extra": max(0, int(out.get("extra") or 0)), "problems": [p for p in out.get("problems") or [] if p.strip()]}


def flags_of(result: dict, where: str) -> list[str]:
    out = [f"{name} appears {n} times{where}" for name, n in result["counts"].items() if n > 1]
    if result["extra"]:
        out.append(f"{result['extra']} extra {'person or animal' if result['extra'] == 1 else 'people or animals'}{where}")
    out += [p[0].upper() + p[1:].rstrip(".") + where for p in result["problems"]]
    return out


def _frame(clip: Path, t: float) -> bytes:
    return subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(clip), "-frames:v", "1",
                           "-vf", "scale=768:-1", "-q:v", "3", "-f", "image2", "-c:v", "mjpeg", "-strict", "unofficial", "-"],
                          capture_output=True).stdout


def _seconds(clip: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(clip)],
                         capture_output=True, text=True).stdout
    return float(out.strip() or 0)


def targets(ep: pixar.Episode, stage: str, only: list[str] | None = None) -> list[tuple[str, Path, list[str]]]:
    """(output name, file, expected cast) for every made output of the stage."""
    out = []
    for s in ep.shots:
        if only and s.id not in only:
            continue
        if stage == "keys":
            for k in [s.key] + ([s.end_key] if s.end_key else []):
                out.append((k.name, ep.keys_dir / f"{k.name}.png", k.cast))
        else:
            cast = s.key.cast + (s.end_key.cast if s.end_key else [])
            out.append((s.id, ep.clips_dir / f"{s.id}.mp4", cast))
    return [t for t in out if t[1].exists()]


def unchecked(ep: pixar.Episode, stage: str, only: list[str] | None = None) -> list[tuple[str, Path, list[str]]]:
    done = load(ep.dir)[stage]
    return [t for t in targets(ep, stage, only) if not fresh(done.get(t[0]), t[1])]


def run(spec: str, stage: str, only: list[str] | None = None, force: bool = False) -> None:
    ep = pixar.load(spec)
    reg = tomllib.loads(REGISTRY.read_text())
    todo = targets(ep, stage, only) if force else unchecked(ep, stage, only)
    print(f"{len(todo)} {stage} to check", flush=True)
    try:
        for name, f, cast in todo:
            print(f"check {name}", flush=True)
            mtime = f.stat().st_mtime   # the picture this result is about (it may be replaced while we look)
            names = _names(cast, reg)
            if stage == "keys":
                shots = [("", f.read_bytes())]
            else:
                d = _seconds(f)
                moments = sorted({round(t, 1) for t in (0.3, d * 0.25, d * 0.5, d * 0.75, max(0.3, d - 0.3))})
                shots = [(f" at {t:.1f} s", _frame(f, t)) for t in moments]
            frames = [{"at": where.strip(), **ask(img, names)} for where, img in shots if img]
            flags = list(dict.fromkeys(x for fr in frames for x in flags_of(fr, fr["at"] and f" ({fr['at']})")))
            data = load(ep.dir)
            data[stage][name] = {"mtime": mtime, "expected": [n for n, _ in names], "frames": frames, "flags": flags}
            _save(ep.dir, data)
            print(f"  {name}: {'; '.join(flags) or 'looks right'}", flush=True)
    finally:   # free the memory for the next GPU job
        try:
            urllib.request.urlopen(urllib.request.Request(f"{OLLAMA}/api/generate", data=json.dumps(
                {"model": WRITER_MODEL, "keep_alive": 0}).encode(), headers={"Content-Type": "application/json"}), timeout=30)
        except OSError:
            pass


def main(args) -> None:
    run(args.spec, args.stage, args.only, args.force)


# ---------------------------------------------------------------- what the studio shows

def summary(ep: pixar.Episode, checks: dict, stage: str, shot: pixar.Shot, checking: bool) -> dict:
    """state: ok | flag | checking | none, with plain-words flags and what passed."""
    flags, passed, missing = [], [], False
    if stage == "clips":
        clip = ep.clips_dir / f"{shot.id}.mp4"
        if not clip.exists():
            return {"state": "none", "flags": [], "passed": []}
        m = motion_cached(clip)
        (flags if m["frozen"] else passed).append("Barely moves (looks frozen)" if m["frozen"] else "Moves")
        names = [(shot.id, clip)]
    else:
        names = [(k.name, ep.keys_dir / f"{k.name}.png") for k in [shot.key] + ([shot.end_key] if shot.end_key else [])]
        names = [(n, f) for n, f in names if f.exists()]
        if not names:
            return {"state": "none", "flags": [], "passed": []}
    look = [checks[stage].get(n) for n, f in names]
    if all(fresh(e, f) for e, (_, f) in zip(look, names)):
        lf = [x for e in look for x in e["flags"]]
        flags += [(f"End keyframe: {x[0].lower()}{x[1:]}" if n.endswith("_b") else x) for e, (n, _) in zip(look, names) for x in e["flags"]]
        if not lf:
            passed.append("Pictures look right")
    else:
        missing = True
    state = "flag" if flags else "checking" if missing and checking else "ok" if not missing else "partial"
    return {"state": state, "flags": flags, "passed": passed}
