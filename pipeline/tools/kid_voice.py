"""'Kid voice' transform: raise pitch AND formants together by N semitones, tempo unchanged (ffmpeg only).

asetrate speeds up + raises pitch/formants; atempo then restores the original tempo without changing pitch.
Timing is preserved, so existing lyric alignment and lip-sync stay exact.
Usage: python kid_voice.py <in.wav> <out.wav> <semitones>
"""

import subprocess
import sys

src, dst, semis = sys.argv[1], sys.argv[2], float(sys.argv[3])
ratio = 2 ** (semis / 12)
sr = 48000
af = f"aresample={sr},asetrate={sr * ratio:.0f},aresample={sr},atempo={1 / ratio:.6f}"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-af", af, "-ar", str(sr), dst], check=True)
print(f"{dst}: +{semis} semitones (ratio {ratio:.3f})")
