"""Review decisions per episode, stored as a file next to episode.toml: episodes/<slug>/review.toml.

  [keys.s05]
  decision = "approved"          # approved | redo
  at = "2026-11-04T10:12:00"
  file_mtime = 1793731234.5      # the output the decision was about; a newer file makes the decision stale
  note = "monkey has no moustache"
"""

import datetime as dt
import json
import tomllib
from pathlib import Path

STAGES = ("keys", "clips")


def path(ep_dir: Path) -> Path:
    return ep_dir / "review.toml"


def load(ep_dir: Path) -> dict:
    p = path(ep_dir)
    data = tomllib.loads(p.read_text()) if p.exists() else {}
    return {st: data.get(st, {}) for st in STAGES}


def save(ep_dir: Path, data: dict) -> None:
    lines = ["# Review decisions made in the Rhymeworks studio (written by the app; safe to edit by hand).", ""]
    for st in STAGES:
        for shot in sorted(data.get(st, {})):
            d = data[st][shot]
            lines.append(f"[{st}.{shot}]")
            for k in ("decision", "at", "note"):
                if d.get(k) is not None:
                    lines.append(f"{k} = {json.dumps(d[k])}")   # JSON strings are valid TOML basic strings
            if d.get("file_mtime") is not None:
                lines.append(f"file_mtime = {float(d['file_mtime'])}")
            lines.append("")
    path(ep_dir).write_text("\n".join(lines))


def decide(ep_dir: Path, stage: str, shot: str, decision: str | None, file_mtime: float | None, note: str = "") -> dict:
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}")
    data = load(ep_dir)
    if decision is None:
        data[stage].pop(shot, None)
    else:
        if decision not in ("approved", "redo"):
            raise ValueError("decision must be approved | redo")
        data[stage][shot] = {"decision": decision, "at": dt.datetime.now().isoformat(timespec="seconds"),
                             "file_mtime": file_mtime, "note": note or None}
    save(ep_dir, data)
    return data


def status(decision: dict | None, file_mtime: float | None) -> str:
    """missing | to_review | approved | redo — an approval of an older version of the file doesn't count."""
    if file_mtime is None:
        return "redo" if decision and decision.get("decision") == "redo" else "missing"
    if not decision:
        return "to_review"
    if decision.get("file_mtime") is not None and abs(decision["file_mtime"] - file_mtime) > 1e-3:
        return "to_review"
    return decision["decision"]
