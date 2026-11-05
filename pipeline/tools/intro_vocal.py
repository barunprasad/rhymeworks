"""How much singing is in the first <sec> seconds of each file (vocal/accompaniment energy, dB, Spleeter 2-stem).
Usage (sep env): python intro_vocal.py <sec> <a.wav> [b.wav ...]  → JSON {file: dB}
"""
import json
import sys

import numpy as np
from spleeter.audio.adapter import AudioAdapter
from spleeter.separator import Separator

sec, files = float(sys.argv[1]), sys.argv[2:]
sep, ad = Separator("spleeter:2stems"), AudioAdapter.default()
out = {}
for f in files:
    x, sr = ad.load(f, duration=sec + 2, sample_rate=44100)
    r = sep.separate(x)
    s = slice(0, int(sec * sr))
    out[f] = round(float(10 * np.log10((r["vocals"][s] ** 2).mean() / ((r["accompaniment"][s] ** 2).mean() + 1e-12) + 1e-12)), 1)
print(json.dumps(out))
