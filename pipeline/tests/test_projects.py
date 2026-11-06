"""Projects (channels) in projects.toml: add, edit, per-language upload text; comments survive and bad edits never reach disk."""
import tomllib

import pytest

from kidzone import paths
from kidzone.studio import projects

START = """# My channels (this comment must survive)
[project.gaana-gaadi]
name = "Gaana Gaadi"
languages = ["en", "hi"]   # both
"""


@pytest.fixture
def file(tmp_path, monkeypatch):
    p = tmp_path / "projects.toml"
    p.write_text(START)
    monkeypatch.setattr(paths, "PROJECTS", p)
    monkeypatch.setattr(paths, "HOME", tmp_path)
    return p


def test_create_and_default(file):
    pid = projects.create("Bedtime Songs", ["hi", "en"])
    assert pid == "bedtime-songs"
    assert projects.create("Bedtime Songs") == "bedtime-songs-2"
    data = tomllib.loads(file.read_text())["project"]
    assert data["bedtime-songs"] == {"name": "Bedtime Songs", "languages": ["en", "hi"]}
    assert paths.default_project() == "gaana-gaadi"          # still the first one
    assert file.read_text().startswith("# My channels (this comment must survive)")


def test_update_fields_and_upload_text(file):
    (file.parent / "assets").mkdir()
    (file.parent / "assets" / "icon.png").write_bytes(b"png")
    p = projects.update("gaana-gaadi", {"name": "Gaana Gaadi!", "tagline": "Songs", "icon": "assets/icon.png",
                                        "subscribe": {"en": "Subscribe!", "hi": "सब्सक्राइब करें"}, "playlists": {"en": "Rhymes"}})
    assert p["name"] == "Gaana Gaadi!" and p["icon"] == "assets/icon.png"
    assert p["subscribe"] == {"en": "Subscribe!", "hi": "सब्सक्राइब करें"} and p["playlists"] == {"en": "Rhymes"}
    assert "# both" in file.read_text()                       # the comment on languages is kept
    p = projects.update("gaana-gaadi", {"tagline": "", "subscribe": {"hi": ""}})
    assert "tagline" not in p and p["subscribe"] == {"en": "Subscribe!"}


def test_bad_edits_are_refused(file):
    before = file.read_text()
    for pid, fields in [("gaana-gaadi", {"name": " "}), ("gaana-gaadi", {"languages": ["fr"]}),
                        ("gaana-gaadi", {"icon": "assets/missing.png"}), ("nope", {"name": "x"}),
                        ("gaana-gaadi", {"subscribe": {"fr": "x"}}), ("gaana-gaadi", {"colour": "red"})]:
        with pytest.raises(projects.ProjectError):
            projects.update(pid, fields)
    assert file.read_text() == before


def test_intro_clip_must_be_a_video_in_home(file):
    (file.parent / "assets").mkdir()
    (file.parent / "assets" / "intro.mp4").write_bytes(b"mp4")
    (file.parent / "assets" / "icon.png").write_bytes(b"png")
    assert projects.update("gaana-gaadi", {"intro": "assets/intro.mp4"})["intro"] == "assets/intro.mp4"
    for bad in ("assets/icon.png", "assets/none.mp4"):
        with pytest.raises(projects.ProjectError):
            projects.update("gaana-gaadi", {"intro": bad})
    assert "intro" not in projects.update("gaana-gaadi", {"intro": ""})
