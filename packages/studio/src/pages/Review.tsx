import { useState } from "react";
import { api, useLoad, type Shot } from "../api";
import { go, href } from "../router";
import { CheckDetails, CheckPill, ErrorNote, ReviewPill } from "../components/bits";
import { useIsDesktop } from "../components/MobileBars";
import { JobBar } from "./Episode";

type Decision = "approved" | "redo" | null;

export function ReviewPage({ slug, stage }: { slug: string; stage: "keys" | "clips" }) {
  const ep = useLoad(() => api.episode(slug), [slug], ["job", "output", "review"], slug);
  const desktop = useIsDesktop();
  const [selId, setSelId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const d = ep.data;
  if (!d) return <ErrorNote msg={ep.error} />;

  const out = (s: Shot) => (stage === "keys" ? s.key : s.clip);
  const made = d.shots.filter((s) => out(s).url);
  const decided = made.filter((s) => ["approved", "redo"].includes(out(s).status)).length;
  const allApproved = d.shots.length > 0 && d.shots.every((s) => out(s).status === "approved");
  const sel = d.shots.find((s) => s.id === selId) ?? made.find((s) => out(s).status === "to_review") ?? made[0];
  const what = stage === "keys" ? "keyframes" : "clips";
  const flagged = made.filter((s) => out(s).check?.state === "flag" && out(s).status === "to_review");   // decided ones keep their pill only

  const decide = async (s: Shot, decision: Decision, withNote = "") => {
    setErr(null);
    try {
      await api.review(slug, stage, s.id, decision, withNote);
      setNote("");
      if (decision) {   // jump to the next one waiting
        const next = made.find((x) => x.id !== s.id && out(x).status === "to_review");
        if (next) setSelId(next.id);
      }
      ep.reload();
    } catch (e) { setErr((e as Error).message); }
  };
  const approveRest = async () => {
    for (const s of made.filter((x) => out(x).status === "to_review")) await api.review(slug, stage, s.id, "approved");
    ep.reload();
  };
  const redoFlagged = async () => {
    setErr(null);
    try {
      for (const s of flagged) await api.review(slug, stage, s.id, "redo", (out(s).check?.flags ?? []).join("; ").slice(0, 200));
      ep.reload();
    } catch (e) { setErr((e as Error).message); }
  };
  const checkAgain = async () => {
    try { await api.check(slug, stage); ep.reload(); } catch (e) { setErr((e as Error).message); }
  };
  const next = async () => {
    try { await api.run(slug, stage === "keys" ? "clips" : "assemble"); go("episodes", slug); } catch (e) { setErr((e as Error).message); }
  };
  const step = (dir: 1 | -1) => {
    if (!sel || !made.length) return;
    const i = made.findIndex((s) => s.id === sel.id);
    setSelId(made[(i + dir + made.length) % made.length].id);
  };

  const continueBtn = (
    <button className={`btn ${allApproved ? "btn-go" : ""}`} disabled={!allApproved} onClick={next}>
      {allApproved ? (stage === "keys" ? "Render clips →" : "Assemble episode →") : "Approve all to continue"}
    </button>
  );
  const approveRestBtn = <button className="btn" onClick={approveRest} disabled={!made.some((s) => out(s).status === "to_review")}>Approve all remaining</button>;
  const progress = (
    <div className="bar" role="progressbar" aria-valuenow={decided} aria-valuemin={0} aria-valuemax={made.length} aria-label={`${what} decided`}>
      <span style={{ width: `${made.length ? (decided / made.length) * 100 : 0}%` }} />
    </div>
  );
  const banner = flagged.length > 0 && (
    <div className="ac-banner" role="status">
      <span>⚠ Auto-check: {flagged.length === 1 ? "1 shot" : `${flagged.length} shots`} to look at:{" "}
        {flagged.map((s, i) => <span key={s.id}>{i ? ", " : ""}<button className="linkish" onClick={() => setSelId(s.id)}>{s.id}</button></span>)}
      </span>
      <button className="btn" style={{ marginLeft: "auto" }} onClick={redoFlagged}>Redo {flagged.length === 1 ? "it" : `all ${flagged.length}`}</button>
    </div>
  );
  const summary = `${decided} of ${made.length} decided${made.length < d.shots.length ? ` · ${d.shots.length - made.length} not made yet` : ""}`;

  const details = sel && (
    <>
      <div className="row between"><h2>{sel.id}</h2><ReviewPill s={out(sel).status} /></div>
      {out(sel).note && <div className="small" style={{ color: "var(--gate-text)" }}>Note: {out(sel).note}</div>}
      <CheckDetails c={out(sel).check} stage={stage} onAgain={out(sel).url ? checkAgain : undefined} />
      <details className="prompt" open={desktop}>
        <summary className="label">{stage === "keys" ? "KEYFRAME PROMPT" : "MOTION PROMPT"}</summary>
        <div className="small" style={{ color: "var(--text-2)", lineHeight: 1.5, maxHeight: 220, overflow: "auto", marginTop: 6 }}>{stage === "keys" ? sel.key_prompt : sel.motion}</div>
      </details>
      <div className="faint small">seed {sel.seed} · scene {sel.scene} · {sel.frames} frames{sel.sing ? " · lip-sync" : ""}</div>
      <label className="col" style={{ gap: 6 }}>
        <span className="small muted">Note for the redo (optional)</span>
        <input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. the monkey should have no moustache" />
      </label>
    </>
  );
  const media = (s: Shot, controls: boolean) => (stage === "keys"
    ? <img src={out(s).url!} alt={`Keyframe ${s.id}`} className="thumb" />
    : <video key={out(s).url} src={out(s).url!} className="thumb" controls={controls} autoPlay loop muted playsInline />);

  // ---------------------------------------------------------------- phones: one shot at a time
  if (!desktop) {
    return (
      <>
        <div className="row between" style={{ gap: 6 }}><span className="muted small">{summary}</span></div>
        {progress}
        <ErrorNote msg={err ?? ep.error} />
        {d.jobs.map((j) => <JobBar key={j.id} j={j} />)}
        {banner}
        {sel && out(sel).url ? (
          <div className="viewer">
            {media(sel, true)}
            {made.length > 1 && <>
              <button className="viewer-nav prev" onClick={() => step(-1)} aria-label="Previous shot"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M15 5l-7 7 7 7" /></svg></button>
              <button className="viewer-nav next" onClick={() => step(1)} aria-label="Next shot"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M9 5l7 7-7 7" /></svg></button>
            </>}
          </div>
        ) : <div className="empty">Nothing made yet for this step.</div>}
        <div className="filmstrip" role="group" aria-label={`All ${what}`}>
          {d.shots.map((s) => {
            const o = out(s);
            const thumb = s.key.url;   // clips use their keyframe as the thumbnail
            return (
              <button key={s.id} onClick={() => setSelId(s.id)} disabled={!o.url} aria-label={`${s.id}, ${o.status.replace("_", " ")}${o.check?.state === "flag" ? ", auto-check found something" : ""}`}
                aria-current={sel?.id === s.id ? "true" : undefined} className={sel?.id === s.id ? "on" : ""}>
                {thumb ? <img src={thumb} alt="" /> : <span />}
                <i className={`st ${o.status}`} />
                {o.check?.state === "flag" && <b className="warn" aria-hidden="true">⚠</b>}
              </button>
            );
          })}
        </div>
        <div className="col">{details}</div>
        <div className="col" style={{ gap: 8 }}>{approveRestBtn}{continueBtn}</div>
        {sel && (
          <div className="actionbar">
            <button className="btn" style={{ flex: 1 }} disabled={!out(sel).url} onClick={() => decide(sel, "redo", note)}>Redo</button>
            {out(sel).status === "approved" || out(sel).status === "redo"
              ? <button className="btn" style={{ flex: 2 }} onClick={() => decide(sel, null)}>Undo decision</button>
              : <button className="btn btn-go" style={{ flex: 2 }} disabled={!out(sel).url} onClick={() => decide(sel, "approved")}>Approve</button>}
          </div>
        )}
      </>
    );
  }

  // ---------------------------------------------------------------- desktop: grid + side panel
  return (
    <>
      <div className="crumbs"><a href={href("episodes", slug)}>{d.title}</a> / Review {what}</div>
      <header className="row between">
        <div>
          <h1>Review {what}</h1>
          <p className="muted" style={{ margin: "4px 0 0" }}>{summary} · a redo re-renders just that shot</p>
        </div>
        <div className="row">{approveRestBtn}{continueBtn}</div>
      </header>
      <ErrorNote msg={err ?? ep.error} />
      {progress}
      {d.jobs.map((j) => <JobBar key={j.id} j={j} />)}
      {banner}

      <div className="split">
        <div className="grow">
          <div className="grid grid-keys">
            {d.shots.map((s) => {
              const o = out(s);
              return (
                <div key={s.id} className={`card ${sel?.id === s.id ? "selected" : o.status === "to_review" ? "gate" : ""}`} style={{ overflow: "hidden" }}>
                  <button onClick={() => setSelId(s.id)} aria-label={`Open ${s.id}`} style={{ padding: 0, border: 0, background: "none", display: "block", width: "100%", cursor: "pointer" }}>
                    {o.url ? (stage === "keys" ? <img src={o.url} alt="" className="thumb" style={{ borderRadius: 0 }} />
                      : <video src={o.url} className="thumb" style={{ borderRadius: 0 }} muted loop playsInline preload="metadata"
                          onMouseEnter={(e) => e.currentTarget.play()} onMouseLeave={(e) => e.currentTarget.pause()} />)
                      : <div className="thumb" style={{ borderRadius: 0, display: "grid", placeItems: "center", color: "var(--faint)", fontSize: 13 }}>not made yet</div>}
                  </button>
                  <div className="col" style={{ padding: "10px 12px", gap: 8 }}>
                    <div className="row between"><b>{s.id}</b><ReviewPill s={o.status} /></div>
                    <CheckPill c={o.check} stage={stage} />
                    {o.url && (
                      <div className="row" style={{ gap: 6 }}>
                        <button className="btn btn-soft-go" style={{ flex: 1, justifyContent: "center" }} onClick={() => decide(s, "approved")}>Approve</button>
                        <button className="btn" style={{ flex: 1, justifyContent: "center" }} onClick={() => decide(s, "redo")}>Redo</button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {sel && (
          <aside className="side panel" aria-label="Selected shot">
            {out(sel).url && media(sel, true)}
            {details}
            <div className="row">
              <button className="btn btn-go" disabled={!out(sel).url} onClick={() => decide(sel, "approved")}>Approve</button>
              <button className="btn" disabled={!out(sel).url} onClick={() => decide(sel, "redo", note)}>Redo this shot</button>
              {out(sel).status !== "to_review" && out(sel).status !== "missing" && <button className="btn btn-quiet" onClick={() => decide(sel, null)}>Undo decision</button>}
            </div>
            <p className="faint small" style={{ margin: 0 }}>Redo picks a new seed (saved in episode.toml) so you get a different take. Prompt editing comes with the shot editor.</p>
          </aside>
        )}
      </div>
    </>
  );
}
