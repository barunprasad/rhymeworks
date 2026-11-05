"""Shared paths, worker invocation, Ollama access and episode workspace helpers."""

import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

from .paths import CODE, EPISODES, HOME, LIB  # noqa: F401  (content lives in HOME, see paths.py)

ROOT = CODE   # the repository: code, tools, envs, models
TOOLS = ROOT / "pipeline" / "tools"
IMAGE_ENV = ROOT / "spikes" / "envs" / "image"
AUDIO_ENV = ROOT / "spikes" / "envs" / "audio"
ACE_DIR = ROOT / "spikes" / "vendor" / "ACE-Step-1.5"
COMPOSITIONS = ROOT / "packages" / "compositions"
OLLAMA = "http://127.0.0.1:11434"
WRITER_MODEL = "gemma4:26b"

OFFLINE = {**os.environ, "HF_HUB_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"}


def log(stage: str, msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {stage:<8} {msg}", flush=True)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "episode"


def read_json(p: Path) -> Any:
    return json.loads(p.read_text())


def write_json(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1))


def run_tool(env: Path, script: str, *args: str, capture: bool = True) -> str:
    """Run a pipeline/tools script inside a model env (one heavy process at a time)."""
    cmd = ["uv", "run", "--project", str(env), "python", str(TOOLS / script), *map(str, args)]
    out = subprocess.run(cmd, capture_output=capture, text=True, env=OFFLINE)
    if out.returncode:
        raise RuntimeError(f"{script} failed:\n{(out.stderr or '')[-3000:]}")
    return out.stdout or ""


def run_env_cmd(env: Path, *cmd: str) -> None:
    out = subprocess.run(["uv", "run", "--project", str(env), *cmd], capture_output=True, text=True, env=OFFLINE)
    if out.returncode:
        raise RuntimeError(f"{cmd[0]} failed:\n{out.stderr[-3000:]}")


def ollama_loaded() -> list[str]:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/ps", timeout=5) as r:
            return [m["name"] for m in json.load(r).get("models", [])]
    except OSError:
        return []


def wait_ollama_unloaded(timeout: float = 60) -> None:
    """Memory governor: never start an image/audio model while an LLM is still resident."""
    t0 = time.time()
    while ollama_loaded() and time.time() - t0 < timeout:
        time.sleep(1)


def chat_json(system: str, user: str, schema: dict, images: list[str] | None = None, temperature: float = 0.7) -> dict:
    msg: dict[str, Any] = {"role": "user", "content": user}
    if images:
        msg["images"] = images
    body = {
        "model": WRITER_MODEL,
        "messages": [{"role": "system", "content": system}, msg],
        "format": schema,
        "stream": False,
        "keep_alive": 0,
        "think": False,
        "options": {"temperature": temperature, "num_ctx": 16384, "num_predict": 12000},
    }
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        content = json.load(r)["message"]["content"]
    return json.loads(content)


class Episode:
    """Episode workspace: episodes/<slug>/ with one output file per stage (presence = done)."""

    def __init__(self, slug: str):
        self.slug = slug
        self.dir = EPISODES / slug
        self.dir.mkdir(parents=True, exist_ok=True)
        self.public = COMPOSITIONS / "public" / "ep" / slug

    def path(self, *parts: str) -> Path:
        return self.dir.joinpath(*parts)

    def has(self, *parts: str) -> bool:
        return self.path(*parts).exists()
