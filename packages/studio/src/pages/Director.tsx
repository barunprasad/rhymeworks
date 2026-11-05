// Director: change the shot list in plain words. The writer model proposes; nothing changes until you press Apply.
import { useState } from "react";
import { api, useLoad, type DirectorChange, type DirectorProposal } from "../api";
import { href } from "../router";
import { ErrorNote } from "../components/bits";

const SUGGEST = ["Less singing, more feelings on faces", "More close-ups of Jagannath", "Slower camera moves in the last verse", "Bring the animals into the meadow shots"];
const FIELD: Record<string, string> = { key: "Keyframe", motion: "Motion", feel: "Feeling", sing: "Lip-sync", scene: "Scene", end: "Hold pose", lines: "Length" };
const show = (k: string, v: unknown) => (v === null || v === undefined || v === "" ? "none"
  : k === "sing" ? (v ? "on" : "off") : k === "end" ? (v === "same" ? "on" : "off") : k === "lines" ? `${v} bar${v === 1 ? "" : "s"}` : String(v));

function Change({ c }: { c: DirectorChange }) {
  return (
    <div className="change">
      {c.image ? <img src={c.image} alt="" /> : <span className="ph" />}
      <div className="col" style={{ gap: 4, minWidth: 0, flex: 1 }}>
        <b style={{ fontSize: 13.5 }}>{c.id}{c.why ? <span className="faint" style={{ fontWeight: 400 }}> · {c.why}</span> : null}</b>
        {Object.entries(c.fields).map(([k, v]) => (
          <div key={k} className="diff">
            <span className="faint">{FIELD[k] ?? k}: </span>
            {k === "key" || k === "motion"
              ? <ins>{show(k, v)}</ins>
              : <><del>{show(k, c.before[k])}</del> → <ins>{show(k, v)}</ins></>}
          </div>
        ))}
      </div>
    </div>
  );
}

function Proposal({ p, slug, onDone, busy, act }: { p: DirectorProposal; slug: string; onDone?: () => void; busy: string | null; act: (l: string, f: () => Promise<unknown>) => void }) {
  const live = p.status === "proposed";
  return (
    <div className="col" style={{ gap: 10, alignSelf: "stretch" }}>
      <div className="bubble me">{p.ask}{p.shots.length ? <span style={{ opacity: .7 }}> · {p.shots.join(", ")}</span> : null}</div>
      <div className="bubble it">{p.reply || "No reply."}</div>
      {(p.changes.length > 0 || p.moves.length > 0) && (
        <div className="card" style={{ overflow: "hidden", opacity: live ? 1 : 0.7 }}>
          {p.changes.map((c) => <Change key={c.id} c={c} />)}
          {p.moves.map((m) => (
            <div key={"m" + m.id} className="change"><span className="diff">Move <b>{m.id}</b> {m.before ? <>before <b>{m.before}</b></> : "to the end"}</span></div>
          ))}
          {live ? (
            <div className="row" style={{ padding: "10px 12px 12px", gap: 8, flexWrap: "nowrap", borderTop: "1px solid rgba(255,255,255,.06)" }}>
              <button className="btn btn-go" style={{ flex: 2, justifyContent: "center" }} disabled={!!busy} onClick={() => act("apply", async () => { await api.applyDirector(slug); onDone?.(); })}>{busy === "apply" ? "Applying…" : "Apply changes"}</button>
              <button className="btn" style={{ flex: 1, justifyContent: "center" }} disabled={!!busy} onClick={() => act("discard", () => api.discardDirector(slug))}>Discard</button>
            </div>
          ) : <div className="faint small" style={{ padding: "8px 12px 10px" }}>{p.status === "applied" ? `Applied${p.errors?.length ? ` · ${p.errors.length} could not be applied` : ""}` : p.status === "discarded" ? "Discarded" : "Replaced by a newer request"}</div>}
        </div>
      )}
      {live && p.changes.some((c) => ["key", "feel", "scene", "sing", "end"].some((k) => k in c.fields)) && (
        <span className="faint small">Applying makes {p.changes.filter((c) => ["key", "feel", "scene", "sing", "end"].some((k) => k in c.fields)).length} keyframe(s) out of date; you can remake them right after.</span>
      )}
    </div>
  );
}

/** The conversation + composer. `compact` = the desktop side panel on the episode page. */
export function DirectorPanel({ slug, shot, compact = false }: { slug: string; shot?: string; compact?: boolean }) {
  const dir = useLoad(() => api.director(slug), [slug], ["job", "spec"], slug);
  const [ask, setAsk] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [remake, setRemake] = useState<string[]>([]);
  const d = dir.data;
  const act = async (label: string, f: () => Promise<unknown>) => {
    setBusy(label); setErr(null);
    try { const r = await f(); if (r && typeof r === "object" && "result" in r) setRemake((r as { result: { remake: string[] } }).result.remake); dir.reload(); }
    catch (e) { setErr((e as Error).message.replace(/^\w+ \S+: /, "")); } finally { setBusy(null); }
  };
  const send = (text: string) => text.trim() && act("ask", async () => { await api.askDirector(slug, text, shot ? [shot] : undefined); setAsk(""); });
  const thinking = d?.jobs.length ? d.jobs[0] : null;
  const past = (d?.history ?? []).slice(0, compact ? 1 : 6);

  return (
    <div className="col" style={{ gap: 14 }}>
      <ErrorNote msg={err ?? dir.error} />
      {!d?.proposal && !thinking && past.length === 0 && (
        <div className="bubble it">Tell me what to change: who is in a shot, the feeling, less singing, the order, a calmer camera. I'll show you the changes first.</div>
      )}
      {[...past].reverse().map((p) => <Proposal key={p.created + p.status} p={p} slug={slug} busy={busy} act={act} />)}
      {d?.proposal && <Proposal p={d.proposal} slug={slug} busy={busy} act={act} />}
      {thinking && (
        <>
          {thinking.args.ask && <div className="bubble me">{thinking.args.ask}</div>}
          <div className="bubble it">{thinking.status === "running" ? "Thinking… (the writer model takes about a minute)" : "Waiting for the GPU queue…"}</div>
        </>
      )}
      {remake.length > 0 && (
        <div className="notice" role="status">
          <span style={{ flex: 1 }}>{remake.length} keyframe{remake.length > 1 ? "s" : ""} changed: {remake.join(", ")}.</span>
          <button className="btn btn-gate" disabled={!!busy} onClick={() => act("remake", async () => { await api.run(slug, "keys", remake, remake); setRemake([]); })}>Remake them</button>
        </div>
      )}
      <form className="col" style={{ gap: 8 }} onSubmit={(e) => { e.preventDefault(); send(ask); }}>
        {!compact && (
          <div className="chips" role="group" aria-label="Suggestions">
            {SUGGEST.map((s) => <button type="button" key={s} className="chip-btn" onClick={() => setAsk(s)}>{s}</button>)}
          </div>
        )}
        <div className="composer">
          <label htmlFor={`dir-${compact ? "p" : "f"}`} className="visually-hidden">Tell the director what to change</label>
          <input id={`dir-${compact ? "p" : "f"}`} value={ask} onChange={(e) => setAsk(e.target.value)} placeholder={shot ? `What should change in ${shot}?` : "Tell the director what to change"} />
          <button className="round-go" aria-label="Send" disabled={!ask.trim() || !!busy || !!thinking}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
          </button>
        </div>
        {d?.proposal && <span className="faint small">A new request replaces the open proposal.</span>}
      </form>
    </div>
  );
}

export function DirectorPage({ slug, shot }: { slug: string; shot?: string }) {
  return (
    <>
      {shot && <div className="row small muted" style={{ gap: 6 }}>About shot <b style={{ color: "var(--text)" }}>{shot}</b> · <a href={href("episodes", slug, "director")}>whole episode</a></div>}
      <DirectorPanel slug={slug} shot={shot} />
    </>
  );
}
