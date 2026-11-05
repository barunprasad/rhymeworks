"""Cut flat-vector art out of its plain background → transparent PNG, trimmed, plus metadata.

The art has thick dark outlines on a near-uniform background, so flood-filling from the image
border is exact and instant (no segmentation model). Edge pixels get partial alpha by how close
they are to the background colour, which keeps outlines anti-aliased.
Usage (image env): python cutout.py <in.png>... (writes <name>.cut.png + <name>.cut.json beside it)
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SENTINEL = (255, 0, 255)
PROBE = (0, 255, 1)
KEPT = (1, 254, 255)


def cutout(path: Path, thresh: int = 38, hole_frac: float = 0.0, top_only: bool = False) -> dict:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    bg = np.median(
        np.concatenate([np.asarray(img)[0], np.asarray(img)[-1], np.asarray(img)[:, 0], np.asarray(img)[:, -1]]), axis=0
    )
    filled = img.copy()
    # Seed the fill from many border points so separated background pockets touching the edge are caught.
    for x in range(0, w, max(1, w // 32)):
        for y in ((0,) if top_only else (0, h - 1)):
            if tuple(filled.getpixel((x, y))) != SENTINEL:
                ImageDraw.floodfill(filled, (x, y), SENTINEL, thresh=thresh)
    for y in range(0, 0 if top_only else h, max(1, h // 32)):
        for x in (0, w - 1):
            if tuple(filled.getpixel((x, y))) != SENTINEL:
                ImageDraw.floodfill(filled, (x, y), SENTINEL, thresh=thresh)

    if hole_frac > 0:
        # Enclosed background pockets (e.g. inside a basket handle) don't touch the border. Fill each
        # near-background island; islands bigger than hole_frac of the image become background too.
        # Off for characters, whose eye whites are small enclosed islands that must stay.
        grid = max(4, min(w, h) // 64)
        rgb0 = np.asarray(img).astype(np.int32)
        for y in range(0, h, grid):
            for x in range(0, w, grid):
                px = filled.getpixel((x, y))
                if px in (SENTINEL, KEPT) or np.abs(rgb0[y, x] - bg).max() > thresh:
                    continue
                ImageDraw.floodfill(filled, (x, y), PROBE, thresh=thresh)
                f = np.asarray(filled)
                island = np.all(f == PROBE, axis=-1)
                colour = SENTINEL if island.mean() > hole_frac else KEPT
                arr = f.copy()
                arr[island] = colour
                filled = Image.fromarray(arr)

    f = np.asarray(filled)
    is_bg = np.all(f == SENTINEL, axis=-1)
    if hole_frac > 0:
        # Restore original pixels for islands we decided to keep.
        kept = np.all(f == KEPT, axis=-1)
        f = f.copy()
        f[kept] = np.asarray(img)[kept]
    # Soft edge: foreground pixels bordering the background get alpha by colour distance from bg.
    rgb = np.asarray(img).astype(np.float32)
    dist = np.linalg.norm(rgb - bg, axis=-1)
    alpha = np.where(is_bg, 0.0, 1.0)
    border = np.asarray(Image.fromarray((~is_bg).astype(np.uint8) * 255).filter(ImageFilter.MinFilter(3))) == 0
    edge = border & ~is_bg
    alpha[edge] = np.clip(dist[edge] / 90.0, 0, 1)

    rgba = np.dstack([np.asarray(img), (alpha * 255).astype(np.uint8)])
    ys, xs = np.nonzero(alpha > 0.05)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    pad = 4
    x0, y0, x1, y1 = max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad)
    out = Image.fromarray(rgba).crop((x0, y0, x1, y1))
    dest = path.with_suffix(".cut.png")
    out.save(dest)
    meta = {
        "src": path.name,
        "src_size": [w, h],
        "crop": [int(x0), int(y0), int(x1), int(y1)],
        "size": [int(x1 - x0), int(y1 - y0)],
        "coverage": round(float((alpha > 0.5).mean()), 3),
    }
    path.with_suffix(".cut.json").write_text(json.dumps(meta))
    return meta


if __name__ == "__main__":
    args = sys.argv[1:]
    holes, top = 0.0, False
    while args and args[0].startswith("--"):
        if args[0] == "--holes":
            holes, args = float(args[1]), args[2:]
        elif args[0] == "--seed-top":
            top, args = True, args[1:]
    for p in args:
        m = cutout(Path(p), hole_frac=holes, top_only=top)
        print(Path(p).name, m["size"], "coverage", m["coverage"], flush=True)
