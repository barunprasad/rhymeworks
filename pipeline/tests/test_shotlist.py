"""Shot list editing keeps episode.toml hand-readable and never writes a spec the engine can't run."""
import shutil
import tomllib

import pytest

from kidzone import drafter, pixar
from kidzone import paths
from kidzone.studio import shotlist as sl

WHEELS = paths.EPISODES / "wheels-on-the-bus/episode.toml"
pytestmark = pytest.mark.skipif(not WHEELS.exists(), reason="Wheels on the Bus is not in this content folder")


@pytest.fixture
def spec(tmp_path):
    p = tmp_path / "episode.toml"
    shutil.copy(WHEELS, p)
    return p


def test_update_rewrites_only_that_line_and_keeps_comments(spec):
    before = spec.read_text().splitlines()
    sl.update(spec, "s06", {"seed": 6060, "lyric": "The calf goes moo"})
    after = spec.read_text().splitlines()
    assert 'seed = 6060' in after and 'lyric = "The calf goes moo"' in after
    assert 'end = "same"    # same key as start + end pins them in their seats' in after   # trailing comment kept
    assert len(after) == len(before) + 1
    assert [l for l in after if l.startswith("#")] == [l for l in before if l.startswith("#")]


def test_unknown_token_is_refused_and_file_untouched(spec):
    orig = spec.read_text()
    with pytest.raises(sl.SpecError, match="unknown token"):
        sl.update(spec, "s01", {"key": "{nobody} waves"})
    assert spec.read_text() == orig


def test_unknown_field_and_bad_end_refused(spec):
    with pytest.raises(sl.SpecError):
        sl.update(spec, "s01", {"colour": "red"})
    with pytest.raises(sl.SpecError):
        sl.update(spec, "s01", {"end": "later"})


def test_values_round_trip_including_hindi_and_quotes(spec):
    sl.update(spec, "s02", {"lyric": 'जगन्नाथ "चका नैन"', "end": {"seed": 9, "key": "{Gopu} sits # not a comment"}})
    s = next(x for x in sl.read(spec)["shots"] if x["id"] == "s02")
    assert s["lyric"] == 'जगन्नाथ "चका नैन"' and s["end"] == {"seed": 9, "key": "{Gopu} sits # not a comment"}
    assert pixar.load(spec).shots[2].end_key.name == "s02_b"
    sl.update(spec, "s02", {"end": None, "sing": False})
    assert "end" not in tomllib.loads(spec.read_text())["shot"][2]


def test_add_copy_move_delete(spec):
    new = sl.add(spec, after="s03")
    assert new["id"] == "s18" and [s["id"] for s in sl.read(spec)["shots"]][4] == "s18"
    dup = sl.add(spec, copy_of="s05")
    assert dup["key"] == next(s for s in sl.read(spec)["shots"] if s["id"] == "s05")["key"] and dup["seed"] != 505
    sl.move(spec, "s19", "s00")
    assert sl.read(spec)["shots"][0]["id"] == "s19"
    sl.delete(spec, "s19")
    sl.delete(spec, "s18")
    assert [s["id"] for s in sl.read(spec)["shots"]] == [f"s{i:02d}" for i in range(18)]
    assert "# ---------------- verse 2: calf ----------------" in spec.read_text()


def test_new_episode_one_shot_per_line(tmp_path):
    spec = sl.new_episode(tmp_path / "fruit-friends", "Fruit Friends", "hi", ["केला पीला", "सेब लाल"], 4.8, "gaana-gaadi", "meadow")
    ep = pixar.load(spec)   # no song yet: planned on the line grid
    assert [s.id for s in ep.shots] == ["s00", "s01"] and ep.shots[1].start == pytest.approx(4.8)
    assert sl.read(spec)["shots"][0]["lyric"] == "केला पीला"
    with pytest.raises(sl.SpecError):
        sl.new_episode(tmp_path / "fruit-friends", "x", "en", [], 4.8, "gaana-gaadi", "meadow")


def test_new_episode_from_another_reuses_style_shots_and_keyframes(tmp_path):
    wheels = tmp_path / "wheels" / "episode.toml"     # a real spec with [style] and [vars]
    wheels.parent.mkdir()
    shutil.copy(WHEELS, wheels)
    plain = sl.new_episode(tmp_path / "bus-2", "Bus 2", "en", ["a", "b"], 4.8, "gaana-gaadi", "meadow", source=wheels)
    data, before = tomllib.loads(plain.read_text()), tomllib.loads(wheels.read_text())
    assert data["style"] == before["style"] and data["vars"] == before["vars"]
    assert all(not s["key"] for s in sl.read(plain)["shots"]) and not (plain.parent / "keys").exists()

    src = sl.new_episode(tmp_path / "kite", "Kite", "en", ["up we go", "round we go", "up we go"], 4.8, "gaana-gaadi", "meadow")
    for sid, key in (("s00", "Kite flies"), ("s01", "Kite circles"), ("s02", "Kite again")):
        sl.update(src, sid, {"key": key, "motion": "it moves"})
    sl.update(src, "s01", {"lines": 2})
    (src.parent / "keys").mkdir()
    (src.parent / "keys" / "s01_a.png").write_bytes(b"key")
    spec = sl.new_episode(tmp_path / "kite-hi", "Kite HI", "hi", ["ऊपर", "गोल", "नई पंक्ति"], 4.8, "gaana-gaadi", "meadow",
                          source=src, copy_shots=True)
    new = sl.read(spec)["shots"]
    assert [s["lyric"] for s in new] == ["ऊपर", "गोल", "ऊपर", "नई पंक्ति"]     # repeats follow; the extra line is new
    assert [s["key"] for s in new] == ["Kite flies", "Kite circles", "Kite again", ""] and new[1]["lines"] == 2
    assert (spec.parent / "keys" / "s01_a.png").read_bytes() == b"key"
    pixar.load(spec)


def test_drafter_fills_empty_shots_and_strips_invented_tokens(tmp_path):
    spec = sl.new_episode(tmp_path / "t", "Test", "en", ["one", "two"], 4.8, "gaana-gaadi", "meadow")

    def fake_chat(system, user, schema, temperature=0.6):
        assert "{gopu}" in user and "s00: one" in user
        return {"shots": [
            {"id": "s00", "scene": "pond", "key": "{Gopu} waves. Alone in the frame.", "motion": "The boy walks along the pond", "sing": True, "end": ""},
            {"id": "s01", "scene": "moon", "key": "{Gopu} meets {kela_banana}", "motion": "{Gopu} walks to the {bus}. {keep:bus}", "sing": False, "end": "same"},
        ]}
    assert drafter.draft(spec, chat=fake_chat) == ["s00", "s01"]
    s0, s1 = sl.read(spec)["shots"]
    assert s0["scene"] == "pond" and s0["sing"] is True
    assert s1["scene"] == "meadow" and s1["key"] == "{Gopu} meets kela banana" and s1["end"] == "same"
    assert s1["motion"].startswith("The boy in the orange kurta walks to the painted") and s1["motion"].endswith("{keep:bus}")
    assert drafter.draft(spec, chat=fake_chat) == []   # nothing left to draft


def test_table_field_edits_keep_layout(spec):
    from kidzone.studio.specedit import set_table_field
    set_table_field(spec, "song", "bpm", 116)
    set_table_field(spec, "song", "voice", "nursery_bright")
    set_table_field(spec, "episode", "status", None)
    d = tomllib.loads(spec.read_text())
    assert d["song"]["bpm"] == 116 and d["song"]["voice"] == "nursery_bright" and "status" not in d["episode"]
    assert 'vocals = "song/vox/en_s75_1.wav"       # Spleeter vocal of the chosen take → lip-sync shots' in spec.read_text()
    set_table_field(spec, "episode", "status", "published", "uploaded today")
    assert 'status = "published"   # uploaded today' in spec.read_text()


def test_voice_styles_parse_and_captions():
    from kidzone import songmaker
    v = songmaker.voices()
    assert {"bal_bhakti", "nursery_bright"} <= set(v) and all(x["caption"] for x in v.values())
    assert "Hindi" in songmaker.voice_caption("kids_chorus", "hi")


def test_bar_grid_plan_from_aligned_lines():
    from kidzone.songmaker import plan_bar_shots
    bar = 2.6
    lines = [{"text": "one", "start": 4.8, "end": 9.9},       # pickup just before bar 2
             {"text": "two", "start": 10.3, "end": 20.0},     # 4 bars → two 2-bar shots, both sung
             {"text": "tag", "start": 20.9, "end": 22.0},     # sung 1 bar, then a 5-bar instrumental break
             {"text": "tag2", "start": 21.2, "end": 22.4},    # same downbeat as "tag": merged into one shot
             {"text": "end", "start": 36.4, "end": 40.0}]
    plan = plan_bar_shots(lines, bar, 44.0)
    assert plan == [{"lyric": None, "lines": 2}, {"lyric": "one", "lines": 2}, {"lyric": "two", "lines": 2}, {"lyric": "two", "lines": 2},
                    {"lyric": "tag tag2", "lines": 2}, {"lyric": None, "lines": 2}, {"lyric": None, "lines": 2},
                    {"lyric": "end", "lines": 3}]
    assert sum(p["lines"] for p in plan) == round(44.0 / bar)


def test_replace_shots_keeps_prompts_for_the_same_lyric(tmp_path):
    spec = sl.new_episode(tmp_path / "t", "Test", "en", ["one", "two"], 4.8, "gaana-gaadi", "meadow")
    sl.update(spec, "s01", {"key": "{Gopu} waves", "motion": "The boy waves", "scene": "pond"})
    sl.replace_shots(spec, [{"lyric": None, "lines": 2}, {"lyric": "one", "lines": 1}, {"lyric": "two", "lines": 3}])
    s = sl.read(spec)["shots"]
    assert [x["lyric"] for x in s] == [None, "one", "two"] and [x["lines"] for x in s] == [2, None, 3]
    assert s[2]["key"] == "{Gopu} waves" and s[2]["scene"] == "pond" and s[1]["key"] == ""
    assert pixar.load(spec).shots[2].start == pytest.approx(3 * 4.8)


def test_feel_reaches_prompts_and_blocks_singing(spec):
    sid = sl.read(spec)["shots"][0]["id"]
    sl.update(spec, sid, {"feel": "quiet devotion", "sing": False})
    ep = pixar.load(spec)
    s = ep.shots[0]
    assert "Feeling: quiet devotion" in s.key.prompt and "nobody is singing" in s.key.prompt
    assert "The feeling: quiet devotion" in s.motion and pixar.NO_SINGING in s.motion
    sl.update(spec, sid, {"sing": True})
    s = pixar.load(spec).shots[0]
    assert pixar.NO_SINGING not in s.motion and "nobody is singing" not in s.key.prompt
    sl.update(spec, sid, {"feel": ""})   # cleared → line removed
    assert "feel" not in spec.read_text().split("[[shot]]")[1]


def test_director_proposes_validates_and_applies(spec):
    from kidzone import shotdirector
    def fake(system, user, schema, temperature=0.4):
        assert "REQUEST: less singing" in user
        return {"reply": "Minu no longer sings in s03.", "moves": [{"id": "s05", "before": "s04"}, {"id": "zz", "before": ""}],
                "changes": [{"id": "s03", "why": "less singing", "sing": False, "feel": "quiet joy", "motion": "The girl in the {minu} waves"},
                            {"id": "nope", "why": "x", "feel": "y"}, {"id": "s04", "why": "same", "scene": "no_such_scene"}]}
    p = shotdirector.propose(spec, "less singing", chat=fake)
    assert [c["id"] for c in p["changes"]] == ["s03"] and p["moves"] == [{"id": "s05", "before": "s04"}]
    assert "{" not in p["changes"][0]["fields"]["motion"]          # tokens in motion become plain words
    res = shotdirector.apply(spec)
    assert res["errors"] == [] and res["remake"] == ["s03"]
    rows = sl.read(spec)["shots"]
    s03 = next(s for s in rows if s["id"] == "s03")
    assert s03["sing"] is False and s03["feel"] == "quiet joy"
    ids = [s["id"] for s in rows]
    assert ids.index("s05") == ids.index("s04") - 1
    assert shotdirector.load(spec.parent)["proposal"] is None


def test_keyframe_redo_reseeds_the_end_key_too(tmp_path):
    from kidzone.studio.specedit import bump_seed
    spec = sl.new_episode(tmp_path / "e", "E", "en", ["one"], 4.8, "gaana-gaadi", "meadow")
    sl.update(spec, "s00", {"key": "A", "motion": "m", "end": {"seed": 1104, "key": "B"}})
    bump_seed(spec, "s00", "seed", 7)
    s0 = sl.read(spec)["shots"][0]
    assert s0["seed"] != 100 and s0["end"]["seed"] != 1104 and s0["end"]["key"] == "B"
    clip = bump_seed(spec, "s00", "clip_seed", 7)   # a clip redo leaves both keyframes alone
    assert sl.read(spec)["shots"][0]["end"]["seed"] == s0["end"]["seed"] and clip
