"""Shot list drafter: lyric lines + the asset registry → keyframe and motion prompts for every shot whose prompts are empty.

  kidzone draft <episode.toml> [--all]      (--all redrafts every shot, not only the empty ones)

Runs the local writer LLM (Ollama, unloaded right after). It follows the production rules learned on Wheels on the Bus,
and only writes through studio.shotlist, so every result is validated against the registry before it is saved.
"""

import json
import re
import tomllib
from pathlib import Path

from . import pixar
from .core import chat_json, log
from . import paths
from .studio import shotlist

RULES = """You plan shots for a Pixar-style 3D animated kids' song video. One shot = one lyric line (about 4-5 s).
Write for each shot:
- scene: one scene id from the list (the background plate). Vary scenes so the video travels, but keep runs of 2-4 shots in one place.
- key: the KEYFRAME prompt (an image model draws the first frame). Name characters ONLY with their tokens like {gopu} (write {Gopu} at
  the start of a sentence). Say where each character is, their pose and the camera framing (wide / medium / close-up). Mention ONLY
  the characters in this shot; at most 3 characters; say "Alone in the frame." for single-character shots.
- motion: the MOTION prompt (a video model animates from the keyframe). Plain words, no tokens except {keep:<prop id>} for vehicles.
  Characters must MOVE THROUGH the scene (walk, run, turn, point, travel), each doing something different, plus a camera move
  (pan, track, push in, crane). Never only "swaying in place".
- feel: the emotion the line carries, as a short phrase the audience must SEE on faces and bodies (e.g. "quiet devotion, eyes
  shining with love", "joyful wonder", "trusting surrender, a calm smile", "playful delight"). Every shot with characters has one.
- sing: true only when a character sings this line to camera (close/medium shot, one character, mouth visible). Use it sparingly,
  for a few key lines (at most 1 in 5 shots); everywhere else the characters do NOT sing: they act out the meaning and show the
  feeling (devotional songs: mostly feelings, folded hands, offering flowers, gazing at the deity, not mouthing the words).
- end: "same" when characters are seated or must stay put (pins the last frame to the first), otherwise "".
Hard rules: keep vehicles in the mid-distance, never driving straight at the camera; never write "bouncing", "dancing" or "springing"
for vehicles; seated characters sit on seats that face the camera; no text, letters or signs in images; no extra people.
Hindi lyrics: understand the meaning and stage it, but write the prompts in English. Devotional songs: gentle, joyful, respectful."""

SCHEMA = {
    "type": "object",
    "properties": {"shots": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "scene": {"type": "string"}, "key": {"type": "string"}, "motion": {"type": "string"},
                       "feel": {"type": "string"}, "sing": {"type": "boolean"}, "end": {"type": "string"}},
        "required": ["id", "scene", "key", "motion", "feel", "sing", "end"]}}},
    "required": ["shots"],
}


def _catalogue() -> str:
    reg = pixar._registry()
    cast = "\n".join(f"- {{{k}}}: {v['ref']}" + (" (person)" if v.get("person") else "") for k, v in reg.get("cast", {}).items())
    props = "\n".join(f"- {{{k}}}: {v['ref']}" for k, v in reg.get("props", {}).items())
    scenes = ", ".join(reg.get("scenes", {}))
    return f"CHARACTERS (tokens):\n{cast}\nPROPS (tokens):\n{props}\nSCENES: {scenes}"


def _clean_key(text: str, things: dict, variables: dict) -> str:
    """Invented tokens → plain words (the image model then just reads them)."""
    return pixar.TOKEN.sub(lambda m: m.group(0) if m.group(1).lower() in things or m.group(1).lower() in variables
                           else m.group(1).replace("_", " "), text)


def _clean_motion(text: str, things: dict, variables: dict) -> str:
    """Motion prompts take plain words: {gopu} → "the boy in the orange kurta"."""
    def sub(m):
        tid = m.group(1)
        if tid.startswith("keep:"):
            return m.group(0) if "keep" in things.get(tid[5:], {}) else ""
        if tid in variables:
            return m.group(0)
        return things[tid.lower()]["ref"] if tid.lower() in things else tid.replace("_", " ")
    out = re.sub(r"\{([A-Za-z_:]+)(?:\|[^}]*)?\}", sub, text)
    out = re.sub(r"\b([Tt])he the\b", r"\1he", out)        # "the {bus}" → "the the painted bus" → "the painted bus"
    out = re.sub(r"\b([Aa]n?) the\b", "the", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out[:1].upper() + out[1:]


def things() -> dict:
    reg = pixar._registry()
    return {**reg.get("cast", {}), **reg.get("props", {})}


def draft(spec: Path, redraft_all: bool = False, chat=chat_json) -> list[str]:
    data = shotlist.read(spec)
    todo = [s for s in data["shots"] if redraft_all or not (s["key"] or "").strip() or not (s["motion"] or "").strip()]
    if not todo:
        log("draft", "every shot already has prompts")
        return []
    ep = data["episode"]
    lines = "\n".join(f"{s['id']}: {s['lyric'] or '(instrumental)'}" + ("" if s in todo else f"   [already planned: {s['key'][:120]}]")
                      for s in data["shots"])
    user = (f"Song: {ep.get('title')} (language: {ep.get('lang')}).\n{_catalogue()}\n"
            f"[vars] you may use as tokens too: {', '.join('{' + v + '}' for v in data['vars']) or 'none'}\n\n"
            f"LYRIC LINES:\n{lines}\n\nReturn shots for these ids only: {', '.join(s['id'] for s in todo)}.")
    log("draft", f"asking the writer model for {len(todo)} shots …")
    out = chat(RULES, user, SCHEMA, temperature=0.6)
    reg = pixar._registry()
    things = {**reg.get("cast", {}), **reg.get("props", {})}
    by_id = {s["id"]: s for s in out.get("shots", [])}

    clean_key = lambda t: _clean_key(t, things, data["vars"])
    clean_motion = lambda t: _clean_motion(t, things, data["vars"])

    done = []
    for s in todo:
        d = by_id.get(s["id"])
        if not d:
            log("draft", f"{s['id']}: no draft returned, left empty")
            continue
        fields = {"key": clean_key(d["key"]), "motion": clean_motion(d["motion"]), "sing": bool(d.get("sing")),
                  "feel": (d.get("feel") or "").strip() or None,
                  "end": "same" if d.get("end") == "same" else None,
                  "scene": d["scene"] if d.get("scene") in reg["scenes"] else s["scene"]}
        try:
            shotlist.update(spec, s["id"], fields)
        except shotlist.SpecError as e:   # never fail the whole draft for one shot: leave it empty and say why
            log("draft", f"{s['id']}: draft refused ({e}); left for you to write")
            continue
        done.append(s["id"])
        print(f"key {s['id']}", flush=True)   # progress line for the studio worker
    log("draft", f"drafted {len(done)} shots")
    return done


def main(args) -> None:
    spec = paths.find_spec(args.spec)
    tomllib.loads(spec.read_text())
    draft(spec, args.all)
    print(json.dumps({"ok": True}))
