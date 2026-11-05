import { useState } from "react";
import { api, fmtTime, jobLabel, useLoad, type EpisodeDetail, type Job, type JobKind, type Phase, type Shot } from "../api";
import { go, href } from "../router";
import { ErrorNote } from "../components/bits";
import { useIsDesktop } from "../components/MobileBars";
import { ChipRow, ResultLine, SearchBox, matches, useSaved } from "../components/Filters";
import { AnimaticPlayer, FilmPlayer, type Mode } from "./Animatic";
import { DirectorPanel } from "./Director";

type NodeKind = "done" | "you" | "running" | "wait";
interface FlowNode { n: string; title: string; kind: NodeKind; state: string; detail: string; gate?: boolean; action?: { label: string; phase?: Phase; to?: string } }

export function EpisodePage({ slug }: { slug: string }) {
  const ep = useLoad(() => api.episode(slug), [slug], ["job", "output", "review", "spec"], slug);
  const desktop = useIsDesktop();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);        // the shot the player shows
  const [pinned, setPinned] = useState<string | null>(null);  // a storyboard click restarts the player there
  const [view, setView] = useState<"film" | Mode | null>(null);   // desktop: finished film / moving clips / keyframes
  const [q, setQ] = useSaved(`sb.q.${slug}`, "");
  const [status, setStatus] = useSaved(`sb.status.${slug}`, "");
  const [who, setWho] = useSaved(`sb.who.${slug}`, "");
  const [where, setWhere] = useSaved(`sb.where.${slug}`, "");
  const lib = useLoad(api.library, [], ["library"]);
  const d = ep.data;

  const run = async (phase: Phase) => {
    setBusy(phase); setErr(null);
    try { await api.run(slug, phase); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };
  if (!d) return <ErrorNote msg={ep.error} />;

  const nodes = buildNodes(d);
  const hasClips = d.shots.some((s) => s.clip.url);
  const watching = view ?? (d.film ? "film" : hasClips ? "clips" : "keys");   // what the desktop player shows
  const next = nodes.find((n) => n.kind === "running") ?? nodes.find((n) => n.kind === "you") ?? nodes.find((n) => n.kind === "wait" && n.action);
  const portraits = Object.fromEntries((lib.data?.cast ?? []).concat(lib.data?.props ?? []).map((c) => [c.id, c.image]));
  const count = (f: (s: Shot) => boolean) => d.shots.filter(f).length;
  const STATUS: [string, string, (s: Shot) => boolean][] = [
    ["to_review", "To review", (s) => s.key.status === "to_review" || s.clip.status === "to_review"],
    ["approved", "Approved", (s) => s.key.status === "approved"],
    ["redo", "Redo queued", (s) => s.key.status === "redo" || s.clip.status === "redo"],
    ["missing", "Not made", (s) => s.key.status === "missing"],
    ["sing", "Sings", (s) => s.sing],
    ["options", "Has options", (s) => s.options > 0],
  ];
  const castIds = [...new Set(d.shots.flatMap((s) => s.cast))];
  const sceneIds = [...new Set(d.shots.map((s) => s.scene))];
  const shown = d.shots.filter((s) => matches(q, s.id, s.lyric, s.feel, s.motion)
    && (!status || STATUS.find(([k]) => k === status)![2](s)) && (!who || s.cast.includes(who)) && (!where || s.scene === where));
  const clear = () => { setQ(""); setStatus(""); setWho(""); setWhere(""); };
  const nice = (id: string) => id.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  const open = (s: Shot) => {
    if (!desktop) return go("episodes", slug, "watch", s.id);
    setPinned(s.id); setSel(s.id); if (watching === "film") setView(hasClips ? "clips" : "keys");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const stepState = (n: FlowNode) => (n.kind === "done" ? "var(--go)" : n.kind === "you" ? "var(--gate)" : n.kind === "running" ? "var(--auto-text)" : "var(--line-2)");

  return (
    <div className="col" style={{ gap: 18 }}>
      <header className="col" style={{ gap: 12 }}>
        <div>
          <div className="muted small">{(d.lang ?? "").toUpperCase()} · {fmtTime(d.shots.length ? d.shots[d.shots.length - 1].start + d.shots[d.shots.length - 1].dur : 0)} · {d.shots.length} shots</div>
          <h1 lang={d.lang}>{d.title}</h1>
        </div>
        <nav className="steps-strip" aria-label="Episode steps">
          {nodes.map((n) => (
            <a key={n.n} className={`step ${n === next ? "now" : ""}`} href={n.action?.to ?? href("episodes", slug)} title={n.detail}>
              <span className="dot" style={{ background: stepState(n) }} />{n.title}<span className="faint" style={{ fontWeight: 400 }}>{n.state}</span>
            </a>
          ))}
        </nav>
      </header>
      <ErrorNote msg={err ?? ep.error} />
      {d.jobs.map((j) => <JobBar key={j.id} j={j} />)}

      {next?.action && next.kind !== "running" && (
        next.action.to
          ? <a className="next-card" href={next.action.to}><NextIcon gate={next.kind === "you"} /><span className="col" style={{ gap: 2, flex: 1 }}><b>{next.action.label.replace(/ →$/, "")}</b><span className="muted small">{next.detail}</span></span></a>
          : <button className="next-card" style={{ border: 0, font: "inherit", textAlign: "left", cursor: "pointer" }} disabled={!!busy} onClick={() => run(next.action!.phase!)}><NextIcon gate={false} /><span className="col" style={{ gap: 2, flex: 1 }}><b>{busy ? "Queuing…" : next.action.label}</b><span className="muted small">{next.detail}</span></span></button>
      )}

      {d.shots.length > 0 && (desktop ? (
        <div className="split" style={{ alignItems: "stretch" }}>
          <section className="grow col" style={{ gap: 12 }} aria-label={watching === "film" ? "Film" : "Animatic"}>
            {(d.film || hasClips) && (
              <div className="chips" role="group" aria-label="Watch">
                {d.film && <button className="chip-btn" aria-pressed={watching === "film"} onClick={() => setView("film")}>Finished film</button>}
                {hasClips && <button className="chip-btn" aria-pressed={watching === "clips"} onClick={() => setView("clips")}>Moving clips</button>}
                <button className="chip-btn" aria-pressed={watching === "keys"} onClick={() => setView("keys")}>Keyframes</button>
              </div>
            )}
            {watching === "film" && d.film
              ? <FilmPlayer src={d.film} poster={d.poster} title={d.title} />
              : <AnimaticPlayer key={(pinned ?? "start") + watching} d={d} start={pinned ?? undefined} onShot={setSel} mode={watching === "clips" ? "clips" : "keys"} />}
            {sel && watching !== "film" && (
              <div className="row" style={{ gap: 8 }}>
                <a className="btn" href={href("episodes", slug, "options", sel)}>Try 4 options for {sel}</a>
                <a className="btn" href={href("episodes", slug, "director", sel)}>Change {sel}…</a>
                <a className="btn" href={href("episodes", slug, "review", "keys")}>Review keyframes</a>
              </div>
            )}
          </section>
          <aside className="side panel" aria-label="Director" style={{ maxWidth: 440 }}>
            <div className="row between"><h2 className="h2">Director</h2><a className="small" href={href("episodes", slug, "director")}>Open</a></div>
            <DirectorPanel slug={slug} compact />
          </aside>
        </div>
      ) : (<>
        {d.film && <FilmPlayer src={d.film} poster={d.poster} title={d.title} />}
        <a className="next-card" href={href("episodes", slug, "watch")}>
          <span className="round-go" aria-hidden="true"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M7 4l14 8-14 8z" /></svg></span>
          <span className="col" style={{ gap: 2, flex: 1 }}><b>{d.shots.some((s) => s.clip.url) ? "Watch shot by shot" : "Watch the animatic"}</b><span className="muted small">{d.shots.some((s) => s.clip.url) ? "Moving clips (or keyframes) cut to the song" : "All keyframes cut to the song · no GPU needed"}</span></span>
        </a>
      </>))}
      {!desktop && <a className="next-card" href={href("episodes", slug, "director")}><NextIcon gate={false} director /><span className="col" style={{ gap: 2, flex: 1 }}><b>Ask the director</b><span className="muted small">Change shots in plain words</span></span></a>}

      <section className="col" style={{ gap: 12 }} aria-labelledby="sb">
        <div className="row between"><h2 id="sb" className="h2">Storyboard</h2><a className="small" href={href("episodes", slug, "shots")}>Edit prompts</a></div>
        <div className="filters">
          <SearchBox id="sb-q" value={q} onChange={setQ} placeholder="Search lyrics, feelings, shots" />
          <ChipRow label="Status" value={status} onChange={setStatus} options={STATUS.map(([k, l, f]) => ({ value: k, label: l, n: count(f) })).filter((o) => o.n)} />
          {castIds.length > 1 && <ChipRow label="Who is in it" all="Everyone" value={who} onChange={setWho}
            options={castIds.map((c) => ({ value: c, label: nice(c).split(" ")[0], n: count((s) => s.cast.includes(c)), image: portraits[c] }))} />}
          {sceneIds.length > 1 && <ChipRow label="Where" all="Everywhere" value={where} onChange={setWhere}
            options={sceneIds.map((c) => ({ value: c, label: nice(c), n: count((s) => s.scene === c) }))} />}
          <ResultLine shown={shown.length} total={d.shots.length} what="shots" onClear={clear} />
        </div>
        {shown.length === 0 && <div className="empty">No shots match. <button className="btn-quiet" style={{ color: "var(--go-text)" }} onClick={clear}>Clear filters</button></div>}
        <div className="grid-tiles">
          {shown.map((s, i) => {
            const flag = s.key.status === "redo" ? "redoing" : s.key.status === "to_review" ? "review" : "";
            const newPlace = i === 0 || shown[i - 1].scene !== s.scene;
            return (
              <button key={s.id} className={`tile ${desktop && sel === s.id ? "on" : s.key.status === "redo" ? "flag" : ""}`} onClick={() => open(s)} aria-label={`${s.id}: ${s.lyric ?? "instrumental"}`}>
                {s.key.url ? <img src={s.key.url} alt="" loading="lazy" /> : <span className="ph">{s.key.status === "redo" ? "Redoing" : "Not made yet"}</span>}
                <span className="tags">
                  <span className="tag">{s.id} · {fmtTime(s.start)}</span>
                  {s.sing && <span className="tag sing">sings</span>}
                  {flag && <span className="tag gate">{flag}</span>}
                  {s.key.status === "approved" && <span className="tag go" aria-label="approved">✓</span>}
                  {s.options > 0 && <span className="tag">{s.options} options</span>}
                  {newPlace && <span className="tag" style={{ marginLeft: "auto", gap: 4 }}>
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" aria-hidden="true"><path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z" /><circle cx="12" cy="10" r="2.5" /></svg>{nice(s.scene)}</span>}
                </span>
                <span className="meta">
                  <span className="line1" lang={d.lang}>{s.lyric || "(instrumental)"}</span>
                  <span className="line2">{s.feel || s.cast.map((c) => nice(c).split(" ")[0]).join(", ") || "\u00a0"}</span>
                </span>
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function NextIcon({ gate, director = false }: { gate: boolean; director?: boolean }) {
  return (
    <span aria-hidden="true" style={{ width: 44, height: 44, borderRadius: 22, flex: "none", display: "grid", placeItems: "center", background: gate ? "var(--gate)" : "var(--panel-2)", color: gate ? "var(--gate-ink)" : "var(--go-text)" }}>
      {director
        ? <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"><path d="M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z" /></svg>
        : <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>}
    </span>
  );
}

function buildNodes(d: EpisodeDetail): FlowNode[] {
  const total = d.shots.length;
  const running = (p: JobKind) => d.jobs.some((j) => j.kind === p && (j.status === "running" || j.status === "queued"));
  const keysToReview = d.shots.filter((s) => s.key.status === "to_review").length;
  const clipsToReview = d.shots.filter((s) => s.clip.status === "to_review").length;
  const keysApproved = d.shots.filter((s) => s.key.status === "approved").length;
  const clipsApproved = d.shots.filter((s) => s.clip.status === "approved").length;
  const published = d.stage === "published";
  const node = (n: string, title: string, f: Omit<FlowNode, "n" | "title">): FlowNode => ({ n, title, ...f });
  const doneish = (cond: boolean): NodeKind => (published || cond ? "done" : "wait");

  return [
    node("01", "Song", {
      gate: true, kind: d.song ? "done" : "you", state: d.song ? "Ready" : "Needs a song",
      detail: d.song ? "Mastered song and line timings are in place." : "Pick a voice style, make takes for the lyrics and choose the one you like.",
      action: { label: d.song ? "Open song" : "Make the song →", to: href("episodes", d.slug, "song") },
    }),
    node("02", "Shot list", {
      gate: true,
      kind: running("draft") ? "running" : !total || d.empty_shots ? "you" : "done",
      state: running("draft") ? "Drafting" : !total ? "Empty" : d.empty_shots ? `${d.empty_shots} need prompts` : `${total} shots`,
      detail: d.empty_shots ? "Some lyric lines have no keyframe/motion prompts yet. The writer model can draft them." : "One shot per lyric line: who is where, and what happens.",
      action: { label: d.empty_shots ? "Open shot list →" : "Edit shot list", to: href("episodes", d.slug, "shots") },
    }),
    node("03", "Keyframes", {
      gate: true,
      kind: running("keys") ? "running" : published ? "done" : keysToReview ? "you" : d.keys === total && keysApproved === total ? "done" : "wait",
      state: running("keys") ? "Rendering" : published ? "Done" : keysToReview ? "Needs you" : `${d.keys}/${total}`,
      detail: `${d.keys} of ${total} made · ${keysApproved} approved${keysToReview ? ` · ${keysToReview} waiting for you` : ""}.`,
      action: keysToReview ? { label: "Review keyframes →", to: href("episodes", d.slug, "review", "keys") }
        : d.empty_shots ? undefined
        : d.keys < total ? { label: "Make missing keyframes", phase: "keys" } : { label: "Open review", to: href("episodes", d.slug, "review", "keys") },
    }),
    node("04", "Clips", {
      gate: true,
      kind: running("clips") ? "running" : published ? "done" : clipsToReview ? "you" : d.clips === total && clipsApproved === total ? "done" : "wait",
      state: running("clips") ? "Rendering" : published ? "Done" : clipsToReview ? "Needs you" : `${d.clips}/${total}`,
      detail: `${d.clips} of ${total} rendered (~8 min each at 720p) · ${clipsApproved} approved.`,
      action: clipsToReview ? { label: "Review clips →", to: href("episodes", d.slug, "review", "clips") }
        : d.clips < total ? { label: "Render missing clips", phase: "clips" } : { label: "Open review", to: href("episodes", d.slug, "review", "clips") },
    }),
    node("05", "Assemble", {
      kind: running("assemble") ? "running" : doneish(!!d.output), state: running("assemble") ? "Running" : d.output ? "Done" : "Waiting",
      detail: "Cut every clip to its slot on the song grid and add the song.",
      action: d.output ? { label: "Watch episode", to: d.film ?? d.output } : { label: "Assemble now", phase: "assemble" },
    }),
    node("06", "Upload pack", {
      gate: true, kind: running("package") || running("upload") ? "running" : published ? "done" : d.output ? "you" : "wait",
      state: published ? "Published" : running("package") || running("upload") ? "Running" : d.output ? "Ready to upload" : "Waiting",
      detail: "1080p file with your channel intro (if you have one), thumbnail, title, description, tags and the YouTube checklist.",
      action: d.output || published ? { label: published ? "Open upload pack" : "Open upload pack →", to: href("episodes", d.slug, "upload") } : undefined,
    }),
  ];
}

export function JobBar({ j }: { j: Job }) {
  return (
    <div className="card pad row" style={{ borderColor: j.status === "running" ? "#1f4a47" : undefined }}>
      <span className={`pill ${j.status === "running" ? "go" : "idle"}`}>{j.status === "running" ? "Rendering" : "Queued"}</span>
      <span style={{ fontWeight: 700 }}>{jobLabel[j.kind] ?? j.kind}{j.args.only ? ` · ${j.args.only.join(", ")}` : ""}</span>
      <div className="bar" style={{ flex: "1 1 200px" }}><span style={{ width: `${Math.max(2, j.progress * 100)}%` }} /></div>
      <span className="muted small">{j.message}</span>
    </div>
  );
}
