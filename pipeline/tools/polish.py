"""Polish a chosen song take into a release master.

1. Intro fix (optional): splice a repainted intro (ACE-Step repaint) onto the original take with an
   equal-power crossfade, so everything after the splice is the untouched original (lip-sync exact).
2. Optional stem remix: vocals (Spleeter) get de-essing, presence EQ, a little plate reverb and
   +gain; the accompaniment keeps the repainted intro.
3. Master: EQ toward a target tonal balance, de-ess, glue compression, true-peak limit, loudness.

Usage (audio env):
  python polish.py <take.wav> <out.wav> '<json opts>'
opts: {"intro": "intro.wav", "splice": [4.0, 4.5], "target": {...master target...},
       "stems": {"vocals": "v.wav", "accompaniment": "a.wav", "vocal_gain_db": 1.5, "reverb": 0.12},
       "lufs": -14}
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))
from master import BANDS, band_balance  # noqa: E402

SR = 48000


def load(p: str) -> np.ndarray:
    x, sr = sf.read(p, always_2d=True)
    if sr != SR:
        import librosa
        x = librosa.resample(x.T, orig_sr=sr, target_sr=SR).T
    if x.shape[1] == 1:
        x = np.repeat(x, 2, 1)
    return x


def splice(base: np.ndarray, intro: np.ndarray, a: float, b: float) -> np.ndarray:
    i0, i1 = int(a * SR), int(b * SR)
    t = np.linspace(0, np.pi / 2, i1 - i0)[:, None]
    out = base.copy()
    out[:i0] = intro[:i0]
    out[i0:i1] = intro[i0:i1] * np.cos(t) + base[i0:i1] * np.sin(t)
    fade = int(0.02 * SR)
    out[:fade] *= np.linspace(0, 1, fade)[:, None]
    return out


def plate_ir(sec: float = 1.4, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(sec * SR)
    env = np.exp(-np.linspace(0, 7, n))[:, None]
    ir = rng.standard_normal((n, 2)) * env
    # darker tail: one-pole lowpass
    for c in range(2):
        for k in range(1, n):
            ir[k, c] = 0.6 * ir[k, c] + 0.4 * ir[k - 1, c]
    ir[: int(0.012 * SR)] = 0  # pre-delay
    return ir / np.sqrt((ir ** 2).sum(0))


def ff(src: str, dst: str, chain: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-af", ",".join(chain), "-ar", str(SR), dst], check=True)


def main() -> None:
    take, out, opts = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
    tmp = Path(tempfile.mkdtemp(prefix="polish_"))
    x = load(take)
    a, b = opts.get("splice", [4.0, 4.5])
    if opts.get("intro"):
        x = splice(x, load(opts["intro"]), a, b)

    if opts.get("stems"):
        st = opts["stems"]
        v, acc = load(st["vocals"]), load(st["accompaniment"])
        n = min(len(x), len(v), len(acc))
        v, acc = v[:n], acc[:n]
        if opts.get("intro"):  # intro is instrumental: take accompaniment from the spliced mix, mute old vocal
            i1 = int(b * SR)
            acc[:i1] = x[:i1]
            v[:i1] *= np.r_[np.zeros(int(a * SR)), np.linspace(0, 1, i1 - int(a * SR))][:, None]
        sf.write(tmp / "v.wav", v, SR)
        ff(str(tmp / "v.wav"), str(tmp / "v2.wav"), ["highpass=f=110", "equalizer=f=300:width_type=o:width=1.2:g=-2",
           "equalizer=f=3000:width_type=o:width=1.5:g=2.5", "deesser=i=0.4:m=0.5:f=0.5",
           "acompressor=threshold=-22dB:ratio=3:attack=8:release=150:makeup=2"])
        v2 = load(str(tmp / "v2.wav"))[:n]
        from scipy.signal import fftconvolve
        ir = plate_ir()
        wet = np.stack([fftconvolve(v2[:, c], ir[:, c])[:n] for c in range(2)], 1)
        g = 10 ** (st.get("vocal_gain_db", 1.5) / 20)
        x = acc + g * (v2 + st.get("reverb", 0.12) * wet)

    sf.write(tmp / "mix.wav", x / max(1.0, np.abs(x).max() / 0.98), SR)
    target = opts["target"]
    cur = band_balance(str(tmp / "mix.wav"))
    eq = []
    for k, (_, _, fc) in BANDS.items():
        g = max(-6.0, min(6.0, target["bands"][k] - cur[k]))
        if abs(g) < 0.75:
            continue
        eq.append(f"lowshelf=f=70:g={g:.1f}" if k == "sub_20_60" else f"highshelf=f=5000:g={g:.1f}" if k == "high_4k_11k"
                  else f"equalizer=f={fc}:width_type=o:width=1.4:g={g:.1f}")
    lufs = opts.get("lufs", -14)
    chain = ["highpass=f=30", *eq, "deesser=i=0.25:m=0.5:f=0.5",
             "acompressor=threshold=-18dB:ratio=2:attack=25:release=250:makeup=1.5",
             "alimiter=limit=0.89:attack=5:release=60:level=disabled"]
    ff(str(tmp / "mix.wav"), str(tmp / "pre.wav"), chain)
    # two-pass loudnorm for accurate loudness
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(tmp / "pre.wav"), "-af",
                        f"loudnorm=I={lufs}:TP=-1.0:LRA=9:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    j = r[r.rfind("{"):]
    m = json.loads(j[: j.find("}") + 1])
    ff(str(tmp / "pre.wav"), out, [f"loudnorm=I={lufs}:TP=-1.0:LRA=9:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                                   f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true"])
    print(json.dumps({"out": out, "eq": eq}))


if __name__ == "__main__":
    main()
