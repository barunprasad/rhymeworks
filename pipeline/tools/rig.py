"""Auto-rig a flat-vector character from a rig-pose cutout (arms/legs separated from the body).

Thick dark outlines separate the coloured regions, so: label the non-outline regions, classify the
big ones (head / body / arms / legs / antenna) by geometry, attach small details (eyes, cheeks,
highlights) to the region that encloses them, give every outline pixel to its nearest part, and
find joint pivots where parts meet. Pupils become their own layers so eyes can look around.
Writes <dir>/rig/*.png + rig.json + rig_debug.png (colour-coded parts, pivots as dots).
Usage (image env): python rig.py <rig.cut.png>
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

COLORS = {
    "head": (66, 135, 245), "body": (245, 166, 35), "arm_l": (80, 200, 120), "arm_r": (40, 150, 80),
    "leg_l": (200, 80, 200), "leg_r": (140, 50, 140), "antenna": (240, 220, 40), "extra": (150, 150, 150),
}


def octo(path: Path) -> None:
    """Head + tentacle 'skirt' split for octopus-like characters (no limbs). Eyes/pupils as usual."""
    img = np.asarray(Image.open(path).convert("RGBA")).copy()
    H, W = img.shape[:2]
    rgb, alpha = img[..., :3].astype(int), img[..., 3]
    body = alpha > 128
    total = body.sum()
    white = body & np.all(rgb > 225, axis=-1)
    wl, _ = ndimage.label(white)
    eyes = []
    for k, sl in enumerate(ndimage.find_objects(wl), start=1):
        if sl is None:
            continue
        a = (wl[sl] == k).sum()
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if a < 0.0015 * total or not (0.55 < w / max(1, h) < 1.8) or (sl[0].start + sl[0].stop) / 2 > 0.75 * H:
            continue
        pupil = ndimage.binary_fill_holes(wl == k) & ~(wl == k)
        if pupil.sum() < 20:
            continue
        py, px = np.nonzero(pupil)
        eyes.append({"mask": pupil, "cx": float((sl[1].start + sl[1].stop) / 2), "cy": float((sl[0].start + sl[0].stop) / 2),
                     "r": float(max(h, w) / 2), "pcx": float(px.mean()), "pcy": float(py.mean()),
                     "white": [int(c) for c in np.median(rgb[wl == k], axis=0)], "area": a})
    eyes = sorted(sorted(eyes, key=lambda e: -e["area"])[:2], key=lambda e: e["cx"])
    if not eyes:
        raise SystemExit(f"no eyes found in {path}")
    er = max(e["r"] for e in eyes)
    ey = max(e["cy"] for e in eyes)
    split = int(min(H - 1, ey + 2.3 * er))  # just below the mouth
    out_dir = path.parent / "rig"
    out_dir.mkdir(exist_ok=True)

    head_m = body.copy()
    head_m[split:] = False
    skirt_m = body.copy()
    skirt_m[: max(0, split - 24)] = False  # overlap band hides the seam when the skirt deforms

    fill = body & ~np.all(rgb < 95, axis=-1)
    skin = "#%02x%02x%02x" % tuple(int(c) for c in np.median(rgb[head_m & fill & ~white], axis=0))
    parts = []
    for name, m, z in (("skirt", skirt_m, 0), ("head", head_m, 1)):
        layer = img.copy()
        layer[~m] = 0
        if name == "head":
            for e in eyes:
                hole = ndimage.binary_fill_holes(ndimage.binary_dilation(e["mask"], iterations=2)) & body
                layer[hole, :3] = e["white"]
                layer[hole, 3] = 255
        yy, xx = np.nonzero(m)
        x0, y0, x1, y1 = xx.min(), yy.min(), xx.max() + 1, yy.max() + 1
        Image.fromarray(layer[y0:y1, x0:x1]).save(out_dir / f"{name}.png")
        parts.append({"name": name, "src": f"rig/{name}.png", "x": int(x0), "y": int(y0), "w": int(x1 - x0), "h": int(y1 - y0), "z": z})
    for k, e in enumerate(eyes):
        layer = img.copy()
        layer[~e["mask"]] = 0
        yy, xx = np.nonzero(e["mask"])
        x0, y0, x1, y1 = xx.min(), yy.min(), xx.max() + 1, yy.max() + 1
        Image.fromarray(layer[y0:y1, x0:x1]).save(out_dir / f"pupil_{k}.png")
        e.update(src=f"rig/pupil_{k}.png", x=int(x0), y=int(y0), w=int(x1 - x0), h=int(y1 - y0))
    if len(eyes) == 2:
        mouth = {"x": (eyes[0]["cx"] + eyes[1]["cx"]) / 2, "y": ey + 1.5 * er, "width": 0.6 * (eyes[1]["cx"] - eyes[0]["cx"])}
    else:
        mouth = {"x": eyes[0]["cx"], "y": ey + 1.6 * er, "width": 1.2 * er}
    ys, xs = np.nonzero(body)
    rig = {
        "kind": "octo",
        "size": [W, H],
        "skin": skin,
        "parts": parts,
        "pivots": {"skirt": {"x": float((xs.min() + xs.max()) / 2), "y": float(split)}, "head": {"x": float(W / 2), "y": float(split)}},
        "eyes": [{k: e[k] for k in ("src", "x", "y", "w", "h", "cx", "cy", "r", "pcx", "pcy")} for e in eyes],
        "mouth": mouth,
    }
    (out_dir / "rig.json").write_text(json.dumps(rig, indent=1, default=float))
    print(json.dumps({"kind": "octo", "eyes": len(eyes), "split": split, "size": [W, H]}))


def geometric_arm(body: np.ndarray, side: str, top_y: int) -> np.ndarray:
    """Arm cut by geometry for arms-out poses where clothing hides the sleeve/torso outline.
    Scan rows below the shoulder: where a row has a background gap between arm and torso, the torso's edge
    there is the cut line; the arm is everything beyond it that connects to the outermost (hand) pixels."""
    H, W = body.shape
    rows = range(top_y, int(top_y + 0.45 * H))
    edges = []
    for y in rows:
        xs = np.nonzero(body[y])[0]
        if xs.size < 2:
            continue
        gaps = np.nonzero(np.diff(xs) > 3)[0]
        if gaps.size == 0:
            continue
        # torso run edge next to the outermost gap on this side
        edges.append(xs[gaps[0] + 1] if side == "l" else xs[gaps[-1]])
    if not edges:
        return np.zeros_like(body)
    # Median, not extreme: braids/hair hanging beside the shoulders add spurious gaps near the top.
    cut = int(np.median(edges))
    zone = body.copy()
    zone[:top_y] = False
    # Stop just below the hand: a flared skirt lower down must not join the arm.
    ys_u, xs_u = np.nonzero(body[: int(top_y + 0.6 * H)])
    hand_y = ys_u[np.argmin(xs_u)] if side == "l" else ys_u[np.argmax(xs_u)]
    hand_rows = np.nonzero(body[:, xs_u.min() if side == "l" else xs_u.max()])[0]
    zone[int(max(hand_y, hand_rows.max() if hand_rows.size else hand_y) + 0.04 * H):] = False
    if side == "l":
        zone[:, cut:] = False
    else:
        zone[:, : cut + 1] = False
    lab, _ = ndimage.label(zone)
    ys, xs = np.nonzero(zone[: int(top_y + 0.6 * H)])
    if xs.size == 0:
        return np.zeros_like(body)
    k = np.argmin(xs) if side == "l" else np.argmax(xs)
    return lab == lab[ys[k], xs[k]]


def main(path: Path, geo_arms: bool = False) -> None:
    img = np.asarray(Image.open(path).convert("RGBA")).copy()
    H, W = img.shape[:2]
    rgb, alpha = img[..., :3].astype(int), img[..., 3]
    body = alpha > 128
    outline = body & np.all(rgb < 95, axis=-1)
    fill = body & ~outline
    labels, n = ndimage.label(fill)
    areas = ndimage.sum(np.ones_like(labels), labels, index=range(1, n + 1))
    total = body.sum()
    big = [i + 1 for i, a in enumerate(areas) if a > 0.006 * total]
    small = [i + 1 for i, a in enumerate(areas) if 0 < a <= 0.006 * total]

    ys, xs = np.nonzero(body)
    top, bottom, cx_char = ys.min(), ys.max(), (xs.min() + xs.max()) / 2
    span = bottom - top

    info = {}
    for i in big:
        yy, xx = np.nonzero(labels == i)
        info[i] = {"cy": yy.mean(), "cx": xx.mean(), "top": yy.min(), "bot": yy.max(), "left": xx.min(), "right": xx.max(), "area": len(yy)}

    # --- classify big regions ---
    part_of: dict[int, str] = {}
    by_area = sorted(big, key=lambda i: -info[i]["area"])
    # Head: the large region nearest the top among the two biggest-ish regions in the upper half.
    upper = [i for i in by_area[:4] if info[i]["cy"] < top + 0.5 * span]
    head = min(upper, key=lambda i: info[i]["top"]) if upper else by_area[0]
    part_of[head] = "head"
    hb = info[head]
    # Body: biggest remaining region whose centre is below the head and near the centre line.
    centre = [i for i in by_area if i != head and abs(info[i]["cx"] - cx_char) < 0.18 * W and info[i]["cy"] > hb["cy"]]
    bod = centre[0] if centre else [i for i in by_area if i != head][0]
    part_of[bod] = "body"
    bb = info[bod]
    bw = bb["right"] - bb["left"]
    body_mask = labels == bod

    def lateral(r: dict) -> str | None:
        """Arm if the region sits outside the torso's horizontal span at the region's height (a flared
        skirt or wide hem lower down must not hide arms). Only regions at torso height qualify."""
        if r["cy"] < bb["top"] or r["cy"] > bb["bot"]:
            return None
        y = int(r["cy"])
        for dy in range(0, int(bb["bot"] - bb["top"]) + 1, 4):
            for yy in (y - dy, y + dy):
                if bb["top"] <= yy <= bb["bot"]:
                    xs_row = np.nonzero(body_mask[yy])[0]
                    if xs_row.size:
                        lo, hi = xs_row.min(), xs_row.max()
                        w = hi - lo
                        if r["cx"] < lo + 0.08 * w and r["right"] < hi:
                            return "arm_l"
                        if r["cx"] > hi - 0.08 * w and r["left"] > lo:
                            return "arm_r"
                        return None
        return None

    for i in big:
        if i in part_of:
            continue
        r = info[i]
        if r["bot"] < hb["top"] + 0.15 * (hb["bot"] - hb["top"]):
            part_of[i] = "antenna"
        elif r["top"] > bb["bot"] - 0.15 * (bb["bot"] - bb["top"]) and bb["left"] < r["cx"] < bb["right"]:
            part_of[i] = "leg_l" if r["cx"] < cx_char else "leg_r"  # starts under the body: legs/feet
        elif (side := lateral(r)) is not None:  # beside the torso at its own height → arm (hands included)
            part_of[i] = side
        elif r["cy"] > bb["bot"] - 0.1 * (bb["bot"] - bb["top"]):
            part_of[i] = "leg_l" if r["cx"] < cx_char else "leg_r"
        elif hb["top"] <= r["cy"] <= hb["bot"]:
            part_of[i] = "head"
        else:
            part_of[i] = "body"

    # --- small details: attach to the big region that surrounds them most ---
    big_lab = np.zeros_like(labels)
    for i, name in part_of.items():
        big_lab[labels == i] = list(COLORS).index(name) + 1
    for i in small:
        m = labels == i
        ring = ndimage.binary_dilation(m, iterations=12) & ~m
        vals = big_lab[ring & (big_lab > 0)]
        if vals.size:
            big_lab[m] = np.bincount(vals).argmax()
        else:
            yy, xx = np.nonzero(m)
            big_lab[m] = list(COLORS).index("antenna" if yy.mean() < hb["top"] else "head") + 1
    head_i, ant_i = names_idx = (list(COLORS).index("head") + 1, list(COLORS).index("antenna") + 1)
    hm = big_lab == head_i
    widths = hm.sum(axis=1)
    rows = np.nonzero(widths)[0]
    if rows.size > 12:
        stick = np.median(widths[rows[:8]])  # the antenna stick is the narrow column on top
        if stick < 0.15 * widths.max():
            for y in rows:
                if widths[y] <= 1.6 * stick:
                    big_lab[y][hm[y]] = ant_i
                else:
                    break
    am = big_lab == ant_i
    if am.any():
        acols, hcols = np.nonzero(am.any(axis=0))[0], np.nonzero((big_lab == head_i).any(axis=0))[0]
        if hcols.size and (acols.max() - acols.min()) > 0.4 * (hcols.max() - hcols.min()):
            big_lab[am] = head_i  # not an antenna: hair/outline arc spanning the head
    # --- outline + any leftover pixels: nearest part ---
    _, (iy, ix) = ndimage.distance_transform_edt(big_lab == 0, return_indices=True)
    nearest = big_lab[iy, ix]
    part_lab = np.where(body, nearest, 0)

    if geo_arms:
        names_ = list(COLORS)
        head_rows = np.nonzero((big_lab == names_.index("head") + 1).any(axis=1))[0]
        neck_y = int(head_rows.max()) if head_rows.size else int(0.3 * H)
        body_i = names_.index("body") + 1
        for side, name in (("l", "arm_l"), ("r", "arm_r")):
            idx = names_.index(name) + 1
            arm = geometric_arm(body, side, neck_y) & ~(big_lab == names_.index("head") + 1)
            if arm.sum() < 0.01 * body.sum():
                continue
            # previous (region-based) arm pixels not in the geometric arm go back to the body
            part_lab[(part_lab == idx) & ~arm] = body_i
            big_lab[(big_lab == idx) & ~arm] = body_i
            part_lab[arm] = idx
            big_lab[arm & fill] = idx

    names = list(COLORS)
    out_dir = path.parent / "rig"
    out_dir.mkdir(exist_ok=True)

    # --- pupils: dark blobs inside eye whites on the head; cut them into their own layer ---
    head_idx = names.index("head") + 1
    white = (part_lab == head_idx) & np.all(rgb > 225, axis=-1)
    wl, wn = ndimage.label(white)
    eyes = []
    for k, sl in enumerate(ndimage.find_objects(wl), start=1):
        if sl is None:
            continue
        a = (wl[sl] == k).sum()
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if a < 0.0015 * total or not (0.55 < w / max(1, h) < 1.8):
            continue
        y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        box = np.zeros_like(body)
        box[y0:y1, x0:x1] = True
        # Pupil = the hole inside the eye white (dark pupil + its highlight), not the outer outline ring.
        pupil = ndimage.binary_fill_holes(wl == k) & ~(wl == k) & box
        if pupil.sum() < 20:
            continue
        py, px = np.nonzero(pupil)
        eyes.append({"mask": pupil, "cx": float((x0 + x1) / 2), "cy": float((y0 + y1) / 2), "r": float(max(h, w) / 2),
                     "pcx": float(px.mean()), "pcy": float(py.mean()), "white": [int(c) for c in np.median(rgb[wl == k], axis=0)]})

    # --- the drawn mouth: a dark stroke enclosed by the face, below the eyes. The renderer draws its own
    # animated mouth there, so the drawn one is painted out (otherwise it shows under the new one and the
    # pair reads as a moustache). ---
    drawn_mouth = None
    head_m0 = part_lab == head_idx
    if len(eyes) >= 2:
        le, re_ = sorted(eyes, key=lambda e: e["cx"])[:2]
        d_eye, ey, er = re_["cx"] - le["cx"], max(le["cy"], re_["cy"]), max(le["r"], re_["r"])
        y0b, y1b = int(ey + 0.9 * er), int(min(H, ey + 3.4 * er))
        x0b, x1b = int(le["cx"] - 0.15 * d_eye), int(re_["cx"] + 0.15 * d_eye)
        box = np.zeros_like(body)
        box[y0b:y1b, x0b:x1b] = True
        dark = body & np.all(rgb < 140, axis=-1) & head_m0 & box
        ml, mn = ndimage.label(dark)
        best = None
        for k, sl in enumerate(ndimage.find_objects(ml), start=1):
            if sl is None:
                continue
            hh, ww = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
            touches = sl[0].start <= y0b or sl[0].stop >= y1b or sl[1].start <= x0b or sl[1].stop >= x1b
            if touches or ww < 0.22 * d_eye or ww < hh:
                continue
            if best is None or ww > best[1]:
                best = (k, ww)
        if best:
            comp = ml == best[0]
            yy, xx = np.nonzero(comp)
            drawn_mouth = comp
            mouth_found = {"x": float((xx.min() + xx.max()) / 2), "y": float(yy.mean()),
                           "width": float(np.clip(1.15 * (xx.max() - xx.min()), 0.45 * d_eye, 0.8 * d_eye))}

    # Solid dark masses (hair, dark shoes) are "outline"-coloured but are real parts of the drawing: give
    # each to the part it belongs to instead of dropping it with the stray-outline cleanup below.
    thick = ndimage.binary_opening(outline, iterations=3)
    if drawn_mouth is not None:
        thick &= ~ndimage.binary_dilation(drawn_mouth, iterations=3)
    tl, tn = ndimage.label(thick)
    thick_of: dict[int, np.ndarray] = {}
    for k in range(1, tn + 1):
        comp = tl == k
        if comp.sum() < 0.002 * total:
            continue
        owner = np.bincount(part_lab[comp], minlength=len(COLORS) + 1)[1:].argmax() + 1
        grown = ndimage.binary_dilation(comp, iterations=4) & body & np.all(rgb < 140, axis=-1)
        thick_of[owner] = thick_of.get(owner, np.zeros_like(body)) | grown

    parts = []
    z_order = {"leg_l": 0, "leg_r": 0, "antenna": 1, "body": 2, "head": 3, "arm_l": 4, "arm_r": 4, "extra": 5}
    for name in names:
        own = big_lab == names.index(name) + 1
        if own.sum() < 30:
            continue
        m = part_lab == names.index(name) + 1
        # Every part keeps only pixels within ~a stroke of its main mass (fill with thin slivers
        # opened away). This drops stray outline curves that were "nearest" to a part but belong to
        # someone else's silhouette and would stay behind / swing along when limbs move.
        main = ndimage.binary_opening(own, iterations=6)
        if main.sum() < 0.5 * own.sum():
            main = own
        m = m & (ndimage.distance_transform_edt(~main) <= 14)
        if names.index(name) + 1 in thick_of:
            m = m | (thick_of[names.index(name) + 1] & (part_lab == names.index(name) + 1))
        if name in ("body", "head"):
            # Parents keep a closed outline where limbs attach (limbs rotate away and would leave gaps).
            m = m | (ndimage.binary_dilation(main, iterations=14) & outline)
        layer = img.copy()
        layer[~m] = 0
        if name == "head":
            for e in eyes:  # paint pupils out of the head as solid eye-white, so moving pupils reveal white
                hole = ndimage.binary_fill_holes(ndimage.binary_dilation(e["mask"], iterations=2)) & body
                layer[hole, :3] = e["white"]
                layer[hole, 3] = 255
            if drawn_mouth is not None:
                paint = ndimage.binary_dilation(drawn_mouth, iterations=3) & m
                ring = ndimage.binary_dilation(drawn_mouth, iterations=10) & ~ndimage.binary_dilation(drawn_mouth, iterations=4) & fill & m
                if ring.sum() > 10:
                    layer[paint, :3] = np.median(rgb[ring], axis=0).astype(np.uint8)
                    layer[paint, 3] = 255
        yy, xx = np.nonzero(m)
        x0, y0, x1, y1 = xx.min(), yy.min(), xx.max() + 1, yy.max() + 1
        Image.fromarray(layer[y0:y1, x0:x1]).save(out_dir / f"{name}.png")
        parts.append({"name": name, "src": f"rig/{name}.png", "x": int(x0), "y": int(y0), "w": int(x1 - x0), "h": int(y1 - y0), "z": z_order[name], "mask": m})

    for k, e in enumerate(eyes):
        layer = img.copy()
        layer[~e["mask"]] = 0
        yy, xx = np.nonzero(e["mask"])
        x0, y0, x1, y1 = xx.min(), yy.min(), xx.max() + 1, yy.max() + 1
        Image.fromarray(layer[y0:y1, x0:x1]).save(out_dir / f"pupil_{k}.png")
        e.update(src=f"rig/pupil_{k}.png", x=int(x0), y=int(y0), w=int(x1 - x0), h=int(y1 - y0))

    # --- pivots: where each limb meets its parent ---
    pm = {p["name"]: p["mask"] for p in parts}

    def contact(child: str, parent: str, fallback: tuple[float, float]) -> dict:
        if child not in pm or parent not in pm:
            return {"x": fallback[0], "y": fallback[1]}
        near = pm[child] & ndimage.binary_dilation(pm[parent], iterations=10)
        if near.sum() == 0:  # gap between limb and body: use the limb point closest to the parent
            d = ndimage.distance_transform_edt(~pm[parent])
            cy, cxx = np.unravel_index(np.where(pm[child], d, np.inf).argmin(), d.shape)
            return {"x": float(cxx), "y": float(cy)}
        yy, xx = np.nonzero(near)
        return {"x": float(xx.mean()), "y": float(yy.mean())}

    bbx = info[bod]
    pivots = {
        "head": contact("head", "body", (cx_char, hb["bot"])),
        "antenna": contact("antenna", "head", (cx_char, hb["top"])),
        "arm_l": contact("arm_l", "body", (bbx["left"], bbx["top"])),
        "arm_r": contact("arm_r", "body", (bbx["right"], bbx["top"])),
        "leg_l": contact("leg_l", "body", (cx_char - 0.1 * W, bbx["bot"])),
        "leg_r": contact("leg_r", "body", (cx_char + 0.1 * W, bbx["bot"])),
    }
    # Shoulders sit at the top of the arm contact; hips at the top of the leg contact.
    for limb in ("arm_l", "arm_r", "leg_l", "leg_r"):
        if limb in pm:
            yy, xx = np.nonzero(pm[limb])
            pivots[limb]["y"] = float(min(pivots[limb]["y"], yy.min() + 0.12 * (yy.max() - yy.min())))

    # Rest angles: how far each arm is drawn rotated from hanging straight down (same sign convention as
    # the renderer's joints). The renderer subtracts the excess so idle arms hang naturally.
    rest = {}
    for limb in ("arm_l", "arm_r"):
        if limb in pm:
            yy, xx = np.nonzero(pm[limb])
            dx, dy = xx.mean() - pivots[limb]["x"], yy.mean() - pivots[limb]["y"]
            rest[limb] = round(float(np.degrees(np.arctan2(-dx, max(1e-6, dy)))), 1)

    # Mouth: centred below the eyes.
    if drawn_mouth is not None:
        mouth = mouth_found
    elif len(eyes) >= 2:
        l, r = sorted(eyes, key=lambda e: e["cx"])[:2]
        mouth = {"x": (l["cx"] + r["cx"]) / 2, "y": max(l["cy"], r["cy"]) + 1.55 * max(l["r"], r["r"]), "width": 0.7 * (r["cx"] - l["cx"])}
    else:
        mouth = None

    head_fill = (big_lab == names.index("head") + 1) & fill & ~np.all(rgb > 225, axis=-1)
    skin = "#%02x%02x%02x" % tuple(int(c) for c in np.median(rgb[head_fill], axis=0))
    rig = {
        "size": [W, H],
        "skin": skin,
        "parts": [{k: v for k, v in p.items() if k != "mask"} for p in parts],
        "pivots": pivots,
        "rest": rest,
        "eyes": [{k: e[k] for k in ("src", "x", "y", "w", "h", "cx", "cy", "r", "pcx", "pcy")} for e in eyes],
        "mouth": mouth,
    }
    (out_dir / "rig.json").write_text(json.dumps(rig, indent=1, default=float))

    # Debug overlay
    dbg = np.zeros((H, W, 3), np.uint8) + 255
    for p in parts:
        dbg[p["mask"]] = COLORS[p["name"]]
    for e in eyes:
        dbg[e["mask"]] = (0, 0, 0)
    d = Image.fromarray(dbg)
    dr = ImageDraw.Draw(d)
    for nm, pv in pivots.items():
        dr.ellipse([pv["x"] - 9, pv["y"] - 9, pv["x"] + 9, pv["y"] + 9], fill=(255, 0, 0))
    if mouth:
        dr.ellipse([mouth["x"] - 6, mouth["y"] - 6, mouth["x"] + 6, mouth["y"] + 6], fill=(255, 0, 160))
    d.save(out_dir / "rig_debug.png")
    print(json.dumps({"rest": rest, "parts": [p["name"] for p in parts], "eyes": len(eyes), "big_regions": len(big), "pivots": {k: [round(v["x"]), round(v["y"])] for k, v in pivots.items()}}))


if __name__ == "__main__":
    if sys.argv[1] == "--octo":
        octo(Path(sys.argv[2]))
    else:
        main(Path(sys.argv[-1]), geo_arms="--geo-arms" in sys.argv)
