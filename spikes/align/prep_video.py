"""Build Remotion props for the mouth prototype: locate mouth/eyes with a local vision model,
copy assets into remotion/public, write props.json.

Mouth anchor comes from qwen3-vl:8b (already installed in Ollama) asked for normalized boxes.
Usage: python prep_video.py <character.png> <take-stem> <en|hi> [vision-model]
"""

import base64
import json
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "remotion" / "public"

ANCHOR_SCHEMA = {
    "type": "object",
    "required": ["mouth", "eyes"],
    "properties": {
        "mouth": {
            "type": "object",
            "required": ["x", "y", "width"],
            "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "width": {"type": "number"}},
        },
        "eyes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["x", "y", "r"],
                "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "r": {"type": "number"}},
            },
        },
    },
}

PROMPT = """This is a cartoon character on a plain background. Return the position of its mouth and eyes as
fractions of the image (0..1, origin top-left): mouth center x,y and mouth width; each eye center x,y and
radius r. If the mouth is not drawn, estimate where it would be on the face (below the eyes, centered)."""


def locate(image: Path, model: str) -> dict:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT, "images": [base64.b64encode(image.read_bytes()).decode()]}],
        "format": ANCHOR_SCHEMA,
        "stream": False,
        "keep_alive": 0,
        "think": False,
        "options": {"temperature": 0},
    }
    req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(json.load(r)["message"]["content"])


def main() -> None:
    image, stem, lang = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    model = sys.argv[4] if len(sys.argv) > 4 else "qwen3-vl:8b"
    align = json.loads((ROOT / "results" / "align" / f"{stem}.json").read_text())

    anchors = locate(image, model)
    print("anchors", json.dumps(anchors), flush=True)

    PUBLIC.mkdir(parents=True, exist_ok=True)
    shutil.copy(image, PUBLIC / "character.png")
    shutil.copy(ROOT / "results" / "song" / f"{stem}.wav", PUBLIC / "take.wav")
    props = {
        "audio": "take.wav",
        "character": "character.png",
        "mouthAnchor": anchors["mouth"],
        "eyeAnchors": anchors["eyes"],
        "fps": align["fps"],
        "mouth": align["mouth"],
        "segments": align["segments"],
        "lang": lang,
    }
    (PUBLIC / "props.json").write_text(json.dumps(props, ensure_ascii=False))
    print("wrote", PUBLIC / "props.json")


if __name__ == "__main__":
    main()
