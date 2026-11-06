"""Auto-checks: the instant movement check and how picture-check answers become plain-words hints."""
import shutil
import subprocess

import pytest

from kidzone import checks

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")


def _clip(tmp_path, src: str):
    out = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", src, "-t", "2", "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


@needs_ffmpeg
def test_still_clip_is_frozen_and_moving_clip_is_not(tmp_path):
    assert checks.motion(_clip(tmp_path, "color=c=blue:s=320x180:r=24"))["frozen"]
    assert not checks.motion(_clip(tmp_path, "testsrc2=s=320x180:r=24"))["frozen"]


def test_flags_in_plain_words():
    r = {"counts": {"Tara": 2, "Biscuit": 1}, "extra": 1, "problems": ["extra hand on the girl."]}
    assert checks.flags_of(r, " (at 2.2 s)") == ["Tara appears 2 times (at 2.2 s)", "1 extra person or animal (at 2.2 s)",
                                                 "Extra hand on the girl (at 2.2 s)"]
    assert checks.flags_of({"counts": {"Tara": 1}, "extra": 0, "problems": []}, "") == []


def test_freshness_follows_the_file(tmp_path):
    f = tmp_path / "s01_a.png"
    f.write_bytes(b"x")
    entry = {"mtime": f.stat().st_mtime, "flags": []}
    assert checks.fresh(entry, f)
    assert not checks.fresh({**entry, "mtime": entry["mtime"] - 5}, f)   # redone since: check again
    assert not checks.fresh(None, f)


def test_props_are_not_counted():
    reg = {"cast": {"tara": {"ref": "the girl"}, "nandu_calf": {"ref": "the calf"}}, "props": {"bus": {"ref": "the bus"}}}
    assert checks._names(["tara", "bus", "nandu_calf", "tara"], reg) == [("Tara", "the girl"), ("Nandu", "the calf")]


@needs_ffmpeg
def test_song_end_is_found_before_a_silent_tail(tmp_path):
    from kidzone import ending
    wav = tmp_path / "song.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=3", "-f", "lavfi", "-i",
                    "anullsrc=r=44100:cl=mono", "-filter_complex", "[1]atrim=0:4[s];[0][s]concat=n=2:v=0:a=1", str(wav)], check=True)
    assert ending.last_sound(wav, ending.QUIET_DB) == pytest.approx(3.0, abs=0.15)


def test_chapters_are_swapped_for_the_intro_version(monkeypatch):
    from kidzone import upload
    desc = "Hello.\n\n00:00 Gaana Gaadi!\n00:13 Wheels go round\n01:02 Wipers\n\n🎵 Lyrics\n..."
    monkeypatch.setattr(upload, "chapters", lambda ep, offset=0.0, first=None: [(0.0, first or "Title"), (10.0 + offset, "Wheels go round")])
    monkeypatch.setattr(upload, "intro_seconds", lambda ep: 3.7)
    monkeypatch.setattr(upload.paths, "projects", lambda: {"p": {"name": "Gaana Gaadi"}})
    ep = type("E", (), {"spec": {"episode": {"project": "p"}}})()
    assert "00:00 Title\n00:10 Wheels go round\n\n🎵" in upload.description_for(ep, desc, False)
    assert "00:00 Gaana Gaadi!\n00:14 Wheels go round\n\n🎵" in upload.description_for(ep, desc, True)
