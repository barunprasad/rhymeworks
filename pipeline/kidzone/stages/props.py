"""Props stage: generate every prop the storyboard defines (FLUX.2 klein q4), cut out, cache in the show library.

Props are cached by description slug under library/shows/<show>/props/gen/, so later episodes reuse them.
"""

import time

from ..core import IMAGE_ENV, LIB, Episode, log, run_env_cmd, run_tool, slugify, wait_ollama_unloaded
from ..models import Storyboard

MODEL = ["--model", "mflux-community/flux2-klein-4b-mflux-q4", "--base-model", "flux2-klein-4b"]


def run(ep: Episode, show: dict, sb: Storyboard) -> dict[str, str]:
    """Returns {prop id: path relative to the show library dir (cut PNG)}."""
    gen_dir = LIB / show["id"] / "props" / "gen"
    gen_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}
    wait_ollama_unloaded()
    for i, p in enumerate(sb.props):
        name = slugify(p.description)
        src = gen_dir / f"{name}.png"
        if not src.exists():
            prompt = f"{p.description}, a single object, {show['art_style']}, plain white background, centered, nothing else in the image"
            t0 = time.time()
            run_env_cmd(IMAGE_ENV, "mflux-generate-flux2", *MODEL, "--width", "512", "--height", "512", "--seed", str(100 + i), "--prompt", prompt, "--output", str(src))
            log("props", f"generated '{p.description}' in {time.time() - t0:.0f}s")
        if not src.with_suffix(".cut.png").exists():
            run_tool(IMAGE_ENV, "cutout.py", "--holes", "0.01", str(src))
        out[p.id] = str(src.with_suffix(".cut.png").relative_to(LIB / show["id"]))
    log("props", f"{len(out)} props ready ({sum(1 for _ in gen_dir.glob('*.cut.png'))} cached for this show)")
    return out
