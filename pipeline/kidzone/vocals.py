"""Vocal stem extraction with ACE-Step's base model ("extract" task, MIT) — no Demucs.

Usage: uv run python -m kidzone.vocals <mix.wav> <vocals_out.wav>
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


def extract_vocals(mix: Path, out: Path, steps: int = 48) -> Path:
    with AceServer():
        _post("/v1/init", {"model": "acestep-v15-base"}, timeout=600)
        t0 = time.time()
        # ACE-Step only accepts absolute audio paths inside the system temp dir.
        tmp_src = Path(tempfile.gettempdir()) / f"kidzone_extract_{mix.stem}.wav"
        shutil.copy(mix, tmp_src)
        task = _post("/release_task", {
            "task_type": "extract",
            "src_audio_path": str(tmp_src),
            "instruction": "Extract the vocals track from the audio:",
            "inference_steps": steps,
            "batch_size": 1,
            "audio_format": "wav",
            "thinking": False,
        })
        while True:
            time.sleep(3)
            res = _post("/query_result", {"task_id_list": [task["task_id"]]})[0]
            if res["status"] in (1, 2):
                break
        if res["status"] == 2:
            raise RuntimeError(f"extract failed: {res.get('result')}")
        item = json.loads(res["result"])[0]
        out.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(API + item["file"], out)
        log("vocals", f"extracted vocals from {mix.name} in {time.time() - t0:.0f}s → {out}")
    return out


if __name__ == "__main__":
    extract_vocals(Path(sys.argv[1]), Path(sys.argv[2]))
