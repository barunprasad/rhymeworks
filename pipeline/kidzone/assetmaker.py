"""New library assets (characters, props, scenes): describe → 4 FLUX options → pick → saved to assets/ + registry.toml.

  kidzone asset <draft id>        make 4 more options for a draft in studio/drafts/<id>/

A draft is a folder studio/drafts/<id>/ with draft.json (what you asked for) and cand_<seed>.png options. Nothing touches
assets/ until you pick one (save()). The style prefix is the one the existing cast/scenes were made with, so new things
match Gopu, Minu and the village. The writer LLM suggests how prompts should refer to the new thing (`ref`) and a
consistency rule (`style`), which you can change before saving.
"""

import datetime as dt
import json
import os
import random
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

from .core import IMAGE_ENV, ROOT, chat_json, log, wait_ollama_unloaded

from .paths import ASSETS, DRAFTS, REGISTRY  # noqa: E402,F401
FLUX = ["--model", "mflux-community/flux2-klein-4b-mflux-q4", "--base-model", "flux2-klein-4b", "--steps", "4"]
# A draft folder may hold reference.jpg (e.g. a photo of the user, who asked for a cartoon of themselves): edit mode then
# restyles that photo; it never leaves the gitignored studio/drafts folder.
REF_PROMPT = ("Turn the person in the image into a {style}. Keep their face shape, eyes, nose, smile, skin tone and hairstyle so they "
              "are clearly recognisable, as a stylised Pixar character, not a photo. {desc}")
KINDS = {
    # registry section: (folder, width, height, style prefix used for the existing assets)
    "cast": ("cast", 768, 1024, "3D animated movie character, Pixar-style CGI render, full body, standing, centered, soft studio lighting, "
             "subsurface scattering, big expressive eyes, cute and friendly, plain soft warm cream background, character reference"),
    "props": ("props", 1280, 720, "3D animated movie prop, Pixar-style CGI render, the whole object in view, centered, three-quarter view, "
              "soft studio lighting, vibrant saturated colours, plain soft warm cream background, prop reference, no people, no text"),
    "scenes": ("scenes", 1280, 720, "3D animated movie background, Pixar-style CGI environment, wide establishing shot, no people, no characters, "
               "vibrant saturated colours, soft cinematic lighting, depth of field, magical and joyful, empty open space in the foreground for characters"),
}
PER_ROUND = 4

REF_SYSTEM = """You name things for an image-prompt system of a Pixar-style kids' video. Given a character or prop description, write
`ref`: a short noun phrase starting with "the" that picks it out visually in a scene with other characters (e.g. "the white calf
with the bell", "the boy in the orange kurta"), at most 12 words, no names; and `style`: one sentence that keeps its look
consistent across shots, naming its 2-3 most important visual details (e.g. "The calf keeps its brass bell on a red string.").
For scenes return an empty style and a ref like "the lotus pond at sunset"."""
REF_SCHEMA = {"type": "object", "properties": {"ref": {"type": "string"}, "style": {"type": "string"}}, "required": ["ref", "style"]}


def snake(name: str) -> str:
    """'Kela the Banana' → 'kela_banana' (the library's name_kind style)."""
    words = [w for w in re.split(r"[^a-z0-9]+", name.lower()) if w and w not in ("the", "a", "an")]
    return "_".join(words)[:40]


def registry() -> dict:
    return tomllib.loads(REGISTRY.read_text())


def taken(asset_id: str) -> bool:
    reg = registry()
    return asset_id in reg.get("cast", {}) or asset_id in reg.get("props", {}) or asset_id in reg.get("scenes", {})


# ---------------------------------------------------------------- drafts

def draft_dir(did: str) -> Path:
    if not re.fullmatch(r"[a-z0-9_]{2,48}", did):
        raise ValueError(f"bad draft id {did!r}")
    return DRAFTS / did


def load(did: str) -> dict:
    d = draft_dir(did)
    data = json.loads((d / "draft.json").read_text())
    data["candidates"] = sorted((p.name for p in d.glob("cand_*.png")), key=lambda n: (d / n).stat().st_mtime)
    data["saved"] = json.loads((d / "saved.json").read_text()) if (d / "saved.json").exists() else None
    return data


def create(kind: str, name: str, description: str, person: bool = False) -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {list(KINDS)}")
    if not name.strip() or not description.strip():
        raise ValueError("give it a name and a description")
    base = snake(name) or kind
    did, n = base, 2
    while (DRAFTS / did).exists() or taken(did):
        did, n = f"{base}_{n}", n + 1
    d = draft_dir(did)
    d.mkdir(parents=True)
    data = {"id": did, "kind": kind, "name": name.strip(), "description": description.strip(), "person": bool(person),
            "created": dt.datetime.now().isoformat(timespec="seconds"), "ref": None, "style": None}
    (d / "draft.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return load(did)


def update(did: str, **fields) -> dict:
    d = draft_dir(did)
    data = json.loads((d / "draft.json").read_text())
    data.update({k: v for k, v in fields.items() if k in ("name", "description", "person", "ref", "style")})
    (d / "draft.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return load(did)


def discard(did: str) -> None:
    d = draft_dir(did)
    if d.exists() and d.parent == DRAFTS:
        shutil.rmtree(d)


def drafts() -> list[dict]:
    if not DRAFTS.exists():
        return []
    out = []
    for p in sorted(DRAFTS.glob("*/draft.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            dr = load(p.parent.name)
            if not dr["saved"]:   # saved drafts are done; their folder stays until you clean up studio/drafts
                out.append(dr)
        except (ValueError, json.JSONDecodeError):
            continue
    return out


# ---------------------------------------------------------------- generation (GPU job)

def suggest_ref(data: dict, chat=chat_json) -> dict:
    try:
        r = chat(REF_SYSTEM, f"Kind: {data['kind']}. Name: {data['name']}. Description: {data['description']}", REF_SCHEMA, temperature=0.3)
        ref = r["ref"].strip().rstrip(".")
        return {"ref": ref if ref.lower().startswith("the ") else f"the {ref}", "style": r["style"].strip() or None}
    except Exception as e:  # noqa: BLE001 - suggestions are optional
        log("asset", f"no ref suggestion ({e})")
        return {"ref": f"the {data['name'].lower()}", "style": None}


def make_options(did: str, n: int = PER_ROUND) -> list[Path]:
    data = load(did)
    d = draft_dir(did)
    if data["kind"] != "scenes" and not data.get("ref"):
        log("asset", "suggesting how prompts should name it …")
        data = update(did, **suggest_ref(data))
    wait_ollama_unloaded()
    folder, w, h, style = KINDS[data["kind"]]
    prompt = f"{style}. {data['description']}"
    used = {int(re.search(r"\d+", p).group()) for p in data["candidates"]}
    ref_img = next((p for p in d.glob("reference.*") if p.suffix.lower() in (".jpg", ".jpeg", ".png")), None)
    if ref_img is not None and not data.get("adult_consent"):
        # Channel rule: no photos of children. A photo reference is only for an adult who agreed to it, confirmed in
        # draft.json ("adult_consent": true). The photo itself stays in studio/drafts on this computer (never synced).
        raise ValueError(f"{did}: reference photo needs \"adult_consent\": true in draft.json "
                         "(only photos of an adult who agreed; never children)")
    made = []
    for _ in range(n):
        seed = random.randint(1000, 99999)
        while seed in used:
            seed += 1
        used.add(seed)
        out = d / f"cand_{seed}.png"
        print(f"key cand_{seed}", flush=True)   # progress line for the studio worker
        use_ref = ref_img is not None   # a reference photo: draw every option from it
        cmd = (["mflux-generate-flux2-edit", *FLUX, "--image-paths", str(ref_img), "--prompt", REF_PROMPT.format(style=style, desc=data["description"])]
               if use_ref else ["mflux-generate-flux2", *FLUX, "--prompt", prompt])
        res = subprocess.run(["uv", "run", "--project", str(IMAGE_ENV), *cmd, "--width", str(w), "--height", str(h),
                              "--seed", str(seed), "--output", str(out)], capture_output=True, text=True,
                             env={**os.environ, "HF_HUB_OFFLINE": "1", "AGX_RELAX_CDM_CTXSTORE_TIMEOUT": "1"})
        if res.returncode or not out.exists():
            raise RuntimeError(f"FLUX failed: {(res.stderr or res.stdout)[-800:]}")
        made.append(out)
    log("asset", f"{did}: {len(made)} new options")
    return made


# ---------------------------------------------------------------- save into the library

def _insert_block(text: str, before_patterns: list[str], block: str) -> str:
    for pat in before_patterns:
        m = re.search(pat, text, re.M)
        if m:
            return text[:m.start()].rstrip("\n") + "\n\n" + block.strip("\n") + "\n\n" + text[m.start():]
    return text.rstrip("\n") + "\n\n" + block.strip("\n") + "\n"


def save(did: str, candidate: str, asset_id: str, ref: str | None = None, style: str | None = None,
         person: bool | None = None, keep: str | None = None) -> dict:
    data = load(did)
    kind = data["kind"]
    if candidate not in data["candidates"]:
        raise ValueError(f"no option {candidate}")
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", asset_id):
        raise ValueError("the token must be lowercase letters, digits and _ (e.g. kela_banana)")
    if taken(asset_id):
        raise ValueError(f"{{{asset_id}}} is already in the library")
    folder = KINDS[kind][0]
    rel = f"{folder}/{asset_id}.png"
    dest = ASSETS / rel
    if dest.exists():
        raise ValueError(f"assets/{rel} already exists")
    text = REGISTRY.read_text()
    q = lambda s: json.dumps(s, ensure_ascii=False)
    if kind == "scenes":
        m = re.search(r"^\[scenes\]\s*$", text, re.M)
        if not m:
            out = text.rstrip("\n") + f"\n\n[scenes]\n{asset_id} = {q(rel)}\n"
        else:
            nxt = re.search(r"^\[", text[m.end():], re.M)
            end = m.end() + (nxt.start() if nxt else len(text) - m.end())
            body = text[m.end():end].rstrip("\n")
            out = text[:m.end()] + body + f"\n{asset_id} = {q(rel)}   # {data['name']} (studio)\n" + ("\n" + text[end:] if nxt else "")
    else:
        ref = (ref or data.get("ref") or f"the {data['name'].lower()}").strip()
        lines = [f"[{kind}.{asset_id}]", f"file = {q(rel)}", f"ref = {q(ref)}"]
        style = style if style is not None else data.get("style")
        if style:
            lines.append(f"style = {q(style.strip())}")
        if kind == "props" and keep:
            lines.append(f"keep = {q(keep.strip())}")
        if kind == "cast" and (person if person is not None else data.get("person")):
            lines.append("person = true")
        block = f"# {data['name']}: made in the studio {dt.date.today().isoformat()}\n" + "\n".join(lines)
        before = [r"^# -+ props", r"^\[props\."] if kind == "cast" else [r"^# -+ scenes", r"^\[scenes\]"]
        out = _insert_block(text, before, block)
    reg = tomllib.loads(out)   # never write a broken registry
    assert asset_id in reg.get(kind, {})
    shutil.copy(draft_dir(did) / candidate, dest)
    REGISTRY.write_text(out)
    (draft_dir(did) / "saved.json").write_text(json.dumps({"id": asset_id, "file": rel, "candidate": candidate}))
    return {"id": asset_id, "kind": kind, "file": rel}


def main(args) -> None:
    make_options(args.draft)
