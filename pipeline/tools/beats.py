"""Beat grid for a song take (librosa). Writes <take>.beats.json with beat + downbeat times.
Usage (audio env): python beats.py <take.wav> [bpm_hint]
"""

import json
import sys
from pathlib import Path

import librosa
import numpy as np

path = Path(sys.argv[1])
hint = float(sys.argv[2]) if len(sys.argv) > 2 else 100.0
y, sr = librosa.load(str(path), sr=22050, mono=True)
tempo, frames = librosa.beat.beat_track(y=y, sr=sr, start_bpm=hint, units="frames")
beats = librosa.frames_to_time(frames, sr=sr)
# Downbeats: assume 4/4 and pick the phase whose beats carry the most onset energy.
onset = librosa.onset.onset_strength(y=y, sr=sr)
energy = [float(np.sum(onset[frames[p::4]])) for p in range(4)] if len(frames) >= 8 else [0, 0, 0, 0]
phase = int(np.argmax(energy))
out = {
    "tempo": round(float(np.atleast_1d(tempo)[0]), 1),
    "beats": [round(float(b), 3) for b in beats],
    "downbeats": [round(float(b), 3) for b in beats[phase::4]],
}
dest = path.with_suffix(".beats.json")
dest.write_text(json.dumps(out))
print(dest.name, "tempo", out["tempo"], "beats", len(out["beats"]))
