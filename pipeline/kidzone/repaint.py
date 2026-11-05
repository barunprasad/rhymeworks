"""Regenerate one time range of a song take with ACE-Step "repaint", keeping the rest identical.

Used to fix a bad song intro (e.g. a flat held drone before the first lyric) without touching
the sung part, so lyric timing and lip-sync stay exact.
Usage: uv run python -m kidzone.repaint <src.wav> <out_prefix> <start> <end> "<caption>" [takes] [lyrics_file]
Writes <out_prefix>_<n>.wav
"""

import json
import shutil
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from .core import log
from .stages.song import API, AceServer, _post


def repaint(src: Path, out_prefix: Path, start: float, end: float, caption: str, takes: int = 3,
            lyrics: str = "", model: str = "acestep-v15-turbo") -> list[Path]:
    with AceServer():
        _post("/v1/init", {"model": model}, timeout=600)
        t0 = time.time()
        tmp_src = Path(tempfile.gettempdir()) / f"kidzone_repaint_{src.stem}.wav"  # server only reads temp dir
        shutil.copy(src, tmp_src)
        task = _post("/release_task", {
            "task_type": "repaint", "src_audio_path": str(tmp_src), "repainting_start": start, "repainting_end": end,
            "chunk_mask_mode": "explicit", "prompt": caption, "lyrics": lyrics, "vocal_language": "hi",
            "batch_size": takes, "audio_format": "wav", "thinking": False,
        })
        while True:
            time.sleep(3)
            res = _post("/query_result", {"task_id_list": [task["task_id"]]})[0]
            if res["status"] in (1, 2):
                break
        if res["status"] == 2:
            raise RuntimeError(f"repaint failed: {res.get('result')}")
        outs = []
        for n, item in enumerate(json.loads(res["result"])):
            dest = Path(f"{out_prefix}_{n}.wav")
            dest.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(API + item["file"], dest)
            outs.append(dest)
        log("repaint", f"{len(outs)} repaints of {src.name} [{start}-{end}s] in {time.time() - t0:.0f}s")
    return outs


if __name__ == "__main__":
    a = sys.argv
    lyr = Path(a[7]).read_text() if len(a) > 7 else ""
    repaint(Path(a[1]), Path(a[2]), float(a[3]), float(a[4]), a[5], int(a[6]) if len(a) > 6 else 3, lyr)
