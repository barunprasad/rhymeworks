"""Song stage: storyboard lines → ACE-Step takes per language → intelligibility scores → gate → chosen take.

ACE-Step runs as a local API server that is started for this stage only and stopped afterwards
(it holds ~19 GB). LM is pinned to the 1.7B model and the server runs offline.
"""

import json
import subprocess
import time
import urllib.request
from pathlib import Path

from .. import gates
from ..core import ACE_DIR, AUDIO_ENV, OFFLINE, Episode, log, read_json, run_tool, wait_ollama_unloaded, write_json
from ..models import EpisodeBrief, Storyboard

API = "http://127.0.0.1:8001"
TAGS = {"intro": "Intro", "verse": "Verse", "chorus": "Chorus", "bridge": "Bridge", "outro": "Outro", "interlude": "Instrumental"}
TAKES = {"en": 3, "hi": 4}


def lyrics_text(sb: Storyboard, lang: str) -> str:
    blocks = []
    for sec in sb.sections:
        body = "\n".join(getattr(ln, lang) for ln in sec.lines)
        blocks.append(f"[{TAGS[sec.kind]}]" + (f"\n{body}" if body else ""))
    return "\n\n".join(blocks)


def _post(path: str, payload: dict, timeout: float = 60) -> dict:
    req = urllib.request.Request(API + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.load(r)
    if body.get("code") != 200:
        raise RuntimeError(body)
    return body["data"]


class AceServer:
    def __enter__(self):
        wait_ollama_unloaded()
        env = {**OFFLINE, "ACESTEP_LM_BACKEND": "mlx", "ACESTEP_LM_MODEL_PATH": "acestep-5Hz-lm-1.7B"}
        self.logf = open(ACE_DIR / "kidzone_server.log", "w")
        self.proc = subprocess.Popen(["uv", "run", "acestep-api", "--host", "127.0.0.1", "--port", "8001"], cwd=ACE_DIR, env=env, stdout=self.logf, stderr=subprocess.STDOUT)
        for _ in range(180):
            try:
                urllib.request.urlopen(API + "/health", timeout=2)
                return self
            except OSError:
                if self.proc.poll() is not None:
                    raise RuntimeError("ACE-Step server exited; see kidzone_server.log")
                time.sleep(1)
        raise RuntimeError("ACE-Step server did not start")

    def __exit__(self, *_):
        self.proc.terminate()
        try:
            self.proc.wait(20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.logf.close()


def generate(out_dir: Path, lang: str, lyrics: str, style: str, bpm: int, duration: float, takes: int, key: str | None = None) -> list[str]:
    payload = {
        "prompt": style, "lyrics": lyrics, "vocal_language": lang, "thinking": True, "use_cot_language": False,
        "bpm": bpm, "audio_duration": duration, "batch_size": takes, "audio_format": "wav",
    }
    if key:
        payload["key_scale"] = key
    task = _post("/release_task", payload)
    while True:
        time.sleep(3)
        res = _post("/query_result", {"task_id_list": [task["task_id"]]})[0]
        if res["status"] in (1, 2):
            break
    if res["status"] == 2:
        raise RuntimeError(f"ACE-Step failed: {res.get('result')}")
    files = []
    for n, item in enumerate(json.loads(res["result"])):
        dest = out_dir / f"{lang}_{n}.wav"
        urllib.request.urlretrieve(API + item["file"], dest)
        files.append(dest.name)
    return files


def add_kid_voices(out_dir: Path, brief: EpisodeBrief, scores: dict) -> dict:
    """Takes sing lower than the target (ACE-Step only partly follows "child singer") → add 'kid voice'
    versions of the three clearest: pitch + formants raised together, timing unchanged (lip-sync stays exact)."""
    import math
    import subprocess

    from ..core import TOOLS

    target = brief.voice_pitch_hz
    for lang in brief.languages:
        originals = sorted((k for k, v in scores.items() if k.startswith(f"{lang}_") and not v.get("kid_from")),
                           key=lambda k: scores[k].get("cer_whisper_deloop", scores[k].get("wer_whisper", 9)))
        next_idx = len([k for k in scores if k.startswith(f"{lang}_")])
        for src in originals[:3]:
            f0 = scores[src].get("f0_median_hz")
            if not f0 or f0 >= 0.9 * target or any(v.get("kid_from") == src for v in scores.values()):
                continue
            semis = round(min(5.0, max(1.0, 12 * math.log2(target / f0))) * 2) / 2
            dst = f"{lang}_{next_idx}.wav"
            subprocess.run(["python3", str(TOOLS / "kid_voice.py"), str(out_dir / src), str(out_dir / dst), str(semis)], check=True, capture_output=True)
            scores[dst] = {**scores[src], "take": dst, "kid_from": src, "kid_semitones": semis, "f0_median_hz": round(f0 * 2 ** (semis / 12), 1)}
            next_idx += 1
            log("song", f"kid voice {dst} ← {src} (+{semis} st, ≈{scores[dst]['f0_median_hz']:.0f} Hz)")
    write_json(out_dir / "scores.json", list(scores.values()))
    return scores


def run(ep: Episode, brief: EpisodeBrief, show: dict, sb: Storyboard) -> dict[str, str]:
    """Returns {lang: chosen take filename (in songs/)}."""
    out_dir = ep.path("songs")
    chosen_file = out_dir / "chosen.json"
    if chosen_file.exists():
        return read_json(chosen_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    lyrics = {lang: lyrics_text(sb, lang) for lang in brief.languages}
    write_json(out_dir / "lyrics.json", lyrics)
    n_lines = len(sb.lines())
    duration = float(min(180, max(40, round(n_lines * 4.4 + 8), brief.duration_sec)))
    style = brief.song_style or f"{show['song_style']}, {brief.mood}"
    bpm = brief.bpm or sb.bpm

    if not all((out_dir / f"{lang}_0.wav").exists() for lang in brief.languages):
        with AceServer():
            for lang in brief.languages:
                if (out_dir / f"{lang}_0.wav").exists():
                    continue
                t0 = time.time()
                takes = TAKES[lang] + (2 if brief.voice_pitch_hz else 0)
                files = generate(out_dir, lang, lyrics[lang], style, bpm, duration, takes, brief.key)
                log("song", f"{lang}: {len(files)} takes × {duration:.0f}s in {time.time() - t0:.0f}s")

    if not (out_dir / "scores.json").exists():
        log("song", "scoring takes (Whisper/Parakeet) …")
        run_tool(AUDIO_ENV, "score_songs.py", str(out_dir))
    scores = {s["take"]: s for s in read_json(out_dir / "scores.json")}
    if brief.voice_pitch_hz:
        scores = add_kid_voices(out_dir, brief, scores)

    chosen = {}
    for lang in brief.languages:
        takes = sorted(k for k in scores if k.startswith(f"{lang}_"))
        clarity = (lambda s: min(s.get("wer_parakeet", 9), s["wer_whisper"])) if lang == "en" else (lambda s: s["cer_whisper_deloop"])
        target = brief.voice_pitch_hz

        def metric(sc: dict) -> float:
            # Lower is better: clarity error, plus a penalty for missing the target voice pitch (if set).
            m = clarity(sc)
            if target and sc.get("f0_median_hz"):
                m += abs(sc["f0_median_hz"] - target) / 250
            return m

        best = min(takes, key=lambda k: metric(scores[k]))

        def describe(sc: dict) -> str:
            txt = f"{'WER' if lang == 'en' else 'CER'} {clarity(sc):.2f}"
            f0 = sc.get("f0_median_hz")
            if f0:
                kind = "child-like" if f0 >= 330 else "high adult" if f0 >= 240 else "adult"
                txt += f" · voice ≈ {f0:.0f} Hz ({kind})"
            return txt

        cands = [
            {"id": k, "label": (f"Kid voice ✨ — from take {scores[k]['kid_from'].split('_')[1].split('.')[0]}" if scores[k].get("kid_from")
                                else f"{lang.upper()} take {k.split('_')[1].split('.')[0]}"), "audio": f"songs/{k}",
             "score_text": describe(scores[k]), "best": k == best}
            for k in takes
        ]
        chosen[lang] = gates.choose(ep, f"song_{lang}", f"Pick the {lang.upper()} song take",
                                    f"{sb.title.en} — listen and choose the take you like best.", cands, brief.autopilot)
    write_json(chosen_file, chosen)
    return chosen
