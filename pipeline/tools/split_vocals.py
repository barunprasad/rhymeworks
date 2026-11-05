"""Isolate the vocal of a song take (Spleeter 2-stem) and find where the singing starts.
Usage (sep env, MODEL_PATH=spikes/envs/sep/pretrained_models): python split_vocals.py <take.wav> <vocals_out.wav>
Prints JSON {"first_vocal": seconds, "seconds": length}.
"""
import json
import sys

import numpy as np
from spleeter.audio.adapter import AudioAdapter
from spleeter.separator import Separator

take, out = sys.argv[1], sys.argv[2]
ad = AudioAdapter.default()
x, sr = ad.load(take, sample_rate=44100)
voc = Separator("spleeter:2stems").separate(x)["vocals"]
ad.save(out, voc, sr, "wav")   # ffmpeg writer (no soundfile in the sep env)

# first 50 ms frame (of a run ≥ 0.4 s) whose vocal level is within 18 dB of the song's loud vocal level
mono = voc.mean(axis=1)
hop = int(0.05 * sr)
rms = np.sqrt(np.convolve(mono ** 2, np.ones(hop) / hop, mode="same")[::hop] + 1e-12)
db = 20 * np.log10(rms)
loud = np.percentile(db, 90)
on = db > loud - 18
run = int(0.4 / 0.05)
first = next((i for i in range(len(on) - run) if on[i:i + run].all()), 0)
print(json.dumps({"first_vocal": round(first * 0.05, 3), "seconds": round(len(mono) / sr, 3)}))
