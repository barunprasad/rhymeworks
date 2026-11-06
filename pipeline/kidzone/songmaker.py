"""Song step for Pixar episodes: lyrics + a voice style → ACE-Step takes → scores → you pick → master + vocal on the shot grid.

  kidzone song <episode.toml> --takes [--n 4]     song/takes/<lang>_<k>.wav (+ scores in song/takes/scores.json)
  kidzone song <episode.toml> --master <take>     song/master_<lang>.wav + song/vox_<lang>.wav, [song] updated
  kidzone voice <voice id>                        a ~30 s sample of a voice style → assets/voices/<id>.wav

The shot grid: every shot is `line_seconds` long and one lyric line = one shot. ACE holds the requested tempo, but its intro
length varies, so mastering pads or trims the very start until the first sung line lands exactly on a shot boundary, and adds
an instrumental intro shot in front if the shot list has none. Timing after that point is never changed (lip-sync stays exact).
"""

import json
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
import urllib.request
from pathlib import Path

from . import pixar
from .core import AUDIO_ENV, OFFLINE, ROOT, TOOLS, log
from .stages.song import API, AceServer, _post

from .paths import EPISODES, HOME, VOICE_SAMPLES, VOICES, rel  # noqa: E402
from . import paths  # noqa: E402
SEP_ENV = ROOT / "spikes" / "envs" / "sep"
DEFAULT_TARGET = {"bands": {"sub_20_60": -13.8, "bass_60_250": -5.7, "lowmid_250_1k": -3.6, "mid_1k_4k": -6.4, "high_4k_11k": -16.5}}
SAMPLE_LYRICS = {"en": "[Verse]\nLa la la, sing along with me\nClap your hands, one two three\n[Chorus]\nHappy happy, round we go\nSing it high and sing it low",
                 "hi": "[Verse]\nला ला ला, गाओ मेरे साथ\nताली बजाओ, एक दो तीन\n[Chorus]\nखुश खुश हम, घूमें गोल\nऊँचा गाओ, नीचा बोल"}


# ---------------------------------------------------------------- voices

def voices() -> dict:
    return tomllib.loads(VOICES.read_text()).get("voice", {}) if VOICES.exists() else {}


def voice_caption(vid: str | None, lang: str) -> str:
    v = voices().get(vid or "") or next((x for x in voices().values() if lang in x.get("langs", [])), None)
    if not v:
        raise SystemExit("no voice style: add one in assets/voices.toml")
    cap = v["caption"]
    if lang == "hi" and "Hindi" not in cap:
        cap += ", clear Hindi diction"
    elif lang == "en" and "English" not in cap:
        cap += ", clear English diction"
    return cap


def _ace_generate(dest_names: list[Path], caption: str, lyrics: str, lang: str, bpm: int, seconds: float, key: str | None) -> list[Path]:
    payload = {"prompt": caption, "lyrics": lyrics, "vocal_language": lang, "thinking": True, "use_cot_language": False,
               "bpm": bpm, "audio_duration": seconds, "batch_size": len(dest_names), "audio_format": "wav"}
    if key:
        payload["key_scale"] = key
    task = _post("/release_task", payload)
    while True:
        time.sleep(3)
        res = _post("/query_result", {"task_id_list": [task["task_id"]]})[0]
        if res["status"] in (1, 2):
            break
    if res["status"] == 2:
        raise RuntimeError(f"ACE-Step failed: {res.get('result')}")
    for dest, item in zip(dest_names, json.loads(res["result"])):
        dest.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(API + item["file"], dest)
    return dest_names


def make_voice_samples(vids: list[str]) -> list[Path]:
    """~30 s samples of voice styles → assets/voices/<id>.wav (one ACE server start for all of them)."""
    vs = voices()
    unknown = [v for v in vids if v not in vs]
    if unknown:
        raise SystemExit(f"unknown voice style(s): {', '.join(unknown)}")
    made = []
    with AceServer():
        for vid in vids:
            v = vs[vid]
            lang = (v.get("langs") or ["en"])[0]
            bpm = int(sum(v.get("bpm", [100, 100])) / 2)
            out = VOICE_SAMPLES / f"{vid}.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            print(f"key {vid}", flush=True)
            tmp = out.with_name(f".{vid}.tmp.wav")
            _ace_generate([tmp], voice_caption(vid, lang), SAMPLE_LYRICS[lang], lang, bpm, 32.0, None)
            tmp.replace(out)
            log("voice", f"sample → {rel(out)}")
            made.append(out)
    return made


# ---------------------------------------------------------------- episode song

def lyrics_file(ep: pixar.Episode) -> Path:
    return ep.dir / "song" / f"lyrics_{ep.spec['episode'].get('lang', 'en')}.txt"


def episode_lyrics(ep: pixar.Episode) -> str:
    """song/lyrics_<lang>.txt if present (keeps [Verse]/[Chorus] tags), else the shot list's lyric lines as one verse."""
    f = lyrics_file(ep)
    if f.exists() and f.read_text().strip():
        return f.read_text().strip()
    lines = [s.get("lyric") for s in ep.spec["shot"] if s.get("lyric")]
    return "[Verse]\n" + "\n".join(lines)


def sung_lines(lyrics: str) -> int:
    return sum(1 for ln in lyrics.splitlines() if ln.strip() and not ln.strip().startswith("["))


def song_settings(ep: pixar.Episode) -> dict:
    s = ep.spec["song"]
    line = s.get("line_seconds", 4.8)
    bpm = int(s.get("bpm") or round(8 * 60 / line))
    return {"lang": ep.spec["episode"].get("lang", "en"), "voice": s.get("voice"), "bpm": bpm, "key": s.get("key"),
            "line_seconds": line, "bars_per_line": max(1, round(line * bpm / 240))}


def takes_dir(ep: pixar.Episode) -> Path:
    return ep.dir / "song" / "takes"


def load_scores(ep: pixar.Episode) -> dict:
    f = takes_dir(ep) / "scores.json"
    return {r["take"]: r for r in json.loads(f.read_text())} if f.exists() else {}


def _score(ep: pixar.Episode, files: list[Path], lang: str, lyrics: str) -> None:
    """score_songs.py on just these files (via a temp folder of <lang>_<i>.wav links) and merge into scores.json."""
    scores = load_scores(ep)
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "lyrics.json").write_text(json.dumps({lang: lyrics}, ensure_ascii=False))
        names = {}
        for i, f in enumerate(files[:10]):
            link = t / f"{lang}_{i}.wav"
            link.symlink_to(f)
            names[link.name] = f.name
        subprocess.run(["uv", "run", "--project", str(AUDIO_ENV), "python", str(TOOLS / "score_songs.py"), str(t)],
                       check=True, capture_output=True, text=True, env=OFFLINE)
        for r in json.loads((t / "scores.json").read_text()):
            r["take"] = names[r["take"]]
            scores[r["take"]] = r
    (takes_dir(ep) / "scores.json").write_text(json.dumps(list(scores.values()), ensure_ascii=False, indent=1))


def make_takes(ep: pixar.Episode, n: int = 4) -> list[Path]:
    st = song_settings(ep)
    lang, lyrics = st["lang"], episode_lyrics(ep)
    lines = sung_lines(lyrics)
    seconds = float(min(240, max(30, round(lines * st["line_seconds"] + 2 * st["line_seconds"] + 6))))   # + intro and outro
    d = takes_dir(ep)
    d.mkdir(parents=True, exist_ok=True)
    nums = [int(m.group(1)) for p in d.glob(f"{lang}_*.wav") if (m := re.fullmatch(rf"{lang}_(\d+)", p.stem))]
    start = max(nums) + 1 if nums else 1
    dest = [d / f"{lang}_{start + i}.wav" for i in range(n)]
    caption = voice_caption(st["voice"], lang)
    log("song", f"{n} takes × {seconds:.0f} s at {st['bpm']} bpm · {caption[:80]}…")
    print("key takes", flush=True)
    with AceServer():
        _ace_generate(dest, caption, lyrics, lang, st["bpm"], seconds, st["key"])
    print("key scoring", flush=True)
    log("song", "scoring how clearly the words come through (Whisper) …")
    _score(ep, dest, lang, lyrics)
    return dest


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def master(ep: pixar.Episode, take: str) -> dict:
    from .studio import shotlist
    from .studio.specedit import set_table_field
    st = song_settings(ep)
    lang, line = st["lang"], st["line_seconds"]
    src = takes_dir(ep) / take
    if not src.exists():
        raise SystemExit(f"no take {take}")
    song_dir = ep.dir / "song"
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        print("key vocal", flush=True)
        log("master", "isolating the vocal (Spleeter) …")
        res = subprocess.run(["uv", "run", "--project", str(SEP_ENV), "python", str(TOOLS / "split_vocals.py"), str(src), str(t / "vox.wav")],
                             capture_output=True, text=True, env={**OFFLINE, "MODEL_PATH": str(SEP_ENV / "pretrained_models")})
        if res.returncode:
            raise RuntimeError(f"split_vocals failed:\n{res.stderr[-2000:]}")
        info = json.loads(res.stdout.strip().splitlines()[-1])
        print("key master", flush=True)
        log("master", "mastering (EQ, glue, limiter, −14 LUFS) …")
        subprocess.run(["uv", "run", "--project", str(AUDIO_ENV), "python", str(TOOLS / "polish.py"), str(src), str(t / "master.wav"),
                        json.dumps({"target": DEFAULT_TARGET, "lufs": -14})], check=True, capture_output=True, env=OFFLINE)
        first = info["first_vocal"]
        intro_lines = round(first / line)   # 0 when the singing starts right away (then the start is trimmed, never padded with silence)
        shift = round(intro_lines * line - first, 3)   # > 0: pad silence in front, < 0: trim the start of the intro
        for name in ("master.wav", "vox.wav"):
            out = t / f"grid_{name}"
            if shift >= 0:
                _ffmpeg("-i", str(t / name), "-af", f"adelay={int(shift * 1000)}:all=1", str(out))
            else:
                _ffmpeg("-i", str(t / name), "-af", f"atrim=start={-shift},asetpts=PTS-STARTPTS,afade=t=in:d=0.04", str(out))
        song_dir.mkdir(exist_ok=True)
        shutil.copy(t / "grid_master.wav", song_dir / f"master_{lang}.wav")
        shutil.copy(t / "grid_vox.wav", song_dir / f"vox_{lang}.wav")
    spec = ep.dir / "episode.toml"
    set_table_field(spec, "song", "audio", f"song/master_{lang}.wav", f"take {take}, mastered in the studio")
    set_table_field(spec, "song", "vocals", f"song/vox_{lang}.wav")
    set_table_field(spec, "song", "take", take)
    set_table_field(spec, "song", "seconds", None)   # an ending set for the previous song doesn't apply to this one
    # instrumental intro shot(s) in front of the first sung line
    shots = shotlist.read(spec)["shots"]
    lead = 0
    for s in shots:
        if s.get("lyric"):
            break
        lead += s.get("lines") or 1
    if intro_lines and lead < intro_lines and shots:
        new = shotlist.add(spec, fields={"lines": intro_lines - lead if intro_lines - lead > 1 else None, "scene": shots[0]["scene"], "key": "", "motion": ""})
        shotlist.move(spec, new["id"], shots[0]["id"])
        log("master", f"added an instrumental intro shot {new['id']} ({intro_lines - lead} line{'s' if intro_lines - lead > 1 else ''})")
    log("master", f"first sung line at {first:.2f} s → moved {shift:+.2f} s onto the grid ({intro_lines} intro line{'s' if intro_lines != 1 else ''})")
    return {"take": take, "first_vocal": first, "shift": shift, "intro_lines": intro_lines}


# ---------------------------------------------------------------- use an existing (already mastered) song

def plan_bar_shots(lines: list[dict], bar: float, song_len: float, max_bars: int = 3) -> list[dict]:
    """Shots on a 1-bar grid (grid starts at 0 s) from aligned lyric lines [{text, start, end}].

    A line belongs to the downbeat nearest its first word (sung pickups start up to ~0.8 s early). Each shot covers
    1-3 bars; a long span is cut into 2-bar shots. Bars after a line has finished singing become instrumental shots.
    Returns [{"lyric": str | None, "lines": bars}] in order; the engine gives the last shot whatever time is left.
    """
    total = max(1, round(song_len / bar))
    marks: list[tuple[int, str, float]] = []   # (bar index, text, sung end)
    for ln in lines:
        k = max(0, round(ln["start"] / bar))
        if marks and k <= marks[-1][0]:        # two lines on one downbeat (short tag): one shot sings both
            b, txt, _ = marks[-1]
            marks[-1] = (b, f"{txt} {ln['text']}".strip(), ln["end"])
        else:
            marks.append((k, ln["text"], ln["end"]))

    def chunks(n: int) -> list[int]:
        out = []
        while n > max_bars:
            out.append(2)
            n -= 2
        return out + ([n] if n else [])

    shots: list[dict] = []
    if marks and marks[0][0] > 0:
        shots += [{"lyric": None, "lines": c} for c in chunks(marks[0][0])]
    for i, (k, txt, end) in enumerate(marks):
        nxt = marks[i + 1][0] if i + 1 < len(marks) else max(total, k + 1)
        pos = k
        for j, c in enumerate(chunks(nxt - k)):
            sung = j == 0 or end > pos * bar + 0.3 * bar   # still singing this line when the chunk starts
            shots.append({"lyric": txt if sung else None, "lines": c})
            pos += c
    if not shots:
        shots = [{"lyric": None, "lines": c} for c in chunks(total)]
    return shots


def fit_bar(beats: list[float], downbeats: list[float]) -> float:
    """Bar length from a least-squares line through all downbeats (beat times are quantised to ~23 ms frames,
    so one median gap is not precise enough for a 2-3 minute song)."""
    gaps = sorted(b - a for a, b in zip(beats, beats[1:]))
    bar0 = 4 * gaps[len(gaps) // 2]
    if len(downbeats) < 4:
        return bar0
    idx = [round((d - downbeats[0]) / bar0) for d in downbeats]
    n = len(idx)
    mx, my = sum(idx) / n, sum(downbeats) / n
    sxx = sum((i - mx) ** 2 for i in idx)
    return sum((i - mx) * (d - my) for i, d in zip(idx, downbeats)) / sxx if sxx else bar0


def import_song(ep: pixar.Episode, src: Path) -> dict:
    """Use an existing mastered song: beat grid + lyric alignment + vocal → master/vox on a 1-bar grid, shot list rebuilt
    so each shot starts on the downbeat of its line. Prompts already written are kept for the same lyric."""
    from .studio import shotlist
    from .studio.specedit import set_table_field
    lang = ep.spec["episode"].get("lang", "en")
    song_dir = ep.dir / "song"
    song_dir.mkdir(exist_ok=True)
    lyrics = episode_lyrics(ep)
    if not sung_lines(lyrics):   # no lyrics typed yet: take them from the song's own episode (2D pipeline: songs/lyrics.json)
        src_ep = next((p for p in src.parents if p.parent == EPISODES), None)
        lj = src_ep / "songs" / "lyrics.json" if src_ep else None
        if lj and lj.exists() and json.loads(lj.read_text()).get(lang):
            lyrics = json.loads(lj.read_text())[lang].strip()
            lyrics_file(ep).write_text(lyrics + "\n")
            log("import", f"lyrics taken from {_rel(lj)}")
        else:
            raise SystemExit("add the song's lyrics first (Song → Voice, tempo and lyrics): they are needed to find each line")
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        wav = t / "song.wav"
        _ffmpeg("-i", str(src), "-ar", "48000", "-ac", "2", str(wav))
        print("key beats", flush=True)
        log("import", "finding the beat (librosa) and where each line is sung (Whisper alignment) …")
        hint = ep.spec["song"].get("bpm") or 100
        subprocess.run(["uv", "run", "--project", str(AUDIO_ENV), "python", str(TOOLS / "beats.py"), str(wav), str(hint)],
                       check=True, capture_output=True, env=OFFLINE)
        beats = json.loads((t / "song.beats.json").read_text())
        (t / "lyrics.json").write_text(json.dumps({lang: lyrics}, ensure_ascii=False))
        res = subprocess.run(["uv", "run", "--project", str(AUDIO_ENV), "python", str(TOOLS / "align_and_mouth.py"), str(wav), lang, lang,
                              str(t / "lyrics.json"), str(t / "align")], capture_output=True, text=True, env=OFFLINE)
        if res.returncode:
            raise RuntimeError(f"alignment failed:\n{res.stderr[-1500:]}")
        segs = json.loads((t / "align" / "song.json").read_text())["segments"]
        bar = fit_bar(beats["beats"], beats["downbeats"])
        offs = sorted((d % bar) for d in beats["downbeats"])
        phase = offs[len(offs) // 2]                       # where the downbeats sit inside a bar
        shift = round(-phase if phase < bar / 2 else bar - phase, 3)
        print("key vocal", flush=True)
        log("import", "isolating the vocal (Spleeter) …")
        r2 = subprocess.run(["uv", "run", "--project", str(SEP_ENV), "python", str(TOOLS / "split_vocals.py"), str(wav), str(t / "vox.wav")],
                            capture_output=True, text=True, env={**OFFLINE, "MODEL_PATH": str(SEP_ENV / "pretrained_models")})
        if r2.returncode:
            raise RuntimeError(f"split_vocals failed:\n{r2.stderr[-1500:]}")
        for name in ("song.wav", "vox.wav"):
            out = t / f"grid_{name}"
            if shift >= 0:
                _ffmpeg("-i", str(t / name), "-af", f"adelay={int(shift * 1000)}:all=1", str(out))
            else:
                _ffmpeg("-i", str(t / name), "-af", f"atrim=start={-shift},asetpts=PTS-STARTPTS,afade=t=in:d=0.04", str(out))
        shutil.copy(t / "grid_song.wav", song_dir / f"master_{lang}.wav")
        shutil.copy(t / "grid_vox.wav", song_dir / f"vox_{lang}.wav")
        song_len = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                         str(song_dir / f"master_{lang}.wav")], capture_output=True, text=True).stdout.strip())
    lines = [{"text": s["text"].rstrip(",।."), "start": (s["words"][0]["start"] if s.get("words") else s["start"]) + shift,
              "end": s["end"] + shift} for s in segs]
    plan = plan_bar_shots(lines, bar, song_len)
    spec = ep.dir / "episode.toml"
    bpm = round(240 / bar, 2)
    set_table_field(spec, "song", "audio", f"song/master_{lang}.wav", f"imported from {_rel(src)}")
    set_table_field(spec, "song", "vocals", f"song/vox_{lang}.wav")
    set_table_field(spec, "song", "line_seconds", round(bar, 6), f"1 bar at {bpm} bpm; shots span 1-3 bars (lines = …)")
    set_table_field(spec, "song", "bpm", round(bpm))
    set_table_field(spec, "song", "take", None)
    set_table_field(spec, "song", "imported", _rel(src))
    set_table_field(spec, "song", "seconds", None)
    shotlist.replace_shots(spec, plan)
    log("import", f"{len(segs)} sung lines, bar {bar:.3f} s ({bpm} bpm), start moved {shift:+.3f} s → {len(plan)} shots")
    return {"bar": bar, "shift": shift, "shots": len(plan), "lines": len(segs)}


def _rel(p: Path) -> str:
    return rel(p)


def existing_songs() -> list[Path]:
    """Mastered songs already in the project that could be reused (newest first)."""
    pats = ["episodes/*/songs/master/final_*.wav", "episodes/*/final_*.wav", "episodes/*/song/master_*.wav"]
    found = {p.resolve() for pat in pats for p in HOME.glob(pat)}
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def main(args) -> None:
    ep = pixar.load(paths.find_spec(args.spec))
    if args.import_:
        import_song(ep, Path(args.import_).resolve())
    elif args.master:
        master(ep, args.master)
    else:
        make_takes(ep, args.n)


def voice_main(args) -> None:
    make_voice_samples(args.voice)
