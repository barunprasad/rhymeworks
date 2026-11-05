import { useEffect, useState } from "react";
import { api, ago, useLoad, type LibraryItem } from "../api";
import { href } from "../router";
import { ErrorNote } from "../components/bits";
import { KIND_WORD } from "./NewAsset";
import { useIsDesktop } from "../components/MobileBars";
import { ChipRow, ResultLine, SearchBox, SortSelect, matches, useSaved } from "../components/Filters";

const KINDS = [["cast", "Characters"], ["scenes", "Worlds"], ["props", "Props"]] as const;
type Kind = (typeof KINDS)[number][0];
type Sort = "used" | "new" | "az";
const nice = (id: string) => id.split("_")[0].replace(/^./, (c) => c.toUpperCase());
const full = (id: string) => id.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
const kindOf = (it: LibraryItem): Kind => (it.kind === "cast" ? "cast" : it.kind === "scene" ? "scenes" : "props");

/** Characters, worlds and props in one searchable gallery: filter by kind, person/animal, usage and episode; sort by use or age. */
export function LibraryPage({ tab }: { tab: string }) {
  const lib = useLoad(api.library, [], ["library", "spec"]);
  const drafts = useLoad(api.drafts, [], ["job", "library"]);
  const desktop = useIsDesktop();
  const [sel, setSel] = useState<string | null>(null);
  const kind = (["all", ...KINDS.map(([k]) => k)].includes(tab) ? tab : "all") as Kind | "all";
  const [q, setQ] = useSaved("lib.q", "");
  const [sort, setSort] = useSaved<Sort>("lib.sort", "used");
  const [use, setUse] = useSaved("lib.use", "");
  const [ep, setEp] = useSaved("lib.ep", "");
  const [type, setType] = useSaved("lib.type", "");

  const all: LibraryItem[] = lib.data ? [...lib.data.cast, ...lib.data.scenes, ...lib.data.props] : [];
  const episodes = [...new Map(all.flatMap((i) => i.used.episodes.map((e) => [e.slug, e.title] as const))).entries()];
  const pass = (it: LibraryItem, skip?: string) =>
    (skip === "kind" || kind === "all" || kindOf(it) === kind)
    && matches(q, it.id, it.ref, it.style, ...it.used.episodes.map((e) => e.title))
    && (skip === "use" || !use || (use === "unused" ? it.used.shots === 0 : it.used.shots > 0))
    && (skip === "ep" || !ep || it.used.episodes.some((e) => e.slug === ep))
    && (skip === "type" || !type || (type === "person" ? !!it.person : it.kind === "cast" && !it.person));
  const shown = all.filter((it) => pass(it)).sort((a, b) =>
    sort === "az" ? a.id.localeCompare(b.id) : sort === "new" ? (b.added ?? 0) - (a.added ?? 0) : b.used.shots - a.used.shots || a.id.localeCompare(b.id));
  const cur = shown.find((i) => i.id === sel) ?? (desktop ? shown[0] : undefined);
  const clear = () => { setQ(""); setUse(""); setEp(""); setType(""); };
  const groups: [Kind, LibraryItem[]][] = (kind === "all" ? KINDS.map(([k]) => k) : [kind]).map((k) => [k, shown.filter((i) => kindOf(i) === k)] as [Kind, LibraryItem[]]).filter(([, l]) => l.length);
  const newKind = kind === "all" ? "cast" : kind;

  useEffect(() => {   // Escape closes the phone sheet
    if (desktop || !sel) return;
    const f = (e: KeyboardEvent) => { if (e.key === "Escape") setSel(null); };
    window.addEventListener("keydown", f);
    return () => window.removeEventListener("keydown", f);
  }, [desktop, sel]);

  const details = cur && (
    <>
      {cur.image && <img src={cur.image} alt={full(cur.id)} className={`thumb ${cur.kind === "cast" ? "square" : ""}`}
        style={{ borderRadius: 16, ...(desktop ? {} : { maxHeight: "34vh", objectFit: "contain" }), ...(cur.kind === "cast" ? { background: "#f4ecdd" } : {}) }} />}
      <h2 className="brand" style={{ fontSize: 24, margin: 0 }}>{full(cur.id)}</h2>
      <div className="muted small">{cur.used.shots ? `In ${cur.used.shots} shot${cur.used.shots > 1 ? "s" : ""} across ${cur.used.episodes.length} episode${cur.used.episodes.length > 1 ? "s" : ""}` : "Not used in any episode yet"}{cur.added ? ` · added ${ago(cur.added)}` : ""}</div>
      {cur.used.episodes.map((e) => (
        <div key={e.slug} className="col" style={{ gap: 6 }}>
          <a href={href("episodes", e.slug)} style={{ fontWeight: 700 }}>{e.title}</a>
          <div className="row" style={{ gap: 4 }}>{e.shots.map((s) => <a key={s} className="chip" href={href("episodes", e.slug, "watch", s)}>{s}</a>)}</div>
        </div>
      ))}
      <div className="col" style={{ gap: 6 }}>
        <div className="label">{cur.kind === "scene" ? "USE IN A SHOT" : "PROMPT TOKEN"}</div>
        <code className="token" style={{ alignSelf: "flex-start" }}>{cur.token ?? `scene = "${cur.id}"`}</code>
        {cur.ref && <><div className="label" style={{ marginTop: 6 }}>HOW PROMPTS DESCRIBE IT</div><div style={{ color: "var(--text-2)", lineHeight: 1.45 }}>{cur.ref}</div></>}
        {cur.style && <><div className="label" style={{ marginTop: 6 }}>CONSISTENCY RULE</div><div style={{ color: "var(--text-2)", lineHeight: 1.45 }}>{cur.style}</div></>}
      </div>
      <p className="faint small" style={{ margin: 0 }}>Defined in <span className="mono">assets/registry.toml</span>.</p>
    </>
  );

  return (
    <>
      <header className="row between">
        <h1>Library</h1>
        <a className="btn btn-go" href={href("library", "new", newKind)}>+ New {KIND_WORD[newKind]}</a>
      </header>
      <ErrorNote msg={lib.error} />
      {(drafts.data ?? []).length > 0 && (
        <section className="col" aria-labelledby="drafts" style={{ gap: 8 }}>
          <h2 id="drafts" className="h2">In progress</h2>
          <div className="hscroll">
            {drafts.data!.map((dr) => (
              <a key={dr.id} className="col" style={{ width: 150, gap: 6, color: "var(--text)" }} href={href("library", "draft", dr.id)}>
                {dr.candidates[0] ? <img src={dr.candidates[0].url} alt="" style={{ width: 150, aspectRatio: "1", objectFit: "cover", borderRadius: 14, background: "#f4ecdd", boxShadow: "0 0 0 2px var(--gate)" }} />
                  : <span className="thumb" style={{ aspectRatio: "1" }} />}
                <b style={{ fontSize: 13.5 }}>{dr.name}</b>
                <span className="muted small" style={{ marginTop: -4 }}>{dr.jobs.length ? "drawing…" : dr.candidates.length ? `${dr.candidates.length} options · pick one` : "queued"}</span>
              </a>
            ))}
          </div>
        </section>
      )}

      <div className="filters">
        <div className="chips" role="tablist" aria-label="Library sections">
          {[["all", "All"] as const, ...KINDS].map(([k, label]) => (
            <a key={k} role="tab" aria-selected={k === kind} className="chip-btn" aria-pressed={k === kind} href={href("library", k)} onClick={() => setSel(null)}>
              {label} <span className="n">{k === "all" ? all.filter((i) => pass(i, "kind")).length : all.filter((i) => kindOf(i) === k && pass(i, "kind")).length}</span>
            </a>
          ))}
          <a role="tab" aria-selected={false} className="chip-btn" href={href("library", "voices")}>Voices</a>
        </div>
        <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
          <div style={{ flex: 1 }}><SearchBox id="lib-q" value={q} onChange={setQ} placeholder="Search names, looks, episodes" /></div>
          <SortSelect id="lib-sort" value={sort} onChange={setSort} options={[["used", "Most used"], ["new", "Newest"], ["az", "A–Z"]]} />
        </div>
        <ChipRow label="Usage" all="Any" value={use} onChange={setUse} options={[
          { value: "used", label: "In episodes", n: all.filter((i) => i.used.shots > 0 && pass(i, "use")).length },
          { value: "unused", label: "Not used yet", n: all.filter((i) => i.used.shots === 0 && pass(i, "use")).length },
        ]} />
        {(kind === "all" || kind === "cast") && <ChipRow label="Type" all="People and animals" value={type} onChange={setType} options={[
          { value: "person", label: "People", n: all.filter((i) => i.person && pass(i, "type")).length },
          { value: "animal", label: "Animals", n: all.filter((i) => i.kind === "cast" && !i.person && pass(i, "type")).length },
        ]} />}
        {episodes.length > 0 && <ChipRow label="Episode" all="All episodes" value={ep} onChange={setEp}
          options={episodes.map(([slug, title]) => ({ value: slug, label: title, n: all.filter((i) => i.used.episodes.some((e) => e.slug === slug) && pass(i, "ep")).length }))} />}
        <ResultLine shown={shown.length} total={kind === "all" ? all.length : all.filter((i) => kindOf(i) === kind).length} what="items" onClear={clear} />
      </div>

      <div className="split">
        <div className="grow" style={{ gap: 22 }}>
          {lib.data && shown.length === 0 && <div className="empty">Nothing matches. <button className="btn-quiet" style={{ color: "var(--go-text)" }} onClick={clear}>Clear filters</button></div>}
          {groups.map(([k, items]) => (
            <section key={k} className="col" aria-label={KINDS.find(([x]) => x === k)![1]}>
              {kind === "all" && <div className="row between"><h2 className="h2">{KINDS.find(([x]) => x === k)![1]}</h2>
                {items.length > 6 && <a className="see-all" href={href("library", k)}>See all {items.length}</a>}</div>}
              <div className={k === "cast" ? "grid-portraits" : "grid-tiles"}>
                {(kind === "all" ? items.slice(0, k === "cast" ? 8 : 6) : items).map((it) => (
                  <button key={it.id} onClick={() => setSel(it.id)} className={`tile ${k === "cast" ? "portrait" : ""} ${desktop && cur?.id === it.id ? "on" : ""}`}>
                    {it.image ? <img src={it.image} alt="" loading="lazy" /> : <span className="ph">No image</span>}
                    {it.used.shots === 0 && <span className="tags"><span className="tag">new</span></span>}
                    <span className="meta">
                      <span className="line1" style={{ fontWeight: 700 }}>{k === "cast" ? nice(it.id) : full(it.id)}</span>
                      <span className="line2">{it.used.shots ? `${it.used.shots} shot${it.used.shots > 1 ? "s" : ""} · ${it.used.episodes.length} ep.` : "not used yet"}</span>
                    </span>
                  </button>
                ))}
              </div>
            </section>
          ))}
        </div>
        {desktop && cur && <aside className="side panel" aria-label="Details">{details}</aside>}
      </div>

      {!desktop && cur && (
        <div className="sheet-wrap">
          <button className="sheet-backdrop" aria-label="Close details" onClick={() => setSel(null)} />
          <section className="sheet" role="dialog" aria-modal="true" aria-label={`${full(cur.id)} details`}>
            <span className="sheet-handle" aria-hidden="true" />
            {details}
            <button className="btn btn-go" style={{ justifyContent: "center" }} onClick={() => setSel(null)} autoFocus>Done</button>
          </section>
        </div>
      )}
    </>
  );
}
