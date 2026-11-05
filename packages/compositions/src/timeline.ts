import { Easing, interpolate } from "remotion";
import type { CameraKey, Keyframe } from "./types";

const ease = Easing.inOut(Easing.cubic);

/** Index of the last element whose `t` is <= time (or -1). */
export function lastAt<T extends { t: number }>(keys: T[], time: number): number {
  let i = -1;
  for (let k = 0; k < keys.length; k++) if (keys[k].t <= time) i = k;
  return i;
}

export function cameraAt(keys: CameraKey[], t: number): { cx: number; cy: number; zoom: number } {
  if (!keys.length) return { cx: 960, cy: 540, zoom: 1 };
  const i = lastAt(keys, t);
  if (i < 0) return keys[0];
  const a = keys[i];
  const b = keys[i + 1];
  if (!b || b.cut) return a;
  const p = interpolate(t, [a.t, b.t], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });
  return { cx: a.cx + (b.cx - a.cx) * p, cy: a.cy + (b.cy - a.cy) * p, zoom: a.zoom + (b.zoom - a.zoom) * p };
}

export type CharState = {
  x: number;
  lift: number; // px above ground (positive = up)
  pose: string;
  facing: 1 | -1;
  scale: number;
  moving: boolean;
  move?: Keyframe["move"];
  progress: number;
  since: number; // seconds since the active keyframe started
  prevPose: string; // pose/action of the previous keyframe (for blending)
  look?: Keyframe["look"];
};

/** Resolve a character's position/pose at time t from its keyframes. */
export function charAt(keys: Keyframe[], t: number, beatIndex: number): CharState | null {
  if (!keys.length || t < keys[0].t) return null;
  const i = lastAt(keys, t);
  const a = keys[i];
  const b = keys[i + 1];
  const facing = a.facing ?? 1;
  const scale = a.scale ?? 1;

  if (b && b.move) {
    const raw = (t - a.t) / Math.max(1e-6, b.t - a.t);
    const p = b.move === "jump" ? raw : ease(Math.min(1, Math.max(0, raw)));
    const x = a.x + (b.x - a.x) * p;
    const baseLift = (a.y ?? 0) + ((b.y ?? 0) - (a.y ?? 0)) * p;
    let lift = baseLift;
    if (b.move === "hop") {
      const hops = Math.max(1, Math.round(Math.abs(b.x - a.x) / 140));
      lift += Math.abs(Math.sin(Math.PI * hops * raw)) * 46;
    } else if (b.move === "walk") {
      lift += Math.abs(Math.sin(Math.PI * 6 * raw)) * 10;
    } else if (b.move === "jump") {
      lift += Math.sin(Math.PI * raw) * 190;
    }
    const prevPose = keys[i - 1]?.pose ?? a.pose;
    return { x, lift, pose: b.move === "jump" ? b.pose : a.pose, facing: (b.facing ?? facing) as 1 | -1, scale, moving: true, move: b.move, progress: raw, since: t - a.t, prevPose, look: a.look };
  }

  const pose = a.beatPoses?.length ? a.beatPoses[Math.max(0, beatIndex) % a.beatPoses.length] : a.pose;
  const prevPose = keys[i - 1]?.pose ?? a.pose;
  return { x: a.x, lift: a.y ?? 0, pose, facing, scale, moving: false, progress: 1, since: t - a.t, prevPose, look: a.look };
}

export function beatInfo(beats: number[], t: number): { index: number; since: number } {
  let index = -1;
  for (let k = 0; k < beats.length; k++) if (beats[k] <= t) index = k;
  return { index, since: index >= 0 ? t - beats[index] : 99 };
}
