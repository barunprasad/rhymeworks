"""Writer bake-off: same brief → each local model → bilingual song + storyboard JSON.

Measures wall time, tokens/sec, schema validity, line-skeleton parity (EN/HI) and
rough syllable fit. Outputs land in spikes/results/writer/<model>.json for review.

Usage: python bakeoff.py qwen3:30b gemma4:26b gpt-oss:20b
"""

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434/api/chat"
OUT = Path(__file__).resolve().parent.parent / "results" / "writer"

BRIEF = {
    "show": "Pip & Paro — Pip is a small curious robot, Paro is a parrot who repeats everything",
    "topic": "Counting from 1 to 5 with fruits",
    "learning_goal": "Count objects 1-5 and say the number words",
    "age_band": "2-4",
    "duration_sec": 75,
    "tempo_bpm": 100,
    "repetition_level": "high",
    "call_and_response": "Pip sings a line, Paro repeats the key word",
}

ACTIONS = ["enter", "exit", "bounce", "wave", "point", "jump", "sing", "look", "idle", "clap"]

SCHEMA = {
    "type": "object",
    "required": ["title_en", "title_hi", "sections", "shots"],
    "properties": {
        "title_en": {"type": "string"},
        "title_hi": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "kind", "lines"],
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["intro", "verse", "chorus", "bridge", "outro"]},
                    "lines": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["id", "singer", "syllables", "en", "hi"],
                            "properties": {
                                "id": {"type": "string"},
                                "singer": {"type": "string", "enum": ["pip", "paro", "both"]},
                                "syllables": {"type": "integer"},
                                "en": {"type": "string"},
                                "hi": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
        "shots": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["line_ids", "background", "characters", "camera"],
                "properties": {
                    "line_ids": {"type": "array", "items": {"type": "string"}},
                    "background": {"type": "string"},
                    "characters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["id", "action"],
                            "properties": {
                                "id": {"type": "string", "enum": ["pip", "paro"]},
                                "action": {"type": "string", "enum": ACTIONS},
                            },
                        },
                    },
                    "props": {"type": "array", "items": {"type": "string"}},
                    "camera": {"type": "string", "enum": ["static", "zoom_in", "zoom_out", "pan_left", "pan_right"]},
                    "on_screen_text": {"type": "string"},
                },
            },
        },
    },
}

SYSTEM = """You are the head writer of an original preschool music show.
Write ONE song that teaches the learning goal, plus a storyboard.
Rules:
- English and Hindi versions share the SAME sections and line ids. Hindi is written natively in Devanagari
  (natural, singable Hindi a parent would sing — not a word-for-word translation), with a similar syllable
  count to the English line so both fit the same melody.
- 'syllables' = target sung syllables for that line (aim 5-9 for toddlers).
- Simple words, lots of repetition, a catchy chorus repeated at least twice, call-and-response between
  Pip and Paro. Nothing scary. No brand names or existing characters.
- Storyboard shots reference line ids and only use the allowed actions and cameras.
Return only JSON matching the schema."""


def en_syllables(text: str) -> int:
    words = re.findall(r"[a-zA-Z']+", text.lower())
    total = 0
    for w in words:
        groups = re.findall(r"[aeiouy]+", w)
        n = len(groups) - (1 if w.endswith("e") and len(groups) > 1 and not w.endswith("le") else 0)
        total += max(1, n)
    return total


def hi_syllables(text: str) -> int:
    # Rough akshara count: independent vowels + consonants not followed by virama.
    consonants = re.findall(r"[क-हक़-य़](?!्)", text)
    vowels = re.findall(r"[ऄ-औ]", text)
    return len(consonants) + len(vowels)


def run(model: str) -> dict:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Brief:\n" + json.dumps(BRIEF, ensure_ascii=False, indent=2)},
        ],
        "format": SCHEMA,
        "stream": False,
        "keep_alive": 0,
        # Reasoning off where the model allows it (qwen3 burned 82k tokens thinking and never answered);
        # gpt-oss can't disable reasoning, only lower it.
        "think": "low" if model.startswith("gpt-oss") else False,
        "options": {"temperature": 0.7, "num_ctx": 16384, "num_predict": 12000},
    }
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=1800) as r:
        resp = json.load(r)
    wall = time.time() - t0

    raw = resp["message"]["content"]
    report = {
        "model": model,
        "wall_sec": round(wall, 1),
        "eval_tokens": resp.get("eval_count"),
        "tok_per_sec": round(resp["eval_count"] / (resp["eval_duration"] / 1e9), 1) if resp.get("eval_duration") else None,
        "load_sec": round(resp.get("load_duration", 0) / 1e9, 1),
    }
    try:
        song = json.loads(raw)
    except json.JSONDecodeError as e:
        report.update(valid_json=False, error=str(e), raw=raw[:2000])
        return report

    lines = [ln for s in song.get("sections", []) for ln in s.get("lines", [])]
    line_ids = {ln["id"] for ln in lines}
    shot_ids = {i for sh in song.get("shots", []) for i in sh.get("line_ids", [])}
    fit = []
    for ln in lines:
        e, h, t = en_syllables(ln["en"]), hi_syllables(ln["hi"]), ln["syllables"]
        fit.append({"id": ln["id"], "target": t, "en": e, "hi": h})
    report.update(
        valid_json=True,
        sections=len(song.get("sections", [])),
        lines=len(lines),
        empty_hi=sum(1 for ln in lines if not re.search(r"[ऀ-ॿ]", ln["hi"])),
        shots=len(song.get("shots", [])),
        unknown_shot_line_ids=sorted(shot_ids - line_ids),
        uncovered_lines=sorted(line_ids - shot_ids),
        mean_abs_syllable_gap_en=round(sum(abs(f["en"] - f["target"]) for f in fit) / max(1, len(fit)), 2),
        mean_abs_syllable_gap_hi=round(sum(abs(f["hi"] - f["target"]) for f in fit) / max(1, len(fit)), 2),
        mean_abs_gap_en_vs_hi=round(sum(abs(f["en"] - f["hi"]) for f in fit) / max(1, len(fit)), 2),
        song=song,
    )
    return report


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for model in sys.argv[1:]:
        print(f"→ {model} ...", flush=True)
        rep = run(model)
        (OUT / f"{model.replace(':', '_')}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2))
        summary = {k: v for k, v in rep.items() if k not in ("song", "raw")}
        print(json.dumps(summary, ensure_ascii=False), flush=True)
