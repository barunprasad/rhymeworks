import { Img, staticFile } from "remotion";
import type { Episode, Layer, Segment } from "../types";

/** Wraps children in the camera transform for a given depth (parallax). */
export const Depth: React.FC<{ depth: number; cam: { cx: number; cy: number; zoom: number }; children: React.ReactNode }> = ({ depth, cam, children }) => {
  const z = 1 + (cam.zoom - 1) * depth;
  const fx = 960 + (cam.cx - 960) * depth;
  const fy = 540 + (cam.cy - 540) * depth;
  return (
    <div style={{ position: "absolute", inset: 0, transformOrigin: "0 0", transform: `translate(960px, 540px) scale(${z}) translate(${-fx}px, ${-fy}px)` }}>
      {children}
    </div>
  );
};

function rnd(i: number) {
  const x = Math.sin(i * 91.7) * 43758.5453;
  return x - Math.floor(x);
}

const Underwater: React.FC<{ sky: Episode["sky"]; t: number }> = ({ sky, t }) => (
  <>
    <div style={{ position: "absolute", inset: -400, background: `linear-gradient(${sky.top}, ${sky.bottom})` }} />
    {/* light rays from the surface */}
    {[0, 1, 2, 3, 4].map((i) => (
      <div
        key={`ray${i}`}
        style={{
          position: "absolute",
          left: 180 + i * 380 + Math.sin(t * 0.5 + i) * 40,
          top: -200,
          width: 140 + (i % 2) * 80,
          height: 1300,
          background: "linear-gradient(rgba(255,255,255,0.32), rgba(255,255,255,0))",
          transform: `skewX(${-18 + Math.sin(t * 0.4 + i * 1.7) * 5}deg)`,
          opacity: 0.55 + Math.sin(t * 0.9 + i * 2.1) * 0.25,
          filter: "blur(6px)",
        }}
      />
    ))}
    {/* drifting specks */}
    {Array.from({ length: 40 }, (_, i) => (
      <div
        key={`sp${i}`}
        style={{
          position: "absolute",
          left: (rnd(i) * 2100 + t * (6 + rnd(i + 3) * 10)) % 2100 - 90,
          top: (rnd(i + 7) * 1000 - t * (8 + rnd(i + 5) * 12) + 2000) % 1000,
          width: 4 + rnd(i + 9) * 5,
          height: 4 + rnd(i + 9) * 5,
          borderRadius: "50%",
          background: "rgba(255,255,255,0.5)",
        }}
      />
    ))}
  </>
);

export const Bubbles: React.FC<{ t: number }> = ({ t }) => (
  <>
    {Array.from({ length: 26 }, (_, i) => {
      const period = 5 + rnd(i) * 6;
      const age = (t + rnd(i + 1) * period) % period;
      const p = age / period;
      const size = 10 + rnd(i + 2) * 26;
      const x = rnd(i + 4) * 1920 + Math.sin(age * 2.5 + i) * 18;
      return (
        <div
          key={`b${i}`}
          style={{
            position: "absolute",
            left: x,
            top: 1080 - p * 1250,
            width: size,
            height: size,
            borderRadius: "50%",
            border: "3px solid rgba(255,255,255,0.75)",
            background: "radial-gradient(circle at 30% 30%, rgba(255,255,255,0.75), rgba(255,255,255,0.08) 45%, rgba(255,255,255,0))",
            opacity: Math.min(1, (1 - p) * 3),
          }}
        />
      );
    })}
  </>
);

export const Swimmers: React.FC<{ list: NonNullable<Episode["swimmers"]>; t: number }> = ({ list, t }) => (
  <>
    {list.map((f, i) => {
      if (t < f.start) return null;
      const travel = (t - f.start) * f.speed;
      const span = 1920 + f.size * 2;
      const pos = travel % span;
      const x = f.dir > 0 ? pos - f.size : 1920 - pos;
      const y = f.y + Math.sin((t - f.start) * 2 + i) * (f.bob ?? 18);
      return (
        <Img
          key={`f${i}`}
          src={staticFile(f.src)}
          style={{ position: "absolute", left: x, top: y, width: f.size, transform: `scaleX(${f.dir}) rotate(${Math.sin(t * 6 + i) * 4}deg)` }}
        />
      );
    })}
  </>
);

export const Sky: React.FC<{ sky: Episode["sky"]; t: number }> = ({ sky, t }) => sky.kind === "underwater" ? <Underwater sky={sky} t={t} /> : (
  <>
    <div style={{ position: "absolute", inset: -400, background: `linear-gradient(${sky.top}, ${sky.bottom})` }} />
    <Img
      src={staticFile(sky.sun)}
      style={{
        position: "absolute",
        left: 1560,
        top: 30 + Math.sin(t * 1.3) * 10,
        width: 250,
        transform: `rotate(${Math.sin(t * 0.8) * 8}deg) scale(${1 + Math.sin(t * 2.4) * 0.03})`,
      }}
    />
    {[0, 1, 2, 3].map((i) => {
      const speed = 14 + i * 9;
      const w = 300 - i * 40;
      const x = ((i * 610 + t * speed) % 2600) - 400;
      return <Img key={i} src={staticFile(sky.clouds)} style={{ position: "absolute", left: x, top: 40 + (i % 2) * 110 + i * 18, width: w, opacity: 0.95 }} />;
    })}
  </>
);

export const LayerImg: React.FC<{ layer: Layer; t: number }> = ({ layer, t }) => (
  <Img
    src={staticFile(layer.src)}
    style={{
      position: "absolute",
      left: layer.x,
      top: layer.y,
      width: layer.w,
      height: layer.h,
      transformOrigin: "50% 100%",
      transform:
        `${layer.sway ? `skewX(${Math.sin(t * 1.7 + layer.x * 0.01) * layer.sway}deg) ` : ""}` +
        `${layer.breathe ? `scale(${1 + Math.sin(t * 1.4) * layer.breathe})` : ""}` || undefined,
      filter: layer.glow ? `drop-shadow(0 0 ${22 + Math.sin(t * 1.8) * 10}px ${layer.glow}) drop-shadow(0 0 6px ${layer.glow})` : undefined,
    }}
  />
);

export const Petals: React.FC<{ src: string; count: number; t: number }> = ({ src, count, t }) => (
  <>
    {Array.from({ length: count }, (_, i) => {
      const period = 7 + rnd(i + 11) * 6;
      const age = (t + rnd(i + 13) * period) % period;
      const p = age / period;
      const size = 26 + rnd(i + 17) * 22;
      const x = rnd(i + 19) * 2000 - 40 + Math.sin(age * 1.3 + i) * 70;
      return (
        <Img
          key={`pt${i}`}
          src={staticFile(src)}
          style={{
            position: "absolute",
            left: x,
            top: -80 + p * 1260,
            width: size,
            transform: `rotate(${age * (90 + rnd(i) * 160)}deg) scaleX(${Math.cos(age * 3 + i)})`,
            opacity: 0.95,
          }}
        />
      );
    })}
  </>
);

export const Lyrics: React.FC<{ segments: Segment[]; t: number; lang: string }> = ({ segments, t, lang }) => {
  const seg = segments.find((s) => t >= s.start - 0.25 && t <= s.end + 0.35);
  if (!seg) return null;
  const appear = Math.min(1, (t - (seg.start - 0.25)) / 0.2);
  return (
    <div style={{ position: "absolute", bottom: 46, width: "100%", display: "flex", justifyContent: "center", opacity: appear }}>
      <div
        style={{
          background: "rgba(255,255,255,0.88)",
          borderRadius: 999,
          padding: "14px 44px",
          boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
          fontFamily: lang === "hi" ? "'Noto Sans Devanagari', 'Kohinoor Devanagari', sans-serif" : "'Arial Rounded MT Bold', 'Nunito', sans-serif",
          fontSize: 58,
          fontWeight: 800,
          transform: `translateY(${(1 - appear) * 20}px)`,
        }}
      >
        {seg.words.map((w, i) => {
          const on = t >= w.start;
          const pop = on ? Math.max(0, 1 - (t - w.start) / 0.25) : 0;
          return (
            <span key={i} style={{ color: on ? "#ff7a1a" : "#3a3a3a", marginRight: 16, display: "inline-block", transform: `scale(${1 + pop * 0.18})` }}>
              {w.w}
            </span>
          );
        })}
      </div>
    </div>
  );
};
