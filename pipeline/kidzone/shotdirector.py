"""Director: change an episode's shot list from a plain-words request ("less singing in the chorus, bus before the boat").

  kidzone director <episode.toml> --ask "…" [--shots s18 s19]

The local writer LLM proposes field changes and moves; nothing is written to episode.toml until you apply the proposal
in the studio (then every change goes through the validated shot-list writer). Proposal + history:
episodes/<slug>/director.json.
"""

import datetime as dt
import json
from pathlib import Path

from . import drafter, pixar
from .core import chat_json, log
from . import paths
from .studio import shotlist

FIELDS = ("key", "motion", "feel", "sing", "scene", "end", "lines")
KEY_FIELDS = ("key", "feel", "scene", "sing", "end")   # changing these makes the keyframe stale

RULES = drafter.RULES + """

You are now the DIRECTOR revising an existing shot list. The user asks for a change in plain words. Change as little as
needed to do exactly what they ask, keep everything else as it is, and keep the production rules above.
Return:
- reply: one or two plain sentences for the user saying what you propose to change, in the future tense ("I'll …"), because nothing changes until they apply it (no jargon, no ids unless useful).
- changes: one entry per shot you change, with ONLY the fields that change (leave the others out):
  key / motion (full new prompt text, same token rules as above), feel (short phrase), sing (true/false),
  scene (a scene id from the list), end ("same" or "none"), lines (how many bars/lines the shot spans, 1-4), and why (a few words).
- moves: reorder shots if asked: {"id": shot to move, "before": the shot it should come before, or "" for the end}.
Never invent shot ids. If the request is unclear or impossible, return no changes and say why in reply."""

SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "changes": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "why": {"type": "string"}, "key": {"type": "string"}, "motion": {"type": "string"},
            "feel": {"type": "string"}, "sing": {"type": "boolean"}, "scene": {"type": "string"}, "end": {"type": "string"},
            "lines": {"type": "integer"}}, "required": ["id", "why"]}},
        "moves": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "before": {"type": "string"}},
                                             "required": ["id", "before"]}},
    },
    "required": ["reply", "changes", "moves"],
}


def path(ep_dir: Path) -> Path:
    return ep_dir / "director.json"


def load(ep_dir: Path) -> dict:
    p = path(ep_dir)
    return json.loads(p.read_text()) if p.exists() else {"proposal": None, "history": []}


def _save(ep_dir: Path, data: dict) -> None:
    path(ep_dir).write_text(json.dumps(data, ensure_ascii=False, indent=1))


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def propose(spec: Path, ask: str, shots: list[str] | None = None, chat=chat_json) -> dict:
    data = shotlist.read(spec)
    ids = [s["id"] for s in data["shots"]]
    rows = []
    for s in data["shots"]:
        bits = [f"{s['id']}", f"lyric: {s['lyric'] or '(instrumental)'}", f"scene: {s['scene']}", f"lines: {s['lines'] or 1}",
                f"sing: {bool(s['sing'])}", f"feel: {s['feel'] or '-'}", f"end: {s['end'] if isinstance(s['end'], str) else ('own end key' if s['end'] else 'none')}",
                f"key: {s['key']}", f"motion: {s['motion']}"]
        rows.append(" | ".join(bits))
    focus = f"\nThe user is looking at shot(s) {', '.join(shots)}; 'this shot' means those." if shots else ""
    user = (f"Song: {data['episode'].get('title')} (language: {data['episode'].get('lang')}).\n{drafter._catalogue()}\n\n"
            f"CURRENT SHOT LIST (in order):\n" + "\n".join(rows) + f"\n{focus}\nREQUEST: {ask}")
    log("director", f"asking the writer model: {ask[:80]}")
    print("key thinking", flush=True)   # progress line for the studio worker
    out = chat(RULES, user, SCHEMA, temperature=0.4)
    things, variables = drafter.things(), data["vars"]
    reg = pixar._registry()
    changes = []
    for c in out.get("changes", []):
        if c.get("id") not in ids:
            continue
        f = {}
        for k in FIELDS:
            if k not in c or c[k] in (None, ""):
                continue
            v = c[k]
            if k == "key":
                v = drafter._clean_key(v, things, variables)
            elif k == "motion":
                v = drafter._clean_motion(v, things, variables)
            elif k == "scene" and v not in reg["scenes"]:
                continue
            elif k == "end":
                v = "same" if v == "same" else None
            elif k == "lines":
                v = max(1, min(4, int(v)))
            f[k] = v
        cur = next(s for s in data["shots"] if s["id"] == c["id"])
        f = {k: v for k, v in f.items() if (cur.get(k) or None) != (v or None) and not (k == "lines" and (cur.get("lines") or 1) == v)}
        if f:
            changes.append({"id": c["id"], "why": c.get("why", ""), "fields": f,
                            "before": {k: cur.get(k) for k in f}})
    moves = [{"id": m["id"], "before": m["before"] or None} for m in out.get("moves", [])
             if m.get("id") in ids and (not m.get("before") or m["before"] in ids) and m["id"] != m.get("before")]
    proposal = {"ask": ask, "shots": shots or [], "reply": out.get("reply", "").strip(), "changes": changes, "moves": moves,
                "created": _now(), "status": "proposed"}
    store = load(spec.parent)
    if store.get("proposal") and store["proposal"].get("status") == "proposed":
        store["history"].insert(0, {**store["proposal"], "status": "replaced"})
    store["proposal"] = proposal
    _save(spec.parent, store)
    log("director", f"{len(changes)} changes, {len(moves)} moves proposed")
    return proposal


def apply(spec: Path) -> dict:
    """Write the proposal into episode.toml (each change validated). Returns what changed and which keyframes to remake."""
    store = load(spec.parent)
    p = store.get("proposal")
    if not p or p.get("status") != "proposed":
        raise ValueError("there is no proposal to apply")
    applied, errors, remake = [], [], []
    for c in p["changes"]:
        try:
            shotlist.update(spec, c["id"], c["fields"])
            applied.append(c["id"])
            if any(k in KEY_FIELDS for k in c["fields"]):
                remake.append(c["id"])
        except (shotlist.SpecError, KeyError) as e:
            errors.append(f"{c['id']}: {e}")
    for m in p["moves"]:
        try:
            shotlist.move(spec, m["id"], m["before"])
            applied.append(m["id"])
        except (shotlist.SpecError, KeyError) as e:
            errors.append(f"move {m['id']}: {e}")
    p.update(status="applied", applied_at=_now(), errors=errors, remake=remake)
    store["history"].insert(0, p)
    store["proposal"] = None
    store["history"] = store["history"][:30]
    _save(spec.parent, store)
    return {"applied": applied, "errors": errors, "remake": remake}


def discard(spec: Path) -> None:
    store = load(spec.parent)
    if store.get("proposal"):
        store["history"].insert(0, {**store["proposal"], "status": "discarded"})
        store["proposal"] = None
        store["history"] = store["history"][:30]
        _save(spec.parent, store)


def main(args) -> None:
    propose(paths.find_spec(args.spec), args.ask, args.shots)
