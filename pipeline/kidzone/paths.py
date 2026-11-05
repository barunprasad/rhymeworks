"""Where things live. Three places, never mixed:

CODE   this repository: engine, tools, web app, templates. Public; no personal content.
HOME   your content folder: episodes, characters/places/props (assets/), brand, voices, the old 2D library, projects.toml.
       Put it inside a synced folder (Google Drive for desktop, iCloud Drive, Dropbox) to see it on your other computers.
STATE  this computer only, never synced: the job queue database, logs, drafts (a draft may hold a photo reference of a
       real person) and the phone-link key. Lives in <repo>/studio/ (gitignored).

HOME is chosen by, in order:
  1. $RHYMEWORKS_HOME
  2. `home = "…"` in <repo>/rhymeworks.local.toml (gitignored; written by `kidzone home --set` / `kidzone migrate`)
  3. the legacy layout: content still inside the repo (assets/registry.toml exists there) → the repo itself
  4. ~/Rhymeworks
"""

import os
import tomllib
from pathlib import Path

CODE = Path(__file__).resolve().parents[2]
LOCAL_CONFIG = CODE / "rhymeworks.local.toml"
STATE = CODE / "studio"
TEMPLATES = CODE / "templates"
BRAND_TOOLS = CODE / "pipeline" / "tools" / "brand"   # text.swift, add_intro.sh, the Baloo 2 font (OFL)


def local_config() -> dict:
    try:
        return tomllib.loads(LOCAL_CONFIG.read_text())
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return {}


def find_home() -> tuple[Path, str]:
    """(content folder, why it was chosen)."""
    if env := os.environ.get("RHYMEWORKS_HOME"):
        return Path(env).expanduser().resolve(), "RHYMEWORKS_HOME"
    if h := local_config().get("home"):
        return Path(h).expanduser().resolve(), LOCAL_CONFIG.name
    if (CODE / "assets" / "registry.toml").exists():
        return CODE, "legacy (content inside the repo)"
    return (Path.home() / "Rhymeworks").resolve(), "default"


HOME, HOME_SOURCE = find_home()
LEGACY = HOME == CODE

EPISODES = HOME / "episodes"
ASSETS = HOME / "assets"
REGISTRY = ASSETS / "registry.toml"
BRAND = ASSETS / "brand"               # your channel's logo, icon and 4 s intro (optional)
VOICES = ASSETS / "voices.toml"
VOICE_SAMPLES = ASSETS / "voices"
LIB = HOME / "library" / "shows"       # the earlier 2D pipeline's shows
BRIEFS = HOME / "briefs"
PROJECTS = STATE / "projects.toml" if LEGACY else HOME / "projects.toml"

DRAFTS = STATE / "drafts"
LOGS = STATE / "logs"
DB = STATE / "studio.db"
LAN_KEY = STATE / "lan_key"


def projects() -> dict[str, dict]:
    """Your channels from projects.toml: {id: {name, tagline, icon, languages, subscribe, …}}."""
    try:
        return tomllib.loads(PROJECTS.read_text()).get("project", {})
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return {}


def default_project() -> str:
    """The project an episode belongs to when it doesn't say: the first one in projects.toml."""
    return next(iter(projects()), "my-channel")


def find_spec(spec: str | Path) -> Path:
    """An episode.toml from what you typed: a path (as is, or inside HOME) or just the episode's folder name."""
    p = Path(spec).expanduser()
    for c in (p, HOME / p, EPISODES / p / "episode.toml"):
        if c.is_file():
            return c.resolve()
    return p.resolve()


def rel(p: Path) -> str:
    """A short display path: relative to HOME or CODE when inside them."""
    p = Path(p).resolve()
    for base in (HOME, CODE):
        if p.is_relative_to(base):
            return str(p.relative_to(base))
    return str(p)


# ---------------------------------------------------------------- set up / move the content folder

CONTENT = ["episodes", "assets", "library", "briefs"]   # what `kidzone migrate` moves out of the repo


def ensure_home(home: Path | None = None) -> Path:
    """Create a content folder from templates/home (only the files that are missing)."""
    import shutil
    home = home or HOME
    if home == CODE:
        return home
    src = TEMPLATES / "home"
    for f in src.rglob("*"):
        dest = home / f.relative_to(src)
        if f.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        elif not dest.exists() and f.name != ".gitkeep":
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
    return home


def set_home(home: Path) -> None:
    import json
    LOCAL_CONFIG.write_text(f"# This computer's Rhymeworks settings (gitignored).\nhome = {json.dumps(str(home))}   # your content folder\n")


def migrate(to: Path, dry: bool = False) -> list[str]:
    """Move content that still lives inside the repo into `to`, then point this computer at it.
    Same disk = instant renames. Refuses to overwrite anything already in `to`."""
    import shutil
    to = to.expanduser().resolve()
    if to == CODE or to.is_relative_to(CODE):
        raise ValueError("the content folder must be outside the repository")
    moves = [(CODE / n, to / n) for n in CONTENT if (CODE / n).exists()]
    if (STATE / "projects.toml").exists():
        moves.append((STATE / "projects.toml", to / "projects.toml"))
    clash = [str(d) for _, d in moves if d.exists()]
    if clash:
        raise ValueError(f"already in {to}: {', '.join(clash)} (move or merge them by hand first)")
    done = []
    for s, d in moves:
        done.append(f"{s.relative_to(CODE)} → {d}")
        if not dry:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(s), str(d))
    if not dry:
        ensure_home(to)
        set_home(to)
    return done
