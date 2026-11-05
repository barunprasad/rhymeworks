"""Synthesize a melody guide track from a note list, for ACE-Step "cover" (melody-locked songs).

Traditional / public-domain tunes (nursery rhymes) are written out as notes; this renders a soft
"oo" lead line + piano chords + bass so ACE-Step can lock melody, rhythm and harmony to it while
singing our own lyrics in our own arrangement.

Spec (JSON):
  {"bpm": 120, "intro_bars": 2, "outro_bars": 2, "beats_per_bar": 4, "repeat": 4,
   "pickup": 0.5,                                          # beats of notes[0..] before bar 1
   "notes":  [["C4", 0.5], ["F4", 1], ["r", 1], ...],     # one verse incl. pickup; spans the verse's beats
   "chords": [["F", 4], ["C7", 4], ...]}                   # one verse: chord + beats
The intro starts with chords only; the verse's pickup note is placed at the end of the intro.
Usage (audio env): python melody_guide.py <spec.json> <out.wav> [--lead-only]
"""

import json
import sys

import numpy as np
import soundfile as sf

SR = 44100
NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
CHORD = {"": [0, 4, 7], "m": [0, 3, 7], "7": [0, 4, 7, 10], "maj7": [0, 4, 7, 11]}


def midi(name: str) -> int:
    pc = NOTE[name[0]] + (1 if "#" in name else -1 if name[1:2] == "b" else 0)
    return 12 * (int(name[-1]) + 1) + pc


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def adsr(n: int, a=0.02, d=0.08, s=0.8, r=0.08) -> np.ndarray:
    a, d, r = int(a * SR), int(d * SR), int(r * SR)
    env = np.full(n, s)
    env[:a] = np.linspace(0, 1, a)[: n]
    env[a:a + d] = np.linspace(1, s, len(env[a:a + d]))
    if r < n:
        env[-r:] *= np.linspace(1, 0, r)
    return env


def lead(f: float, n: int) -> np.ndarray:
    """Soft vocal-like 'oo': few harmonics with a steep rolloff + gentle delayed vibrato."""
    t = np.arange(n) / SR
    vib = 1 + 0.006 * np.sin(2 * np.pi * 5.5 * t) * np.clip(t / 0.25, 0, 1)
    ph = 2 * np.pi * np.cumsum(f * vib) / SR
    w = sum(np.sin(k * ph) / k ** 1.8 for k in range(1, 7))
    return w * adsr(n, 0.04, 0.1, 0.85, 0.06)


def piano(f: float, n: int) -> np.ndarray:
    t = np.arange(n) / SR
    w = sum(np.sin(2 * np.pi * k * f * t) * np.exp(-t * (1.5 + k)) / k for k in range(1, 8))
    return w * adsr(n, 0.005, 0.0, 1.0, 0.05)


def render(spec: dict, lead_only: bool = False) -> np.ndarray:
    beat = 60.0 / spec["bpm"]
    bpb = spec.get("beats_per_bar", 4)
    notes, chords = spec["notes"], spec["chords"]
    verse_beats = sum(b for _, b in chords)
    pickup = spec.get("pickup", 0.0)  # beats of the verse's first notes that sit before bar 1 (e.g. "The")
    assert abs(sum(b for _, b in notes) - verse_beats) < 1e-6, "notes must span the verse (last note shortened by the pickup)"
    intro = spec.get("intro_bars", 2) * bpb
    total = intro + spec.get("repeat", 1) * verse_beats + spec.get("outro_bars", 2) * bpb + 2
    out = np.zeros(int(total * beat * SR) + SR)

    def add(sig: np.ndarray, start_beat: float, gain: float):
        i = int(start_beat * beat * SR)
        out[i:i + len(sig)] += gain * sig[: len(out) - i]

    # chords: intro (tonic), verses, outro (tonic)
    tonic = chords[0][0]
    prog = [(tonic, bpb)] * spec.get("intro_bars", 2) + chords * spec.get("repeat", 1) + [(tonic, bpb * spec.get("outro_bars", 2))]
    if not lead_only:
        pos = 0.0
        for name, b in prog:
            root = NOTE[name[0]] + (1 if name[1:2] == "#" else -1 if name[1:2] == "b" else 0)
            qual = name[1:].lstrip("#b")
            for k in range(int(b)):  # one piano stab per beat (oom-pah feel: bass on 1 and 3)
                n = int(beat * SR * 0.95)
                for iv in CHORD.get(qual, CHORD[""]):
                    add(piano(hz(60 + root + iv), n), pos + k, 0.10)
                if k % 2 == 0:
                    add(piano(hz(36 + root + (7 if k % 4 == 2 else 0)), int(beat * 2 * SR)), pos + k, 0.30)
            pos += b
    # lead line, one verse after another; pickup sits at the end of the previous bar
    pos = intro - pickup
    for _ in range(spec.get("repeat", 1)):
        for name, b in notes:
            n = int(b * beat * SR * 0.92)
            if name != "r":
                add(lead(hz(midi(name)), n), pos, 0.32)
            pos += b
    out /= max(1e-6, np.abs(out).max()) / 0.85
    return out.astype(np.float32)


if __name__ == "__main__":
    spec = json.load(open(sys.argv[1]))
    audio = render(spec, "--lead-only" in sys.argv)
    sf.write(sys.argv[2], audio, SR)
    print(f"wrote {sys.argv[2]} ({len(audio) / SR:.1f}s)")
