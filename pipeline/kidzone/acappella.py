"""A cappella vocal takes with ACE-Step (XL turbo): vocals only, so no stem separation is needed downstream.

Usage: uv run python -m kidzone.acappella <episode-slug> [takes] [model]
Writes episodes/<slug>/songs/acappella/hi_<n>.wav
"""

import json
import sys
import time
import urllib.request

from .core import Episode, log, read_json
from .stages.song import API, AceServer, _post

STYLE = (
    "a cappella, unaccompanied solo vocal only, no instruments, no drums, no music, no backing track, "
    "Indian devotional bhajan singing in Hindustani style with gentle meend and gamak ornaments, "
    "sweet young Indian girl singer, innocent and loving, clear Hindi diction, close dry vocal recording"
)


def run(slug: str, takes: int = 3, model: str = "acestep-v15-xl-turbo") -> list[str]:
    ep = Episode(slug)
    brief = read_json(ep.path("brief.json"))
    lyrics = read_json(ep.path("songs", "lyrics.json"))["hi"]
    out = ep.path("songs", "acappella")
    out.mkdir(parents=True, exist_ok=True)
    files = []
    with AceServer():
        _post("/v1/init", {"model": model}, timeout=600)
        t0 = time.time()
        payload = {"prompt": STYLE, "lyrics": lyrics, "vocal_language": "hi", "thinking": True, "use_cot_language": False,
                   "use_cot_caption": False, "bpm": brief.get("bpm") or 92, "audio_duration": brief.get("duration_sec", 140),
                   "batch_size": takes, "audio_format": "wav", "model": model}
        if brief.get("key"):
            payload["key_scale"] = brief["key"]
        task = _post("/release_task", payload)
        while True:
            time.sleep(3)
            res = _post("/query_result", {"task_id_list": [task["task_id"]]})[0]
            if res["status"] in (1, 2):
                break
        if res["status"] == 2:
            raise RuntimeError(res.get("result"))
        for n, item in enumerate(json.loads(res["result"])):
            dest = out / f"hi_{n}.wav"
            urllib.request.urlretrieve(API + item["file"], dest)
            files.append(dest.name)
        log("acappella", f"{len(files)} a cappella takes ({model}) in {time.time() - t0:.0f}s → {out}")
    return files


if __name__ == "__main__":
    run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3, sys.argv[3] if len(sys.argv) > 3 else "acestep-v15-xl-turbo")
