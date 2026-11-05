"""Remix a (converted) vocal over an accompaniment stem, then master toward a target tonal balance.
Usage (audio env): python remix.py <vocals.wav> <accompaniment.wav> <out.wav> '<target_json>' [vocal_gain_db]
"""
import json, subprocess, sys
from pathlib import Path
voc, acc, out, target = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
gain = float(sys.argv[5]) if len(sys.argv) > 5 else 1.5
raw = str(Path(out).with_suffix(".raw.wav"))
fc = (f"[0:a]aresample=48000,pan=stereo|c0=c0|c1=c0,volume={gain}dB,highpass=f=90[v];"
      f"[1:a]aresample=48000[a];[a][v]amix=inputs=2:normalize=0:duration=longest[m]")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", voc, "-i", acc, "-filter_complex", fc, "-map", "[m]", raw], check=True)
subprocess.run([sys.executable, str(Path(__file__).with_name("master.py")), raw, out, target], check=True)
Path(raw).unlink()
print("remixed →", out)
