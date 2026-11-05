"""Align stage: chosen take + known lyrics → per-line/word timings + mouth track; beat grid."""

from ..core import AUDIO_ENV, Episode, log, read_json, run_tool
from ..models import Storyboard


def run(ep: Episode, sb: Storyboard, chosen: dict[str, str]) -> dict[str, dict]:
    """Returns {lang: {"align": {...}, "beats": {...}}}."""
    songs = ep.path("songs")
    out = {}
    for lang, take in chosen.items():
        stem = take.rsplit(".", 1)[0]
        align_f = ep.path("align", f"{stem}.json")
        beats_f = songs / f"{stem}.beats.json"
        if not align_f.exists():
            run_tool(AUDIO_ENV, "align_and_mouth.py", str(songs / take), lang, lang, str(songs / "lyrics.json"), str(ep.path("align")))
        if not beats_f.exists():
            run_tool(AUDIO_ENV, "beats.py", str(songs / take), str(sb.bpm))
        a, b = read_json(align_f), read_json(beats_f)
        expected = len(sb.lines())
        if len(a["segments"]) != expected:
            log("align", f"⚠ {lang}: {len(a['segments'])} aligned segments vs {expected} lines — timeline will be approximate")
        log("align", f"{lang}: {len(a['segments'])} lines, word conf {a['mean_word_prob']:.2f}, tempo {b['tempo']}")
        out[lang] = {"align": a, "beats": b}
    return out
