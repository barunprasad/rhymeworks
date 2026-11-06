"""GPU job worker: runs ONE job at a time (32 GB machine), as a separate `kidzone pixar` process so it can be cancelled.
Honours the queue settings: paused, daytime_only/work_hours, yield_to_ollama (waits while another big model is loaded).
"""

import asyncio
import datetime as dt
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from .. import pixar
from .. import paths
from ..core import ROOT
from .store import Store

LOGS = paths.LOGS
QUICK = ("director",)   # a one-minute text-model answer you are waiting for: allowed outside work hours
PHASES = ("keys", "clips", "assemble", "package")      # `kidzone pixar --phase …`
KINDS = PHASES + ("check", "draft", "upload", "asset", "song", "master", "import", "voice", "options", "director")  # song/master = `kidzone song` takes / mastering; voice = sample  # asset = `kidzone asset <draft>` (4 FLUX options for a new character/prop/scene)
                                               # draft = `kidzone draft` (writer LLM fills empty shot prompts)
                                                       # upload = `kidzone upload` (upload text + thumbnails)
                                                       # check = `kidzone check` (picture auto-check, queued after keys/clips)


def episode_spec(slug: str) -> Path:
    p = paths.EPISODES / slug / "episode.toml"
    if not p.exists():
        raise FileNotFoundError(f"no episode.toml for '{slug}'")
    return p


class Events:
    """Fan-out of studio events to SSE subscribers; safe to publish from worker threads."""

    def __init__(self):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self.subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subs.discard(q)

    def publish(self, etype: str, **data) -> None:
        if not self.loop:
            return
        msg = json.dumps({"type": etype, "at": time.time(), **data})
        for q in list(self.subs):
            self.loop.call_soon_threadsafe(lambda q=q: q.full() or q.put_nowait(msg))


def in_work_hours(spec: str, now: dt.datetime | None = None) -> bool:
    start, end = (dt.time.fromisoformat(x) for x in spec.split("-"))
    t = (now or dt.datetime.now()).time()
    return start <= t < end if start <= end else (t >= start or t < end)


def ollama_busy() -> bool:
    exe = shutil.which("ollama")
    if not exe:
        return False
    try:
        out = subprocess.run([exe, "ps"], capture_output=True, text=True, timeout=5).stdout.strip().splitlines()
    except (subprocess.TimeoutExpired, OSError):
        return False
    return len(out) > 1  # header + at least one loaded model


def pending_items(slug: str, kind: str, only: list[str] | None, redo: list[str] | None, args: dict | None = None) -> int:
    """How many keyframes/clips this job will actually render (existing outputs are skipped by the engine)."""
    if kind == "asset":
        return 4
    if kind == "import":
        return 2   # beat + alignment / vocal
    if kind in ("song", "master"):
        return 2   # takes + scoring / vocal + master
    if kind == "voice":
        return 1
    if kind == "options":
        return int((args or {}).get("n") or 4)
    if kind == "director":
        return 1
    ep = pixar.load(episode_spec(slug))
    if kind == "check":
        from .. import checks
        a = args or {}
        return len(checks.targets(ep, a.get("stage", "clips"), only) if a.get("force") else checks.unchecked(ep, a.get("stage", "clips"), only))
    shots = [s for s in ep.shots if not only or s.id in only]
    if kind == "keys":
        names = [k.name for s in shots for k in [s.key] + ([s.end_key] if s.end_key else [])]
        return sum(1 for n in names if n.split("_")[0] in (redo or []) or not (ep.keys_dir / f"{n}.png").exists())
    if kind == "clips":
        return sum(1 for s in shots if s.id in (redo or []) or not (ep.clips_dir / f"{s.id}.mp4").exists())
    if kind == "upload":
        return 4   # text + 3 thumbnails
    if kind == "draft":
        return sum(1 for s in ep.spec["shot"] if not s.get("key", "").strip() or not s.get("motion", "").strip()) or len(shots)
    return 1


def command_for(kind: str, slug: str, args: dict) -> list[str]:
    if kind == "asset":   # library job: `slug` is the draft id
        return [sys.executable, "-m", "kidzone.cli", "asset", slug]
    if kind == "voice":   # library job: `slug` is the voice id(s), comma-separated
        return [sys.executable, "-m", "kidzone.cli", "voice", *slug.split(",")]
    spec = str(episode_spec(slug))
    if kind == "options":
        return [sys.executable, "-m", "kidzone.cli", "options", spec, args["shot"], "--n", str(args.get("n") or 4)]
    if kind == "director":
        return [sys.executable, "-m", "kidzone.cli", "director", spec, "--ask", args["ask"]] + (["--shots", *args["shots"]] if args.get("shots") else [])
    if kind == "check":
        return [sys.executable, "-m", "kidzone.cli", "check", spec, "--stage", args.get("stage", "clips")] \
            + (["--only", *args["only"]] if args.get("only") else []) + (["--force"] if args.get("force") else [])
    if kind == "draft":
        return [sys.executable, "-m", "kidzone.cli", "draft", spec] + (["--all"] if args.get("all") else [])
    if kind == "song":
        return [sys.executable, "-m", "kidzone.cli", "song", spec, "--n", str(args.get("n") or 4)]
    if kind == "master":
        return [sys.executable, "-m", "kidzone.cli", "song", spec, "--master", args["take"]]
    if kind == "import":
        return [sys.executable, "-m", "kidzone.cli", "song", spec, "--import", args["path"]]
    if kind == "upload":
        return [sys.executable, "-m", "kidzone.cli", "upload", spec] + (["--force"] if args.get("all") else [])
    if kind not in PHASES:
        raise ValueError(f"unknown job kind {kind}")
    cmd = [sys.executable, "-m", "kidzone.cli", "pixar", spec, "--phase", kind]
    if args.get("only"):
        cmd += ["--only", *args["only"]]
    if args.get("redo"):
        cmd += ["--redo", *args["redo"]]
    if kind == "package" and args.get("intro"):
        cmd += ["--intro"]
    return cmd


class Worker(threading.Thread):
    def __init__(self, store: Store, events: Events):
        super().__init__(daemon=True, name="studio-worker")
        self.store, self.events = store, events
        self.wake = threading.Event()
        self.stopping = False
        self.proc: subprocess.Popen | None = None
        self.current: int | None = None
        self.state = "idle"   # idle | running | paused | waiting_hours | waiting_memory

    # ---------------- control
    def poke(self) -> None:
        self.wake.set()

    def stop(self) -> None:
        self.stopping = True
        self.cancel(self.current) if self.current else None
        self.poke()

    def cancel(self, jid: int) -> bool:
        job = self.store.job(jid)
        if not job or job["status"] not in ("queued", "running"):
            return False
        if job["status"] == "running" and self.proc and self.current == jid:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)   # the engine and its ltx/mflux children
            except ProcessLookupError:
                pass
        self.store.update_job(jid, status="cancelled", finished=time.time(), message="cancelled by you")
        self.events.publish("job", job=self.store.job(jid))
        return True

    def _set_state(self, state: str, note: str = "") -> None:
        if state != self.state:
            self.state = state
            self.events.publish("worker", state=state, note=note)

    # ---------------- loop
    def run(self) -> None:
        while not self.stopping:
            s = self.store.settings()
            job = self.store.next_queued()
            if s["paused"]:
                self._set_state("paused")
            elif not job:
                self._set_state("idle")
            elif s["daytime_only"] and not in_work_hours(s["work_hours"]) and not (job := self.store.next_queued(QUICK)):
                self._set_state("waiting_hours", f"jobs run {s['work_hours']}")
            elif s["yield_to_ollama"] and ollama_busy():
                self._set_state("waiting_memory", "another model is loaded in Ollama")
            else:
                try:
                    self._run(job)
                except Exception as e:   # never let one bad job kill the queue
                    import traceback
                    traceback.print_exc()
                    self.proc, self.current = None, None
                    self.store.update_job(job["id"], status="failed", finished=time.time(), message=f"studio error: {e}"[:500])
                    self.events.publish("job", job=self.store.job(job["id"]))
                continue
            self.wake.wait(timeout=20)
            self.wake.clear()

    def _run(self, job: dict) -> None:
        jid, kind, slug, args = job["id"], job["kind"], job["episode"], job["args"]
        LOGS.mkdir(parents=True, exist_ok=True)
        log = LOGS / f"job_{jid}.log"
        try:
            total = max(1, pending_items(slug, kind, args.get("only"), args.get("redo"), args))
            cmd = command_for(kind, slug, args)
        except Exception as e:  # bad episode spec: fail the job, keep the worker alive
            self.store.update_job(jid, status="failed", finished=time.time(), message=str(e)[:500])
            self.events.publish("job", job=self.store.job(jid))
            return
        self.current = jid
        self._set_state("running")
        self.store.update_job(jid, status="running", started=time.time(), progress=0, log=str(log), message="starting")
        self.events.publish("job", job=self.store.job(jid))
        started_items = 0
        with open(log, "w") as lf:
            self.proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                                         env={**os.environ, "PYTHONUNBUFFERED": "1"}, start_new_session=True)
            for line in self.proc.stdout:
                lf.write(line)
                lf.flush()
                line = line.strip()
                if line.startswith(("key ", "clip ", "check ")):          # engine starts the next keyframe / clip
                    if started_items:                            # …so the previous one is ready
                        self.events.publish("output", episode=slug, kind=kind)
                    started_items += 1
                    prog = (started_items - 1) / total
                    self.store.update_job(jid, progress=prog, message=line)
                    self.events.publish("job", job=self.store.job(jid))
            rc = self.proc.wait()
        self.proc, self.current = None, None
        if self.store.job(jid)["status"] == "cancelled":
            return
        ok = rc == 0
        tail = "" if ok else (log.read_text()[-400:] or f"exit code {rc}")
        self.store.update_job(jid, status="done" if ok else "failed", progress=1.0 if ok else job["progress"],
                              finished=time.time(), message="done" if ok else tail)
        self.events.publish("job", job=self.store.job(jid))
        self.events.publish("output", episode=slug, kind=kind)
        if ok and kind in ("keys", "clips"):
            self.queue_check(slug, kind)

    def queue_check(self, slug: str, stage: str) -> None:
        """After keyframes or clips are made: queue the picture auto-check (skips outputs already checked)."""
        if not self.store.settings().get("auto_check"):
            return
        if any(j["kind"] == "check" and j["episode"] == slug and j["args"].get("stage") == stage
               for j in self.store.jobs(("queued",))):
            return
        try:
            if not pending_items(slug, "check", None, None, {"stage": stage}):
                return
        except Exception:
            return
        job = self.store.add_job("check", slug, {"stage": stage})
        self.events.publish("job", job=job)
