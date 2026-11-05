import { Img, spring, staticFile } from "remotion";
import type { Callout, Effect, Prop } from "../types";

const STAR = "M0,-10 L2.9,-3.1 L10,-3.1 L4.3,1.6 L6.2,8.6 L0,4.4 L-6.2,8.6 L-4.3,1.6 L-10,-3.1 L-2.9,-3.1 Z";
const COLORS = ["#ff6b6b", "#ffd93d", "#6bcB77", "#4d96ff", "#c77dff", "#ff9f1c"];

function rand(seed: number) {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

const Sparkles: React.FC<{ age: number; size: number }> = ({ age, size }) => {
  if (age < 0 || age > 0.7) return null;
  const p = age / 0.7;
  return (
    <svg width={size * 2.4} height={size * 2.4} viewBox="-120 -120 240 240" style={{ position: "absolute", left: -size * 0.7, top: -size * 0.7, overflow: "visible" }}>
      {Array.from({ length: 8 }, (_, i) => {
        const a = (i / 8) * Math.PI * 2;
        const r = 30 + p * 85;
        return (
          <path
            key={i}
            d={STAR}
            transform={`translate(${Math.cos(a) * r} ${Math.sin(a) * r}) scale(${1.3 * (1 - p)}) rotate(${p * 180})`}
            fill={COLORS[i % COLORS.length]}
            opacity={1 - p}
          />
        );
      })}
    </svg>
  );
};

export const PropPop: React.FC<{ prop: Prop; frame: number; fps: number; t: number }> = ({ prop, frame, fps, t }) => {
  if (t < prop.t) return null;
  const local = frame - Math.round(prop.t * fps);
  const inS = spring({ frame: local, fps, config: { damping: 9, stiffness: 170, mass: 0.6 } });
  let s = inS;
  if (prop.until !== undefined && t > prop.until) {
    s = 1 - spring({ frame: frame - Math.round(prop.until * fps), fps, config: { damping: 14, stiffness: 200 } });
    if (s <= 0.01) return null;
  }
  const wobble = Math.sin((t - prop.t) * 5) * 5 * Math.exp(-(t - prop.t) * 0.8) + Math.sin(t * 2 + prop.x) * 2;
  const bob = Math.sin(t * 2.6 + prop.x * 0.02) * 6;
  const labelS = spring({ frame: local - 3, fps, config: { damping: 8, stiffness: 180, mass: 0.5 } });
  return (
    <div style={{ position: "absolute", left: prop.x - prop.h / 2, top: prop.y - prop.h / 2 + bob, width: prop.h, height: prop.h }}>
      <Sparkles age={t - prop.t} size={prop.h} />
      <Img
        src={staticFile(prop.src)}
        style={{ width: prop.h, height: prop.h, objectFit: "contain", transform: `scale(${s}) rotate(${wobble}deg)`, filter: "drop-shadow(0 8px 6px rgba(0,0,0,0.18))" }}
      />
      {prop.label && (
        <div
          style={{
            position: "absolute",
            left: -prop.h,
            width: prop.h * 3,
            top: -prop.h * (prop.label.length > 2 ? 0.42 : 0.62),
            textAlign: "center",
            fontFamily: "'Arial Rounded MT Bold', 'Nunito', sans-serif",
            // Numbers big; words shrink with length so neighbouring labels don't collide.
            fontSize: prop.h * Math.max(0.3, Math.min(0.55, 1.45 / Math.max(1, prop.label.length))),
            whiteSpace: "nowrap",
            color: prop.labelColor ?? "#ff7a1a",
            WebkitTextStroke: `${prop.h * 0.03}px #ffffff`,
            textShadow: "0 6px 0 rgba(0,0,0,0.15)",
            transform: `scale(${labelS * s})`,
          }}
        >
          {prop.label}
        </div>
      )}
    </div>
  );
};

export const CalloutPop: React.FC<{ c: Callout; frame: number; fps: number; t: number }> = ({ c, frame, fps, t }) => {
  const dur = c.dur ?? 0.8;
  if (t < c.t || t > c.t + dur) return null;
  const s = spring({ frame: frame - Math.round(c.t * fps), fps, config: { damping: 7, stiffness: 200, mass: 0.5 } });
  const fade = Math.min(1, (c.t + dur - t) / 0.25);
  return (
    <div
      style={{
        position: "absolute",
        left: c.x - 200,
        top: c.y - 110,
        width: 400,
        textAlign: "center",
        fontFamily: "'Arial Rounded MT Bold', 'Nunito', sans-serif",
        fontSize: 170,
        color: c.color ?? "#ffcf3d",
        WebkitTextStroke: "7px #ffffff",
        textShadow: "0 10px 0 rgba(0,0,0,0.18)",
        transform: `scale(${s}) rotate(${(1 - s) * -12}deg)`,
        opacity: fade,
      }}
    >
      {c.text}
    </div>
  );
};

export const Confetti: React.FC<{ e: Effect; t: number }> = ({ e, t }) => {
  const dur = e.dur ?? 2.6;
  const age = t - e.t;
  if (age < 0 || age > dur) return null;
  return (
    <>
      {Array.from({ length: 90 }, (_, i) => {
        const vx = (rand(i + 1) - 0.5) * 1500;
        const vy = -700 - rand(i + 7) * 700;
        const x = 960 + vx * age;
        const y = 760 + vy * age + 900 * age * age;
        const rot = age * (200 + rand(i + 3) * 500) * (i % 2 ? 1 : -1);
        const w = 14 + rand(i + 5) * 14;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: x,
              top: y,
              width: w,
              height: w * 0.45,
              background: COLORS[i % COLORS.length],
              borderRadius: 3,
              transform: `rotate(${rot}deg) scaleX(${Math.cos(age * 9 + i)})`,
              opacity: Math.min(1, (dur - age) / 0.5),
            }}
          />
        );
      })}
    </>
  );
};
