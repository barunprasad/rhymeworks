"""Does the film end when the song does? Finds where the sound and the singing stop and suggests where to end.

  silent  the song goes quiet but shots keep running (e.g. an imported song with a long silent tail): end ~1 s after
          the last sound, dropping shots that would start after it.
  outro   the singing stops long before the music does: optionally end a few seconds after the last sung line; the
          assembly fades the music out over the last 1.5 s whenever [song] seconds is set.

Levels are read from the mastered song (and the isolated vocal) in 0.1 s windows; results are cached per file time.
"""

import math
import subprocess
from array import array
from pathlib import Path

from . import pixar

RATE, WIN = 8000, 800            # 0.1 s windows
QUIET_DB, VOICE_DB = -50.0, -38.0
SILENT_TAIL, OUTRO_TAIL = 3.0, 8.0
_cache: dict[tuple[str, float, float], float | None] = {}


def last_sound(wav: Path, db: float) -> float | None:
    """Time (s) of the last 0.1 s window louder than `db` dBFS, or None if the file is missing or silent."""
    if not wav.exists():
        return None
    k = (str(wav), wav.stat().st_mtime, db)
    if k not in _cache:
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(wav), "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
                             capture_output=True).stdout
        a = array("h")
        a.frombytes(raw[: len(raw) // 2 * 2])
        limit = (10 ** (db / 20) * 32768) ** 2 * WIN
        end = None
        for i in range(len(a) // WIN - 1, -1, -1):
            w = a[i * WIN:(i + 1) * WIN]
            if sum(x * x for x in w) > limit:
                end = (i + 1) * WIN / RATE
                break
        _cache[k] = end
    return _cache[k]


def suggest(ep: pixar.Episode) -> dict | None:
    if not ep.shots or not ep.song.exists():
        return None
    film_end = ep.shots[-1].start + ep.shots[-1].dur
    sound = last_sound(ep.song, QUIET_DB)
    voice = last_sound(ep.vocals, VOICE_DB) if getattr(ep, "vocals", None) else None
    if sound is None:
        return None
    out = {"film_end": round(film_end, 2), "sound_end": round(sound, 2), "voice_end": round(voice, 2) if voice else None,
           "set": ep.spec["song"].get("seconds")}
    if film_end - sound > SILENT_TAIL:
        cut = math.ceil((sound + 1.0) * 10) / 10
        kind = "silent"
    elif voice and sound - voice > OUTRO_TAIL and not out["set"]:
        cut = math.ceil((voice + 4.0) * 10) / 10
        kind = "outro"
    else:
        return {**out, "kind": None}
    drop = [s.id for s in ep.shots if s.start > cut - 1.0]
    if len(drop) >= len(ep.shots):
        return {**out, "kind": None}
    return {**out, "kind": kind, "cut": cut, "drop": drop}
