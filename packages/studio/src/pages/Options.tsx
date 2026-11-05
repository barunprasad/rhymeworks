// Pick 1 of N keyframes for a shot (#/episodes/<slug>/options/<shot>): draw options with new seeds, choose one.
import { useState } from "react";
import { api, useLoad } from "../api";
import { href } from "../router";
import { ErrorNote } from "../components/bits";
import { FEELINGS } from "./ShotList";

export function OptionsPage({ slug, sid }: { slug: string; sid: string }) {
  const o = useLoad(() => api.options(slug, sid), [slug, sid], ["job", "output", "spec", "review"], slug);
  const [pick, setPick] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [ask, setAsk] = useState("");
  const d = o.data;
  if (!d) return <ErrorNote msg={o.error} />;

  const all = [
    ...(d.current.url ? [{ seed: d.current.seed, url: d.current.url, current: true }] : []),
    ...d.options.filter((x) => x.seed !== d.current.seed).map((x) => ({ ...x, current: false })),
  ];
  const chosen = all.find((x) => x.seed === pick) ?? all[0];
  const letter = (i: number) => String.fromCharCode(65 + i);
  const run = async (label: string, f: () => Promise<unknown>) => {
    setBusy(label); setErr(null);
    try { await f(); o.reload(); } catch (e) { setErr((e as Error).message.replace(/^\w+ \S+: /, "")); } finally { setBusy(null); }
  };
  const feel = d.shot.feel ?? "";

  return (
    <>
      <ErrorNote msg={err ?? o.error} />
      {chosen ? <img src={chosen.url} alt={`Option ${letter(all.indexOf(chosen))}`} className="thumb" style={{ borderRadius: 16 }} />
        : <div className="empty">No keyframe yet. Draw some options below.</div>}

      <div className="grid-tiles" role="radiogroup" aria-label="Options">
        {all.map((x, i) => (
          <button key={x.seed} role="radio" aria-checked={chosen?.seed === x.seed} className={`tile ${chosen?.seed === x.seed ? "on" : ""}`} onClick={() => setPick(x.seed)}>
            <img src={x.url} alt="" />
            <span className="tags"><span className="tag">{letter(i)}</span>{x.current && <span className="tag go">in use</span>}</span>
          </button>
        ))}
        {Array.from({ length: d.waiting }, (_, i) => (
          <div key={"w" + i} className="tile" aria-label="Option being drawn"><span className="ph">{i === 0 && d.jobs.some((j) => j.status === "running") ? "Drawing… about 2 min each" : "Waiting in the queue"}</span></div>
        ))}
      </div>

      <div className="col" style={{ gap: 6 }}>
        <span className="label">LYRIC</span>
        <span className="lyric" style={{ fontSize: 19 }}>{d.shot.lyric || "(instrumental)"}</span>
      </div>
      <div className="col" style={{ gap: 8 }}>
        <span className="label">FEELING</span>
        <div className="chips" role="group" aria-label="Feeling">
          {FEELINGS.map((f) => (
            <button key={f} className="chip-btn" aria-pressed={feel === f} disabled={!!busy}
              onClick={() => run("feel", () => api.saveShot(slug, sid, { feel: feel === f ? "" : f }))}>{f}</button>
          ))}
        </div>
        {feel && !FEELINGS.includes(feel) && <span className="faint small">Now: {feel}</span>}
        <span className="faint small">A new feeling applies to the next options you draw.</span>
      </div>
      <form className="col" style={{ gap: 8 }} onSubmit={(e) => { e.preventDefault(); if (ask.trim()) run("ask", async () => { await api.askDirector(slug, ask, [sid]); window.location.hash = href("episodes", slug, "director", sid); }); }}>
        <label htmlFor="opt-ask" className="label">CHANGE IN YOUR WORDS</label>
        <div className="composer">
          <input id="opt-ask" value={ask} onChange={(e) => setAsk(e.target.value)} placeholder="Swing higher, Subhadra laughing with her head back" />
          <button className="round-go" aria-label="Ask the director" disabled={!ask.trim() || !!busy}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
          </button>
        </div>
        <span className="faint small">The director rewrites this shot's prompt; you approve the change before anything is drawn.</span>
      </form>

      <div className="actionbar">
        <button className="btn" style={{ flex: 1 }} disabled={!!busy} onClick={() => run("more", () => api.makeOptions(slug, sid, 4))}>{busy === "more" ? "Queuing…" : all.length ? "4 more" : "Draw 4 options"}</button>
        <button className="btn btn-go" style={{ flex: 2 }} disabled={!chosen || chosen.current || !!busy}
          onClick={() => chosen && run("use", async () => { await api.useOption(slug, sid, chosen.seed); setPick(null); })}>
          {!chosen ? "Nothing to use yet" : chosen.current ? "In use" : busy === "use" ? "Saving…" : `Use option ${letter(all.indexOf(chosen))}`}
        </button>
      </div>
    </>
  );
}
