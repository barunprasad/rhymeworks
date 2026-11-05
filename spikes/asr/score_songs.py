"""Score song takes for intelligibility: transcribe each take and compare with the lyrics.

EN → WER (Whisper + Parakeet). HI → CER on normalized Devanagari (Whisper), for both the
Devanagari-prompted and romanized-prompted takes (both are sung Hindi).
Usage (audio env): python score_songs.py
Writes spikes/results/song/scores.json
"""

import json
import sys
import re
import time
import unicodedata
from pathlib import Path

import jiwer
import mlx_whisper

SONG = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "results" / "song"
WHISPER = "mlx-community/whisper-large-v3-turbo"


def lyric_text(raw: str) -> str:
    return "\n".join(ln for ln in raw.splitlines() if not ln.strip().startswith("["))


def norm_en(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_hi(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.replace("़", "")  # nukta: ज़ ~ ज
    s = re.sub(r"[ँं]", "ं", s)  # chandrabindu ~ anusvara
    s = re.sub(r"[^ऀ-ॿ ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def whisper(path: Path, lang: str) -> str:
    # Whisper loops on sung audio ("पार पार पार…") when it conditions on its own previous text.
    return mlx_whisper.transcribe(
        str(path),
        path_or_hf_repo=WHISPER,
        language=lang,
        condition_on_previous_text=False,
        compression_ratio_threshold=1.8,
        no_speech_threshold=0.6,
    )["text"]


def dedupe_loops(s: str) -> str:
    # Collapse any token repeated 4+ times in a row (residual hallucination loops) to one.
    s = re.sub(r"(\S)\1{5,}", r"\1", s)
    return re.sub(r"\b(\S+)(\s+\1\b){3,}", r"\1", s)


def parakeet(path: Path) -> str | None:
    try:
        from parakeet_mlx import from_pretrained
    except ImportError:
        return None
    model = getattr(parakeet, "_m", None) or from_pretrained("mlx-community/parakeet-tdt-0.6b-v2")
    parakeet._m = model
    return model.transcribe(str(path)).text


def main() -> None:
    lyrics = json.loads((SONG / "lyrics.json").read_text())
    ref_en = norm_en(lyric_text(lyrics["en"]))
    ref_hi = norm_hi(lyric_text(lyrics["hi"]))
    scores = []
    for wav in sorted(SONG.glob("*_[0-9].*")):
        variant = wav.stem.rsplit("_", 1)[0]
        t0 = time.time()
        if variant == "en":
            hyp = whisper(wav, "en")
            row = {"take": wav.name, "wer_whisper": round(jiwer.wer(ref_en, norm_en(hyp)), 3), "whisper": hyp}
            pk = parakeet(wav)
            if pk is not None:
                row.update(wer_parakeet=round(jiwer.wer(ref_en, norm_en(pk)), 3), parakeet=pk)
        else:
            hyp = whisper(wav, "hi")
            row = {
                "take": wav.name,
                "cer_whisper": round(jiwer.cer(ref_hi, norm_hi(hyp)), 3),
                "cer_whisper_deloop": round(jiwer.cer(ref_hi, norm_hi(dedupe_loops(hyp))), 3),
                "whisper": hyp,
            }
        row["sec"] = round(time.time() - t0, 1)
        scores.append(row)
        print(json.dumps({k: v for k, v in row.items() if k not in ("whisper", "parakeet")}), flush=True)
    (SONG / "scores.json").write_text(json.dumps(scores, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
