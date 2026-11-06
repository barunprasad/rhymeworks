import { useEffect, useRef, useState } from "react";
import { api, useLoad } from "../api";
import { go, href } from "../router";
import { ErrorNote } from "../components/bits";
import { ALL, useProject } from "../components/Project";

const slugify = (t: string) => t.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 48);

/** New episode: title, language, lyrics (one line = one shot) and tempo → episodes/<slug>/episode.toml.
 *  "Start from" another episode carries over its look ([style], [vars]), singing voice, tempo and, if wanted, its shots + keyframes. */
export function NewEpisodePage({ from }: { from?: string }) {
  const { current, inProject } = useProject();
  const lib = useLoad(api.library, []);
  const eps = useLoad(api.episodes, []);
  const [source, setSource] = useState(from ?? "");
  const [copyShots, setCopyShots] = useState(true);
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

  const filled = useRef<string | null>(null);   // lyrics put in by the last source (replaced when you pick another)
  useEffect(() => {   // picking an episode to start from fills in its language, tempo, lyrics and first scene
    if (!source) {
      setLyrics((l) => (filled.current !== null && l === filled.current ? "" : l));
      filled.current = null;
      return;
    }
    let live = true;
    Promise.all([api.song(source), api.episode(source)]).then(([sg, ep]) => {
      if (!live) return;
      setLang(sg.lang === "en" ? "en" : "hi");
      setBpm(sg.bpm);
      setBarsPerLine([1, 2, 4].includes(sg.bars_per_line) ? sg.bars_per_line : 2);
      setLyrics((l) => (!l.trim() || l === filled.current ? sg.lyrics : l));   // never overwrite lyrics you typed
      filled.current = sg.lyrics;
      if (ep.shots[0]?.scene) setScene(ep.shots[0].scene);
    }).catch(() => {});
    return () => { live = false; };
  }, [source]);
  const sources = (eps.data ?? []).filter((e) => inProject(e) || e.slug === source);
  const src = sources.find((e) => e.slug === source);

  const autoSlug = slugify(title);
  const theSlug = slug || autoSlug;
  const lines = lyrics.split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("["));
  const lineSeconds = (barsPerLine * 4 * 60) / bpm;
  const ok = title.trim() && theSlug.length > 1;

  const create = async () => {
    setBusy(true); setErr(null);
    try {
      const e = await api.createEpisode({ title: title.trim(), lang, lyrics, line_seconds: Math.round(lineSeconds * 1e6) / 1e6, bpm, scene, slug: theSlug,
        project: current !== ALL ? current : src?.project, source: source || undefined, copy_shots: !!source && copyShots });
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

        {sources.length > 0 && (
          <div className="col" style={{ gap: 6 }}>
            <span className="label" id="start-from">START FROM</span>
            <div className="scroller" role="radiogroup" aria-labelledby="start-from" style={{ gap: 8 }}>
              {[{ slug: "", title: "Blank", poster: null as string | null, lang: undefined as string | undefined }, ...sources].map((e) => (
                <button key={e.slug || "blank"} role="radio" aria-checked={source === e.slug} onClick={() => setSource(e.slug)} className="from-card"
                  style={{ border: source === e.slug ? "2px solid var(--go)" : "1px solid var(--line)" }}>
                  {e.poster ? <img src={e.poster} alt="" /> : <span className="from-blank" aria-hidden="true">+</span>}
                  <span lang={e.lang}>{e.title}</span>
                </button>
              ))}
            </div>
            {src && (<>
              <span className="faint small">Takes its look (style and reusable prompt text), singing voice, tempo, lyrics and first scene. Change anything below.</span>
              <button role="switch" aria-checked={copyShots} onClick={() => setCopyShots(!copyShots)} className="row between card pad"
                style={{ textAlign: "left", cursor: "pointer", color: "var(--text)", gap: 12, flexWrap: "nowrap" }}>
                <span className="col" style={{ gap: 2 }}>
                  <span style={{ fontWeight: 700 }}>Reuse its shots and keyframes</span>
                  <span className="faint small">Every shot comes along with its timing and pictures; each of its lyric lines becomes your line in the same place (repeats too). Good for the same song in another language. Extra lines get new shots.</span>
                </span>
                <span className={`switch ${copyShots ? "on" : ""}`} aria-hidden="true" />
              </button>
            </>)}
          </div>
        )}

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
          style={{ textAlign: "left", cursor: "pointer", color: "var(--text)", gap: 12, flexWrap: "nowrap" }}>
          <span className="col" style={{ gap: 2 }}>
            <span style={{ fontWeight: 700 }}>Draft the shots with AI</span>
            <span className="faint small">The local writer model plans who is where and what happens for every {src && copyShots ? "new " : ""}line. You review before anything is rendered.</span>
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
