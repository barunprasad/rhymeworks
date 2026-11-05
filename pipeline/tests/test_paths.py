"""Content folder: a fresh one is created from templates/home (with the example episode) and is usable; migrate never targets the repo."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from kidzone import paths

CHECK = """
from kidzone import paths, pixar
paths.ensure_home()
assert paths.HOME_SOURCE == "RHYMEWORKS_HOME", paths.HOME_SOURCE
assert paths.REGISTRY.exists() and paths.PROJECTS.exists() and paths.EPISODES.is_dir()
reg = pixar._registry()   # the example: Tara, Biscuit, the red kite, the hilltop
assert set(reg["cast"]) == {"tara", "biscuit"} and set(reg["props"]) == {"red_kite"} and set(reg["scenes"]) == {"kite_hill"}
ep = pixar.load(paths.find_spec("little-red-kite"))   # the example episode plans without a song yet
assert [s.id for s in ep.shots] == ["s00", "s01", "s02", "s03"] and all(s.key.images[1:] for s in ep.shots)
print(paths.HOME)
"""


def test_fresh_content_folder(tmp_path):
    home = tmp_path / "Rhymeworks"
    out = subprocess.run([sys.executable, "-c", CHECK], env={**os.environ, "RHYMEWORKS_HOME": str(home)},
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert Path(out.stdout.strip()) == home.resolve()
    assert not (home / "episodes" / ".gitkeep").exists()


def test_migrate_refuses_the_repo():
    with pytest.raises(ValueError):
        paths.migrate(paths.CODE / "content", dry=True)


def test_rel_is_short():
    assert paths.rel(paths.CODE / "pipeline" / "x.py") == "pipeline/x.py"
