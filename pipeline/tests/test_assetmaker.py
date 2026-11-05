"""New library assets: drafts never touch assets/ until saved; saving adds a valid registry entry in the right section."""
import shutil
from pathlib import Path
import tomllib

import pytest

from kidzone import assetmaker as am


@pytest.fixture
def lib(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    for sub in ("cast", "props", "scenes"):
        (assets / sub).mkdir(parents=True)
    shutil.copy(Path(__file__).parent / "fixtures" / "registry.toml", assets / "registry.toml")
    monkeypatch.setattr(am, "ASSETS", assets)
    monkeypatch.setattr(am, "REGISTRY", assets / "registry.toml")
    monkeypatch.setattr(am, "DRAFTS", tmp_path / "drafts")
    return assets


def _fake_option(did, name="cand_1234.png"):
    (am.draft_dir(did) / name).write_bytes(b"png")


def test_create_save_character(lib):
    before = (lib / "registry.toml").read_text()
    d = am.create("cast", "Kela the Banana", "a cheerful little banana with a green stem", person=False)
    assert d["id"] == "kela_banana" and d["candidates"] == []
    _fake_option(d["id"])
    out = am.save(d["id"], "cand_1234.png", "kela_banana", ref="the little yellow banana", style="The banana keeps its orange scarf.")
    reg = tomllib.loads((lib / "registry.toml").read_text())
    assert reg["cast"]["kela_banana"] == {"file": "cast/kela_banana.png", "ref": "the little yellow banana", "style": "The banana keeps its orange scarf."}
    assert list(reg["cast"])[-1] == "kela_banana" and "cart" in reg["props"]           # inserted at the end of the cast section
    assert (lib / "cast/kela_banana.png").read_bytes() == b"png"
    assert (lib / "registry.toml").read_text().startswith(before.split("[cast.asha]")[0])   # header comments kept
    assert out["file"] == "cast/kela_banana.png" and am.drafts() == []                      # saved drafts leave the list


def test_save_scene_and_prop(lib):
    s = am.create("scenes", "Lotus pond night", "a lotus pond at night with floating lamps")
    _fake_option(s["id"])
    am.save(s["id"], "cand_1234.png", "pond_night")
    p = am.create("props", "Paper boat", "a small paper boat")
    _fake_option(p["id"])
    am.save(p["id"], "cand_1234.png", "paper_boat", ref="the small paper boat", keep="The paper boat keeps its folded shape")
    reg = tomllib.loads((lib / "registry.toml").read_text())
    assert reg["scenes"]["pond_night"] == "scenes/pond_night.png"
    assert reg["props"]["paper_boat"]["keep"] == "The paper boat keeps its folded shape"


def test_refuses_duplicates_and_bad_ids(lib):
    d = am.create("cast", "Asha", "another girl")
    assert d["id"] == "asha_2"     # never collides with the library
    _fake_option(d["id"])
    with pytest.raises(ValueError, match="already"):
        am.save(d["id"], "cand_1234.png", "asha")
    with pytest.raises(ValueError, match="lowercase"):
        am.save(d["id"], "cand_1234.png", "Bad Id")
    with pytest.raises(ValueError, match="no option"):
        am.save(d["id"], "cand_9.png", "asha_two")
    assert not list((lib / "cast").iterdir())
