import { Img, staticFile } from "remotion";
import type { RigDef } from "../types";
import { Mouth } from "./Mouth";

export type Joints = {
  head: number;
  antenna: number;
  arm_l: number;
  arm_r: number;
  leg_l: number;
  leg_r: number;
  body: number;
  skirtSkew: number; // octo: tentacle sway (deg of skewX)
  skirtSquash: number; // octo: tentacle stretch (+) / squash (−), fraction
  spin: number; // whole-body rotation about the centre (deg)
};

/** Smooth beat accent 0..1: quick eased attack, eased release — avoids one-frame snaps. */
export function beatEnvelope(since: number): number {
  if (since < 0) return 0;
  if (since < 0.06) {
    const a = since / 0.06;
    return a * a * (3 - 2 * a);
  }
  const r = Math.max(0, 1 - (since - 0.06) / 0.28);
  return r * r * (3 - 2 * r);
}

const ZERO: Joints = { head: 0, antenna: 0, arm_l: 0, arm_r: 0, leg_l: 0, leg_r: 0, body: 0, skirtSkew: 0, skirtSquash: 0, spin: 0 };

/** Octopus actions: tentacle sway/squash, body tilt, spins. Each family member gets its own flavour. */
export function octoJoints(action: string, t: number, beatPhase: number, beatIndex: number, since: number): Joints {
  const j: Joints = { ...ZERO };
  const hit = beatEnvelope(beatPhase);
  j.skirtSkew = Math.sin(t * 3.2) * 7;
  j.skirtSquash = Math.sin(t * 6.4) * 0.04;
  j.head = Math.sin(t * 1.7) * 3;
  switch (action) {
    case "wiggle": // Baby: fast happy wiggles
      j.skirtSkew = Math.sin(t * 11) * 16;
      j.skirtSquash = 0.08 * hit - 0.03;
      j.body = Math.sin(t * 5.5) * 8;
      break;
    case "swish": // Mama: big graceful swishes
      j.skirtSkew = Math.sin(t * 4.5) * 22;
      j.body = Math.sin(t * 2.25) * 10;
      j.head = Math.sin(t * 2.25 + 1) * 5;
      break;
    case "stomp": // Papa: heavy squash on every beat
      j.skirtSquash = -0.16 * hit + 0.03;
      j.skirtSkew = (beatIndex % 2 ? 1 : -1) * 8 * hit;
      j.body = (beatIndex % 2 ? 1 : -1) * 3 * hit;
      break;
    case "sway": // Grandma: slow gentle sway
      j.skirtSkew = Math.sin(t * 2) * 12;
      j.body = Math.sin(t * 1.6) * 9;
      j.head = Math.sin(t * 1.6 + 0.5) * 6;
      break;
    case "clap": // Grandpa: bouncy beat with tentacle taps
      j.skirtSquash = 0.1 * hit - 0.04;
      j.skirtSkew = Math.sin(beatPhase * Math.PI * 2) * 10;
      j.head = (beatIndex % 2 ? 1 : -1) * 6 * hit;
      break;
    case "spin": // chorus "spin around": one full turn over ~0.9 s, then wiggle
      j.spin = Math.min(1, since / 0.9) * 360;
      j.skirtSkew = Math.sin(t * 9) * 14;
      j.skirtSquash = 0.06;
      break;
    case "dance":
      j.skirtSkew = Math.sin(t * 7) * 18;
      j.skirtSquash = 0.07 * hit;
      j.body = (beatIndex % 2 ? 1 : -1) * 7 * (0.5 + 0.5 * hit);
      break;
    default:
      break;
  }
  return j;
}

/**
 * Procedural actions → joint angles in degrees (positive = clockwise on screen).
 * arm_l is the arm on screen-left: raising it outward is clockwise (+), swinging it inward is (−).
 */
export function actionJoints(action: string, t: number, beatPhase: number, beatIndex: number, moving: boolean, walkPhase: number): Joints {
  const j: Joints = { ...ZERO };
  const idleL = 4 + Math.sin(t * 2.1) * 3;
  const idleR = -(4 + Math.sin(t * 2.1 + 1.3) * 3);
  j.head = Math.sin(t * 1.3) * 3;
  j.arm_l = idleL;
  j.arm_r = idleR;
  const hit = beatEnvelope(beatPhase); // eased accent on the beat

  switch (action) {
    case "wave":
      j.arm_r = -(140 + Math.sin(t * 10) * 20);
      j.head = 6 + Math.sin(t * 2) * 2;
      break;
    case "point":
      j.arm_r = -88 + Math.sin(t * 3) * 3;
      j.head = 5;
      break;
    case "clap": {
      const c = Math.abs(Math.sin(beatPhase * Math.PI * 1.65));
      j.arm_l = -(38 + 34 * (1 - c));
      j.arm_r = 38 + 34 * (1 - c);
      j.head = (beatIndex % 2 ? 1 : -1) * 4 * hit;
      break;
    }
    case "cheer":
      j.arm_l = 150 + Math.sin(t * 12) * 8;
      j.arm_r = -(150 + Math.sin(t * 12 + 1) * 8);
      j.head = Math.sin(t * 6) * 4;
      break;
    case "dance": {
      const even = beatIndex % 2 === 0;
      j.arm_l = even ? 135 : 10;
      j.arm_r = even ? -10 : -135;
      j.head = (even ? -8 : 8) * (0.4 + 0.6 * hit);
      j.body = (even ? -4 : 4) * (0.5 + 0.5 * hit);
      break;
    }
    case "lean":
      j.arm_l = -20;
      j.arm_r = 20;
      j.body = 5;
      j.head = -6;
      break;
    case "squat":
      j.arm_l = 30;
      j.arm_r = -30;
      j.head = 2;
      break;
    default:
      break;
  }

  if (moving) {
    const s = Math.sin(walkPhase);
    j.leg_l = 24 * s;
    j.leg_r = -24 * s;
    if (action === "idle" || action === "base") {
      j.arm_l = 10 - 18 * s;
      j.arm_r = -10 - 18 * s;
    }
  }
  return j;
}

export function blendJoints(a: Joints, b: Joints, p: number): Joints {
  const out = { ...ZERO };
  (Object.keys(out) as (keyof Joints)[]).forEach((k) => (out[k] = a[k] + (b[k] - a[k]) * p));
  return out;
}

type Props = {
  rig: RigDef;
  W: number;
  H: number;
  joints: Joints;
  t: number;
  blinkSeed: number;
  look: { x: number; y: number }; // −1..1
  mouthState: number | null; // null = no mouth (beak characters)
};

export const RigBody: React.FC<Props> = ({ rig, W, H, joints, t, blinkSeed, look, mouthState }) => {
  const s = H / rig.size[1];
  const part = (name: string) => rig.parts.find((p) => p.name === name);
  const piv = (name: string) => rig.pivots[name];

  // Arms drawn held out (for clean rigging) are rotated back so that joint angle 0 = a natural hang.
  const restOffset = (name: string) => {
    const r = rig.rest?.[name] ?? 0;
    return Math.abs(r) > 20 ? r - Math.sign(r) * 8 : 0;
  };

  const layer = (name: string, angle: number) => {
    const p = part(name);
    if (!p) return null;
    const pv = piv(name) ?? { x: p.x + p.w / 2, y: p.y };
    return (
      <Img
        key={name}
        src={staticFile(rig.base + p.src)}
        style={{
          position: "absolute",
          left: p.x * s,
          top: p.y * s,
          width: p.w * s,
          height: p.h * s,
          transformOrigin: `${(pv.x - p.x) * s}px ${(pv.y - p.y) * s}px`,
          transform: `rotate(${angle - restOffset(name)}deg)`,
        }}
      />
    );
  };

  // Blink every ~3.4 s (offset per character), 130 ms close-open.
  const period = 3.4 + (blinkSeed % 3) * 0.4;
  const ph = (t + blinkSeed * 1.37) % period;
  const blink = ph < 0.13 ? Math.sin((ph / 0.13) * Math.PI) : 0;

  const neck = piv("head") ?? { x: rig.size[0] / 2, y: rig.size[1] * 0.45 };
  const hip = { x: rig.size[0] / 2, y: rig.size[1] };
  const centre = { x: rig.size[0] / 2, y: rig.size[1] * 0.5 };

  const skirtLayer = () => {
    const p = part("skirt");
    const pv = piv("skirt");
    if (!p || !pv) return null;
    return (
      <Img
        src={staticFile(rig.base + p.src)}
        style={{
          position: "absolute",
          left: p.x * s,
          top: p.y * s,
          width: p.w * s,
          height: p.h * s,
          transformOrigin: `${(pv.x - p.x) * s}px 0px`,
          transform: `skewX(${joints.skirtSkew}deg) scaleY(${1 + joints.skirtSquash}) scaleX(${1 - joints.skirtSquash * 0.6})`,
        }}
      />
    );
  };

  return (
    <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H, transformOrigin: `${centre.x * s}px ${centre.y * s}px`, transform: `rotate(${joints.spin}deg)` }}>
    <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H, transformOrigin: `${hip.x * s}px ${hip.y * s}px`, transform: `rotate(${joints.body}deg)` }}>
      {skirtLayer()}
      {layer("leg_l", joints.leg_l)}
      {layer("leg_r", joints.leg_r)}
      {layer("body", 0)}
      <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H, transformOrigin: `${neck.x * s}px ${neck.y * s}px`, transform: `rotate(${joints.head}deg)` }}>
        {layer("antenna", joints.antenna)}
        {layer("head", 0)}
        {rig.eyes.map((e, i) => (
          <Img
            key={`pupil${i}`}
            src={staticFile(rig.base + e.src)}
            style={{
              position: "absolute",
              left: (e.x + look.x * e.r * 0.32) * s,
              top: (e.y + look.y * e.r * 0.25) * s,
              width: e.w * s,
              height: e.h * s,
            }}
          />
        ))}
        {blink > 0 &&
          rig.eyes.map((e, i) => (
            <div
              key={`lid${i}`}
              style={{
                position: "absolute",
                left: (e.cx - e.r * 1.08) * s,
                top: (e.cy - e.r * 1.08) * s,
                width: e.r * 2.16 * s,
                height: e.r * 2.16 * s * blink,
                background: rig.skin,
                borderBottom: `${Math.max(2, e.r * 0.12 * s)}px solid #2f2626`,
                borderRadius: `${e.r * s}px ${e.r * s}px ${e.r * 0.6 * s}px ${e.r * 0.6 * s}px`,
              }}
            />
          ))}
        {mouthState !== null && rig.mouth && (
          <div style={{ position: "absolute", left: (rig.mouth.x - rig.mouth.width / 2) * s, top: rig.mouth.y * s - rig.mouth.width * s * 0.3 }}>
            <Mouth state={mouthState} width={rig.mouth.width * s} />
          </div>
        )}
      </div>
      {layer("arm_l", joints.arm_l)}
      {layer("arm_r", joints.arm_r)}
    </div>
    </div>
  );
};
