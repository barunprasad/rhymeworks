import { useState } from "react";
import { api, useLoad, type EpisodeSummary } from "../api";
import { go, href } from "../router";
import { ErrorNote } from "../components/bits";
import { ChipRow, ResultLine, SearchBox, SortSelect, matches, useSaved } from "../components/Filters";

// 8 workflow steps: idea, lyrics, song, shot list, keyframes, clips, assemble, upload
export const stageStep: Record<string, number> = { song: 2, "shot list": 3, keys: 4, clips: 5, package: 6, published: 8 };
const stageLabel: Record<string, string> = { song: "Song", "shot list": "Shot list", keys: "Keyframes", clips: "Clips", package: "Upload pack", published: "Published" };
const LANG: Record<string, string> = { en: "English", hi: "हिंदी" };

const waitingFor = (e: EpisodeSummary) => [
  ...(e.keys_to_review ? [{ e, stage: "keys" as const, n: e.keys_to_review, what: "keyframes" }] : []),
  ...(e.clips_to_review ? [{ e, stage: "clips" as const, n: e.clips_to_review, what: "clips" }] : []),
];

export function Home() {
  const eps = useLoad(api.episodes, [], ["job", "output", "review", "spec"]);
  const drafts = useLoad(api.drafts, [], ["job", "library"]);
  const all = eps.data ?? [];
  const waiting = all.flatMap(waitingFor);
  const recent = [...all].sort((a, b) => (b.updated ?? 0) - (a.updated ?? 0));
  const cont = recent.find((e) => e.stage !== "published");
  const pickDrafts = (drafts.data ?? []).filter((d) => d.candidates.length && !d.jobs.length);

  return (
    <>
      <Ask episodes={recent} />
      <ErrorNote msg={eps.error} />

      {cont && (
        <section className="col" aria-labelledby="cont">
          <h2 id="cont" className="h2">Continue</h2>
          <a className="poster" href={href("episodes", cont.slug)}>
            {cont.poster ? <img src={cont.poster} alt="" /> : <span className="ph">No keyframes yet</span>}
            <span className="corner tag" style={{ height: 30, padding: "0 12px", fontSize: 12.5 }}>{stageLabel[cont.stage] ?? cont.stage}</span>
            <span className="cap">
              <span className="title" lang={cont.lang}>{cont.title}</span>
              <span className="row small" style={{ gap: 8, color: "var(--text-2)" }}>
                {waitingFor(cont).map((w) => <span key={w.stage} className="tag gate">Review {w.n} {w.what}</span>)}
                {cont.shots} shots · {cont.keys} keyframes · {cont.clips} clips
              </span>
            </span>
          </a>
          <div className="row" style={{ gap: 8 }}>
            <a className="btn" href={href("episodes", cont.slug, "watch")}>Watch the animatic</a>
            <a className="btn" href={href("episodes", cont.slug, "director")}>Ask the director</a>
          </div>
        </section>
      )}

      {(waiting.length > 0 || pickDrafts.length > 0) && (
        <section className="col" aria-labelledby="needs">
          <div className="row between"><h2 id="needs" className="h2">Needs you</h2><span className="muted small">{waiting.length + pickDrafts.length}</span></div>
          <div className="hscroll">
            {waiting.map(({ e, stage, n, what }) => (
              <a key={e.slug + stage} className="col" style={{ width: 176, gap: 6, color: "var(--text)" }} href={href("episodes", e.slug, "review", stage)}>
                {e.poster ? <img src={e.poster} alt="" style={{ width: 176, aspectRatio: "4/3", objectFit: "cover", borderRadius: 14, boxShadow: "0 0 0 2px var(--gate)" }} />
                  : <span className="thumb" style={{ aspectRatio: "4/3" }} />}
                <b style={{ fontSize: 14 }}>Review {n} {what}</b>
                <span className="muted small" style={{ marginTop: -4 }} lang={e.lang}>{e.title}</span>
              </a>
            ))}
            {pickDrafts.map((dr) => (
              <a key={dr.id} className="col" style={{ width: 176, gap: 6, color: "var(--text)" }} href={href("library", "draft", dr.id)}>
                <img src={dr.candidates[0].url} alt="" style={{ width: 176, aspectRatio: "4/3", objectFit: "cover", borderRadius: 14, background: "#f4ecdd", boxShadow: "0 0 0 2px var(--gate)" }} />
                <b style={{ fontSize: 14 }}>Pick a look: {dr.name}</b>
                <span className="muted small" style={{ marginTop: -4 }}>{dr.candidates.length} options</span>
              </a>
            ))}
          </div>
        </section>
      )}

      <section className="col" aria-labelledby="eps">
        <div className="row between"><h2 id="eps" className="h2">Episodes</h2><a className="see-all" href={href("episodes")}>See all {all.length}</a></div>
        <div className="grid-posters">{recent.slice(0, 4).map((e) => <EpisodeCard key={e.slug} e={e} />)}</div>
        {all.length === 0 && eps.data && <div className="empty">No episodes yet. Describe one above, or <a href={href("episodes", "new")}>start from lyrics</a>.</div>}
      </section>
    </>
  );
}

/** "What shall we make today?": a new song idea → New episode; a change to an episode → the Director. */
function Ask({ episodes }: { episodes: EpisodeSummary[] }) {
  const [text, setText] = useState("");
  const [target, setTarget] = useState("");   // "" = a new song, else an episode slug
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async () => {
    const t = text.trim();
    if (!t) return;
    if (!target) {
      try { sessionStorage.setItem("rw.idea", t); } catch { /* ignore */ }
      go("episodes", "new");
      return;
    }
    setBusy(true); setErr(null);
    try { await api.askDirector(target, t); go("episodes", target, "director"); } catch (e) { setErr((e as Error).message.replace(/^\w+ \S+: /, "")); setBusy(false); }
  };
  return (
    <section className="col" style={{ gap: 12 }} aria-labelledby="ask-h">
      <h1 id="ask-h">What shall we make today?</h1>
      <form className="ask" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <label htmlFor="ask" className="label">{target ? "WHAT SHOULD CHANGE IN THIS EPISODE" : "A NEW SONG IDEA"}</label>
        <textarea id="ask" rows={3} value={text} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(); }}
          placeholder={target ? "Less singing in the chorus, and bring the kite in earlier" : "A Hindi lullaby about the moon, sung to a sleepy little puppy"} />
        <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
          <div className="chips" role="group" aria-label="This is for" style={{ margin: 0, padding: 0, flex: 1 }}>
            <button type="button" className="chip-btn" aria-pressed={!target} onClick={() => setTarget("")}>New song</button>
            {episodes.filter((e) => e.stage !== "published").slice(0, 4).map((e) => (
              <button type="button" key={e.slug} className="chip-btn" aria-pressed={target === e.slug} onClick={() => setTarget(e.slug)} lang={e.lang}>{e.title}</button>
            ))}
          </div>
          <button className="round-go" aria-label={target ? "Ask the director" : "Start a new episode"} disabled={!text.trim() || busy}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
          </button>
        </div>
      </form>
      <ErrorNote msg={err} />
      <div className="chips" role="group" aria-label="Start from">
        <a className="chip-btn" href={href("episodes", "new")}>Song from lyrics</a>
        <a className="chip-btn" href={href("episodes", "new")}>Use a finished song</a>
        <a className="chip-btn" href={href("library", "new", "cast")}>New character</a>
        <a className="chip-btn" href={href("library", "new", "scenes")}>New world</a>
        <a className="chip-btn" href={href("library", "voices")}>Voice styles</a>
      </div>
    </section>
  );
}

type Sort = "recent" | "title" | "progress";

/** All episodes with search + filters (language, step, needs you) and sorting. */
export function EpisodesPage() {
  const eps = useLoad(api.episodes, [], ["job", "output", "review", "spec"]);
  const [q, setQ] = useSaved("eps.q", "");
  const [lang, setLang] = useSaved("eps.lang", "");
  const [stage, setStage] = useSaved("eps.stage", "");
  const [sort, setSort] = useSaved<Sort>("eps.sort", "recent");
  const all = eps.data ?? [];
  const langs = [...new Set(all.map((e) => e.lang ?? ""))].filter(Boolean);
  const stages = [...new Set(all.map((e) => e.stage))];
  const shown = all
    .filter((e) => matches(q, e.title, e.slug, ...e.cast, ...e.scenes) && (!lang || e.lang === lang)
      && (!stage || (stage === "needs" ? waitingFor(e).length > 0 : e.stage === stage)))
    .sort((a, b) => sort === "title" ? a.title.localeCompare(b.title) : sort === "progress" ? (stageStep[b.stage] ?? 0) - (stageStep[a.stage] ?? 0) : (b.updated ?? 0) - (a.updated ?? 0));
  const clear = () => { setQ(""); setLang(""); setStage(""); };

  return (
    <>
      <header className="row between"><h1>Episodes</h1><a className="btn btn-go" href={href("episodes", "new")}>+ New episode</a></header>
      <ErrorNote msg={eps.error} />
      <div className="filters">
        <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
          <div style={{ flex: 1 }}><SearchBox id="eps-q" value={q} onChange={setQ} placeholder="Search titles, characters, places" /></div>
          <SortSelect id="eps-sort" value={sort} onChange={setSort} options={[["recent", "Recent"], ["title", "A–Z"], ["progress", "Furthest along"]]} />
        </div>
        <ChipRow label="Step" value={stage} onChange={setStage} options={[
          { value: "needs", label: "Needs you", n: all.filter((e) => waitingFor(e).length).length },
          ...stages.map((s) => ({ value: s, label: stageLabel[s] ?? s, n: all.filter((e) => e.stage === s).length })),
        ].filter((o) => o.n)} />
        {langs.length > 1 && <ChipRow label="Language" all="All languages" value={lang} onChange={setLang} options={langs.map((l) => ({ value: l, label: LANG[l] ?? l, n: all.filter((e) => e.lang === l).length }))} />}
        <ResultLine shown={shown.length} total={all.length} what="episodes" onClear={clear} />
      </div>
      {eps.data && shown.length === 0 && <div className="empty">{all.length ? "No episodes match." : "No episodes yet."} {all.length ? <button className="btn-quiet" style={{ color: "var(--go-text)" }} onClick={clear}>Clear filters</button> : <a href={href("episodes", "new")}>Start one</a>}</div>}
      <div className="grid-posters">{shown.map((e) => <EpisodeCard key={e.slug} e={e} />)}</div>
    </>
  );
}

function EpisodeCard({ e }: { e: EpisodeSummary }) {
  const w = waitingFor(e);
  return (
    <a href={href("episodes", e.slug)} className="col" style={{ gap: 6, color: "var(--text)" }}>
      <span style={{ position: "relative", display: "block" }}>
        {e.poster ? <img src={e.poster} alt="" style={{ display: "block", width: "100%", aspectRatio: "16/10", objectFit: "cover", borderRadius: 14 }} />
          : <span className="thumb" style={{ aspectRatio: "16/10", borderRadius: 14, display: "grid", placeItems: "center", color: "var(--faint)", fontSize: 13 }}>No keyframes yet</span>}
        <span className="tags" style={{ position: "absolute", top: 8, left: 8, display: "flex", gap: 4 }}>
          <span className={`tag ${e.stage === "published" ? "go" : w.length ? "gate" : ""}`}>{w.length ? `Review ${w[0].what}` : stageLabel[e.stage] ?? e.stage}</span>
        </span>
      </span>
      <b style={{ fontSize: 14.5, lineHeight: 1.25 }} lang={e.lang}>{e.title}</b>
      <span className="muted small" style={{ marginTop: -3 }}>{LANG[e.lang ?? ""] ?? e.lang} · {e.shots} shots · {e.clips ? `${e.clips} clips` : `${e.keys} keyframes`}</span>
    </a>
  );
}
