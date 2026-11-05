"""Pixar-style episode engine: episodes/<slug>/episode.toml + assets/registry.toml → keyframes → clips → episode → upload pack.

  kidzone pixar <episode.toml> [--phase keys|clips|assemble|package|all] [--only s03 s05] [--redo s05] [--dry-run]

Phases (each resumable; existing outputs are kept unless --redo):
  keys      FLUX.2 klein edit keyframes → keys/<shot>_a.png (+ _b end keys) and keys/contact.jpg   ← review gate
  clips     LTX-2.3 distilled I2V (or a2v lip-sync for sing shots) → clips/<shot>.mp4 and clips/contact.jpg  ← review gate
  assemble  trim each clip to its slot on the song's line grid, concat, mux the mastered song → <output>
  package   prepend the Gaana Gaadi intro and upscale to 1080p → upload/<stem>_1080p.mp4

Prompt tokens: {id} = registry character/prop ref + "(second image)" etc., attached in order of first appearance after
the scene; {id|custom words} = same image with custom words; {Id} = capitalised; {name} = episode [vars]; {keep:id} = the prop's keep text.
"""

import json
import math
import re
import shlex
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .core import ROOT
from .paths import ASSETS, BRAND, BRAND_TOOLS, REGISTRY, find_spec, rel

ORD = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth"]
FLUX = ["--model", "mflux-community/flux2-klein-4b-mflux-q4", "--base-model", "flux2-klein-4b"]
LTX_DIR = ROOT / "spikes/vendor/ltx-2-mlx"
LTX_MODELS = ["--model", str(ROOT / "spikes/models/ltx-2.3-mlx-q4"), "--gemma", str(ROOT / "spikes/models/gemma-3-12b-it-4bit")]
ENV = {"AGX_RELAX_CDM_CTXSTORE_TIMEOUT": "1", "HF_HUB_OFFLINE": "1"}
INTRO_ADD = BRAND_TOOLS / "add_intro.sh"
INTRO = BRAND / "intro/intro.mp4"   # your channel intro; package skips it when missing
DEFAULT_KEY_STYLE = ("Keep each character's exact look, shape, face, body proportions, outfit and colours from their reference "
                     "image. Same Pixar 3D style and lighting as the scene, cinematic. Each character has their own distinct pose. "
                     "Include only the characters described — no extra or duplicate characters, no people or children other "
                     "than those described, animals keep their own animal faces.")
NO_PEOPLE = "There are no children or people anywhere in this image, the bus windows show empty seats."
TOKEN = re.compile(r"\{([A-Za-z_]+)(?:\|([^}]*))?\}")  # {Gopu} = capitalised (sentence start)


def frames_for(seconds: float, fps: int) -> int:
    """Smallest LTX-valid frame count (8k+1) covering `seconds`."""
    n = math.ceil(seconds * fps)
    return n if n % 8 == 1 else n + (1 - n % 8) % 8


@dataclass
class Key:
    name: str
    seed: int
    scene: str
    prompt: str          # final prompt sent to FLUX
    images: list[Path]
    cast: list[str] = field(default_factory=list)   # registry ids, in image order (after the scene)


NO_SINGING = ("Nobody sings or talks: mouths stay closed or softly smiling (laughing is fine), "
              "and the feeling shows through the eyes, faces, gestures and body language")


@dataclass
class Shot:
    id: str
    start: float         # seconds on the song timeline
    dur: float           # slot length in the final cut
    frames: int          # frames rendered by LTX
    motion: str          # final prompt sent to LTX
    sing: bool
    key: Key
    end_key: Key | None = None   # guide key for the last frame ("same" = key itself)
    end_same: bool = False
    clip_seed: int | None = None  # per-shot LTX seed (set by a studio redo); default = [render] seed


@dataclass
class Episode:
    dir: Path
    spec: dict
    width: int
    height: int
    fps: int
    seed: int
    song: Path
    vocals: Path | None
    lead: float
    shots: list[Shot] = field(default_factory=list)

    @property
    def keys_dir(self) -> Path:
        return self.dir / "keys"

    @property
    def clips_dir(self) -> Path:
        return self.dir / "clips"

    @property
    def output(self) -> Path:
        return self.dir / self.spec["episode"]["output"]


def _registry() -> dict:
    return tomllib.loads(REGISTRY.read_text())


def _probe_seconds(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(out.stdout.strip())


def load(spec_path: str | Path) -> Episode:
    spec_path = Path(spec_path).resolve()
    spec = tomllib.loads(spec_path.read_text())
    reg = _registry()
    cast = {**reg.get("cast", {}), **reg.get("props", {})}
    order = list(cast)  # style clauses follow registry order
    r, s, st = spec.get("render", {}), spec["song"], spec.get("style", {})
    ep = Episode(dir=spec_path.parent, spec=spec, width=r.get("width", 1280), height=r.get("height", 720), fps=r.get("fps", 24),
                 seed=r.get("seed", 7), song=spec_path.parent / s["audio"],
                 vocals=(spec_path.parent / s["vocals"]) if s.get("vocals") else None, lead=s.get("lipsync_lead", 0.167))
    variables = spec.get("vars", {})
    key_style = st.get("keyframe", DEFAULT_KEY_STYLE)
    clip_style = st.get("clip", "3D animated Pixar-style movie scene, smooth lively animation")
    line = s["line_seconds"]
    song_len = s.get("seconds") or (_probe_seconds(ep.song) if ep.song.exists()
                                    else sum(sh.get("lines", 1) for sh in spec["shot"]) * line)  # song not made yet: plan on the grid

    def build_key(name: str, seed: int, scene: str, text: str) -> Key:
        images = [ASSETS / reg["scenes"][scene]]
        present: list[str] = []

        def sub(m: re.Match) -> str:
            tid, custom = m.group(1), m.group(2)
            cap = tid[0].isupper()
            tid = tid.lower()
            if tid in variables and custom is None:
                return variables[tid]
            if tid not in cast:
                raise KeyError(f"{name}: unknown token {{{tid}}} (not in registry or [vars])")
            if tid not in present:
                present.append(tid)
                images.append(ASSETS / cast[tid]["file"])
            words = custom or cast[tid]["ref"]
            return f"{words[0].upper() + words[1:] if cap else words} ({ORD[present.index(tid) + 1]} image)"

        body = TOKEN.sub(sub, text)
        sty = key_style
        people = [t for t in present if cast[t].get("person")]
        for t in order:
            if t in present and cast[t].get("style"):
                sty += " " + cast[t]["style"]
        if not people:
            sty += " " + st.get("no_people", NO_PEOPLE)
        elif len(people) == 1 and cast[people[0]].get("alone"):
            sty += " " + cast[people[0]]["alone"]
        return Key(name, seed, scene, f"Use the first image as the scene and keep it unchanged. {body} {sty}", images, present)

    def clip_text(text: str) -> str:
        def sub(m: re.Match) -> str:
            tid = m.group(1)
            if tid.startswith("keep:"):
                if tid[5:] not in cast or "keep" not in cast[tid[5:]]:
                    raise KeyError(f"motion: {{{tid}}} needs a prop with `keep` text in the registry")
                return cast[tid[5:]]["keep"]
            if tid not in variables:
                raise KeyError(f"motion: unknown token {{{tid}}} (motion prompts use plain words; only {{keep:prop}} and [vars] work here)")
            return variables[tid]
        return f"{clip_style}. " + re.sub(r"\{(keep:[a-z_]+|[a-z_]+)\}", sub, text)

    t = 0.0
    shots = spec["shot"]
    for i, sh in enumerate(shots):
        dur = song_len - t if i == len(shots) - 1 else sh.get("lines", 1) * line
        feel = (f" Feeling: {sh['feel']}, clearly readable in the faces, eyes and posture"
                + ("" if sh.get("sing") else "; nobody is singing, lips closed or softly smiling unless laughing") + ".") if sh.get("feel") else ""
        key = build_key(f"{sh['id']}_a", sh["seed"], sh["scene"], sh["key"] + feel)
        end_key, end_same = None, sh.get("end") == "same"
        if isinstance(sh.get("end"), dict):
            e = sh["end"]
            end_key = build_key(f"{sh['id']}_b", e["seed"], e.get("scene", sh["scene"]), e["key"] + feel)
        motion = clip_text(sh["motion"])
        if sh.get("feel"):   # emotion shots: the feeling must read on faces; only lip-sync shots sing
            motion += f". The feeling: {sh['feel']}" + ("" if sh.get("sing") else f". {NO_SINGING}")
        ep.shots.append(Shot(sh["id"], t, dur, sh.get("frames") or frames_for(dur, ep.fps), motion,
                             sh.get("sing", False), key, end_key, end_same, sh.get("clip_seed")))
        t += dur
    return ep


# ---------------------------------------------------------------- runners

def _run(cmd: list[str], dry: bool, cwd: Path | None = None, log: Path | None = None) -> None:
    if dry:
        print(("cd " + shlex.quote(str(cwd)) + " && " if cwd else "") + shlex.join(cmd))
        return
    import os
    env = {**os.environ, **ENV}
    with open(log, "w") if log else open(os.devnull, "w") as f:
        res = subprocess.run(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT)
    if res.returncode:
        raise RuntimeError(f"failed ({res.returncode}): {shlex.join(cmd[:6])} … see {log}")


def _selected(ep: Episode, only: list[str] | None) -> list[Shot]:
    return [s for s in ep.shots if not only or s.id in only]


def _redo(ep: Episode, redo: list[str] | None, phase: str, dry: bool = False) -> list[str]:
    """Delete the given shots' outputs for this phase (dry run: only report). Returns ids that will be regenerated."""
    ids = {s.id for s in ep.shots}
    for sid in redo or []:
        if sid not in ids:
            raise SystemExit(f"--redo: unknown shot {sid}")
        paths = [ep.keys_dir / f"{sid}_a.png", ep.keys_dir / f"{sid}_b.png"] if phase == "keys" else [ep.clips_dir / f"{sid}.mp4"]
        for p in paths:
            if p.exists():
                print(f"redo: {'would remove' if dry else 'removed'} {rel(p)}")
                if not dry:
                    p.unlink()
    return list(redo or [])


def render_key(k: Key, out: Path, seed: int | None = None, dry: bool = False) -> None:
    """One keyframe (FLUX.2 edit: scene + reference images + prompt). Same prompt + seed = same image."""
    _run(["uv", "run", "--project", str(ROOT / "spikes/envs/image"), "mflux-generate-flux2-edit", *FLUX, "--image-paths",
          *map(str, k.images), "--seed", str(k.seed if seed is None else seed), "--width", "1280", "--height", "720",
          "--prompt", k.prompt, "--output", str(out)], dry, log=out.with_suffix(".log"))


def keys(ep: Episode, only=None, dry=False) -> None:
    ep.keys_dir.mkdir(exist_ok=True)
    for s in _selected(ep, only):
        for k in [s.key] + ([s.end_key] if s.end_key else []):
            out = ep.keys_dir / f"{k.name}.png"
            if out.exists():
                continue
            print(f"key {k.name}")
            render_key(k, out, dry=dry)
    if not dry:
        _contact(sorted(ep.keys_dir.glob("*_[ab].png")), ep.keys_dir / "contact.jpg")


def clips(ep: Episode, only=None, dry=False) -> None:
    ep.clips_dir.mkdir(exist_ok=True)
    for s in _selected(ep, only):
        size = ["-W", str(ep.width), "-H", str(ep.height), "--frame-rate", str(ep.fps), "--seed", str(s.clip_seed or ep.seed)]
        out = ep.clips_dir / f"{s.id}.mp4"
        if out.exists():
            continue
        print(f"clip {s.id} ({s.frames} frames{', lip-sync' if s.sing else ''})")
        log = ep.clips_dir / f"{s.id}.log"
        key = str(ep.keys_dir / f"{s.key.name}.png")
        if s.sing:
            raw = ep.clips_dir / f"{s.id}_raw.mp4"
            _run(["uv", "run", "ltx-2-mlx", "a2v", "--distilled", *LTX_MODELS, *size, "-f", str(s.frames), "--image", key,
                  "--audio", str(ep.vocals), "--audio-start", str(round(s.start - ep.lead, 3)), "-p", s.motion, "-o", str(raw)],
                 dry, cwd=LTX_DIR, log=log)
            _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-an", "-c:v", "copy", str(out)], dry)
            if not dry:
                raw.unlink()
        else:
            imgs = ["--image", key, "0", "1.0"]
            if s.end_same or s.end_key:
                end = key if s.end_same else str(ep.keys_dir / f"{s.end_key.name}.png")
                imgs += ["--image", end, "last", "1.0", "guide"]
            _run(["uv", "run", "ltx-2-mlx", "generate", "--distilled", *LTX_MODELS, *size, "-f", str(s.frames), *imgs, "--no-audio",
                  "-p", s.motion, "-o", str(out)], dry, cwd=LTX_DIR, log=log)
    if not dry:
        mids = []
        for s in ep.shots:
            c = ep.clips_dir / f"{s.id}.mp4"
            if c.exists():
                m = ep.clips_dir / f"_mid_{s.id}.png"
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{s.dur / 2:.2f}", "-i", str(c), "-frames:v", "1", str(m)])
                mids.append(m)
        _contact(mids, ep.clips_dir / "contact.jpg")
        for m in mids:
            m.unlink(missing_ok=True)


def assemble(ep: Episode, dry=False) -> Path:
    seg = ep.dir / "_seg"
    seg.mkdir(exist_ok=True)
    total = round((ep.shots[-1].start + ep.shots[-1].dur) * ep.fps)
    lines = []
    for i, s in enumerate(ep.shots):
        a = round(s.start * ep.fps)
        b = total if i == len(ep.shots) - 1 else round((s.start + s.dur) * ep.fps)
        out = seg / f"{s.id}.mp4"
        _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(ep.clips_dir / f"{s.id}.mp4"), "-vf",
              f"scale={ep.width}:{ep.height},fps={ep.fps},tpad=stop_mode=clone:stop_duration=2", "-frames:v", str(b - a), "-an",
              "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", str(out)], dry)
        lines.append(f"file '{out}'")
    (seg / "list.txt").write_text("\n".join(lines) + "\n")
    video = seg / "video_only.mp4"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(seg / "list.txt"), "-c", "copy", str(video)], dry)
    end = total / ep.fps   # [song] seconds shorter than the song: fade the music out instead of cutting it off
    fade = ["-af", f"afade=t=out:st={max(0, end - 1.5):.3f}:d=1.5"] if ep.spec["song"].get("seconds") else []
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(ep.song), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
          *fade, "-c:a", "aac", "-b:a", "192k", "-shortest", str(ep.output)], dry)
    if not dry:
        for p in seg.iterdir():
            p.unlink()
        seg.rmdir()
        print(f"episode → {rel(ep.output)} ({_probe_seconds(ep.output):.1f}s)")
    return ep.output


def package(ep: Episode, dry=False) -> Path:
    up = ep.dir / "upload"
    up.mkdir(exist_ok=True)
    stem = ep.output.stem
    with_intro = ep.dir / f"{stem}_intro.mp4"
    final = up / f"{stem}_1080p.mp4"
    if INTRO.exists():
        _run([str(INTRO_ADD), str(INTRO), str(ep.output), str(with_intro)], dry)
    else:   # no channel intro in your content folder: package the episode as it is
        print("no brand intro (assets/brand/intro/intro.mp4): packaging without one")
        with_intro = ep.output
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(with_intro), "-vf", "scale=1920:1080:flags=lanczos,unsharp=5:5:0.4:5:5:0.0",
          "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(final)], dry)
    if not dry:
        print(f"upload pack → {rel(final)}")
    return final


def _contact(images: list[Path], out: Path, per_row: int = 4) -> None:
    if not images:
        return
    rows = [images[i:i + per_row] for i in range(0, len(images), per_row)]
    args = ["magick"]
    for r in rows:
        args += ["("] + [str(p) for p in r] + ["-resize", "480x270", "+append", ")"]
    args += ["-background", "#222", "-gravity", "west", "-append", str(out)]
    subprocess.run(args, check=False)
    print(f"contact sheet → {rel(out)}")


def describe(ep: Episode) -> dict:
    """Plan summary (used by --dry-run and tests)."""
    return {"shots": [{"id": s.id, "start": round(s.start, 3), "dur": round(s.dur, 3), "frames": s.frames, "sing": s.sing,
                       "key": {"seed": s.key.seed, "images": [rel(p) for p in s.key.images], "prompt": s.key.prompt},
                       "end": "same" if s.end_same else (s.end_key.name if s.end_key else None), "motion": s.motion,
                       "clip_seed": s.clip_seed or ep.seed} for s in ep.shots]}


def main(args) -> None:
    ep = load(find_spec(args.spec))
    print(f"{ep.spec['episode']['title']}: {len(ep.shots)} shots, {ep.width}×{ep.height}, "
          f"{ep.shots[-1].start + ep.shots[-1].dur:.1f}s song")
    phases = ["keys", "clips", "assemble", "package"] if args.phase == "all" else [args.phase]
    if args.plan:
        print(json.dumps(describe(ep), indent=1, ensure_ascii=False))
        return
    for ph in phases:
        if ph in ("keys", "clips"):
            _redo(ep, args.redo, ph, args.dry_run)
        {"keys": lambda: keys(ep, args.only, args.dry_run), "clips": lambda: clips(ep, args.only, args.dry_run),
         "assemble": lambda: assemble(ep, args.dry_run), "package": lambda: package(ep, args.dry_run)}[ph]()
