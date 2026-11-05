"""Deterministic mouth anchor from a character cutout: find the eyes, put the mouth below them.

Eyes in this flat style are enclosed near-white blobs containing a dark pupil. We label white
blobs inside the character, keep round ones in the upper body that contain dark pixels, and take
the two largest as the eyes (one eye = side/profile pose). The mouth sits centred below them.
Returns fractions of the cut image, or None if no eye is found (caller falls back).
Usage (image env): python face_anchor.py <x.cut.png>...
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


def eyes(img: np.ndarray) -> list[dict]:
    rgb, alpha = img[..., :3].astype(int), img[..., 3]
    body = alpha > 128
    ys, xs = np.nonzero(body)
    top, bottom = ys.min(), ys.max()
    white = body & np.all(rgb > 225, axis=-1)
    dark = np.all(rgb < 80, axis=-1)
    labels, n = ndimage.label(white)
    found = []
    char_px = body.sum()
    for i, sl in enumerate(ndimage.find_objects(labels), start=1):
        if sl is None:
            continue
        area = int((labels[sl] == i).sum())
        if not (0.0015 * char_px < area < 0.05 * char_px):
            continue
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if not (0.55 < w / max(1, h) < 1.8):
            continue
        cy, cx = (sl[0].start + sl[0].stop) / 2, (sl[1].start + sl[1].stop) / 2
        if cy > top + 0.6 * (bottom - top):
            continue
        if dark[sl].mean() < 0.04:  # needs a pupil
            continue
        found.append({"cx": cx, "cy": cy, "r": max(h, w) / 2, "area": area})
    found.sort(key=lambda e: -e["area"])
    # Keep the largest, plus a second eye of similar size and height if present.
    if len(found) >= 2:
        a, b = found[0], found[1]
        if abs(a["cy"] - b["cy"]) < 1.2 * a["r"] and 0.5 < b["area"] / a["area"] < 2.0:
            return sorted([a, b], key=lambda e: e["cx"])
    return found[:1]


def anchor(path: Path) -> dict | None:
    img = np.asarray(Image.open(path).convert("RGBA"))
    H, W = img.shape[:2]
    es = eyes(img)
    if not es:
        return None
    if len(es) == 2:
        l, r = es
        x = (l["cx"] + r["cx"]) / 2
        y = max(l["cy"], r["cy"]) + 1.55 * max(l["r"], r["r"])
        width = 0.55 * (r["cx"] - l["cx"])
    else:  # profile: mouth below and slightly ahead of the single eye
        e = es[0]
        x, y, width = e["cx"] + 0.35 * e["r"], e["cy"] + 1.7 * e["r"], 1.3 * e["r"]
    return {"x": round(x / W, 4), "y": round(y / H, 4), "width": round(width / W, 4), "eyes": len(es)}


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(Path(p).name, json.dumps(anchor(Path(p))))
