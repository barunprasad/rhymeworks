// "Open on your phone": the studio's Wi-Fi address as a branded QR code (desktop only; phones are already there).
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { logoArea, qrEncode } from "../lib/qr.js";

const INK = "#062423";

/** QR code as SVG: square data modules, rounded finder "eyes", the Rhymeworks ♪ tile in the middle (error correction H). */
export function QRCodeSVG({ text, size = 260 }: { text: string; size?: number }) {
  const q = useMemo(() => qrEncode(text, "H"), [text]);
  const a = logoArea(q);
  const Q = 2, N = q.size + 2 * Q;
  const inFinder = (x: number, y: number) =>
    (x < 7 && y < 7) || (x >= q.size - 7 && y < 7) || (x < 7 && y >= q.size - 7);
  const inLogo = (x: number, y: number) => x >= a.x && x < a.x + a.n && y >= a.y && y < a.y + a.n && !q.isFunction[y][x];
  let d = "";
  for (let y = 0; y < q.size; y++) for (let x = 0; x < q.size; x++) {
    if (q.dark[y][x] && !inFinder(x, y) && !inLogo(x, y)) d += `M${x + Q} ${y + Q}h1v1h-1z`;
  }
  const eyes = [[0, 0], [q.size - 7, 0], [0, q.size - 7]];
  const lx = a.x + Q + 0.6, ln = a.n - 1.2;   // the logo tile, inset so a white ring stays around it
  return (
    <svg viewBox={`0 0 ${N} ${N}`} width={size} height={size} role="img" aria-label={`QR code for ${text}`} shapeRendering="crispEdges" style={{ display: "block" }}>
      <rect width={N} height={N} rx={1.6} fill="#fff" />
      <path d={d} fill={INK} />
      {eyes.map(([ex, ey]) => (
        <g key={`${ex}-${ey}`} shapeRendering="geometricPrecision">
          <rect x={ex + Q + 0.5} y={ey + Q + 0.5} width={6} height={6} rx={1.6} fill="none" stroke={INK} strokeWidth={1} />
          <rect x={ex + Q + 2} y={ey + Q + 2} width={3} height={3} rx={0.8} fill={INK} />
        </g>
      ))}
      <g shapeRendering="geometricPrecision" transform={`translate(${lx} ${lx}) scale(${ln / 32})`}>
        <rect width="32" height="32" rx="9" fill="#19C6C0" />
        <path d="M13 22V10l9-2v12" fill="none" stroke={INK} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="10.5" cy="22" r="2.6" fill={INK} /><circle cx="19.5" cy="20" r="2.6" fill={INK} />
      </g>
    </svg>
  );
}

export function PhoneSheet({ url: first, onClose }: { url: string | null; onClose: () => void }) {
  const done = useRef<HTMLButtonElement>(null);
  const [url, setUrl] = useState(first);   // the link carries a private key (studio/lock.py)
  const [busy, setBusy] = useState(false);
  const renew = () => { setBusy(true); api.lanReset().then((r) => setUrl(r.lan_url)).finally(() => setBusy(false)); };
  useEffect(() => {
    done.current?.focus();
    const f = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", f);
    return () => window.removeEventListener("keydown", f);
  }, [onClose]);
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 50, display: "grid", placeItems: "center", padding: 16 }}>
      <button aria-label="Close" onClick={onClose} style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,.6)", border: 0, cursor: "pointer" }} />
      <section role="dialog" aria-modal="true" aria-labelledby="phone-title" className="card"
        style={{ position: "relative", width: "min(380px, 100%)", padding: 24, display: "flex", flexDirection: "column", alignItems: "center", gap: 14, textAlign: "center",
          background: "linear-gradient(180deg, #1d2a2c 0%, var(--panel) 55%)", borderColor: "#1f4a47" }}>
        <div className="row" style={{ gap: 10 }}>
          <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="#19C6C0" />
            <path d="M13 22V10l9-2v12" fill="none" stroke={INK} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="10.5" cy="22" r="2.6" fill={INK} /><circle cx="19.5" cy="20" r="2.6" fill={INK} /></svg>
          <h2 id="phone-title" className="brand" style={{ margin: 0, fontSize: 24 }}>Rhymeworks Studio</h2>
        </div>
        {url ? (
          <>
            <p className="muted" style={{ margin: 0 }}>Point your phone's camera at the code.</p>
            <div style={{ padding: 10, background: "#fff", borderRadius: 18, boxShadow: "0 10px 30px rgba(0,0,0,.35)" }}><QRCodeSVG text={url} /></div>
            <code className="mono" style={{ fontSize: 15, color: "var(--go-text)" }}>{url.split("/api/")[0]}</code>
            <p className="faint small" style={{ margin: 0, lineHeight: 1.45 }}>Phone and Mac on the same Wi-Fi. The code holds a private key: only phones that scan it can open the studio, and they stay linked.</p>
            <button className="btn" disabled={busy} onClick={renew} style={{ justifyContent: "center" }}>Make a new link (unlinks every phone)</button>
          </>
        ) : (
          <>
            <p className="muted" style={{ margin: 0, lineHeight: 1.5 }}>The studio is only open on this Mac right now. To use it on your phone, stop it (Ctrl-C) and start it with:</p>
            <code className="token" style={{ fontSize: 15, padding: "8px 12px" }}>npm run studio:lan</code>
            <p className="faint small" style={{ margin: 0 }}>The terminal and this window then show a code to scan.</p>
          </>
        )}
        <button ref={done} className="btn btn-go" style={{ width: "100%", justifyContent: "center" }} onClick={onClose}>Done</button>
      </section>
    </div>
  );
}
