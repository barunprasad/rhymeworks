import { useState } from "react";
import { api, useLoad } from "../api";
import { go, href } from "../router";
import { ErrorNote } from "../components/bits";
import { ALL, useProject } from "../components/Project";

const slugify = (t: string) => t.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 48);

/** New episode: title, language, lyrics (one line = one shot) and tempo → episodes/<slug>/episode.toml. */
export function NewEpisodePage() {
  const { current } = useProject();
  const lib = useLoad(api.library, []);
  const [title, setTitle] = useState(() => {   // an idea typed on the home page arrives here once
    try { const i = sessionStorage.getItem("rw.idea") ?? ""; sessionStorage.removeItem("rw.idea"); return i.slice(0, 80); } catch { return ""; }
  });
  const [slug, setSlug] = useState("");
  const [lang, setLang] = useState<"en" | "hi">("hi");
  const [lyrics, setLyrics] = useState("");
  const [bpm, setBpm] = useState(100);
  const [barsPerLine, setBarsPerLine] = useState(2);
  const [scene, setScene] = useState("meadow");
  const [draft, setDraft] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const autoSlug = slugify(title);
  const theSlug = slug || autoSlug;
  const lines = lyrics.split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("["));
  const lineSeconds = (barsPerLine * 4 * 60) / bpm;
  const ok = title.trim() && theSlug.length > 1;

  const create = async () => {
    setBusy(true); setErr(null);
    try {
      const e = await api.createEpisode({ title: title.trim(), lang, lyrics, line_seconds: Math.round(lineSeconds * 1e6) / 1e6, bpm, scene, slug: theSlug, project: current !== ALL ? current : undefined });
      if (draft && lines.length) await api.run(e.slug, "draft");
      go("episodes", e.slug, "shots");
    } catch (x) { setErr((x as Error).message.replace(/^\w+ \S+: /, "")); setBusy(false); }
  };

  return (
    <>
      <div className="crumbs only-desktop"><a href={href("episodes")}>Episodes</a> / New episode</div>
      <h1 className="only-desktop">New episode</h1>
      <div className="col" style={{ gap: 18, maxWidth: 720 }}>
        <label className="col" style={{ gap: 6 }}>
          <span className="label">TITLE</span>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Jagannath, My Protector" autoFocus />
          {(autoSlug || slug) && (
            <span className="faint small">Folder: <span className="mono">episodes/</span>
              <input aria-label="Folder name" className="mono" value={theSlug} onChange={(e) => setSlug(slugify(e.target.value))}
                style={{ background: "none", border: 0, borderBottom: "1px dashed var(--line-2)", color: "var(--text-2)", font: "inherit", fontSize: 12.5, width: `${Math.max(8, theSlug.length + 1)}ch` }} />
            </span>
          )}
        </label>

        <div className="col" style={{ gap: 6 }}>
          <span className="label" id="lang">LANGUAGE</span>
          <div className="row" role="radiogroup" aria-labelledby="lang" style={{ gap: 8 }}>
            {([["hi", "हिंदी"], ["en", "English"]] as const).map(([k, l]) => (
              <button key={k} role="radio" aria-checked={lang === k} className={`tab ${lang === k ? "active" : ""}`} onClick={() => setLang(k)} style={{ minHeight: 44 }}>{l}</button>
            ))}
          </div>
        </div>

        <label className="col" style={{ gap: 6 }}>
          <span className="label">LYRICS · ONE LINE = ONE SHOT</span>
          <textarea className="textarea" rows={10} value={lyrics} onChange={(e) => setLyrics(e.target.value)} lang={lang} style={{ lineHeight: 1.6, resize: "vertical" }}
            placeholder={lang === "hi" ? "[Verse]\nजगन्नाथ, जगन्नाथ, चका नैन, चका नैन\nनीलाचल वारे, तू ना संभाले तो हमें कौन संभाले" : "[Verse]\nThe wheels on the bus go round and round\nRound and round, round and round"} />
          <span className="faint small">{lines.length} shot{lines.length === 1 ? "" : "s"} · lines in [brackets] are section tags and are skipped · original or traditional lyrics only</span>
        </label>

        <div className="row" style={{ gap: 12, alignItems: "flex-end" }}>
          <label className="col" style={{ gap: 6, flex: "1 1 120px" }}>
            <span className="label">TEMPO (BPM)</span>
            <input className="input" type="number" inputMode="numeric" min={60} max={180} value={bpm} onChange={(e) => setBpm(Math.max(40, Number(e.target.value) || 100))} />
          </label>
          <label className="col" style={{ gap: 6, flex: "1 1 120px" }}>
            <span className="label">BARS PER LINE</span>
            <select className="select" value={barsPerLine} onChange={(e) => setBarsPerLine(Number(e.target.value))}>
              {[1, 2, 4].map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </label>
          <div className="muted small" style={{ flex: "1 1 160px", paddingBottom: 12 }}>
            = {lineSeconds.toFixed(2)} s per shot · ≈ {Math.round((lines.length * lineSeconds) / 6) / 10} min
          </div>
        </div>

        <div className="col" style={{ gap: 6 }}>
          <span className="label" id="start-scene">STARTING SCENE</span>
          <div className="scroller" role="radiogroup" aria-labelledby="start-scene" style={{ gap: 8 }}>
            {(lib.data?.scenes ?? []).map((sc) => (
              <button key={sc.id} role="radio" aria-checked={scene === sc.id} onClick={() => setScene(sc.id)}
                style={{ flex: "none", width: 120, padding: 0, borderRadius: 10, overflow: "hidden", cursor: "pointer", background: "var(--panel-2)", textAlign: "left",
                  border: scene === sc.id ? "2px solid var(--go)" : "1px solid var(--line)", color: "var(--text-2)" }}>
                {sc.image && <img src={sc.image} alt="" style={{ display: "block", width: "100%", aspectRatio: "16/9", objectFit: "cover" }} />}
                <span style={{ display: "block", padding: "4px 8px", fontSize: 12 }}>{sc.id.replace(/_/g, " ")}</span>
              </button>
            ))}
          </div>
        </div>

        <button role="switch" aria-checked={draft} onClick={() => setDraft(!draft)} className="row between card pad"
          style={{ textAlign: "left", cursor: "pointer", color: "var(--text)", gap: 12 }}>
          <span className="col" style={{ gap: 2 }}>
            <span style={{ fontWeight: 700 }}>Draft the shots with AI</span>
            <span className="faint small">The local writer model plans who is where and what happens for every line. You review before anything is rendered.</span>
          </span>
          <span className={`switch ${draft ? "on" : ""}`} aria-hidden="true" />
        </button>

        <ErrorNote msg={err} />
        <button className="btn btn-go" style={{ justifyContent: "center", minHeight: 52, fontSize: 16 }} disabled={!ok || busy} onClick={create}>
          {busy ? "Creating…" : `Create episode${lines.length ? ` with ${lines.length} shots` : ""}`}
        </button>
        <p className="faint small" style={{ margin: 0 }}>The song comes next: the Song step makes takes for these lyrics, or you can drop a mastered file at <span className="mono">song/master_{lang}.wav</span>.</p>
      </div>
    </>
  );
}
