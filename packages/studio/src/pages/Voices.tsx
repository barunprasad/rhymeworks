import { useState } from "react";
import { api, useLoad, type Voice } from "../api";
import { href } from "../router";
import { ErrorNote } from "../components/bits";
import { PlayIcon, useAudio } from "../components/useAudio";

/** Voice styles (mock-up P9): saved singer + music recipes for ACE-Step, with a sample to listen to and an approve step. */
export function VoicesPage() {
  const vs = useLoad(api.voices, [], ["job", "library"]);
  const audio = useAudio();
  const [open, setOpen] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const act = async (f: () => Promise<unknown>) => {
    setErr(null);
    try { await f(); vs.reload(); } catch (e) { setErr((e as Error).message.replace(/^\w+ \S+: /, "")); }
  };
  return (
    <>
      <div className="crumbs only-desktop"><a href={href("library", "cast")}>Library</a> / Voice styles</div>
      <header className="row between">
        <div>
          <h1>Voice styles</h1>
          <p className="muted small" style={{ margin: "4px 0 0" }}>Saved singer + music recipes, so every episode sounds on-brand. Kept in <span className="mono">assets/voices.toml</span>.</p>
        </div>
        <button className="btn btn-go" onClick={() => setAdding(!adding)} aria-expanded={adding}>+ New voice style</button>
      </header>
      <ErrorNote msg={err ?? vs.error} />
      {adding && <NewVoice onDone={() => { setAdding(false); vs.reload(); }} setErr={setErr} />}
      <div className="col" style={{ gap: 10, maxWidth: 860 }}>
        {(vs.data ?? []).map((v) => (
          <VoiceCard key={v.id} v={v} open={open === v.id} onToggle={() => setOpen(open === v.id ? null : v.id)} audio={audio} act={act} />
        ))}
      </div>
    </>
  );
}

function VoiceCard({ v, open, onToggle, audio, act }: { v: Voice; open: boolean; onToggle: () => void; audio: ReturnType<typeof useAudio>; act: (f: () => Promise<unknown>) => void }) {
  const playing = !!v.sample && audio.playing === v.sample;
  const [caption, setCaption] = useState(v.caption);
  const busy = !!v.job;
  return (
    <div className="card" style={{ padding: "10px 12px", display: "flex", flexDirection: "column", gap: 8, borderColor: !v.sample || v.status === "draft" ? undefined : undefined }}>
      <div className="row" style={{ gap: 10, flexWrap: "nowrap" }}>
        <button disabled={!v.sample} onClick={() => v.sample && audio.toggle(v.sample)} aria-label={v.sample ? `${playing ? "Pause" : "Play"} sample of ${v.name}` : `No sample of ${v.name} yet`}
          style={{ flex: "none", width: 44, height: 44, borderRadius: 22, border: 0, display: "grid", placeItems: "center", cursor: v.sample ? "pointer" : "default",
            background: playing ? "var(--go)" : "var(--panel-2)", color: playing ? "var(--go-ink)" : v.sample ? "var(--text)" : "var(--faint)" }}><PlayIcon on={playing} /></button>
        <button onClick={onToggle} aria-expanded={open} style={{ flex: 1, minWidth: 0, background: "none", border: 0, padding: 0, textAlign: "left", cursor: "pointer", color: "var(--text)" }}>
          <span className="row" style={{ gap: 6 }}><b>{v.name}</b>
            <span className={`pill ${v.status === "approved" ? "go" : busy ? "auto" : !v.sample ? "idle" : "gate"}`}>{v.status === "approved" ? "Approved" : busy ? "Making sample" : !v.sample ? "Draft" : "Needs review"}</span></span>
          <span className="faint small" style={{ display: "block" }}>{v.desc}</span>
        </button>
      </div>
      {open && (
        <div className="col" style={{ gap: 10, paddingTop: 4 }}>
          <div className="row" style={{ gap: 6 }}>
            {(v.langs ?? []).map((l) => <span key={l} className="chip">{l === "hi" ? "Hindi" : "English"}</span>)}
            {v.bpm && <span className="chip">{v.bpm[0]}–{v.bpm[1]} bpm</span>}
            {v.mood && <span className="chip">{v.mood}</span>}
          </div>
          <label className="col" style={{ gap: 6 }}>
            <span className="label">WHAT THE MUSIC MODEL RECEIVES</span>
            <textarea className="textarea" rows={4} value={caption} onChange={(e) => setCaption(e.target.value)} style={{ lineHeight: 1.5, fontSize: 14 }} />
          </label>
          {caption.trim() !== v.caption && <button className="btn" style={{ alignSelf: "flex-start" }} onClick={() => act(() => api.patchVoice(v.id, { caption, status: "draft" }))}>Save recipe (back to draft)</button>}
          <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
            <button className="btn" style={{ flex: 1, justifyContent: "center" }} disabled={busy} onClick={() => act(() => api.voiceSample(v.id))}>{busy ? "Making sample…" : v.sample ? "New sample · ~2 min" : "Make a sample · ~2 min"}</button>
            {v.status === "approved"
              ? <button className="btn" style={{ flex: 1, justifyContent: "center" }} onClick={() => act(() => api.patchVoice(v.id, { status: "draft" }))}>Back to draft</button>
              : <button className="btn btn-go" style={{ flex: 1, justifyContent: "center" }} disabled={!v.sample} title={v.sample ? undefined : "Listen to a sample first"} onClick={() => act(() => api.patchVoice(v.id, { status: "approved" }))}>Approve</button>}
          </div>
        </div>
      )}
    </div>
  );
}

function NewVoice({ onDone, setErr }: { onDone: () => void; setErr: (e: string | null) => void }) {
  const [name, setName] = useState("");
  const [caption, setCaption] = useState("");
  const [desc, setDesc] = useState("");
  const [langs, setLangs] = useState<string[]>(["hi", "en"]);
  const [busy, setBusy] = useState(false);
  const toggle = (l: string) => setLangs(langs.includes(l) ? langs.filter((x) => x !== l) : [...langs, l]);
  return (
    <div className="card pad col" style={{ gap: 12, maxWidth: 860 }}>
      <label className="col" style={{ gap: 6 }}><span className="label">NAME</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Village kirtan" /></label>
      <label className="col" style={{ gap: 6 }}><span className="label">SHORT DESCRIPTION</span><input className="input" value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Group of kids, dholak and manjira, call and response" /></label>
      <label className="col" style={{ gap: 6 }}>
        <span className="label">SINGER + MUSIC RECIPE</span>
        <textarea className="textarea" rows={3} value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="kids bhajan, group of children singing call and response, dholak, manjira, harmonium, joyful village kirtan feel" style={{ lineHeight: 1.5 }} />
      </label>
      <div className="row" style={{ gap: 8 }}>
        {[["hi", "Hindi"], ["en", "English"]].map(([k, l]) => <button key={k} className={`tab ${langs.includes(k) ? "active" : ""}`} aria-pressed={langs.includes(k)} onClick={() => toggle(k)}>{l}</button>)}
      </div>
      <button className="btn btn-go" style={{ alignSelf: "flex-start" }} disabled={busy || !name.trim() || caption.trim().split(/\s+/).length < 4}
        onClick={async () => { setBusy(true); setErr(null); try { await api.newVoice({ name, caption, desc, langs }); onDone(); } catch (e) { setErr((e as Error).message.replace(/^\w+ \S+: /, "")); } finally { setBusy(false); } }}>
        Save and make a sample
      </button>
    </div>
  );
}
