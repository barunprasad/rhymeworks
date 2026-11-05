import { useRef, useState } from "react";
import { api, fmtTime, useLoad, type ShotFields, type ShotList, type ShotRow, type TokenInfo } from "../api";
import { go, href } from "../router";
import { ErrorNote } from "../components/bits";
import { useIsDesktop } from "../components/MobileBars";
import { JobBar } from "./Episode";

export const FEELINGS = ["quiet devotion, eyes shining with love", "joyful wonder", "trusting surrender, a calm smile", "playful delight",
  "longing, hopeful eyes", "peaceful calm", "excited celebration", "gentle tenderness"];

interface Draft { lyric: string; scene: string; key: string; motion: string; feel: string; sing: boolean; end: ShotRow["end"]; lines: number }
const toDraft = (s: ShotRow): Draft => ({ lyric: s.lyric ?? "", scene: s.scene, key: s.key ?? "", motion: s.motion ?? "", feel: s.feel ?? "", sing: s.sing, end: s.end, lines: s.lines ?? 1 });
const same = (a: Draft, b: Draft) => JSON.stringify(a) === JSON.stringify(b);

/** Shot list editor (mock-up P5): one card per lyric line; tap to edit who is where (keyframe) and what happens (motion). */
export function ShotListPage({ slug }: { slug: string }) {
  const sl = useLoad(() => api.shotlist(slug), [slug], ["spec", "job", "output"], slug);
  const desktop = useIsDesktop();
  const [open, setOpen] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [stale, setStale] = useState<Set<string>>(new Set());   // keyframe exists but its prompt was changed since
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const d = sl.data;
  if (!d) return <ErrorNote msg={sl.error} />;

  const empty = d.shots.filter((s) => s.empty).length;
  const missing = d.shots.filter((s) => !s.image && !s.empty).length;
  const drafting = d.jobs.some((j) => j.kind === "draft");
  const making = d.jobs.some((j) => j.kind === "keys");
  const lineSec = d.song.line_seconds ?? 0;

  const act = async (f: () => Promise<unknown>) => {
    setBusy(true); setErr(null);
    try { await f(); sl.reload(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const draftAll = () => act(() => api.run(slug, "draft"));
  const makeKeys = () => act(async () => { await api.run(slug, "keys"); go("episodes", slug); });

  const cta = drafting ? <button className="btn btn-go" disabled style={{ flex: 1 }}>Drafting shots…</button>
    : empty ? <button className="btn btn-go" style={{ flex: 1 }} disabled={busy} onClick={draftAll}>Draft {empty} shot{empty > 1 ? "s" : ""} with AI</button>
    : making ? <a className="btn btn-go" style={{ flex: 1 }} href={href("queue")}>Keyframes are being made · see queue</a>
    : missing ? <button className="btn btn-go" style={{ flex: 1 }} disabled={busy} onClick={makeKeys}>Approve and make {missing} keyframe{missing > 1 ? "s" : ""}</button>
    : <a className="btn btn-go" style={{ flex: 1 }} href={href("episodes", slug, "review", "keys")}>Review keyframes</a>;

  return (
    <>
      <div className="crumbs only-desktop"><a href={href("episodes", slug)}>{d.episode.title}</a> / Shot list</div>
      <header className="row between">
        <div>
          <h1 className="only-desktop">Shot list</h1>
          <p className="muted small" style={{ margin: "4px 0 0" }}>
            {d.shots.length} shots{lineSec ? ` · ${lineSec.toFixed(1)} s per lyric line` : ""}{empty ? ` · ${empty} without prompts` : ""} · saved to episode.toml
          </p>
        </div>
        {desktop && <div className="row">{cta}</div>}
      </header>
      <ErrorNote msg={err ?? sl.error} />
      {d.jobs.map((j) => <JobBar key={j.id} j={j} />)}
      {empty > 0 && !drafting && (
        <div className="card pad col" style={{ gap: 8, borderColor: "var(--gate-line)" }}>
          <b>{empty} shot{empty > 1 ? "s need" : " needs"} prompts</b>
          <span className="muted small" style={{ lineHeight: 1.45 }}>
            The writer model (gemma4, local, about a minute) drafts who is where and what happens for each lyric line, using your characters and scenes.
            You then tweak anything here before a single keyframe is made.
          </span>
        </div>
      )}

      <div className="col" style={{ gap: 8, maxWidth: 980 }}>
        {d.shots.map((s, i) => (
          <ShotCard key={s.id} s={s} list={d} index={i} open={open === s.id} draft={drafts[s.id]} stale={stale.has(s.id)}
            onToggle={() => setOpen(open === s.id ? null : s.id)}
            onDraft={(x) => setDrafts((m) => { const n = { ...m }; if (x) n[s.id] = x; else delete n[s.id]; return n; })}
            onSaved={(keyChanged) => { if (keyChanged && s.image) setStale((x) => new Set(x).add(s.id)); }}
            onRemade={() => setStale((x) => { const n = new Set(x); n.delete(s.id); return n; })}
            reload={sl.reload} setErr={setErr} slug={slug}
            onOpen={(id) => setOpen(id)} />
        ))}
        <button className="btn" style={{ justifyContent: "center", borderStyle: "dashed", minHeight: 48 }} disabled={busy}
          onClick={() => act(async () => { const n = await api.addShot(slug, {}); setOpen(n.id); })}>+ Add a shot at the end</button>
      </div>

      {!desktop && <div className="actionbar">{cta}</div>}
    </>
  );
}

interface CardProps {
  s: ShotRow; list: ShotList; index: number; open: boolean; draft?: Draft; stale: boolean; slug: string;
  onToggle: () => void; onDraft: (d: Draft | null) => void; onSaved: (keyChanged: boolean) => void; onRemade: () => void;
  onOpen: (id: string) => void; reload: () => void; setErr: (e: string | null) => void;
}

function ShotCard({ s, list, index, open, draft, stale, slug, onToggle, onDraft, onSaved, onRemade, onOpen, reload, setErr }: CardProps) {
  const dirty = !!draft && !same(draft, toDraft(s));
  const thumb = s.image ?? list.scenes.find((x) => x.id === s.scene)?.image;
  const summary = s.lyric || (s.key ? s.key : "No prompts yet");
  return (
    <div className="card" style={{ borderColor: open ? "var(--line-2)" : s.empty ? "var(--gate-line)" : undefined }}>
      <button className="shot-card" onClick={onToggle} aria-expanded={open} aria-controls={`edit-${s.id}`}
        style={{ width: "100%", background: "none", border: 0, textAlign: "left", cursor: "pointer", color: "var(--text)" }}>
        {thumb ? <img src={thumb} alt="" style={{ opacity: s.image ? 1 : 0.35 }} /> : <span className="thumb" />}
        <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 4 }}>
          <span className="row" style={{ gap: 6 }}>
            <b>{s.id}</b>
            {s.start !== undefined && <span className="faint small">{fmtTime(s.start)}{s.dur ? ` · ${s.dur.toFixed(1)} s` : ""}</span>}
            {s.sing && <span className="pill sing">Lip-sync</span>}
            {!s.sing && s.feel && <span className="pill idle" style={{ maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.feel.split(",")[0]}</span>}
            {s.empty && <span className="pill gate">Needs prompts</span>}
            {dirty && !open && <span className="pill auto">Unsaved</span>}
          </span>
          <span className="small clamp-2" style={{ color: s.lyric ? "var(--text)" : "var(--muted)" }} lang={list.episode.lang}>{summary}</span>
        </span>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--faint)" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true" style={{ flex: "none", marginTop: 4 }}>
          <path d={open ? "M6 15l6-6 6 6" : "M6 9l6 6 6-6"} />
        </svg>
      </button>
      {open && <ShotEditor s={s} list={list} index={index} draft={draft ?? toDraft(s)} dirty={dirty} stale={stale} slug={slug}
        onDraft={onDraft} onSaved={onSaved} onRemade={onRemade} onOpen={onOpen} reload={reload} setErr={setErr} />}
    </div>
  );
}

function ShotEditor({ s, list, index, draft, dirty, stale, slug, onDraft, onSaved, onRemade, onOpen, reload, setErr }:
  Omit<CardProps, "open" | "onToggle" | "draft"> & { draft: Draft; dirty: boolean }) {
  const keyRef = useRef<HTMLTextAreaElement>(null);
  const motionRef = useRef<HTMLTextAreaElement>(null);
  const [focus, setFocus] = useState<"key" | "motion">("key");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [localErr, setLocalErr] = useState<string | null>(null);
  const scrolled = useRef(false);
  const set = (patch: Partial<Draft>) => onDraft({ ...draft, ...patch });
  const n = list.shots.length;

  const insert = (t: TokenInfo) => {
    const which = focus;
    const el = which === "key" ? keyRef.current : motionRef.current;
    const text = which === "motion" && t.kind === "prop" ? `{keep:${t.token.slice(1, -1)}}` : t.token;
    const cur = draft[which];
    const a = el?.selectionStart ?? cur.length, b = el?.selectionEnd ?? cur.length;
    const pad = a > 0 && !/\s$/.test(cur.slice(0, a)) ? " " : "";
    set({ [which]: cur.slice(0, a) + pad + text + " " + cur.slice(b) } as Partial<Draft>);
    requestAnimationFrame(() => { el?.focus(); const p = a + pad.length + text.length + 1; el?.setSelectionRange(p, p); });
  };

  const run = async (label: string, f: () => Promise<unknown>) => {
    setBusy(label); setLocalErr(null); setErr(null);
    try { await f(); reload(); } catch (e) { setLocalErr((e as Error).message.replace(/^\w+ \S+: /, "")); } finally { setBusy(null); }
  };
  const save = () => run("save", async () => {
    const before = toDraft(s);
    const fields: ShotFields = {};
    (Object.keys(draft) as (keyof Draft)[]).forEach((k) => { if (JSON.stringify(draft[k]) !== JSON.stringify(before[k])) (fields as Record<string, unknown>)[k] = draft[k]; });
    if ("lines" in fields && fields.lines === 1) fields.lines = null;   // 1 line is the default: don't write it
    await api.saveShot(slug, s.id, fields);
    onDraft(null);
    onSaved(["key", "feel", "scene", "sing", "end"].some((k) => k in fields));
  });
  const remake = () => run("remake", async () => { await api.run(slug, "keys", [s.id], s.image ? [s.id] : undefined); onRemade(); });
  const keyTokens = list.tokens;
  const motionTokens = list.tokens.filter((t) => t.kind === "prop");

  return (
    <div id={`edit-${s.id}`} className="col" style={{ gap: 14, padding: "4px 12px 14px", borderTop: "1px solid var(--line)" }}>
      {stale && !dirty && (
        <div className="notice" role="status">
          <span style={{ flex: 1 }}>The keyframe was made from the old prompt.</span>
          <button className="btn btn-gate" disabled={!!busy} onClick={remake}>{busy === "remake" ? "Queuing…" : "Remake keyframe"}</button>
        </div>
      )}
      <label className="col" style={{ gap: 6, marginTop: 10 }}>
        <span className="label">LYRIC LINE</span>
        <input className="input" value={draft.lyric} onChange={(e) => set({ lyric: e.target.value })} placeholder="(instrumental)" lang={list.episode.lang} />
      </label>

      <div className="col" style={{ gap: 6 }}>
        <span className="label" id={`scene-${s.id}`}>SCENE</span>
        <div className="scroller" role="radiogroup" aria-labelledby={`scene-${s.id}`} style={{ gap: 8, margin: "0 -12px", padding: "0 12px 2px" }}>
          {list.scenes.map((sc) => (
            <button key={sc.id} role="radio" aria-checked={draft.scene === sc.id} onClick={() => set({ scene: sc.id })}
              ref={draft.scene === sc.id ? (el) => { if (el && !scrolled.current) { scrolled.current = true; el.scrollIntoView({ block: "nearest", inline: "center" }); } } : undefined}
              style={{ flex: "none", width: 112, padding: 0, borderRadius: 10, overflow: "hidden", cursor: "pointer", background: "var(--panel-2)",
                border: draft.scene === sc.id ? "2px solid var(--go)" : "1px solid var(--line)", color: "var(--text-2)", textAlign: "left" }}>
              {sc.image && <img src={sc.image} alt="" style={{ display: "block", width: "100%", aspectRatio: "16/9", objectFit: "cover" }} />}
              <span style={{ display: "block", padding: "4px 8px", fontSize: 12 }}>{sc.id.replace(/_/g, " ")}</span>
            </button>
          ))}
        </div>
      </div>

      <label className="col" style={{ gap: 6 }}>
        <span className="label">KEYFRAME · WHO IS WHERE</span>
        <textarea ref={keyRef} className="textarea" rows={4} value={draft.key} onFocus={() => setFocus("key")} onChange={(e) => set({ key: e.target.value })}
          placeholder="{Tara} and {biscuit} run across the hilltop towards the big tree, laughing. Medium-wide shot." style={{ lineHeight: 1.45, resize: "vertical" }} />
      </label>
      <div className="col" style={{ gap: 6 }}>
        <span className="faint small">Tap to insert into the {focus === "key" ? "keyframe" : "motion"} prompt{focus === "motion" ? " (props keep their shape)" : ""}</span>
        <div className="scroller" role="group" aria-label="Insert a character or prop" style={{ gap: 6, margin: "0 -12px", padding: "0 12px 2px" }}>
          {(focus === "key" ? keyTokens : motionTokens).map((t) => (
            <button key={t.token} className="tab" onMouseDown={(e) => e.preventDefault()} onClick={() => insert(t)} style={{ paddingLeft: t.image ? 4 : 12 }}>
              {t.image && <img src={t.image} alt="" style={{ width: 30, height: 30, borderRadius: "50%", objectFit: "cover", background: "#fff" }} />}
              {t.label}
            </button>
          ))}
          {focus === "motion" && motionTokens.length === 0 && <span className="faint small">No props in the library.</span>}
        </div>
      </div>
      <label className="col" style={{ gap: 6 }}>
        <span className="label">MOTION · WHAT HAPPENS</span>
        <textarea ref={motionRef} className="textarea" rows={3} value={draft.motion} onFocus={() => setFocus("motion")}
          onChange={(e) => set({ motion: e.target.value })} placeholder="The children run towards the tree, each moving differently; the camera tracks alongside."
          style={{ lineHeight: 1.45, resize: "vertical" }} />
      </label>

      <div className="col" style={{ gap: 6 }}>
        <label className="col" style={{ gap: 6 }}>
          <span className="label">FEELING · WHAT THE FACES SHOW</span>
          <input className="input" value={draft.feel} onChange={(e) => set({ feel: e.target.value })} placeholder="quiet devotion, eyes shining with love" />
        </label>
        <div className="scroller" role="group" aria-label="Pick a feeling" style={{ gap: 6, margin: "0 -12px", padding: "0 12px 2px" }}>
          {FEELINGS.map((f) => (
            <button key={f} className={`tab ${draft.feel === f ? "active" : ""}`} aria-pressed={draft.feel === f} onClick={() => set({ feel: draft.feel === f ? "" : f })}>{f}</button>
          ))}
        </div>
        <span className="faint small">{draft.sing ? "This shot is lip-synced, so the character sings the line with this feeling." : "Nobody mouths the words in this shot: the feeling shows in eyes, faces and gestures."}</span>
      </div>

      <div className="col" style={{ gap: 2 }}>
        <Toggle on={draft.sing} onChange={(v) => set({ sing: v })} title="Lip-sync" detail="One character sings this line to camera (uses the song's vocal). Keep it for a few key lines." />
        {typeof draft.end === "object" && draft.end
          ? <div className="faint small" style={{ padding: "10px 0" }}>Has its own end keyframe (seed {draft.end.seed}); edit it in episode.toml.</div>
          : <Toggle on={draft.end === "same"} onChange={(v) => set({ end: v ? "same" : null })} title="Hold the pose" detail="Start and end on the same frame. Use it for seated characters." />}
        <label className="row between" style={{ minHeight: 48, flexWrap: "nowrap", gap: 12 }}>
          <span className="col" style={{ gap: 2, flex: 1, minWidth: 0 }}><span style={{ fontWeight: 500 }}>Length</span><span className="faint small">How many lyric lines this shot covers.</span></span>
          <select className="select" style={{ width: "auto" }} value={draft.lines} onChange={(e) => set({ lines: Number(e.target.value) })}>
            {[1, 2, 3, 4].map((x) => <option key={x} value={x}>{x} line{x > 1 ? "s" : ""}</option>)}
          </select>
        </label>
      </div>

      <ErrorNote msg={localErr} />
      <div className="row" style={{ gap: 8 }}>
        <button className="btn btn-go" style={{ flex: 2, justifyContent: "center" }} disabled={!dirty || !!busy} onClick={save}>{busy === "save" ? "Saving…" : dirty ? "Save changes" : "Saved"}</button>
        {dirty && <button className="btn" style={{ flex: 1, justifyContent: "center" }} onClick={() => { onDraft(null); setLocalErr(null); }}>Undo</button>}
      </div>
      <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
        <button className="btn" style={{ flex: 1, justifyContent: "center" }} disabled={!!busy || dirty || s.empty} onClick={remake} title={dirty ? "Save first" : undefined}>
          {busy === "remake" ? "Queuing…" : s.image ? "Remake keyframe" : "Make this keyframe"}
        </button>
        <button className="btn" style={{ flex: 1, justifyContent: "center" }} disabled={!!busy} onClick={() => run("dup", async () => { const x = await api.addShot(slug, { copy_of: s.id }); onOpen(x.id); })}>Duplicate</button>
      </div>
      <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
        <button className="btn" style={{ width: 52, justifyContent: "center" }} aria-label={`Move ${s.id} up`} disabled={!!busy || index === 0} onClick={() => run("up", () => api.moveShot(slug, s.id, list.shots[index - 1].id))}>↑</button>
        <button className="btn" style={{ width: 52, justifyContent: "center" }} aria-label={`Move ${s.id} down`} disabled={!!busy || index === n - 1}
          onClick={() => run("down", () => api.moveShot(slug, s.id, index + 2 < n ? list.shots[index + 2].id : null))}>↓</button>
        <button className="btn" style={{ marginLeft: "auto", color: confirmDelete ? "var(--danger)" : undefined, borderColor: confirmDelete ? "var(--danger)" : undefined }}
          disabled={!!busy || n === 1}
          onClick={() => confirmDelete ? run("del", () => api.deleteShot(slug, s.id)) : setConfirmDelete(true)} onBlur={() => setConfirmDelete(false)}>
          {confirmDelete ? "Tap again to delete" : "Delete shot"}
        </button>
      </div>
      <p className="faint small" style={{ margin: 0 }}>seed {s.seed}{s.frames ? ` · ${s.frames} frames` : ""} · files in keys/ and clips/ are kept when you edit</p>
    </div>
  );
}

function Toggle({ on, onChange, title, detail }: { on: boolean; onChange: (v: boolean) => void; title: string; detail: string }) {
  return (
    <button role="switch" aria-checked={on} onClick={() => onChange(!on)} className="row between"
      style={{ minHeight: 52, background: "none", border: 0, padding: "4px 0", textAlign: "left", cursor: "pointer", color: "var(--text)", gap: 12, flexWrap: "nowrap" }}>
      <span className="col" style={{ gap: 2, flex: 1, minWidth: 0 }}><span style={{ fontWeight: 500 }}>{title}</span><span className="faint small">{detail}</span></span>
      <span className={`switch ${on ? "on" : ""}`} aria-hidden="true" />
    </button>
  );
}
