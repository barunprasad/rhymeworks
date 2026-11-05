"""Run a command and report wall time + peak system memory growth.

Apple Silicon GPU allocations live in unified memory and don't show up reliably in
per-process RSS, so we sample system-wide used memory (active + wired + compressed)
from vm_stat and report peak minus the pre-run baseline.

Usage: python bench.py <label> -- <command...>
Appends a JSON line to spikes/results/bench.jsonl.
"""

import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results" / "bench.jsonl"


def used_gb() -> float:
    out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
    page = int(re.search(r"page size of (\d+)", out).group(1))
    stat = {m.group(1): int(m.group(2)) for m in re.finditer(r"^(.+?):\s+(\d+)\.", out, re.M)}
    pages = stat["Pages active"] + stat["Pages wired down"] + stat["Pages occupied by compressor"]
    return pages * page / 1024**3


def main() -> None:
    sep = sys.argv.index("--")
    label, cmd = " ".join(sys.argv[1:sep]), sys.argv[sep + 1 :]

    baseline = used_gb()
    peak = baseline
    done = threading.Event()

    def sample() -> None:
        nonlocal peak
        while not done.is_set():
            peak = max(peak, used_gb())
            time.sleep(0.5)

    threading.Thread(target=sample, daemon=True).start()
    t0 = time.time()
    proc = subprocess.run(cmd)
    wall = time.time() - t0
    done.set()

    row = {
        "label": label,
        "exit": proc.returncode,
        "wall_sec": round(wall, 1),
        "baseline_used_gb": round(baseline, 1),
        "peak_used_gb": round(peak, 1),
        "peak_delta_gb": round(peak - baseline, 1),
        "cmd": " ".join(cmd),
    }
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a") as f:
        f.write(json.dumps(row) + "\n")
    print("BENCH", json.dumps(row), flush=True)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
