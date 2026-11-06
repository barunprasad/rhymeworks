"""Rhymeworks studio API (FastAPI). Local only: bind to 127.0.0.1.

  kidzone studio [--port 8765]

REST under /api, live events on /api/events (Server-Sent Events), project files under /files/assets and /files/episodes.
"""

import asyncio
import tomllib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from concurrent.futures import ThreadPoolExecutor

from .. import checks, ending, pixar
from .. import paths
from . import lock, review, shotlist
from . import projects as projectsedit
from .store import Store
from .specedit import bump_seed, set_table_field
from .worker import KINDS, Events, Worker, episode_spec, in_work_hours

ASSETS = paths.ASSETS
EPISODES = paths.EPISODES
PROJECTS = paths.PROJECTS
paths.ensure_home()   # a new content folder starts from templates/home
ASSETS.mkdir(parents=True, exist_ok=True)
EPISODES.mkdir(parents=True, exist_ok=True)

store = Store()
events = Events()
worker = Worker(store, events)


@asynccontextmanager
async def lifespan(app: FastAPI):
    events.loop = asyncio.get_running_loop()
    worker.start()
    yield
    worker.stop()


app = FastAPI(title="Rhymeworks Studio", lifespan=lifespan)


@app.middleware("http")
async def _lock(request: Request, call_next):
    """This computer is trusted; phones need the key cookie from the QR link; other websites are refused (lock.py)."""
    if bad := lock.problem(request):
        return JSONResponse({"detail": bad[1], "locked": bad[0] == 401}, status_code=bad[0])
    return await call_next(request)


@app.get("/api/unlock")
def unlock(k: str = ""):
    """The phone link (QR code): remembers this phone with a cookie, then opens the studio."""
    if not lock.unlocks(k):
        return JSONResponse({"detail": "This link is out of date: scan the code on your Mac again.", "locked": True}, status_code=401)
    r = RedirectResponse("/", status_code=303)
    r.set_cookie(lock.COOKIE, k, max_age=400 * 86400, httponly=True, samesite="lax")
    return r


def _lan_url(request: Request) -> str | None:
    """The phone link with its key, for this computer's eyes only (the desktop "Open on your phone" QR code)."""
    import os
    base = os.environ.get("STUDIO_LAN_URL")   # set by `npm run studio:lan` (scripts/studio.mjs)
    return f"{base}/api/unlock?k={lock.key()}" if base and lock.is_local(request) else None


@app.post("/api/lan/reset")
def lan_reset(request: Request):
    """Make a new phone link: every linked phone has to scan again."""
    if not lock.is_local(request):
        raise HTTPException(403, "only on the Mac itself")
    lock.reset_key()
    return {"lan_url": _lan_url(request)}
app.mount("/files/assets", StaticFiles(directory=ASSETS), name="assets")
app.mount("/files/episodes", StaticFiles(directory=EPISODES), name="episodes")
from .. import assetmaker, keyoptions, shotdirector  # noqa: E402
assetmaker.DRAFTS.mkdir(parents=True, exist_ok=True)
app.mount("/files/studio/drafts", StaticFiles(directory=assetmaker.DRAFTS), name="drafts")


def file_url(p: Path) -> str | None:
    """URL for a project file, cache-busted by its modification time (so a redone keyframe refreshes)."""
    if not p.exists():
        return None
    p = p.resolve()
    if p.is_relative_to(paths.STATE):          # drafts: this computer only
        rel = "studio/" + str(p.relative_to(paths.STATE))
    elif p.is_relative_to(paths.HOME):         # episodes/…, assets/… in your content folder
        rel = str(p.relative_to(paths.HOME))
    else:
        return None
    return f"/files/{rel}?v={int(p.stat().st_mtime)}"


def _mtime(p: Path) -> float | None:
    return p.stat().st_mtime if p.exists() else None


# ---------------------------------------------------------------- read models

@app.get("/api/health")
def health(request: Request):
    return {"ok": True, "worker": worker.state, "running_job": worker.current, "lan_url": _lan_url(request)}


def _project_out(pid: str, p: dict) -> dict:
    intro = paths.HOME / p["intro"] if p.get("intro") else None
    return {"id": pid, **p, "icon": file_url(paths.HOME / p["icon"]) if p.get("icon") else None, "icon_path": p.get("icon"),
            "intro_url": file_url(intro) if intro and intro.is_file() else None}


@app.get("/api/projects")
def projects():
    return [_project_out(pid, p) for pid, p in paths.projects().items()]


@app.get("/api/intro-clips")
def intro_clips():
    """Short videos in the content folder's assets/ that could open a channel's videos (Project settings → Channel intro)."""
    out = []
    for f in sorted(ASSETS.rglob("*")):
        if f.suffix.lower() in projectsedit.VIDEO and f.is_file() and not any(p.startswith(".") for p in f.parts):
            try:
                sec = pixar._probe_seconds(f)
            except ValueError:
                continue
            if sec <= 15:
                out.append({"path": str(f.relative_to(paths.HOME)), "url": file_url(f), "seconds": round(sec, 1)})
    return out[:40]


class NewProject(BaseModel):
    name: str
    languages: list[str] | None = None


@app.post("/api/projects")
def create_project(req: NewProject):
    try:
        pid = projectsedit.create(req.name, req.languages)
    except projectsedit.ProjectError as e:
        raise HTTPException(400, str(e))
    events.publish("projects")
    return _project_out(pid, paths.projects()[pid])


class ProjectPatch(BaseModel):
    name: str | None = None
    tagline: str | None = None
    icon: str | None = None
    intro: str | None = None
    languages: list[str] | None = None
    subscribe: dict[str, str | None] | None = None
    playlists: dict[str, str | None] | None = None


@app.patch("/api/projects/{pid}")
def patch_project(pid: str, req: ProjectPatch):
    try:
        p = projectsedit.update(pid, req.model_dump(exclude_unset=True))
    except projectsedit.ProjectError as e:
        raise HTTPException(400 if pid in paths.projects() else 404, str(e))
    events.publish("projects")
    return _project_out(pid, p)


def _usage() -> dict:
    """Which episodes/shots use each registry id (cast/prop tokens in key prompts, scenes by id)."""
    use: dict[str, dict] = {}
    for d in _episode_dirs():
        try:
            spec = tomllib.loads((d / "episode.toml").read_text())
        except Exception:
            continue
        for sh in spec.get("shot", []):
            text = sh.get("key", "") + " " + (sh["end"].get("key", "") if isinstance(sh.get("end"), dict) else "")
            ids = {m.group(1).lower() for m in pixar.TOKEN.finditer(text)} | {f"scene:{sh.get('scene')}"}
            for i in ids:
                u = use.setdefault(i, {"shots": 0, "episodes": {}})
                u["shots"] += 1
                e = u["episodes"].setdefault(d.name, {"slug": d.name, "title": spec["episode"]["title"], "shots": []})
                e["shots"].append(sh["id"])
    return use


@app.get("/api/library")
def library():
    reg = tomllib.loads((ASSETS / "registry.toml").read_text())
    use = _usage()

    def uses(key: str) -> dict:
        u = use.get(key, {"shots": 0, "episodes": {}})
        return {"shots": u["shots"], "episodes": list(u["episodes"].values())}
    item = lambda kind, iid, v: {"id": iid, "kind": kind, "token": "{" + iid + "}", "ref": v.get("ref"), "style": v.get("style"),
                                 "person": v.get("person", False), "image": file_url(ASSETS / v["file"]), "path": f"assets/{v['file']}",
                                 "added": _mtime(ASSETS / v["file"]), "used": uses(iid)}
    return {"cast": [item("cast", k, v) for k, v in reg.get("cast", {}).items()],
            "props": [item("prop", k, v) for k, v in reg.get("props", {}).items()],
            "scenes": [{"id": k, "kind": "scene", "image": file_url(ASSETS / f), "path": f"assets/{f}", "added": _mtime(ASSETS / f), "used": uses(f"scene:{k}")}
                       for k, f in reg.get("scenes", {}).items()]}


def _episode_dirs() -> list[Path]:
    return sorted(p.parent for p in EPISODES.glob("*/episode.toml") if not p.parent.name.startswith("_"))


def _summary(d: Path) -> dict:
    spec = tomllib.loads((d / "episode.toml").read_text())
    shots = spec.get("shot", [])
    keys = sum(1 for s in shots if (d / "keys" / f"{s['id']}_a.png").exists())
    clips = sum(1 for s in shots if (d / "clips" / f"{s['id']}.mp4").exists())
    rv = review.load(d)
    waiting = lambda stage, f: sum(1 for s in shots if review.status(rv[stage].get(s["id"]), _mtime(f(s["id"]))) == "to_review")
    keys_to_review = waiting("keys", lambda i: d / "keys" / f"{i}_a.png")
    clips_to_review = waiting("clips", lambda i: d / "clips" / f"{i}.mp4")
    out = d / spec["episode"]["output"]
    published = spec["episode"].get("status") == "published"
    song = d / spec.get("song", {}).get("audio", "song/master.wav")
    empty = sum(1 for s in shots if not s.get("key", "").strip() or not s.get("motion", "").strip())
    stage = ("published" if published else "package" if out.exists() else "clips" if keys == len(shots) and shots
             else "song" if not song.exists() else "shot list" if empty or not shots else "keys")
    if published:   # finished before/outside the studio: nothing waits for review
        keys_to_review = clips_to_review = 0
    return {"slug": d.name, "title": spec["episode"]["title"], "lang": spec["episode"].get("lang"),
            "project": spec["episode"].get("project") or paths.default_project(), "shots": len(shots), "keys": keys, "clips": clips,
            "keys_to_review": keys_to_review, "clips_to_review": clips_to_review, "empty_shots": empty, "has_song": song.exists(),
            "stage": stage, "output": file_url(out), "film": file_url(_film(d, out)), "contact": file_url(d / "keys" / "contact.jpg"),
            "poster": _poster(d, shots), "updated": max(filter(None, [_mtime(d / "episode.toml"), _mtime(d / "review.toml")]), default=None),
            "scenes": sorted({s.get("scene") for s in shots if s.get("scene")}),
            "cast": sorted({m.group(1).lower() for s in shots for m in pixar.TOKEN.finditer(s.get("key", ""))})}


def _film(d: Path, out: Path) -> Path:
    """The best finished cut to watch: the upload pack's 1080p, else a finished *_1080p.mp4 next to the spec, else the assembled film."""
    for up in (d / "upload" / f"{out.stem}_1080p.mp4", d / "upload" / f"{out.stem}_intro_1080p.mp4"):
        if up.exists() and (not out.exists() or up.stat().st_mtime >= out.stat().st_mtime):
            return up
    done = sorted(d.glob("*_1080p.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
    return done[0] if done else out


def _poster(d: Path, shots: list[dict]) -> str | None:
    """The episode's cover in lists: its first sung line's keyframe, else any keyframe."""
    for s in shots[1:] + shots[:1]:
        p = d / "keys" / f"{s['id']}_a.png"
        if p.exists():
            return file_url(p)
    return None


@app.get("/api/episodes")
def episodes():
    return [_summary(d) for d in _episode_dirs()]


@app.get("/api/episodes/{slug}")
def episode(slug: str):
    try:
        ep = pixar.load(episode_spec(slug))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    rv = review.load(ep.dir)
    summary = _summary(ep.dir)
    published = summary["stage"] == "published"

    def st(stage: str, sid: str, f: Path) -> str:
        v = review.status(rv[stage].get(sid), _mtime(f))
        return "approved" if published and v == "to_review" else v   # finished outside the studio = accepted
    raw = {sh["id"]: sh for sh in ep.spec.get("shot", [])}
    active = [j for j in store.jobs(("queued", "running")) if j["episode"] == slug]
    checking = {st: any(j["kind"] == "check" and j["args"].get("stage") == st for j in active) for st in checks.STAGES}
    looked = checks.load(ep.dir)
    with ThreadPoolExecutor(8) as pool:   # movement check: ~0.15 s per new clip, cached by file time
        list(pool.map(checks.motion_cached, [ep.clips_dir / f"{s.id}.mp4" for s in ep.shots]))
    shots = []
    for s in ep.shots:
        kp, cp = ep.keys_dir / f"{s.key.name}.png", ep.clips_dir / f"{s.id}.mp4"
        r = raw.get(s.id, {})
        shots.append({
            "id": s.id, "start": round(s.start, 3), "dur": round(s.dur, 3), "frames": s.frames, "sing": s.sing,
            "end": "same" if s.end_same else (s.end_key.name if s.end_key else None),
            "scene": s.key.scene, "seed": s.key.seed,
            "cast": s.key.cast,
            "key_prompt": s.key.prompt, "motion": s.motion, "lyric": r.get("lyric"), "feel": r.get("feel"),
            "options": len(keyoptions.listing(ep.dir, s.id)),
            "key": {"url": file_url(kp), "status": st("keys", s.id, kp), "note": (rv["keys"].get(s.id) or {}).get("note"),
                    "check": checks.summary(ep, looked, "keys", s, checking["keys"])},
            "clip": {"url": file_url(cp), "status": st("clips", s.id, cp), "note": (rv["clips"].get(s.id) or {}).get("note"),
                     "check": checks.summary(ep, looked, "clips", s, checking["clips"])},
        })
    end = None if published else ending.suggest(ep)
    return {**summary, "width": ep.width, "height": ep.height, "song": file_url(ep.song), "shots": shots, "jobs": active,
            "ending": end if end and end.get("kind") else None}


class EndingReq(BaseModel):
    seconds: float


@app.post("/api/episodes/{slug}/ending")
def set_ending(slug: str, req: EndingReq):
    """End the film at `seconds` (the music fades out over the last 1.5 s). Shots that would start after it are taken out
    of episode.toml and kept in removed_shots.toml (with their keyframes and clips still on disk); then it re-assembles."""
    spec = _spec(slug)
    ep = pixar.load(spec)
    song_len = pixar._probe_seconds(ep.song) if ep.song.exists() else 0
    if not 5 <= req.seconds <= max(song_len, ep.shots[-1].start + ep.shots[-1].dur) + 0.05:
        raise HTTPException(400, "the end must be inside the song")
    drop = [s.id for s in ep.shots if s.start > req.seconds - 1.0]
    if len(drop) >= len(ep.shots):
        raise HTTPException(400, "that would remove every shot")
    text = spec.read_text()
    kept = []
    for sid in drop:
        a, b = shotlist._own_span(text, sid)
        kept.append(text[a:b].rstrip("\n"))
    if kept:
        import datetime as dt
        backup = ep.dir / "removed_shots.toml"
        note = f"# Removed when the film was set to end at {req.seconds:.1f} s ({dt.datetime.now():%Y-%m-%d %H:%M}). Paste back into episode.toml to restore.\n"
        backup.write_text((backup.read_text() + "\n" if backup.exists() else "") + note + "\n\n".join(kept) + "\n")
    try:
        for sid in drop:
            shotlist.delete(spec, sid)
        set_table_field(spec, "song", "seconds", round(req.seconds, 2), "end of the film (the music fades out)")
    except shotlist.SpecError as e:
        raise HTTPException(400, str(e))
    _edited(slug)
    ep = pixar.load(spec)
    job = None
    if all((ep.clips_dir / f"{s.id}.mp4").exists() for s in ep.shots):
        job = store.add_job("assemble", slug, {})
        events.publish("job", job=job)
        worker.poke()
    return {"ok": True, "removed": drop, "job": job}


# ---------------------------------------------------------------- shot list (episode.toml editing)

def _spec(slug: str) -> Path:
    try:
        return episode_spec(slug)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


def _spec_error(e: Exception) -> HTTPException:
    return HTTPException(400 if isinstance(e, shotlist.SpecError) else 404, str(e).strip("'\""))


@app.get("/api/episodes/{slug}/shotlist")
def get_shotlist(slug: str):
    spec = _spec(slug)
    data = shotlist.read(spec)
    timing: dict = {}
    try:
        ep = pixar.load(spec)
        timing = {s.id: {"start": round(s.start, 3), "dur": round(s.dur, 3), "frames": s.frames} for s in ep.shots}
        keys_dir = ep.keys_dir
    except Exception:   # the spec is hand-edited and broken: still show what's there
        keys_dir = spec.parent / "keys"
    for s in data["shots"]:
        s.update(timing.get(s["id"], {}))
        s["image"] = file_url(keys_dir / f"{s['id']}_a.png")
        s["empty"] = not (s["key"] or "").strip() or not (s["motion"] or "").strip()
    reg = tomllib.loads((ASSETS / "registry.toml").read_text())
    tokens = [{"token": "{" + k + "}", "label": k.split("_")[0].capitalize(), "kind": kind, "image": file_url(ASSETS / v["file"])}
              for kind, sec in (("cast", "cast"), ("prop", "props")) for k, v in reg.get(sec, {}).items()]
    tokens += [{"token": "{" + k + "}", "label": k, "kind": "var", "image": None} for k in data["vars"]]
    return {**data, "slug": slug, "tokens": tokens, "scenes": [{"id": k, "image": file_url(ASSETS / f)} for k, f in reg["scenes"].items()],
            "jobs": [j for j in store.jobs(("queued", "running")) if j["episode"] == slug]}


def _edited(slug: str) -> None:
    events.publish("spec", episode=slug)


class ShotPatch(BaseModel):
    fields: dict


@app.patch("/api/episodes/{slug}/shots/{sid}")
def patch_shot(slug: str, sid: str, req: ShotPatch):
    try:
        shot = shotlist.update(_spec(slug), sid, req.fields)
    except (shotlist.SpecError, KeyError) as e:
        raise _spec_error(e)
    _edited(slug)
    return shot


class ShotAdd(BaseModel):
    after: str | None = None
    copy_of: str | None = None
    fields: dict | None = None


@app.post("/api/episodes/{slug}/shots")
def add_shot(slug: str, req: ShotAdd):
    try:
        shot = shotlist.add(_spec(slug), req.after, req.copy_of, req.fields)
    except (shotlist.SpecError, KeyError) as e:
        raise _spec_error(e)
    _edited(slug)
    return shot


@app.delete("/api/episodes/{slug}/shots/{sid}")
def delete_shot(slug: str, sid: str):
    try:
        shotlist.delete(_spec(slug), sid)
    except (shotlist.SpecError, KeyError) as e:
        raise _spec_error(e)
    _edited(slug)
    return {"ok": True}


class ShotMove(BaseModel):
    before: str | None = None


@app.post("/api/episodes/{slug}/shots/{sid}/move")
def move_shot(slug: str, sid: str, req: ShotMove):
    try:
        shotlist.move(_spec(slug), sid, req.before)
    except (shotlist.SpecError, KeyError) as e:
        raise _spec_error(e)
    _edited(slug)
    return {"ok": True}


class NewEpisode(BaseModel):
    title: str
    lang: str = "en"
    lyrics: str = ""
    slug: str | None = None
    line_seconds: float = 4.8
    bpm: int | None = None
    project: str | None = None   # default: the first project in projects.toml
    scene: str = "meadow"
    source: str | None = None    # start from this episode: its style, vars and voice
    copy_shots: bool = False     # …and its shots (in order) with their keyframes


@app.post("/api/episodes")
def create_episode(req: NewEpisode):
    from ..core import slugify
    slug = req.slug or slugify(req.title)
    if not req.title.strip():
        raise HTTPException(400, "give the episode a title")
    if not shotlist.slug_ok(slug) or slug.startswith("_"):
        raise HTTPException(400, f"'{slug}' can't be used as a folder name")
    if req.lang not in ("en", "hi"):
        raise HTTPException(400, "lang must be en or hi")
    lines = [ln.strip() for ln in req.lyrics.splitlines() if ln.strip() and not ln.strip().startswith("[")]
    source = _spec(req.source) if req.source else None
    if req.project and req.project not in paths.projects():
        raise HTTPException(400, f"no project {req.project}")
    try:
        shotlist.new_episode(EPISODES / slug, req.title.strip(), req.lang, lines, req.line_seconds, req.project or paths.default_project(), req.scene,
                             req.lyrics, req.bpm, source, req.copy_shots)
    except shotlist.SpecError as e:
        raise HTTPException(409, str(e))
    events.publish("spec", episode=slug)
    return _summary(EPISODES / slug)


# ---------------------------------------------------------------- library: new characters / props / scenes

class EpisodeProject(BaseModel):
    project: str


@app.put("/api/episodes/{slug}/project")
def move_episode(slug: str, req: EpisodeProject):
    """Move an episode to another project (channel): one line in its episode.toml."""
    spec = _spec(slug)
    if req.project not in paths.projects():
        raise HTTPException(400, f"no project {req.project}")
    set_table_field(spec, "episode", "project", req.project)
    _edited(slug)
    events.publish("projects")
    return _summary(spec.parent)


def _draft_out(d: dict) -> dict:
    folder = assetmaker.draft_dir(d["id"])
    jobs = [j for j in store.jobs(("queued", "running")) if j["kind"] == "asset" and j["episode"] == d["id"]]
    return {**d, "candidates": [{"name": c, "url": file_url(folder / c)} for c in d["candidates"]], "jobs": jobs,
            "suggested_id": d["id"]}


@app.get("/api/drafts")
def list_drafts():
    return [_draft_out(d) for d in assetmaker.drafts()]


class DraftReq(BaseModel):
    kind: str
    name: str
    description: str
    person: bool = False


@app.post("/api/drafts")
def new_draft(req: DraftReq):
    try:
        d = assetmaker.create(req.kind, req.name, req.description, req.person)
    except ValueError as e:
        raise HTTPException(400, str(e))
    job = store.add_job("asset", d["id"], {})
    events.publish("job", job=job)
    worker.poke()
    return _draft_out(d)


def _draft(did: str) -> dict:
    try:
        return assetmaker.load(did)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, f"no draft {did}")


@app.get("/api/drafts/{did}")
def get_draft(did: str):
    return _draft_out(_draft(did))


class DraftPatch(BaseModel):
    description: str | None = None
    ref: str | None = None
    style: str | None = None
    person: bool | None = None


@app.patch("/api/drafts/{did}")
def patch_draft(did: str, req: DraftPatch):
    _draft(did)
    return _draft_out(assetmaker.update(did, **req.model_dump(exclude_none=True)))


@app.post("/api/drafts/{did}/more")
def more_options(did: str):
    _draft(did)
    job = store.add_job("asset", did, {})
    events.publish("job", job=job)
    worker.poke()
    return job


class SaveAsset(BaseModel):
    candidate: str
    id: str
    ref: str | None = None
    style: str | None = None
    person: bool | None = None
    keep: str | None = None


@app.post("/api/drafts/{did}/save")
def save_asset(did: str, req: SaveAsset):
    _draft(did)
    try:
        out = assetmaker.save(did, req.candidate, req.id, req.ref, req.style, req.person, req.keep)
    except ValueError as e:
        raise HTTPException(400, str(e))
    events.publish("library", id=out["id"])
    return out


@app.delete("/api/drafts/{did}")
def discard_draft(did: str):
    d = _draft(did)
    if d["saved"]:
        raise HTTPException(409, "already saved to the library")
    for j in store.jobs(("queued", "running")):
        if j["kind"] == "asset" and j["episode"] == did:
            worker.cancel(j["id"])
    assetmaker.discard(did)
    return {"ok": True}


# ---------------------------------------------------------------- song step + voice styles

@app.get("/api/episodes/{slug}/song")
def get_song(slug: str):
    from .. import songmaker as sm
    ep = pixar.load(_spec(slug))
    st = sm.song_settings(ep)
    scores = sm.load_scores(ep)
    lang = st["lang"]

    def take_row(p: Path) -> dict:
        r = scores.get(p.name, {})
        err = r.get("cer_whisper_deloop", r.get("cer_whisper")) if lang == "hi" else min(r.get("wer_parakeet", 9), r.get("wer_whisper", 9)) if r else None
        return {"name": p.name, "url": file_url(p), "n": int(p.stem.split("_")[-1]),
                "words": None if err is None or err >= 9 else max(0, round((1 - err) * 100)), "pitch_hz": r.get("f0_median_hz")}
    tk = sorted(sm.takes_dir(ep).glob(f"{lang}_*.wav"), key=lambda p: int(p.stem.split("_")[-1])) if sm.takes_dir(ep).exists() else []
    lyr = sm.episode_lyrics(ep)
    return {"slug": slug, "title": ep.spec["episode"]["title"], **st, "lyrics": lyr, "lines": sm.sung_lines(lyr),
            "takes": [take_row(p) for p in tk], "chosen": ep.spec["song"].get("take"),
            "master": file_url(ep.song), "vocals": file_url(ep.vocals) if ep.vocals else None,
            "voices": [{"id": k, **v, "sample": file_url(paths.VOICE_SAMPLES / f"{k}.wav")} for k, v in sm.voices().items()],
            "imported": ep.spec["song"].get("imported"),
            "jobs": [j for j in store.jobs(("queued", "running")) if j["episode"] == slug and j["kind"] in ("song", "master", "import")]}


class SongSettings(BaseModel):
    voice: str | None = None
    bpm: int | None = None
    bars_per_line: int | None = None
    lyrics: str | None = None


@app.put("/api/episodes/{slug}/song")
def put_song(slug: str, req: SongSettings):
    from .. import songmaker as sm
    spec = _spec(slug)
    ep = pixar.load(spec)
    st = sm.song_settings(ep)
    if req.voice is not None:
        if req.voice not in sm.voices():
            raise HTTPException(404, f"no voice style {req.voice}")
        set_table_field(spec, "song", "voice", req.voice)
    if req.bpm is not None or req.bars_per_line is not None:
        bpm = req.bpm or st["bpm"]
        bars = req.bars_per_line or st["bars_per_line"]
        if not 50 <= bpm <= 200:
            raise HTTPException(400, "tempo must be between 50 and 200 bpm")
        set_table_field(spec, "song", "bpm", int(bpm))
        set_table_field(spec, "song", "line_seconds", round(bars * 240 / bpm, 6), f"{bars} bars at {bpm} bpm = one shot")
    if req.lyrics is not None:
        f = sm.lyrics_file(ep)
        f.parent.mkdir(exist_ok=True)
        f.write_text(req.lyrics.strip() + "\n")
    events.publish("spec", episode=slug)
    return get_song(slug)


@app.get("/api/songs/existing")
def existing_songs():
    import subprocess
    from .. import songmaker as sm
    out = []
    for p in sm.existing_songs():
        try:
            sec = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                       capture_output=True, text=True, timeout=10).stdout.strip())
        except ValueError:
            continue
        rel = p.relative_to(paths.HOME)
        out.append({"path": str(rel), "episode": rel.parts[1], "name": p.name, "seconds": round(sec, 1), "url": file_url(p)})
    return out


@app.get("/api/voices")
def get_voices():
    from .. import songmaker as sm
    jobs = {j["episode"]: j for j in store.jobs(("queued", "running")) if j["kind"] == "voice"}
    return [{"id": k, **v, "sample": file_url(paths.VOICE_SAMPLES / f"{k}.wav"), "job": jobs.get(k)} for k, v in sm.voices().items()]


class VoicePatch(BaseModel):
    name: str | None = None
    desc: str | None = None
    caption: str | None = None
    status: str | None = None


@app.patch("/api/voices/{vid}")
def patch_voice(vid: str, req: VoicePatch):
    from .. import songmaker as sm
    if vid not in sm.voices():
        raise HTTPException(404, f"no voice style {vid}")
    if req.status is not None and req.status not in ("draft", "approved"):
        raise HTTPException(400, "status must be draft or approved")
    for k, v in req.model_dump(exclude_none=True).items():
        set_table_field(sm.VOICES, f"voice.{vid}", k, " ".join(v.split()) if k == "caption" else v.strip())
    events.publish("library")
    return get_voices()


class NewVoice(BaseModel):
    name: str
    caption: str
    desc: str = ""
    langs: list[str] = ["hi", "en"]
    bpm: list[int] = [96, 116]


@app.post("/api/voices")
def new_voice(req: NewVoice):
    import json as _j
    import re as _re
    from .. import songmaker as sm
    vid = _re.sub(r"[^a-z0-9]+", "_", req.name.lower()).strip("_")[:32]
    if not vid or vid in sm.voices():
        raise HTTPException(400, "pick a different name")
    if len(req.caption.split()) < 4:
        raise HTTPException(400, "describe the singer and the instruments (a few words at least)")
    q = lambda s: _j.dumps(s, ensure_ascii=False)
    block = (f"\n[voice.{vid}]\nname = {q(req.name.strip())}\ndesc = {q(req.desc.strip())}\nlangs = {q([l for l in req.langs if l in ('hi', 'en')] or ['en'])}\n"
             f"bpm = {q(req.bpm[:2])}\nmood = \"\"\nstatus = \"draft\"\ncaption = {q(' '.join(req.caption.split()))}\n")
    text = sm.VOICES.read_text().rstrip("\n") + "\n" + block
    tomllib.loads(text)
    sm.VOICES.write_text(text)
    job = store.add_job("voice", vid, {})
    events.publish("job", job=job)
    worker.poke()
    return get_voices()


@app.post("/api/voices/{vid}/sample")
def voice_sample(vid: str):
    from .. import songmaker as sm
    if vid not in sm.voices():
        raise HTTPException(404, f"no voice style {vid}")
    job = store.add_job("voice", vid, {})
    events.publish("job", job=job)
    worker.poke()
    return job


# ---------------------------------------------------------------- upload pack

CHECKS = [
    ("kids", "Audience: made for kids", "Required for children's content."),
    ("ai", "Altered or synthetic content: Yes", "The song is AI-generated music and is the main focus."),
    ("category", "Category: Education", "Same on every video."),
    ("playlist", "Playlist: {playlist}", "English songs → English Rhymes, Hindi → हिंदी बालगीत, bhajans → Bal Bhakti."),
    ("unlisted", "Visibility: Unlisted first", "Watch it once on your phone, then switch to Public."),
    ("watermark", "Watermark set", "The Gaana Gaadi icon, bottom right (channel setting, once)."),
]


@app.get("/api/episodes/{slug}/upload")
def get_upload(slug: str):
    from .. import upload as up
    spec = _spec(slug)
    ep = pixar.load(spec)
    d = ep.dir / "upload"
    stem = ep.output.stem
    intro = pixar.project_intro(ep)
    text_f = d / "upload_text.md"
    text = up.parse_text(text_f.read_text()) if text_f.exists() else None
    thumbs = sorted([p for p in d.glob("thumb*.jpg") if not p.name.startswith("thumb_704")] if d.exists() else [],
                    key=lambda p: (p.name != "thumbnail.jpg", p.name))
    st = up.load_state(ep.dir)
    lang = ep.spec["episode"].get("lang", "en")
    proj = paths.projects().get(ep.spec["episode"].get("project") or paths.default_project(), {})
    playlist = ep.spec["episode"].get("playlist") or proj.get("playlists", {}).get(lang) or up.PLAYLISTS.get(lang, "English Rhymes")
    chosen = st.get("thumbnail") or (thumbs[0].name if thumbs else None)
    videos = []
    for variant, f in (("original", d / f"{stem}_1080p.mp4"), ("intro", d / f"{stem}_intro_1080p.mp4")):
        if f.exists():
            videos.append({"variant": variant, "url": file_url(f), "name": f.name, "mb": round(f.stat().st_size / 1e6, 1),
                           "old": ep.output.exists() and f.stat().st_mtime < ep.output.stat().st_mtime,
                           "description": up.description_for(ep, text["description"], variant == "intro") if text else None})
    return {
        "slug": slug, "title": ep.spec["episode"]["title"], "lang": lang, "playlist": playlist,
        "published": ep.spec["episode"].get("status") == "published",
        "episode_ready": ep.output.exists(),
        "video": videos[0] if videos else None, "videos": videos,
        "intro": {"name": intro.name, "url": file_url(intro), "project": proj.get("name")} if intro else None,
        "text": text, "thumbs": [{"name": p.name, "url": file_url(p)} for p in thumbs], "thumbnail": chosen,
        "checks": [{"id": k, "title": a.format(playlist=playlist), "detail": b, "on": k in st.get("checks", []) or ("checks" not in st and ep.spec["episode"].get("status") == "published")} for k, a, b in CHECKS],
        "jobs": [j for j in store.jobs(("queued", "running")) if j["episode"] == slug],
    }


class UploadState(BaseModel):
    thumbnail: str | None = None
    checks: list[str] | None = None


@app.put("/api/episodes/{slug}/upload")
def put_upload(slug: str, req: UploadState):
    from .. import upload as up
    d = _spec(slug).parent
    st = up.load_state(d)
    if req.thumbnail is not None:
        if not (d / "upload" / req.thumbnail).is_file() or "/" in req.thumbnail:
            raise HTTPException(404, f"no thumbnail {req.thumbnail}")
        st["thumbnail"] = req.thumbnail
    if req.checks is not None:
        st["checks"] = [c for c in req.checks if c in {k for k, _, _ in CHECKS}]
    up.save_state(d, st)
    events.publish("spec", episode=slug)
    return {"ok": True}


class PublishReq(BaseModel):
    published: bool = True


@app.post("/api/episodes/{slug}/publish")
def publish(slug: str, req: PublishReq):
    import datetime as dt
    spec = _spec(slug)
    set_table_field(spec, "episode", "status", "published" if req.published else None,
                    f"uploaded {dt.date.today().isoformat()}" if req.published else "")
    events.publish("spec", episode=slug)
    return _summary(spec.parent)


# ---------------------------------------------------------------- keyframe options (pick 1 of N)

def _queue(kind: str, episode: str, args: dict) -> dict:
    job = store.add_job(kind, episode, args)
    events.publish("job", job=job)
    worker.poke()
    return job


@app.get("/api/episodes/{slug}/shots/{sid}/options")
def get_options(slug: str, sid: str):
    spec = _spec(slug)
    row = next((s for s in shotlist.read(spec)["shots"] if s["id"] == sid), None)
    if not row:
        raise HTTPException(404, f"no shot {sid}")
    jobs = [j for j in store.jobs(("queued", "running")) if j["episode"] == slug and j["kind"] == "options" and j["args"].get("shot") == sid]
    return {"shot": row, "current": {"seed": row["seed"], "url": file_url(spec.parent / "keys" / f"{sid}_a.png")},
            "options": [{"seed": o["seed"], "url": file_url(o["path"])} for o in keyoptions.listing(spec.parent, sid)],
            "waiting": sum(int(j["args"].get("n") or 4) for j in jobs), "jobs": jobs}


class OptionsReq(BaseModel):
    n: int = 4


@app.post("/api/episodes/{slug}/shots/{sid}/options")
def make_options(slug: str, sid: str, req: OptionsReq):
    _spec(slug)
    return _queue("options", slug, {"shot": sid, "n": max(1, min(8, req.n)), "only": [sid]})


class UseOptionReq(BaseModel):
    seed: int


@app.post("/api/episodes/{slug}/shots/{sid}/options/use")
def use_option(slug: str, sid: str, req: UseOptionReq):
    try:
        keyoptions.use(_spec(slug), sid, req.seed)
    except (FileNotFoundError, shotlist.SpecError, KeyError) as e:
        raise _spec_error(e)
    _edited(slug)
    events.publish("review", episode=slug, stage="keys", shot=sid, decision="approved")
    return get_options(slug, sid)


# ---------------------------------------------------------------- director (shot-list changes in plain words)

def _director_out(slug: str) -> dict:
    spec = _spec(slug)
    data = shotdirector.load(spec.parent)
    thumb = lambda sid: file_url(spec.parent / "keys" / f"{sid}_a.png")
    for p in [data.get("proposal")] + data.get("history", []):
        if p:
            for c in p.get("changes", []):
                c["image"] = thumb(c["id"])
    jobs = [j for j in store.jobs(("queued", "running")) if j["episode"] == slug and j["kind"] == "director"]
    return {**data, "jobs": jobs}


@app.get("/api/episodes/{slug}/director")
def get_director(slug: str):
    return _director_out(slug)


class DirectorReq(BaseModel):
    ask: str
    shots: list[str] | None = None


@app.post("/api/episodes/{slug}/director")
def ask_director(slug: str, req: DirectorReq):
    _spec(slug)
    if len(req.ask.strip()) < 4:
        raise HTTPException(400, "say what you'd like to change")
    _queue("director", slug, {"ask": req.ask.strip()[:600], "shots": req.shots or None})
    return _director_out(slug)


@app.post("/api/episodes/{slug}/director/apply")
def apply_director(slug: str):
    try:
        res = shotdirector.apply(_spec(slug))
    except ValueError as e:
        raise HTTPException(409, str(e))
    _edited(slug)
    return {**_director_out(slug), "result": res}


@app.post("/api/episodes/{slug}/director/discard")
def discard_director(slug: str):
    shotdirector.discard(_spec(slug))
    return _director_out(slug)


# ---------------------------------------------------------------- actions

class RunReq(BaseModel):
    phase: str
    only: list[str] | None = None
    redo: list[str] | None = None
    all: bool = False           # draft: redraft every shot
    take: str | None = None     # master: the picked take
    n: int | None = None        # song: how many takes
    path: str | None = None     # import: an existing mastered song (from /api/songs/existing)
    stage: str | None = None    # check: keys | clips
    force: bool = False         # check: check again even if unchanged
    intro: bool = False         # package: also the version with the project's intro clip


@app.post("/api/episodes/{slug}/run")
def run(slug: str, req: RunReq):
    if req.phase not in KINDS or req.phase in ("options", "director"):
        raise HTTPException(400, f"phase must be one of {KINDS} (options/director have their own endpoints)")
    _spec(slug)
    if req.phase == "master" and not req.take:
        raise HTTPException(400, "pick a take to master")
    if req.phase == "import":
        from .. import songmaker as sm
        allowed = {str(p.relative_to(paths.HOME)) for p in sm.existing_songs()}
        if req.path not in allowed:
            raise HTTPException(400, "pick one of the songs listed in the studio")
    if req.phase == "check" and req.stage not in checks.STAGES:
        raise HTTPException(400, "check needs stage keys or clips")
    args = {"only": req.only, "redo": req.redo} | ({"stage": req.stage, "force": req.force} if req.phase == "check" else {}) \
        | ({"intro": True} if req.phase == "package" and req.intro else {}) \
        | ({"all": True} if req.all else {}) | ({"take": req.take} if req.take else {}) \
        | ({"n": max(1, min(8, req.n))} if req.n else {}) | ({"path": str(paths.HOME / req.path)} if req.path else {})
    job = store.add_job(req.phase, slug, args)
    events.publish("job", job=job)
    worker.poke()
    return job


class ReviewReq(BaseModel):
    stage: str                  # keys | clips
    shot: str
    decision: str | None        # approved | redo | null (clear)
    note: str = ""


@app.post("/api/episodes/{slug}/review")
def decide(slug: str, req: ReviewReq):
    ep = pixar.load(episode_spec(slug))
    if req.shot not in {s.id for s in ep.shots}:
        raise HTTPException(404, f"no shot {req.shot}")
    f = ep.keys_dir / f"{req.shot}_a.png" if req.stage == "keys" else ep.clips_dir / f"{req.shot}.mp4"
    try:
        review.decide(ep.dir, req.stage, req.shot, req.decision, _mtime(f), req.note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    job = None
    if req.decision == "redo":   # new seed (same seed = identical result) + a queued job for that one shot
        bump_seed(episode_spec(slug), req.shot, "seed" if req.stage == "keys" else "clip_seed", ep.seed)
        job = store.add_job(req.stage, slug, {"only": [req.shot], "redo": [req.shot]})
        events.publish("job", job=job)
        worker.poke()
    events.publish("review", episode=slug, stage=req.stage, shot=req.shot, decision=req.decision)
    return {"ok": True, "job": job}


@app.get("/api/jobs")
def jobs(limit: int = 50):
    return store.jobs(limit=limit)


@app.delete("/api/jobs/history")
def clear_history():
    n = store.clear_history()
    events.publish("queue")
    return {"cleared": n}


@app.post("/api/jobs/{jid}/cancel")
def cancel(jid: int):
    if not worker.cancel(jid):
        raise HTTPException(409, "job is not queued or running")
    return store.job(jid)


class MoveReq(BaseModel):
    before: int | None = None


@app.post("/api/jobs/{jid}/move")
def move(jid: int, req: MoveReq):
    store.move_job(jid, req.before)
    events.publish("queue")
    return store.jobs(("queued",))


@app.get("/api/settings")
def get_settings():
    return {**store.settings(), "worker": worker.state}


@app.put("/api/settings")
def put_settings(body: dict):
    if "work_hours" in body:
        try:
            in_work_hours(str(body["work_hours"]))
        except ValueError:
            raise HTTPException(400, "work_hours must look like 09:00-22:00")
    try:
        s = store.set_settings(**body)
    except KeyError as e:
        raise HTTPException(400, f"unknown setting {e}")
    worker.poke()
    events.publish("settings", settings=s)
    return s


@app.get("/api/events")
async def stream():
    q = events.subscribe()

    async def gen():
        try:
            yield f"data: {{\"type\": \"hello\", \"worker\": \"{worker.state}\"}}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            events.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def serve(port: int = 8765) -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", timeout_graceful_shutdown=3)
