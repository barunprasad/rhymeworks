import { useEffect, useState } from "react";
import { api, useLoad, type AssetDraft, type AssetKind } from "../api";
import { go, href } from "../router";
import { ErrorNote } from "../components/bits";
import { useIsDesktop } from "../components/MobileBars";
import { JobBar } from "./Episode";

export const KIND_WORD: Record<AssetKind, string> = { cast: "character", props: "prop", scenes: "scene" };
const PLACEHOLDER: Record<AssetKind, [string, string]> = {
  cast: ["Kela the banana", "A cheerful little banana for toddlers: bright yellow peel, a green stem like a tuft of hair, big round eyes, rosy cheeks, tiny arms and legs, a small orange scarf."],
  props: ["Paper boat", "A small folded paper boat made of bright red paper with a tiny marigold flower inside."],
  scenes: ["Lotus pond at night", "A calm lotus pond at night under a full moon, small oil lamps floating on the water, stone steps, a temple silhouette and palm trees reflected in the water."],
};

function StepDots({ step }: { step: 1 | 2 | 3 }) {
  const names = ["Describe", "Pick a look", "Name and save"];
  return (
    <div className="row" style={{ gap: 6, flexWrap: "nowrap" }} aria-label={`Step ${step} of 3: ${names[step - 1]}`}>
      {names.map((n, i) => (
        <span key={n} style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ height: 4, borderRadius: 2, background: i + 1 < step ? "var(--go)" : i + 1 === step ? "var(--gate)" : "var(--line-2)" }} />
          <span className="small" style={{ color: i + 1 === step ? "var(--text)" : "var(--faint)", fontWeight: i + 1 === step ? 700 : 400 }}>{n}</span>
        </span>
      ))}
    </div>
  );
}

/** Step 1 (mock-up P8): describe the new character / prop / scene. Making the options is a GPU job (FLUX, ~3 min for 4). */
export function NewAssetPage({ kind }: { kind: AssetKind }) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [person, setPerson] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const word = KIND_WORD[kind];
  const create = async () => {
    setBusy(true); setErr(null);
    try { const d = await api.newDraft({ kind, name, description: desc, person }); go("library", "draft", d.id); }
    catch (e) { setErr((e as Error).message.replace(/^\w+ \S+: /, "")); setBusy(false); }
  };
  return (
    <>
      <div className="crumbs only-desktop"><a href={href("library", kind)}>Library</a> / New {word}</div>
      <h1 className="only-desktop">New {word}</h1>
      <div className="col" style={{ gap: 18, maxWidth: 680 }}>
        <StepDots step={1} />
        <label className="col" style={{ gap: 6 }}>
          <span className="label">NAME</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder={PLACEHOLDER[kind][0]} autoFocus />
        </label>
        <label className="col" style={{ gap: 6 }}>
          <span className="label">WHAT IT LOOKS LIKE</span>
          <textarea className="textarea" rows={6} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder={PLACEHOLDER[kind][1]} style={{ lineHeight: 1.5, resize: "vertical" }} />
          <span className="faint small">
            {kind === "scenes" ? "Describe an empty place: no characters (they are added per shot). Wide, with open space in front."
              : "Colours, shape, clothes and one or two details that make it recognisable. The studio adds the Pixar style that matches Gopu and Minu."}
          </span>
        </label>
        {kind === "cast" && (
          <button role="switch" aria-checked={person} onClick={() => setPerson(!person)} className="row between card pad" style={{ textAlign: "left", cursor: "pointer", color: "var(--text)", flexWrap: "nowrap", gap: 12 }}>
            <span className="col" style={{ gap: 2 }}>
              <span style={{ fontWeight: 700 }}>This is a person (child or adult)</span>
              <span className="faint small">People get the "no extra people" rule in every shot they are in. Animals and fruit friends are not people.</span>
            </span>
            <span className={`switch ${person ? "on" : ""}`} aria-hidden="true" />
          </button>
        )}
        <ErrorNote msg={err} />
        <button className="btn btn-go" style={{ justifyContent: "center", minHeight: 52, fontSize: 16 }} disabled={busy || !name.trim() || desc.trim().length < 10} onClick={create}>
          {busy ? "Starting…" : "Make 4 options · about 3 min"}
        </button>
        <p className="faint small" style={{ margin: 0 }}>Nothing is added to the library until you pick one. No photos of real people, and only original characters.</p>
      </div>
    </>
  );
}

/** Steps 2 + 3: pick one of the options, then name it and save it into assets/ + registry.toml. */
export function DraftPage({ id }: { id: string }) {
  const dr = useLoad(() => api.draft(id), [id], ["job", "library"], id);
  const desktop = useIsDesktop();
  const [pick, setPick] = useState<string | null>(null);
  const [naming, setNaming] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const d = dr.data;
  if (!d) return <ErrorNote msg={dr.error} />;

  const word = KIND_WORD[d.kind];
  const working = d.jobs.length > 0;
  const pickedIdx = d.candidates.findIndex((c) => c.name === pick);
  const act = async (f: () => Promise<unknown>) => {
    setBusy(true); setErr(null);
    try { await f(); dr.reload(); } catch (e) { setErr((e as Error).message.replace(/^\w+ \S+: /, "")); } finally { setBusy(false); }
  };
  if (d.saved) {
    return (
      <div className="col" style={{ gap: 14, maxWidth: 680 }}>
        <h1>{d.name} is in the library</h1>
        <p className="muted">Use <code className="token">{`{${d.saved.id}}`}</code> in keyframe prompts.</p>
        <a className="btn btn-go" style={{ alignSelf: "flex-start" }} href={href("library", d.kind)}>Open the library</a>
      </div>
    );
  }
  if (naming && pick) return <NameStep d={d} candidate={pick} onBack={() => setNaming(false)} />;

  const portrait = d.kind === "cast";
  const cta = <button className="btn btn-go" style={{ flex: 1, justifyContent: "center" }} disabled={!pick} onClick={() => setNaming(true)}>
    {pick ? `Use option ${pickedIdx + 1} · name it` : d.candidates.length ? "Choose an option first" : "Making options…"}</button>;

  return (
    <>
      <div className="crumbs only-desktop"><a href={href("library", d.kind)}>Library</a> / New {word}</div>
      <header className="row between">
        <h1>{d.candidates.length ? "Pick the look that feels right" : `Making ${d.name}…`}</h1>
        {desktop && <div className="row">{cta}</div>}
      </header>
      <div className="col" style={{ gap: 16 }}>
        <StepDots step={2} />
        <details className="card pad">
          <summary style={{ cursor: "pointer", fontWeight: 500 }}>Your description</summary>
          <p className="muted" style={{ margin: "8px 0 0", lineHeight: 1.5 }}>{d.description}</p>
        </details>
        <ErrorNote msg={err ?? dr.error} />
        {d.jobs.map((j) => <JobBar key={j.id} j={j} />)}
        <div className={`grid ${portrait ? "grid-cards" : "grid-keys"}`} role="radiogroup" aria-label="Options">
          {d.candidates.map((c, i) => (
            <button key={c.name} role="radio" aria-checked={pick === c.name} aria-label={`Option ${i + 1}`} onClick={() => setPick(c.name)}
              style={{ padding: 0, borderRadius: 14, overflow: "hidden", background: "var(--panel)", cursor: "pointer", textAlign: "left", color: "var(--text)",
                border: pick === c.name ? "2px solid var(--go)" : "1px solid var(--line)" }}>
              <img src={c.url} alt="" style={{ display: "block", width: "100%", aspectRatio: portrait ? "3/4" : "16/9", objectFit: "cover", background: "#fff" }} />
              <span className="row between" style={{ padding: "8px 10px" }}><b>Option {i + 1}</b>{pick === c.name && <span style={{ color: "var(--go-text)", fontSize: 13, fontWeight: 700 }}>Picked</span>}</span>
            </button>
          ))}
          {working && Array.from({ length: Math.max(1, 4 - Math.floor((d.jobs[0]?.progress ?? 0) * 4)) }, (_, i) => (
            <div key={`ph${i}`} className="card" style={{ aspectRatio: portrait ? "3/4" : "16/9", display: "grid", placeItems: "center", color: "var(--faint)", fontSize: 13 }}>drawing…</div>
          ))}
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn" style={{ flex: 1, justifyContent: "center", borderStyle: "dashed" }} disabled={busy || working} onClick={() => act(() => api.moreOptions(id))}>
            {working ? "Drawing options…" : "Make 4 more · about 3 min"}
          </button>
          <button className="btn btn-quiet" disabled={busy} onClick={() => act(async () => { await api.discardDraft(id); go("library", d.kind); })}>Discard</button>
        </div>
        <p className="faint small" style={{ margin: 0 }}>Nothing happens until you choose. Not quite right? Change the description and make more:</p>
        <EditDescription d={d} onSaved={dr.reload} disabled={working} />
      </div>
      {!desktop && <div className="actionbar">{cta}</div>}
    </>
  );
}

function EditDescription({ d, onSaved, disabled }: { d: AssetDraft; onSaved: () => void; disabled: boolean }) {
  const [text, setText] = useState(d.description);
  const [busy, setBusy] = useState(false);
  useEffect(() => setText(d.description), [d.description]);
  const changed = text.trim() !== d.description;
  return (
    <div className="col" style={{ gap: 8 }}>
      <textarea className="textarea" rows={3} value={text} onChange={(e) => setText(e.target.value)} aria-label="Description" style={{ lineHeight: 1.5 }} />
      {changed && (
        <button className="btn" style={{ alignSelf: "flex-start" }} disabled={busy || disabled}
          onClick={async () => { setBusy(true); try { await api.patchDraft(d.id, { description: text.trim() }); await api.moreOptions(d.id); onSaved(); } finally { setBusy(false); } }}>
          Save and make 4 more
        </button>
      )}
    </div>
  );
}

function NameStep({ d, candidate, onBack }: { d: AssetDraft; candidate: string; onBack: () => void }) {
  const desktop = useIsDesktop();
  const [token, setToken] = useState(d.suggested_id);
  const [ref, setRef] = useState(d.ref ?? `the ${d.name.toLowerCase()}`);
  const [style, setStyle] = useState(d.style ?? "");
  const [keep, setKeep] = useState(d.kind === "props" ? `The ${d.name.toLowerCase()} keeps its exact shape and colours` : "");
  const [person, setPerson] = useState(d.person);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const url = d.candidates.find((c) => c.name === candidate)?.url;
  const save = async () => {
    setBusy(true); setErr(null);
    try {
      const out = await api.saveAsset(d.id, { candidate, id: token, ref: d.kind === "scenes" ? undefined : ref, style: style || undefined, person, keep: keep || undefined });
      go("library", out.kind);
    } catch (e) { setErr((e as Error).message.replace(/^\w+ \S+: /, "")); setBusy(false); }
  };
  const cta = <button className="btn btn-go" style={{ flex: 1, justifyContent: "center" }} disabled={busy || !/^[a-z][a-z0-9_]{1,39}$/.test(token)} onClick={save}>
    {busy ? "Saving…" : `Add ${d.name} to the library`}</button>;
  return (
    <>
      <header className="row between"><h1>Name and save</h1>{desktop && <div className="row">{cta}</div>}</header>
      <div className="col" style={{ gap: 16, maxWidth: 680 }}>
        <StepDots step={3} />
        <div className="row" style={{ gap: 12, flexWrap: "nowrap", alignItems: "flex-start" }}>
          {url && <img src={url} alt="" style={{ width: d.kind === "cast" ? 96 : 160, borderRadius: 10, background: "#fff", flex: "none" }} />}
          <div className="col" style={{ gap: 6 }}>
            <b style={{ fontSize: 18 }}>{d.name}</b>
            <button className="btn btn-quiet" style={{ alignSelf: "flex-start", color: "var(--go)", padding: 0, minHeight: 32 }} onClick={onBack}>Pick a different option</button>
          </div>
        </div>
        <label className="col" style={{ gap: 6 }}>
          <span className="label">TOKEN FOR PROMPTS</span>
          <div className="row" style={{ gap: 0, flexWrap: "nowrap" }}>
            <span className="mono" style={{ color: "var(--go-text)", fontSize: 18 }}>{"{"}</span>
            <input className="input mono" value={token} onChange={(e) => setToken(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"))} style={{ margin: "0 4px" }} />
            <span className="mono" style={{ color: "var(--go-text)", fontSize: 18 }}>{"}"}</span>
          </div>
          <span className="faint small">Name plus what it is works best, like <span className="mono">nandu_calf</span> or <span className="mono">kela_banana</span>.</span>
        </label>
        {d.kind !== "scenes" && (
          <label className="col" style={{ gap: 6 }}>
            <span className="label">HOW PROMPTS DESCRIBE IT</span>
            <input className="input" value={ref} onChange={(e) => setRef(e.target.value)} />
            <span className="faint small">Shown to the image model instead of the name, so it can tell who is who. Suggested by the writer model.</span>
          </label>
        )}
        {d.kind !== "scenes" && (
          <label className="col" style={{ gap: 6 }}>
            <span className="label">CONSISTENCY RULE (OPTIONAL)</span>
            <textarea className="textarea" rows={2} value={style} onChange={(e) => setStyle(e.target.value)} placeholder="The banana keeps its small orange scarf." style={{ lineHeight: 1.5 }} />
            <span className="faint small">Added to every keyframe this {KIND_WORD[d.kind]} is in.</span>
          </label>
        )}
        {d.kind === "props" && (
          <label className="col" style={{ gap: 6 }}>
            <span className="label">KEEP RULE FOR MOTION (OPTIONAL)</span>
            <input className="input" value={keep} onChange={(e) => setKeep(e.target.value)} />
            <span className="faint small">Used as <span className="mono">{`{keep:${token}}`}</span> in motion prompts so it doesn't melt or change shape.</span>
          </label>
        )}
        {d.kind === "cast" && (
          <button role="switch" aria-checked={person} onClick={() => setPerson(!person)} className="row between" style={{ background: "none", border: 0, padding: 0, textAlign: "left", cursor: "pointer", color: "var(--text)", flexWrap: "nowrap", minHeight: 48 }}>
            <span style={{ fontWeight: 500 }}>This is a person</span><span className={`switch ${person ? "on" : ""}`} aria-hidden="true" />
          </button>
        )}
        <ErrorNote msg={err} />
      </div>
      {!desktop && <div className="actionbar">{cta}</div>}
    </>
  );
}
