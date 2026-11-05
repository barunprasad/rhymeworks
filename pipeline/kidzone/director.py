"""Director: storyboard + timings → episode.json for the Remotion renderer (one per language).

Turns per-line intent (singers, shot, actions, props, scene) into keyframes on the real word/beat
timeline: entrances, front/back staging, default actions per character type, jumps with anticipation,
spins on the word "spin", camera shots, props popping on beats, name callouts, confetti, iris wipes.
"""

import json
import shutil
from pathlib import Path

from PIL import Image

from .core import IMAGE_ENV, LIB, Episode, read_json, run_tool, write_json
from .models import Storyboard

FPS = 60  # render rate; all motion is time-based so more frames = smoother
MOUTH_FPS = 30  # sample rate of the mouth track from alignment (interpolated by the renderer)
NAME_COLORS = ["#ff7eb6", "#a77bff", "#3d9bff", "#ff9f43", "#2ec4a6", "#ff5e5e"]
PROP_COLORS = ["#e8453c", "#d98a00", "#ef6c00", "#3f9e34", "#8a4fd6", "#2f7fe0"]  # dark enough to read on sky
BACK_SLOTS = [330, 1590, 580, 1340, 180, 1740]
LYRICS_BAND = 150  # px at the bottom of the frame reserved for the karaoke bar


class Publisher:
    """Copies show/episode assets into packages/compositions/public/ep/<slug>/ (cut versions where they exist)."""

    def __init__(self, ep: Episode, show: dict):
        self.ep, self.show = ep, show
        self.lib = LIB / show["id"]
        self.root = ep.public
        self.root.mkdir(parents=True, exist_ok=True)

    def ensure_cut(self, rel: str, kind: str) -> Path:
        src = self.lib / rel
        cut = src.with_suffix(".cut.png")
        if not cut.exists():
            args = {"bg": ["--seed-top"], "char": [], "prop": ["--holes", "0.01"]}[kind]
            run_tool(IMAGE_ENV, "cutout.py", *args, str(src))
        return cut

    def file(self, rel: str, kind: str = "prop", full_frame: bool = False) -> str:
        cut = self.ensure_cut(rel, "bg" if full_frame else kind) if not rel.endswith(".cut.png") else self.lib / rel
        dest = self.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if full_frame:
            meta = read_json(cut.with_suffix(".json"))
            canvas = Image.new("RGBA", Image.open(self.lib / rel).size, (0, 0, 0, 0))
            canvas.paste(Image.open(cut), (meta["crop"][0], meta["crop"][1]))
            canvas.save(dest)
        else:
            shutil.copy(cut, dest)
        return f"ep/{self.ep.slug}/{rel}"

    def rig(self, rel_dir: str) -> dict:
        src = self.lib / rel_dir
        dest = self.root / rel_dir
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns("rig_debug.png", "rig.json", "*.cut.*"))
        rig = read_json(src / "rig.json")
        rig["base"] = f"ep/{self.ep.slug}/{str(Path(rel_dir).parent)}/"
        return rig

    def raw(self, src: Path, name: str) -> str:
        dest = self.root / name
        shutil.copy(src, dest)
        return f"ep/{self.ep.slug}/{name}"


def character_defs(pub: Publisher, cast: list[dict]) -> dict:
    defs = {}
    for c in cast:
        if c["type"] == "rig":
            defs[c["id"]] = {"rig": pub.rig(c["rig"]), "poses": {}, "height": c["height"], "mouthMode": c["mouth"]}
        else:
            poses = {}
            for name, rel in c["poses"].items():
                url = pub.file(rel, "char")
                m = read_json((pub.lib / rel).with_suffix(".cut.json"))
                poses[name] = {"src": url, "w": m["size"][0], "h": m["size"][1]}
            d = {"poses": poses, "height": c["height"], "mouthMode": c["mouth"]}
            if c.get("beak"):
                d["beak"] = c["beak"]
            if c.get("fly"):
                d["fly"] = c["fly"]
            defs[c["id"]] = d
    return defs


def default_action(c: dict, singing: bool, kind: str) -> str:
    if c["type"] == "rig" and c.get("signature"):  # octopus-style rigs have a signature dance
        if singing:
            return c.get("signature", "dance") if kind in ("verse", "intro") else "dance"
        return "sway" if "sway" in c["actions"] else "dance"
    if singing:
        return "clap" if kind == "chorus" and "clap" in c["actions"] else "dance" if "dance" in c["actions"] else c["actions"][0]
    return "idle" if "idle" in c["actions"] else c["actions"][0]


def build(ep: Episode, show: dict, sb: Storyboard, lang: str, timing: dict, props: dict[str, str], song_file: str, pub: Publisher) -> dict:
    align, beats = timing["align"], timing["beats"]["beats"]
    segs = align["segments"]
    lines = sb.lines()
    n = min(len(lines), len(segs))
    cast = {c["id"]: c for c in show["cast"]}
    ground = show["ground_y"]
    end = min(segs[n - 1]["end"] + 2.8, len(align["mouth"]) / MOUTH_FPS)

    # Section index per line, and section time bounds.
    sec_of, sec_bounds, k = [], [], 0
    for si, sec in enumerate(sb.sections):
        start_k = k
        for _ in sec.lines:
            sec_of.append(si)
            k += 1
        if start_k < n:
            sec_bounds.append((segs[start_k]["start"], segs[min(k, n) - 1]["end"]))
        else:
            sec_bounds.append((end, end))

    tracks: dict[str, list] = {}
    state: dict[str, dict] = {}  # current x, y, scale, pose
    present: list[str] = []
    camera = [{"t": 0, "cx": 960, "cy": 540, "zoom": 1.0}]
    singing, callouts, effects, prop_items = [], [], [], []
    named: set[str] = set()
    prev_shot = None

    def key(cid: str, **kw):
        tracks.setdefault(cid, []).append(kw)

    for i in range(n):
        ln, seg, sec = lines[i], segs[i], sb.sections[sec_of[i]]
        ls, le = seg["start"], seg["end"]
        involved = list(dict.fromkeys(ln.singers + [a.who for a in ln.actions]))
        for cid in involved:
            if cid in cast and cid not in present:
                present.append(cid)
        front = [s for s in ln.singers if s in present]
        back = [c for c in present if c not in front]
        spacing = min(440, 1150 / max(1, len(front)))
        targets = {}
        fixed = show.get("front_x")  # shows can keep the centre clear (e.g. a centrepiece altar)
        for j, cid in enumerate(front):
            fly = cast[cid]["travel"] == "fly"
            if fixed and len(front) <= len(fixed):
                x = fixed[j] if len(front) > 1 else fixed[list(cast).index(cid) % len(fixed)]
            else:
                x = 960 + (j - (len(front) - 1) / 2) * spacing
            targets[cid] = (x, 40 if fly else 0, 1.0)
        for j, cid in enumerate(back):
            fly = cast[cid]["travel"] == "fly"
            if fixed and len(cast) <= len(fixed):  # fixed-side shows: non-singers stay on their own side
                targets[cid] = (fixed[list(cast).index(cid) % len(fixed)], 40 if fly else 0, 1.0)
            else:
                targets[cid] = (BACK_SLOTS[j % len(BACK_SLOTS)], 210 if fly else 0, 0.62 if fly else 0.78)

        acts = {a.who: a.action for a in ln.actions}
        for cid in present:
            c = cast[cid]
            x, y, sc = targets[cid]
            action = acts.get(cid) or default_action(c, cid in front, sec.kind)
            pose = c.get("action_poses", {}).get(action, action) if c["type"] == "poses" else action
            directional = c["type"] == "poses"
            facing = (1 if x < 960 else -1) if directional else 1
            travel = c["travel"] if c["type"] == "poses" or c["travel"] == "fly" else "walk"
            look = None
            if ln.props:
                look = {"x": 0.3, "y": -0.7}
            elif ln.focus and ln.focus != cid and ln.focus in targets:
                look = {"x": 0.9 if targets[ln.focus][0] > x else -0.9, "y": 0}

            if cid not in state:  # entrance from the side it will stand on
                sx = -280 if x < 960 else 2200
                key(cid, t=max(0.0, ls - 1.6), x=sx, y=260 if travel == "fly" else 0, pose=pose, facing=(1 if sx < 0 else -1) if directional else 1, scale=sc)
                key(cid, t=ls + 0.1, x=x, y=y, pose=pose, move=travel, facing=facing, scale=sc)
            elif abs(state[cid]["x"] - x) > 40 or state[cid]["scale"] != sc:
                st = state[cid]
                key(cid, t=max(ls - 0.5, st["t"] + 0.05), x=st["x"], y=st["y"], pose=st["pose"], facing=st["facing"], scale=st["scale"])
                key(cid, t=ls + 0.25, x=x, y=y, pose=pose, move=travel, facing=facing, scale=sc)

            t0 = ls + 0.3 if cid in state else ls + 0.15
            if action == "cheer" and c["type"] == "rig" and "squat" in c["actions"]:
                key(cid, t=t0, x=x, y=y, pose="squat", facing=facing, scale=sc)
                key(cid, t=t0 + 0.4, x=x, y=y, pose="cheer", move="jump", facing=facing, scale=sc, look={"x": 0, "y": -0.8})
                key(cid, t=t0 + 0.45, x=x, y=y, pose="cheer", facing=facing, scale=sc)
            elif action == "spin":
                spin_t = next((w["start"] for w in seg["words"] if any(s in w["w"].lower() for s in ("spin", "घूम", "round"))), t0)
                key(cid, t=max(t0, spin_t), x=x, y=y, pose="spin", facing=facing, scale=sc)
                key(cid, t=max(t0, spin_t) + 1.0, x=x, y=y, pose="dance", facing=facing, scale=sc)
            else:
                kf = {"t": t0, "x": x, "y": y, "pose": pose, "facing": facing, "scale": sc}
                if look:
                    kf["look"] = look
                key(cid, **kf)
            state[cid] = {"x": x, "y": y, "scale": sc, "pose": pose, "facing": facing, "t": tracks[cid][-1]["t"]}

            if cid in front and cid not in named and len(cast) > 1:
                named.add(cid)
                callouts.append({"t": ls + 0.15, "text": c["name"][lang], "x": x, "y": 440, "color": NAME_COLORS[list(cast).index(cid) % len(NAME_COLORS)], "dur": 1.5})

        singing.append({"start": ls, "end": le, "who": front})

        # Camera
        # Framing: keep the whole character (head to feet, plus room for a jump) above the lyrics bar.
        # Usable frame = 1080 px minus LYRICS_BAND at the bottom and a small top margin.
        if ln.shot == "wide" or not ln.focus or ln.focus not in targets:
            # Wide: shift down just enough that the ground line sits above the lyrics bar.
            cy = 540 + max(0, ground + 30 - (1080 - LYRICS_BAND))
            shot = {"cx": 960, "cy": cy, "zoom": 1.0}
        else:
            fx, fy, fsc = targets[ln.focus]
            h = cast[ln.focus]["height"] * fsc
            jumping = acts.get(ln.focus) == "cheer"
            headroom = 230 if jumping else 70
            want = 1.22 if ln.shot == "medium" else 1.5
            fit = (1080 - LYRICS_BAND - 40) / (h + fy + headroom + 30)
            z = max(1.0, min(want, fit, show.get("max_zoom", 9.0)))
            feet_screen = 1080 - LYRICS_BAND - 20  # feet sit just above the lyrics bar
            cy = (ground - fy) - (feet_screen - 540) / z
            half_w = 960 / z
            shot = {"cx": max(half_w - 60, min(1920 - half_w + 60, fx)), "cy": cy, "zoom": round(z, 3)}
        cut = (ln.shot, ln.focus) != prev_shot
        camera.append({"t": ls - 0.05, **shot, "cut": cut} if cut else {"t": ls - 0.05, **shot})
        camera.append({"t": le, "cx": shot["cx"], "cy": shot["cy"], "zoom": round(shot["zoom"] + 0.06, 3)})
        prev_shot = (ln.shot, ln.focus)

        # Props pop on the beats of this line, stay until the section ends.
        if ln.props:
            line_beats = [b for b in beats if ls - 0.05 <= b <= le] or [ls + (le - ls) * f for f in (0.1, 0.35, 0.6, 0.85)]
            while len(line_beats) < len(ln.props):
                line_beats.append(line_beats[-1] + 0.3)
            in_section = [p for p in prop_items if p["_sec"] == sec_of[i] and p["_wide"]]
            # Shows with a protected centrepiece (prop_row) always use their prop row, even in close-ups.
            close_up = ln.shot != "wide" and ln.focus in targets and "prop_row" not in show
            for k2, pr in enumerate(ln.props):
                if close_up:
                    # Beside the featured character at head height, on the side facing the centre, so the
                    # zoomed camera keeps it in frame; it leaves when the shot changes.
                    fx, fy, fsc = targets[ln.focus]
                    fh = cast[ln.focus]["height"] * fsc
                    side = 1 if fx <= 960 else -1
                    gap = 300 if ln.shot == "medium" else 240
                    px, py, ph = fx + side * (gap + k2 * 190), ground - fy - fh * 0.72, 150
                    until, wide = le + 0.8, False
                else:
                    slot = len(in_section) + k2
                    row = show.get("prop_row", {"y": 300, "x0": 480, "dx": 240})
                    px, py, ph = row["x0"] + (slot % 5) * row["dx"], row["y"] if slot < 5 else row["y"] - 120, 170
                    until, wide = sec_bounds[sec_of[i]][1] + 0.2, True
                prop_items.append({
                    "_sec": sec_of[i], "_wide": wide, "src": pub.file(props[pr.id]), "t": line_beats[k2], "until": until,
                    "x": px, "y": py, "h": ph,
                    **({"label": pr.label, "labelColor": PROP_COLORS[(len(prop_items)) % len(PROP_COLORS)]} if pr.label else {}),
                })

        # Confetti at the end of each chorus / the outro.
        last_in_sec = i + 1 >= n or sec_of[i + 1] != sec_of[i]
        if last_in_sec and sec.kind in ("chorus", "outro"):
            effects.append({"type": "confetti", "t": le - 0.3, "dur": 2.2})

    # Scenes + iris transitions on scene changes.
    scene_defs = {s["id"]: s for s in show["scenes"]}
    scenes, transitions, last_scene = [], [], None
    for si, sec in enumerate(sb.sections):
        if sec.scene == last_scene:
            continue
        start = 0.0 if not scenes else sec_bounds[si][0] - 0.35
        layers = [{**{k: v for k, v in L.items() if k not in ("src", "full_frame")}, "src": pub.file(L["src"], full_frame=L.get("full_frame", False))} for L in scene_defs[sec.scene]["layers"]]
        scenes.append({"start": start, "layers": layers})
        if last_scene is not None:
            transitions.append({"t": start, "type": "iris", "dur": 0.9})
        last_scene = sec.scene

    sky = dict(show["sky"])
    for k2 in ("clouds", "sun"):
        if sky.get(k2):
            sky[k2] = pub.file(sky[k2])
    episode = {
        "fps": FPS,
        "durationSec": round(end, 2),
        "audio": song_file,
        "lang": lang,
        "groundY": ground,
        "beats": [b for b in beats if b < end],
        "mouth": align["mouth"][: int(end * MOUTH_FPS) + 1],
        "mouthFps": MOUTH_FPS,
        "segments": segs[:n],
        "sky": sky,
        "layers": scenes[0]["layers"],
        "scenes": scenes,
        "transitions": transitions,
        "characters": character_defs(pub, [cast[c] for c in present]),
        "tracks": tracks,
        "singing": singing,
        "camera": sorted(camera, key=lambda c: c["t"]),
        "props": [{k2: v for k2, v in p.items() if not k2.startswith("_")} for p in prop_items],
        "callouts": callouts,
        "effects": effects,
    }
    if show.get("petals"):
        episode["petals"] = {"src": pub.file(show["petals"]["src"]), "count": show["petals"].get("count", 24)}
    if show.get("swimmers"):
        episode["swimmers"] = [{**s, "src": pub.file(s["src"])} for s in show["swimmers"]]
    return episode


def run(ep: Episode, show: dict, sb: Storyboard, timings: dict, props: dict, audio: dict[str, str]) -> dict[str, Path]:
    """audio: {lang: release audio path relative to songs/} (same timing as the aligned take)."""
    pub = Publisher(ep, show)
    out = {}
    for lang, timing in timings.items():
        song_url = pub.raw(ep.path("songs", audio[lang]), f"song_{lang}.wav")
        episode = build(ep, show, sb, lang, timing, props, song_url, pub)
        f = ep.path(f"episode_{lang}.json")
        write_json(f, {"episode": episode})
        out[lang] = f
    return out
