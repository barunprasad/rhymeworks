"""Render (Remotion) and package (mp4 + captions + thumbnail + YouTube metadata + license record)."""

import shutil
import subprocess
import time
from pathlib import Path

from ..core import COMPOSITIONS, Episode, log, read_json, write_json
from ..models import EpisodeBrief, Storyboard

LICENSES = [
    {"component": "Gemma 4 26B (writer)", "license": "Apache-2.0"},
    {"component": "ACE-Step 1.5 (music)", "license": "MIT"},
    {"component": "FLUX.2 klein 4B (art)", "license": "Apache-2.0"},
    {"component": "Whisper large-v3-turbo (alignment)", "license": "MIT"},
    {"component": "Parakeet TDT 0.6B v2 (scoring)", "license": "CC-BY-4.0"},
    {"component": "stable-ts, mflux, librosa", "license": "MIT / MIT / ISC"},
    {"component": "Remotion (render)", "license": "Remotion License (individual / ≤3-person company: free)"},
]


def _remotion(*args: str) -> None:
    out = subprocess.run(["npx", "remotion", *args, "--log=error"], cwd=COMPOSITIONS, capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(f"remotion {args[0]} failed:\n{out.stderr[-3000:]}")


def render(ep: Episode, episodes: dict[str, Path]) -> dict[str, Path]:
    out = {}
    for lang, props in episodes.items():
        mp4 = ep.path("renders", f"{lang}.mp4")
        mp4.parent.mkdir(parents=True, exist_ok=True)
        if not mp4.exists() or mp4.stat().st_mtime < props.stat().st_mtime:
            t0 = time.time()
            _remotion("render", "src/index.ts", "Episode", str(mp4), f"--props={props}")
            log("render", f"{lang}: {mp4.name} in {time.time() - t0:.0f}s")
        out[lang] = mp4
    return out


def _srt_time(t: float) -> str:
    h, rem = divmod(max(0.0, t), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"


def package(ep: Episode, brief: EpisodeBrief, show: dict, sb: Storyboard, episodes: dict[str, Path], renders: dict[str, Path]) -> Path:
    root = ep.path("package")
    for lang, mp4 in renders.items():
        d = root / lang
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy(mp4, d / f"{ep.slug}-{lang}.mp4")
        e = read_json(episodes[lang])["episode"]
        srt = []
        for k, s in enumerate(e["segments"], start=1):
            srt.append(f"{k}\n{_srt_time(s['start'])} --> {_srt_time(s['end'] + 0.2)}\n{s['text']}\n")
        (d / "captions.srt").write_text("\n".join(srt))
        # Thumbnail: a wide chorus moment (most cast on screen).
        chorus_t = next((e["segments"][i]["start"] + 1.0 for i, ln in enumerate(sb.lines()) if i < len(e["segments"]) and
                         any(sec.kind == "chorus" and ln in sec.lines for sec in sb.sections)), e["durationSec"] / 2)
        _remotion("still", "src/index.ts", "Episode", str(d / "thumbnail.png"), f"--props={episodes[lang]}", f"--frame={int(chorus_t * e['fps'])}")
        title = getattr(sb.title, lang)
        desc = getattr(sb.description, lang)
        write_json(d / "metadata.json", {
            "title": f"{title} | {show['title']}"[:100],
            "description": f"{desc}\n\n{show['title']} — original songs for little learners.\n#kidssongs #nurseryrhymes #learning",
            "tags": [show["title"], brief.topic, "kids songs", "preschool", "learning song", "toddler"],
            "defaultLanguage": lang,
            "categoryId": "27",
            "madeForKids": True,
            "containsSyntheticMedia": False,
            "notes": "Upload manually in YouTube Studio; set Made for Kids = Yes; check the Copyright column before publishing."
            + (" LYRICS WERE SUPPLIED IN THE BRIEF — confirm they are traditional/public domain (or that you hold the rights) before uploading." if brief.lyrics else ""),
        })
    write_json(root / "license.json", {"episode": ep.slug, "show": show["id"], "components": LICENSES,
                                         "assets": "All characters, scenes, props, lyrics and music generated locally for this show."})
    log("package", f"ready → {root}")
    return root
