"""Master stage: chosen take → release audio (songs/master/final_<lang>.wav).

1. Intro check: if the first lyric starts late and the intro holds singing (ACE-Step often opens with a
   flat held vowel), the intro is repainted as an instrumental (ACE-Step repaint, several variants) and
   the variant with the least singing is spliced in front of the untouched take.
2. Polish: EQ toward the show's reference tonal balance, de-ess, glue compression, limiter, -14 LUFS.
Timing never changes, so the alignment / lip-sync made from the raw take stays exact.
"""

import json
import shutil

from ..core import AUDIO_ENV, ROOT, Episode, log, read_json, run_tool
from ..models import EpisodeBrief

SEP_ENV = ROOT / "spikes" / "envs" / "sep"
DEFAULT_TARGET = {"bands": {"sub_20_60": -13.8, "bass_60_250": -5.7, "lowmid_250_1k": -3.6, "mid_1k_4k": -6.4, "high_4k_11k": -16.5}}
INTRO_CAPTION = ("gentle intro, soft melodic lead instrument over a warm drone, light percussion pickup, "
                 "instrumental, no vocals, warm and sweet")


def run(ep: Episode, brief: EpisodeBrief, show: dict, chosen: dict[str, str], timings: dict) -> dict[str, str]:
    """Returns {lang: path relative to songs/} of the release audio."""
    songs, out_dir = ep.path("songs"), ep.path("songs", "master")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = show.get("master_target", DEFAULT_TARGET)
    finals = {}
    for lang, take in chosen.items():
        final = out_dir / f"final_{lang}.wav"
        finals[lang] = f"master/{final.name}"
        if final.exists():
            continue
        src = songs / take
        segs = timings[lang]["align"]["segments"]
        first = segs[0]["start"] if segs else 0.0
        opts: dict = {"target": target, "lufs": -14}
        if first > 2.5:
            probe = first - 0.4
            leak = json.loads(run_tool(SEP_ENV, "intro_vocal.py", f"{probe:.2f}", str(src)).strip().splitlines()[-1])[str(src)]
            if leak > -12:  # the intro is mostly singing (a held vowel) — make it instrumental
                from ..repaint import repaint
                caption = f"{show.get('intro_style', INTRO_CAPTION)}; {brief.song_style or show.get('song_style', '')}"
                lyrics = "[Intro - Instrumental]\n\n" + read_json(songs / "lyrics.json")[lang]
                cands = repaint(src, out_dir / f"intro_{lang}", 0.0, probe + 0.2, caption, 4, lyrics)
                scores = json.loads(run_tool(SEP_ENV, "intro_vocal.py", f"{probe:.2f}", *map(str, cands)).strip().splitlines()[-1])
                best = min(scores, key=scores.get)
                log("master", f"{lang}: intro held singing ({leak:+.1f} dB) → repainted; picked {best.rsplit('/', 1)[-1]} ({scores[best]:+.1f} dB)")
                opts.update(intro=best, splice=[max(0.0, probe - 0.5), probe])
        run_tool(AUDIO_ENV, "polish.py", str(src), str(final), json.dumps(opts))
        log("master", f"{lang}: release audio → {final}")
    return finals
