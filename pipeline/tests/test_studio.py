"""Studio backend: queue order/cancel state, settings, review decisions (incl. stale approvals), work hours."""
import datetime as dt
import os
import time

from kidzone.studio import review
from kidzone.studio.store import Store
from kidzone.studio.worker import in_work_hours


def test_queue_order_move_and_settings(tmp_path):
    s = Store(tmp_path / "t.db")
    a, b, c = (s.add_job("keys", "ep", {"only": [x]}) for x in ("s1", "s2", "s3"))
    assert s.next_queued()["id"] == a["id"]
    s.move_job(a["id"], None)                       # a to the end
    assert [j["id"] for j in s.jobs(("queued",))] == [b["id"], c["id"], a["id"]]
    s.move_job(a["id"], b["id"])                    # a back in front of b
    assert s.next_queued()["id"] == a["id"]
    s.update_job(a["id"], status="running")
    assert Store(tmp_path / "t.db").job(a["id"])["status"] == "queued"   # a crash mid-job requeues it
    assert s.settings()["daytime_only"] is True
    assert s.set_settings(paused=True)["paused"] is True


def test_review_decisions_and_staleness(tmp_path):
    f = tmp_path / "keys" / "s05_a.png"
    f.parent.mkdir()
    f.write_bytes(b"x")
    m = f.stat().st_mtime
    review.decide(tmp_path, "keys", "s05", "approved", m, note="looks good")
    d = review.load(tmp_path)["keys"]["s05"]
    assert review.status(d, m) == "approved" and d["note"] == "looks good"
    os.utime(f, (time.time() + 10, time.time() + 10))   # file re-rendered → approval no longer counts
    assert review.status(d, f.stat().st_mtime) == "to_review"
    assert review.status(None, None) == "missing"
    review.decide(tmp_path, "keys", "s05", None, None)
    assert review.load(tmp_path)["keys"] == {}


def test_work_hours():
    at = lambda h, m=0: dt.datetime(2026, 11, 4, h, m)
    assert in_work_hours("09:00-22:00", at(10)) and not in_work_hours("09:00-22:00", at(1))
    assert not in_work_hours("09:00-22:00", at(22)) and in_work_hours("22:00-06:00", at(1))


def test_bump_seed_keeps_format(tmp_path):
    import tomllib
    from kidzone.studio.specedit import bump_seed
    p = tmp_path / "episode.toml"
    p.write_text('# top comment\n[render]\nseed = 7\n\n[[shot]]\nid = "s00"\nseed = 400   # keep me\nkey = "a"\n\n[[shot]]\nid = "s01"\nseed = 401\nkey = "b"\n')
    assert bump_seed(p, "s01", "seed", 7) == 1401
    assert bump_seed(p, "s00", "clip_seed", 7) == 1007
    assert bump_seed(p, "s00", "clip_seed", 7) == 2007
    d = tomllib.loads(p.read_text())
    assert [(s["id"], s["seed"], s.get("clip_seed")) for s in d["shot"]] == [("s00", 400, 2007), ("s01", 1401, None)]
    assert p.read_text().startswith("# top comment")
    bump_seed(p, "s00", "seed", 7)
    assert "seed = 1400   # keep me" in p.read_text()
