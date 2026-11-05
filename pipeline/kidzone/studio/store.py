"""Rhymeworks studio working state (SQLite). Only transient things live here: the job queue, its history and settings.
Every creative decision is written to files (episode.toml, review.toml, assets/registry.toml), never only to this DB.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path

from ..paths import DB

DB_PATH = DB
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  kind      TEXT NOT NULL,             -- keys | clips | assemble | package
  episode   TEXT NOT NULL,             -- episode slug
  args      TEXT NOT NULL DEFAULT '{}',-- JSON: only, redo
  status    TEXT NOT NULL DEFAULT 'queued',  -- queued | running | done | failed | cancelled
  position  REAL NOT NULL,             -- queue order (lower runs first)
  progress  REAL NOT NULL DEFAULT 0,   -- 0..1
  message   TEXT NOT NULL DEFAULT '',
  log       TEXT NOT NULL DEFAULT '',  -- path of the job's log file
  created   REAL NOT NULL,
  started   REAL,
  finished  REAL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
DEFAULTS = {"paused": False, "work_hours": "09:00-22:00", "daytime_only": True, "yield_to_ollama": True}
JOB_COLS = ["id", "kind", "episode", "args", "status", "position", "progress", "message", "log", "created", "started", "finished"]


class Store:
    def __init__(self, path: Path = DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)
            # a job left 'running' by a crash/restart goes back to the front of the queue
            self._db.execute("UPDATE jobs SET status='queued', message='restarted after studio restart' WHERE status='running'")
            self._db.commit()

    def _q(self, sql: str, params=()) -> list[tuple]:
        with self._lock:
            cur = self._db.execute(sql, params)
            rows = cur.fetchall()   # read results BEFORE committing (INSERT … RETURNING / concurrent SELECTs)
            self._db.commit()
            return rows

    # ---------------- jobs
    @staticmethod
    def _row(r: tuple) -> dict:
        d = dict(zip(JOB_COLS, r))
        d["args"] = json.loads(d["args"])
        return d

    def add_job(self, kind: str, episode: str, args: dict) -> dict:
        pos = (self._q("SELECT COALESCE(MAX(position), 0) FROM jobs WHERE status='queued'")[0][0] or 0) + 1
        jid = self._q("INSERT INTO jobs (kind, episode, args, position, created) VALUES (?,?,?,?,?) RETURNING id",
                      (kind, episode, json.dumps(args), pos, time.time()))[0][0]
        return self.job(jid)

    def job(self, jid: int) -> dict | None:
        r = self._q(f"SELECT {','.join(JOB_COLS)} FROM jobs WHERE id=?", (jid,))
        return self._row(r[0]) if r else None

    def jobs(self, statuses: tuple[str, ...] | None = None, limit: int = 100) -> list[dict]:
        where = f"WHERE status IN ({','.join('?' * len(statuses))})" if statuses else ""
        order = "CASE status WHEN 'running' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END, " \
                "CASE WHEN status IN ('running','queued') THEN position ELSE -COALESCE(finished, created) END"
        rows = self._q(f"SELECT {','.join(JOB_COLS)} FROM jobs {where} ORDER BY {order} LIMIT ?", (*(statuses or ()), limit))
        return [self._row(r) for r in rows]

    def next_queued(self, kinds: tuple[str, ...] | None = None) -> dict | None:
        where = f" AND kind IN ({','.join('?' * len(kinds))})" if kinds else ""
        r = self._q(f"SELECT {','.join(JOB_COLS)} FROM jobs WHERE status='queued'{where} ORDER BY position LIMIT 1", kinds or ())
        return self._row(r[0]) if r else None

    def update_job(self, jid: int, **fields) -> dict:
        sets = ", ".join(f"{k}=?" for k in fields)
        self._q(f"UPDATE jobs SET {sets} WHERE id=?", (*fields.values(), jid))
        return self.job(jid)

    def clear_history(self) -> int:
        """Forget finished jobs (done / failed / cancelled). Files on disk are not touched."""
        n = self._q("SELECT COUNT(*) FROM jobs WHERE status NOT IN ('queued','running')")[0][0]
        self._q("DELETE FROM jobs WHERE status NOT IN ('queued','running')")
        return n

    def move_job(self, jid: int, before: int | None) -> None:
        """Reorder: put job `jid` just before job `before` (None = end of queue)."""
        q = [j["id"] for j in self.jobs(("queued",)) if j["id"] != jid]
        q.insert(q.index(before) if before in q else len(q), jid)
        for i, x in enumerate(q):
            self._q("UPDATE jobs SET position=? WHERE id=?", (i + 1, x))

    # ---------------- settings
    def settings(self) -> dict:
        s = dict(DEFAULTS)
        for k, v in self._q("SELECT key, value FROM settings"):
            s[k] = json.loads(v)
        return s

    def set_settings(self, **kv) -> dict:
        for k, v in kv.items():
            if k not in DEFAULTS:
                raise KeyError(k)
            self._q("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, json.dumps(v)))
        return self.settings()
