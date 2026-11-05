"""Regression: the Wheels on the Bus episode.toml must resolve to exactly the prompts, images, seeds, frame counts,
lip-sync timing and end keys that the original hand-written make_episode.sh produced (recorded in fixtures/)."""
import json
import os
from pathlib import Path

import pytest

from kidzone import paths, pixar

FIX = Path(__file__).parent / "fixtures" / "wheels_old_script_calls.jsonl"
K = "<ROOT>/"   # the recorded calls had absolute repo paths
WHEELS = paths.EPISODES / "wheels-on-the-bus/episode.toml"
needs_wheels = pytest.mark.skipif(not WHEELS.exists(), reason="Wheels on the Bus is not in this content folder")


def _opt(a, k):
    return a[a.index(k) + 1] if k in a else None


@needs_wheels
def test_wheels_matches_original_script():
    calls = [json.loads(l) for l in FIX.read_text().splitlines()]
    keys, clips = {}, {}
    for a in calls:
        if "mflux-generate-flux2-edit" in a:
            i, j = a.index("--image-paths"), a.index("--seed")
            keys[os.path.basename(_opt(a, "--output"))[:-4]] = (int(_opt(a, "--seed")), [p.replace(K, "") for p in a[i + 1:j]], _opt(a, "--prompt"))
        elif "ltx-2-mlx" in a:
            imgs = [a[k + 1] for k, x in enumerate(a) if x == "--image"]
            clips[os.path.basename(_opt(a, "-o"))[:-4].replace("_raw", "")] = (
                int(_opt(a, "-f")), _opt(a, "-p"), "a2v" in a, _opt(a, "--audio-start"), len(imgs) == 2 and imgs[0] == imgs[1])
    ep = pixar.load(WHEELS)
    assert len(ep.shots) == 18
    for s in ep.shots:
        assert keys[s.key.name] == (s.key.seed, [paths.rel(p) for p in s.key.images], s.key.prompt), s.id
        frames, prompt, sing, ast, same = clips[s.id]
        assert (frames, prompt, sing, same) == (s.frames, s.motion, s.sing, s.end_same), s.id
        if sing:
            assert float(ast) == round(s.start - ep.lead, 3), s.id


def test_frames_are_ltx_valid():
    for sec in (1.0, 4.137931, 6.135, 10.0):
        n = pixar.frames_for(sec, 24)
        assert n % 8 == 1 and n >= sec * 24


@needs_wheels
def test_redo_dry_run_deletes_nothing(tmp_path, monkeypatch):
    import kidzone.pixar as px
    ep = px.load(WHEELS)
    ep.dir = tmp_path
    (tmp_path / "clips").mkdir()
    clip = tmp_path / "clips" / "s05.mp4"
    clip.write_bytes(b"x")
    px._redo(ep, ["s05"], "clips", dry=True)
    assert clip.exists()            # dry run only reports
    px._redo(ep, ["s05"], "clips", dry=False)
    assert not clip.exists()
