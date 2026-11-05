"""Small, format-preserving edits to episode.toml (the file stays hand-readable; comments and layout are kept)."""

import re
import tomllib
from pathlib import Path

SEED_STEP = 1000


def _shot_block(text: str, shot: str) -> tuple[int, int]:
    """(start, end) character span of the [[shot]] block whose id is `shot`."""
    starts = [m.start() for m in re.finditer(r"^\[\[shot\]\]\s*$", text, re.M)] + [len(text)]
    for a, b in zip(starts, starts[1:]):
        if re.search(rf'^id\s*=\s*"{re.escape(shot)}"\s*$', text[a:b], re.M):
            return a, b
    raise KeyError(f"no [[shot]] with id {shot}")


def bump_seed(spec: Path, shot: str, field: str, default: int) -> int:
    """Give `shot` a new `field` (seed | clip_seed) so a redo renders a different take. Returns the new seed."""
    text = spec.read_text()
    a, b = _shot_block(text, shot)
    block = text[a:b]
    m = re.search(rf"^{field}\s*=\s*(\d+)([^\n]*)$", block, re.M)
    if m:
        new = int(m.group(1)) + SEED_STEP
        block = block[:m.start()] + f"{field} = {new}{m.group(2)}" + block[m.end():]   # keeps a trailing comment
    else:   # add the line right after the shot's id
        new = default + SEED_STEP
        idm = re.search(r"^id\s*=.*$", block, re.M)
        block = block[:idm.end()] + f"\n{field} = {new}" + block[idm.end():]
    out = text[:a] + block + text[b:]
    tomllib.loads(out)   # never write a broken spec
    spec.write_text(out)
    return new


def set_table_field(spec: Path, table: str, field: str, value: str | int | float | bool | None, comment: str = "") -> None:
    """Set (or remove, value None) a `field` in a [table] of episode.toml, keeping everything else as written."""
    import json
    text = spec.read_text()
    m = re.search(rf"^\[{re.escape(table)}\]\s*(#.*)?$", text, re.M)
    if not m:
        raise KeyError(f"no [{table}] table")
    nxt = re.search(r"^\[", text[m.end():], re.M)
    a, b = m.end(), m.end() + (nxt.start() if nxt else len(text) - m.end())
    body = text[a:b]
    fm = re.search(rf"^{re.escape(field)}\s*=.*$\n?", body, re.M)
    line = "" if value is None else f"{field} = {json.dumps(value, ensure_ascii=False)}" + (f"   # {comment}" if comment else "") + "\n"
    if fm:
        body = body[:fm.start()] + line + body[fm.end():]
    elif line:
        stripped = body.rstrip("\n")
        body = stripped + "\n" + line + body[len(stripped) + 1:] if stripped else "\n" + line + body.lstrip("\n")
    out = text[:a] + body + text[b:]
    tomllib.loads(out)
    spec.write_text(out)
