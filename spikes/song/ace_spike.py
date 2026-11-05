"""ACE-Step 1.5 spike: one EN, one HI (Devanagari), one HI (romanized) kids song, N takes each.

Requires the ACE-Step API server on 127.0.0.1:8001 (MLX backend).
Usage: python ace_spike.py [takes]
Outputs: spikes/results/song/<variant>_<n>.<ext> + timings.json
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:8001"
OUT = Path(__file__).resolve().parent.parent / "results" / "song"

STYLE = "cheerful preschool children's song, ukulele, xylophone, hand claps, warm bright female vocal, clear diction, simple melody"

LYRICS = {
    "en": """[Verse 1]
One red apple, one, one, one!
Pip found an apple in the sun.
[Chorus]
Count with me, count with me,
One, two, three, four, five!
Count with me, count with me,
Fruits are fun, let's count tonight!
[Verse 2]
Two yellow bananas, two, two, two!
Paro says bananas, how about you?
[Chorus]
Count with me, count with me,
One, two, three, four, five!
Count with me, count with me,
Fruits are fun, let's count tonight!""",
    "hi": """[Verse 1]
एक लाल सेब, एक, एक, एक!
पिप को मिला सेब, देखो नेक!
[Chorus]
गिनो मेरे साथ, गिनो मेरे साथ,
एक, दो, तीन, चार, पाँच!
गिनो मेरे साथ, गिनो मेरे साथ,
फल हैं मज़ेदार, आओ नाच!
[Verse 2]
दो पीले केले, दो, दो, दो!
पारो बोले केले, तुम भी बोलो!
[Chorus]
गिनो मेरे साथ, गिनो मेरे साथ,
एक, दो, तीन, चार, पाँच!
गिनो मेरे साथ, गिनो मेरे साथ,
फल हैं मज़ेदार, आओ नाच!""",
    "hi_roman": """[Verse 1]
Ek laal seb, ek, ek, ek!
Pip ko mila seb, dekho nek!
[Chorus]
Gino mere saath, gino mere saath,
Ek, do, teen, chaar, paanch!
Gino mere saath, gino mere saath,
Phal hain mazedaar, aao naach!
[Verse 2]
Do peele kele, do, do, do!
Paaro bole kele, tum bhi bolo!
[Chorus]
Gino mere saath, gino mere saath,
Ek, do, teen, chaar, paanch!
Gino mere saath, gino mere saath,
Phal hain mazedaar, aao naach!""",
}
LANG = {"en": "en", "hi": "hi", "hi_roman": "hi"}


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(API + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if body.get("code") != 200:
        raise RuntimeError(body)
    return body["data"]


def main(takes: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    timings = {}
    for variant, lyrics in LYRICS.items():
        t0 = time.time()
        task = post(
            "/release_task",
            {
                "prompt": STYLE,
                "lyrics": lyrics,
                "vocal_language": LANG[variant],
                "thinking": True,
                "use_cot_language": False,
                "bpm": 100,
                "audio_duration": 60,
                "batch_size": takes,
                "audio_format": "wav",
            },
        )
        tid = task["task_id"]
        while True:
            time.sleep(3)
            res = post("/query_result", {"task_id_list": [tid]})[0]
            if res["status"] in (1, 2):
                break
        wall = time.time() - t0
        if res["status"] == 2:
            timings[variant] = {"wall_sec": round(wall, 1), "error": res.get("result")}
            print(variant, "FAILED", res.get("result"), flush=True)
            continue
        items = json.loads(res["result"])
        files = []
        for n, item in enumerate(items):
            url = API + item["file"]
            ext = Path(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["path"][0]).suffix or ".wav"
            dest = OUT / f"{variant}_{n}{ext}"
            urllib.request.urlretrieve(url, dest)
            files.append(dest.name)
        timings[variant] = {
            "wall_sec": round(wall, 1),
            "takes": len(files),
            "files": files,
            "dit_model": items[0].get("dit_model"),
            "lm_model": items[0].get("lm_model"),
            "metas": items[0].get("metas"),
        }
        print(variant, json.dumps(timings[variant], ensure_ascii=False), flush=True)
    (OUT / "timings.json").write_text(json.dumps(timings, ensure_ascii=False, indent=2))
    (OUT / "lyrics.json").write_text(json.dumps(LYRICS, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
