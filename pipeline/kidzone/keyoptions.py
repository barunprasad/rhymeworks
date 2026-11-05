"""Keyframe options: draw N versions of one shot's start keyframe (different seeds), pick one.

  kidzone options <episode.toml> <shot> [--n 4]

Options land in keys/options/<shot>/<seed>.png. Picking one writes its seed into episode.toml (validated) and copies the
image to keys/<shot>_a.png, so the spec still reproduces exactly that keyframe (same prompt + seed = same image).
"""

import random
import shutil
from pathlib import Path

from . import pixar
from .core import log
from . import paths
from .studio import review, shotlist


def folder(ep_dir: Path, sid: str) -> Path:
    return ep_dir / "keys" / "options" / sid


def listing(ep_dir: Path, sid: str) -> list[dict]:
    d = folder(ep_dir, sid)
    if not d.exists():
        return []
    return [{"seed": int(p.stem), "path": p} for p in sorted(d.glob("*.png"), key=lambda p: p.stat().st_mtime)]


def make(spec: Path, sid: str, n: int = 4) -> list[Path]:
    ep = pixar.load(spec)
    shot = next((s for s in ep.shots if s.id == sid), None)
    if not shot:
        raise KeyError(f"no shot {sid}")
    d = folder(ep.dir, sid)
    d.mkdir(parents=True, exist_ok=True)
    used = {o["seed"] for o in listing(ep.dir, sid)} | {shot.key.seed}
    made = []
    for _ in range(n):
        seed = random.randint(1000, 99999)
        while seed in used:
            seed += 1
        used.add(seed)
        out = d / f"{seed}.png"
        print(f"key {sid} option {seed}", flush=True)   # progress line for the studio worker
        pixar.render_key(shot.key, out, seed=seed)
        out.with_suffix(".log").unlink(missing_ok=True)
        made.append(out)
    log("options", f"{sid}: {len(made)} new options")
    return made


def use(spec: Path, sid: str, seed: int) -> Path:
    """Make option `seed` the shot's keyframe: seed → episode.toml, image → keys/<sid>_a.png, marked approved."""
    ep_dir = spec.parent
    src = folder(ep_dir, sid) / f"{seed}.png"
    if not src.exists():
        raise FileNotFoundError(f"no option {seed} for {sid}")
    cur = ep_dir / "keys" / f"{sid}_a.png"
    old = next((s for s in shotlist.read(spec)["shots"] if s["id"] == sid), None)
    if old and cur.exists() and old["seed"] != seed:   # keep the current keyframe as an option, so nothing is lost
        dst = folder(ep_dir, sid) / f"{old['seed']}.png"
        if not dst.exists():
            shutil.copy2(cur, dst)
    shotlist.update(spec, sid, {"seed": seed})
    shutil.copy2(src, cur)
    review.decide(ep_dir, "keys", sid, "approved", cur.stat().st_mtime)
    return cur


def main(args) -> None:
    make(paths.find_spec(args.spec), args.shot, args.n)
