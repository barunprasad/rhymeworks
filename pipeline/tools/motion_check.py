"""Flag clips that barely move (LTX sometimes returns an almost still video, e.g. with end = "same").

  uv run --project spikes/envs/image python pipeline/tools/motion_check.py <episode>/clips/s*.mp4

Per clip: mean absolute change (0–255, 64×36 grey, 4 fps) from the first to the last frame and between neighbouring
frames. step < 1.5 = frozen; a pinned shot (end = "same") has first→last near 0 but should still have step > 3.
"""
import subprocess
import sys

import numpy as np

W, H = 64, 36
for f in sys.argv[1:]:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", f, "-vf", f"fps=4,scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(float)
    if len(a) < 2:
        print(f"{f}: too short")
        continue
    step = np.abs(np.diff(a, axis=0)).mean()
    print(f"{f.split('/')[-1]:10} first→last {np.abs(a[-1] - a[0]).mean():5.1f}   step {step:4.1f}" + ("   FROZEN" if step < 1.5 else ""))
