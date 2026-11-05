"""Align known lyrics to a song take (line + word level) and derive a mouth track.

- stable-ts `align` with the known lyrics (no transcription) → per-line / per-word times.
- Loudness envelope (RMS of the given audio, 30 fps) → 4 mouth states (0 closed … 3 wide),
  gated to aligned sung regions so the mouth stays shut during instrumental gaps.
Usage (audio env): python align_and_mouth.py <take.wav> <en|hi> [lyrics_key]
Writes spikes/results/align/<take>.json
"""

import json
import sys
import time
from pathlib import Path

import librosa
import numpy as np
import stable_whisper

ROOT = Path(__file__).resolve().parent.parent
FPS = 30


def lyric_lines(raw: str) -> list[str]:
    return [ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("[")]


def mouth_track(audio: Path, sung: list[tuple[float, float]]) -> list[int]:
    y, sr = librosa.load(str(audio), sr=22050, mono=True)
    hop = sr // FPS
    rms = librosa.feature.rms(y=y, frame_length=hop * 2, hop_length=hop)[0]
    db = librosa.amplitude_to_db(rms, ref=np.max)
    lo, hi = np.percentile(db, 30), np.percentile(db, 98)
    level = np.clip((db - lo) / max(1e-6, hi - lo), 0, 1)
    states = np.digitize(level, [0.25, 0.5, 0.75])  # 0..3
    t = np.arange(len(states)) / FPS
    in_sung = np.zeros(len(states), bool)
    for s, e in sung:
        in_sung |= (t >= s) & (t <= e)
    states[~in_sung] = 0
    # Hold each state ≥ 2 frames to avoid jitter.
    for i in range(1, len(states) - 1):
        if states[i] != states[i - 1] and states[i] != states[i + 1]:
            states[i] = states[i - 1]
    return states.astype(int).tolist()


def main() -> None:
    take, lang = Path(sys.argv[1]), sys.argv[2]
    key = sys.argv[3] if len(sys.argv) > 3 else lang
    lyrics_path = Path(sys.argv[4]) if len(sys.argv) > 4 else ROOT / "results" / "song" / "lyrics.json"
    out_dir = Path(sys.argv[5]) if len(sys.argv) > 5 else ROOT / "results" / "align"
    lyrics = json.loads(lyrics_path.read_text())[key]
    lines = lyric_lines(lyrics)

    t0 = time.time()
    # MLX loader reuses the already-cached mlx-community weights (no extra download, runs on GPU).
    model = stable_whisper.load_mlx_whisper("mlx-community/whisper-large-v3-turbo")
    result = model.align(str(take), "\n".join(lines), language=lang, original_split=True)
    align_sec = time.time() - t0

    segs = [
        {
            "text": s.text.strip(),
            "start": round(s.start, 2),
            "end": round(s.end, 2),
            "words": [{"w": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2), "p": round(w.probability, 2)} for w in s.words],
        }
        for s in result.segments
    ]
    mouth = mouth_track(take, [(s["start"], s["end"]) for s in segs])
    out = {
        "take": take.name,
        "lang": lang,
        "align_sec": round(align_sec, 1),
        "lines_expected": len(lines),
        "lines_aligned": len(segs),
        "mean_word_prob": round(float(np.mean([w["p"] for s in segs for w in s["words"]] or [0])), 3),
        "segments": segs,
        "fps": FPS,
        "mouth": mouth,
    }
    dest = out_dir / f"{take.stem}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({k: out[k] for k in ("take", "align_sec", "lines_expected", "lines_aligned", "mean_word_prob")}), flush=True)


if __name__ == "__main__":
    main()
