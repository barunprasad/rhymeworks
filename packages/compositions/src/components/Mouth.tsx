const INK = "#2f2626";
const FILL = "#7a2e3a";
const TONGUE = "#ee8a97";

/** Procedural mouth: identical on every pose. `state` is continuous openness 0 (closed) … 3 (wide). */
export const Mouth: React.FC<{ state: number; width: number }> = ({ state, width }) => {
  const h = width * 0.7;
  if (state < 0.3) {
    return (
      <svg width={width} height={h} viewBox="0 0 100 70" style={{ overflow: "visible" }}>
        <path d="M22 28 Q50 48 78 28" stroke={INK} strokeWidth={8} fill="none" strokeLinecap="round" />
      </svg>
    );
  }
  const open = Math.min(38, 6 + state * 11);
  return (
    <svg width={width} height={h} viewBox="0 0 100 70" style={{ overflow: "visible" }}>
      <path
        d={`M18 24 Q50 ${24 + open * 0.3} 82 24 Q50 ${24 + open * 1.55} 18 24 Z`}
        fill={FILL}
        stroke={INK}
        strokeWidth={7}
        strokeLinejoin="round"
      />
      {state >= 1.6 && <ellipse cx={50} cy={24 + open * 1.0} rx={15} ry={open * 0.26} fill={TONGUE} />}
    </svg>
  );
};
