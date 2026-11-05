"""Your projects (channels) in projects.toml, edited format-preserving: comments and layout stay as written, and
every write is checked by parsing the result before it reaches disk.

[project.<id>]
name = "My channel"
tagline = "Songs for kids"             # optional
icon = "assets/cast/tara.jpg"          # optional, relative to the content folder; also used on thumbnails
languages = ["en", "hi"]

[project.<id>.subscribe]               # optional: the closing line of upload descriptions, per language
en = "…"
[project.<id>.playlists]               # optional: the playlist suggested in the upload checklist, per language
en = "…"
"""

import json
import re
import tomllib

from .. import paths
from .specedit import set_table_field

LANGS = ("en", "hi")
EXTRA = ("subscribe", "playlists")


class ProjectError(ValueError):
    pass


def _text() -> str:
    try:
        return paths.PROJECTS.read_text()
    except FileNotFoundError:
        return "# Projects (channels) in the Rhymeworks studio. Episodes join one with [episode] project = \"<id>\".\n"


def _write(text: str) -> None:
    data = tomllib.loads(text)          # never write a broken file
    if not isinstance(data.get("project"), dict):
        raise ProjectError("projects.toml must keep its [project.<id>] tables")
    paths.PROJECTS.parent.mkdir(parents=True, exist_ok=True)
    paths.PROJECTS.write_text(text)


def all_projects() -> dict[str, dict]:
    return paths.projects()


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "project"


def create(name: str, languages: list[str] | None = None) -> str:
    name = name.strip()
    if not 1 <= len(name) <= 60:
        raise ProjectError("give the project a name (up to 60 characters)")
    langs = _langs(languages or ["en"])
    have = all_projects()
    pid, n = slug(name), 2
    while pid in have:
        pid, n = f"{slug(name)}-{n}", n + 1
    block = f"[project.{pid}]\nname = {json.dumps(name, ensure_ascii=False)}\nlanguages = {json.dumps(langs)}\n"
    _write(_text().rstrip("\n") + "\n\n" + block)
    return pid


def _langs(v: list[str]) -> list[str]:
    langs = [x for x in LANGS if x in set(v)]
    if not langs:
        raise ProjectError("pick at least one language")
    return langs


def _table_span(text: str, table: str) -> tuple[int, int] | None:
    m = re.search(rf"^\[{re.escape(table)}\]\s*(#.*)?$", text, re.M)
    if not m:
        return None
    nxt = re.search(r"^\[", text[m.end():], re.M)
    return m.start(), m.end() + (nxt.start() if nxt else len(text) - m.end())


def _ensure_table(pid: str, sub: str) -> None:
    """Add an empty [project.<id>.<sub>] right after the project's own block (and its other sub-tables)."""
    text = _text()
    table = f"project.{pid}.{sub}"
    if _table_span(text, table):
        return
    end = _table_span(text, f"project.{pid}")[1]
    for other in EXTRA:
        span = _table_span(text, f"project.{pid}.{other}")
        if span:
            end = max(end, span[1])
    head, tail = text[:end].rstrip("\n"), text[end:].lstrip("\n")
    _write(head + f"\n\n[{table}]\n" + ("\n" + tail if tail else ""))


def update(pid: str, fields: dict) -> dict:
    """Change name / tagline / icon / languages and the per-language subscribe and playlists text.
    A value of "" or None removes an optional field."""
    if pid not in all_projects():
        raise ProjectError(f"no project {pid}")
    table = f"project.{pid}"
    for key, value in fields.items():
        if key == "name":
            value = (value or "").strip()
            if not 1 <= len(value) <= 60:
                raise ProjectError("the name can't be empty (up to 60 characters)")
            set_table_field(paths.PROJECTS, table, "name", value)
        elif key == "tagline":
            set_table_field(paths.PROJECTS, table, "tagline", (value or "").strip()[:100] or None)
        elif key == "icon":
            value = (value or "").strip() or None
            if value and not (paths.HOME / value).is_file():
                raise ProjectError(f"no picture at {value}")
            set_table_field(paths.PROJECTS, table, "icon", value)
        elif key == "languages":
            set_table_field(paths.PROJECTS, table, "languages", _langs(value or []))
        elif key in EXTRA:
            for lang, text in (value or {}).items():
                if lang not in LANGS:
                    raise ProjectError(f"unknown language {lang}")
                text = (text or "").strip()
                if text:
                    _ensure_table(pid, key)
                    set_table_field(paths.PROJECTS, f"{table}.{key}", lang, text[:300])
                elif _table_span(_text(), f"{table}.{key}"):
                    set_table_field(paths.PROJECTS, f"{table}.{key}", lang, None)
        else:
            raise ProjectError(f"unknown field {key}")
    return all_projects()[pid]
