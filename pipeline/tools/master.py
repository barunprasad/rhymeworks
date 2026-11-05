"""Mastering: EQ a take toward a target tonal balance, compress gently, normalise loudness.

The target is a band-balance profile (dB share of total energy per band), e.g. measured from genre
references — it shapes the overall tone (less boom, more voice), not any melody.
Usage (audio env): python master.py <in.wav> <out.wav> '<target_json>'
target_json: {"bands": {"sub_20_60": -13.8, "bass_60_250": -5.7, "lowmid_250_1k": -3.6, "mid_1k_4k": -6.4,
              "high_4k_11k": -16.5}, "lufs": -16}
"""

import json
import subprocess
import sys

import librosa
import numpy as np

BANDS = {"sub_20_60": (20, 60, 40), "bass_60_250": (60, 250, 130), "lowmid_250_1k": (250, 1000, 500),
         "mid_1k_4k": (1000, 4000, 2200), "high_4k_11k": (4000, 11000, 7000)}


def band_balance(path: str) -> dict:
    y, sr = librosa.load(path, sr=22050, mono=True)
    S = np.abs(librosa.stft(y, n_fft=4096)) ** 2
    fr = librosa.fft_frequencies(sr=sr, n_fft=4096)
    tot = S.sum()
    return {k: float(10 * np.log10(S[(fr >= a) & (fr < b)].sum() / tot)) for k, (a, b, _) in BANDS.items()}


def main() -> None:
    src, dst, target = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
    cur = band_balance(src)
    eq = []
    gains = {}
    for k, (_, _, fc) in BANDS.items():
        g = max(-6.0, min(6.0, target["bands"][k] - cur[k]))
        gains[k] = round(g, 1)
        if abs(g) < 0.75:
            continue
        if k == "sub_20_60":
            eq.append(f"lowshelf=f=70:g={g:.1f}")
        elif k == "high_4k_11k":
            eq.append(f"highshelf=f=5000:g={g:.1f}")
        else:
            eq.append(f"equalizer=f={fc}:width_type=o:width=1.4:g={g:.1f}")
    chain = ["highpass=f=35", *eq,
             "acompressor=threshold=-20dB:ratio=2.5:attack=15:release=220:makeup=2",
             f"loudnorm=I={target.get('lufs', -16)}:TP=-1.5:LRA=7"]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-af", ",".join(chain), "-ar", "48000", dst], check=True)
    print(json.dumps({"gains_db": gains}))


if __name__ == "__main__":
    main()
