// Animatic: the whole episode as keyframes (or clips, once made) cut to the song, in the browser. No GPU needed.
import { useEffect, useRef, useState } from "react";
import { api, fmtTime, useLoad, type EpisodeDetail, type Shot } from "../api";
import { go, href } from "../router";
import { ErrorNote, ReviewPill } from "../components/bits";
import { JobBar } from "./Episode";
import { useFullscreen, useIdle } from "../components/Fullscreen";

export type Mode = "keys" | "clips";

const shotAt = (shots: Shot[], t: number) => {
  let cur = shots[0];
  for (const s of shots) if (s.start <= t + 0.01) cur = s;
  return cur;
};

/** One clip of the stack. Only the active one is visible and plays; the others wait, preloaded and rewound, underneath.
 *  The poster is the shot's keyframe (= the clip's first frame), so even a slow load never shows black. */
function ClipLayer({ s, active, playing, offset }: { s: Shot; active: boolean; playing: boolean; offset: number }) {
  const v = useRef<HTMLVideoElement>(null);
  const tick = Math.round(offset * 4);   // re-check sync 4× a second, not every frame
  useEffect(() => {
    const el = v.current;
    if (!el) return;
    if (!active) {
      el.pause();
      if (el.currentTime > 0.05) el.currentTime = 0;
      return;
    }
    if (Math.abs(el.currentTime - offset) > 0.35 && el.readyState >= 1) el.currentTime = Math.max(0, offset);   // a seek, or drift
    if (playing) el.play().catch(() => {});
    else el.pause();
  }, [active, playing, tick]); // eslint-disable-line react-hooks/exhaustive-deps
  return <video ref={v} src={s.clip.url!} poster={s.key.url ?? undefined} muted playsInline preload="auto"
    style={{ opacity: active ? 1 : 0, zIndex: active ? 1 : 0 }} aria-hidden={!active} />;
}

/** The player itself: picture + lyric + transport + filmstrip. Used full-screen on phones and inside the episode page on desktop. */
export function AnimaticPlayer({ d, start, onShot, mode = "keys" }: { d: EpisodeDetail; start?: string; onShot?: (id: string) => void; mode?: Mode }) {
  const audio = useRef<HTMLAudioElement>(null);
  const strip = useRef<HTMLDivElement>(null);
  const total = d.shots.length ? d.shots[d.shots.length - 1].start + d.shots[d.shots.length - 1].dur : 0;
  const initial = d.shots.find((s) => s.id === start)?.start ?? 0;
  const [t, setT] = useState(initial);
  const [playing, setPlaying] = useState(false);
  const cur = shotAt(d.shots, t);
  const idx = d.shots.indexOf(cur);
  const fs = useFullscreen<HTMLDivElement>();
  const { idle, poke } = useIdle(!!fs.full && playing);
  const wasIdle = useRef(false);

  // follow the song while it plays (no song yet: a plain clock)
  useEffect(() => {
    if (!playing) return;
    let raf = 0, last = performance.now();
    const tick = (now: number) => {
      const a = audio.current;
      if (a && d.song) setT(a.currentTime);
      else setT((x) => x + (now - last) / 1000);
      last = now;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, d.song]);
  useEffect(() => { if (t >= total && playing) { setPlaying(false); audio.current?.pause(); } }, [t, total, playing]);
  useEffect(() => {
    onShot?.(cur.id);
    const box = strip.current, el = box?.querySelector<HTMLElement>(`[data-id="${cur.id}"]`);
    if (box && el) box.scrollTo({ left: el.offsetLeft - box.offsetLeft - box.clientWidth / 2 + el.clientWidth / 2, behavior: "smooth" });   // never scrolls the page
  }, [cur.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const seek = (s: Shot) => {
    setT(s.start + 0.01);
    const a = audio.current;
    if (!a) return;
    if (a.readyState < 1) a.addEventListener("loadedmetadata", () => { a.currentTime = s.start + 0.01; }, { once: true });
    else a.currentTime = s.start + 0.01;
  };
  const toggle = async () => {
    const a = audio.current;
    if (playing) { a?.pause(); setPlaying(false); return; }
    if (t >= total - 0.05) seek(d.shots[0]);
    else if (a && Math.abs(a.currentTime - t) > 0.3) {   // start where the picture is (seeking needs the song's metadata)
      if (a.readyState < 1) await new Promise((r) => a.addEventListener("loadedmetadata", r, { once: true }));
      a.currentTime = t;
    }
    try { if (a && d.song) await a.play(); } catch { /* the browser blocked audio: play silent */ }
    setPlaying(true);
  };
  const step = (dir: 1 | -1) => seek(d.shots[Math.max(0, Math.min(d.shots.length - 1, idx + dir))]);
  useEffect(() => {
    const f = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, textarea, select")) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === " ") { e.preventDefault(); toggle(); } else if (e.key === "ArrowRight") step(1); else if (e.key === "ArrowLeft") step(-1);
      else if (e.key === "f" || e.key === "F") fs.toggle();
      else return;
      poke();
    };
    window.addEventListener("keydown", f);
    return () => window.removeEventListener("keydown", f);
  });

  const useClip = mode === "clips" && !!cur.clip.url;
  // clips: the previous, current and next clip stay mounted (stable keys), so a cut shows an already-loaded video
  const layers = useClip ? d.shots.slice(Math.max(0, idx - 1), idx + 2).filter((s) => s.clip.url) : [];
  const media = useClip
    ? <>{layers.map((s) => <ClipLayer key={s.id} s={s} active={s.id === cur.id} playing={playing} offset={t - s.start} />)}</>
    : cur.key.url
      ? <img key={cur.id} src={cur.key.url} alt={`Keyframe ${cur.id}`} className={`kb-${idx % 4}`}
          style={{ ["--kb" as string]: `${Math.max(2, cur.dur)}s`, animationPlayState: playing ? "running" : "paused" }} />
      : <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: "var(--faint)" }}>No keyframe yet for {cur.id}</div>;

  return (
    <div className="col" style={{ gap: 14 }}>
      {d.song && <audio ref={audio} src={d.song} preload="auto" onEnded={() => setPlaying(false)} />}
      <div ref={fs.ref} className={`player${fs.full ? " full" : ""}${fs.full === "page" ? " page-full" : ""}${idle ? " idle" : ""}`}
        role={fs.full ? "dialog" : undefined} aria-label={fs.full ? `${d.title}, full screen` : undefined}
        onPointerMove={poke} onPointerDown={() => { wasIdle.current = idle; poke(); }} onDoubleClick={fs.toggle}>
        {/* a click plays / pauses (YouTube-style); the first tap on hidden full-screen controls only shows them */}
        <div className="stage" onClick={() => { if (!wasIdle.current) toggle(); }}>{media}</div>
        <span className="tag" style={{ position: "absolute", top: "max(10px, env(safe-area-inset-top))", left: "max(10px, env(safe-area-inset-left))" }}>{cur.id} · {fmtTime(t)} / {fmtTime(total)}</span>
        {fs.full ? (
          <div className="ov" onClick={(e) => e.stopPropagation()} onDoubleClick={(e) => e.stopPropagation()}>
            <p className="lyric" lang={d.lang}>{cur.lyric || "♪"}</p>
            <div className="ov-bar">
              <button onClick={() => step(-1)} aria-label="Previous shot"><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 5h2v14H6zM20 5v14L9 12z" /></svg></button>
              <button className="big" onClick={toggle} aria-label={playing ? "Pause" : "Play"}><svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d={playing ? "M6 5h4v14H6zM14 5h4v14h-4z" : "M7 4l14 8-14 8z"} /></svg></button>
              <button onClick={() => step(1)} aria-label="Next shot"><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M16 5h2v14h-2zM4 5v14l11-7z" /></svg></button>
              <span className="time">{fmtTime(t)} / {fmtTime(total)}</span>
              <span className="sp" />
              <button onClick={fs.exit} aria-label="Exit full screen" title="Exit full screen (Esc)"><ExitIcon /></button>
            </div>
          </div>
        ) : (
          <button className="fs-btn" onClick={(e) => { e.stopPropagation(); fs.enter(); }} onDoubleClick={(e) => e.stopPropagation()} aria-label="Full screen" title="Full screen (F)"><EnterIcon /></button>
        )}
        <div className="progress" aria-hidden="true"><span style={{ width: `${total ? Math.min(100, (t / total) * 100) : 0}%` }} /></div>
      </div>
      <div className="col" style={{ gap: 8, minHeight: 96 }}>
        <p className="lyric" lang={d.lang}>{cur.lyric || "(instrumental)"}</p>
        <div className="row" style={{ gap: 6 }}>
          {cur.feel && <span className="chip">Feeling: {cur.feel}</span>}
          {cur.sing && <span className="tag sing">Sings this line</span>}
          <span className="faint small">{cur.dur.toFixed(1)} s · {cur.scene.replace(/_/g, " ")}</span>
        </div>
      </div>
      <div className="transport">
        <button className="small" onClick={() => step(-1)} aria-label="Previous shot"><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 5h2v14H6zM20 5v14L9 12z" /></svg></button>
        <button className="big" onClick={toggle} aria-label={playing ? "Pause" : "Play"}>
          <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d={playing ? "M6 5h4v14H6zM14 5h4v14h-4z" : "M7 4l14 8-14 8z"} /></svg>
        </button>
        <button className="small" onClick={() => step(1)} aria-label="Next shot"><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M16 5h2v14h-2zM4 5v14l11-7z" /></svg></button>
      </div>
      <div className="filmstrip" ref={strip} role="group" aria-label="Jump to a shot">
        {d.shots.map((s) => (
          <button key={s.id} data-id={s.id} onClick={() => seek(s)} aria-label={`Shot ${s.id}`} aria-current={s.id === cur.id ? "true" : undefined} className={s.id === cur.id ? "on" : ""}>
            {s.key.url ? <img src={s.key.url} alt="" /> : <span />}
            <i className={`st ${(mode === "clips" ? s.clip : s.key).status}`} />
          </button>
        ))}
      </div>
    </div>
  );
}

const EnterIcon = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></svg>;
const ExitIcon = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" /></svg>;

/** The finished film (a real mp4): the browser's own player, so full screen and AirPlay work everywhere, iPhone included. */
export function FilmPlayer({ src, poster, title }: { src: string; poster?: string | null; title: string }) {
  return (
    <div className="player film">
      <video src={src} poster={poster ?? undefined} controls playsInline preload="metadata" x-webkit-airplay="allow" aria-label={`${title}, finished film`} />
    </div>
  );
}

/** Phone page: #/episodes/<slug>/watch[/<shot>] */
export function AnimaticPage({ slug, start }: { slug: string; start?: string }) {
  const ep = useLoad(() => api.episode(slug), [slug], ["job", "output", "review", "spec"], slug);
  const [curId, setCurId] = useState<string | undefined>(start);
  const [picked, setMode] = useState<Mode | null>(null);   // default: the moving clips once there are any
  const [err, setErr] = useState<string | null>(null);
  const d = ep.data;
  if (!d) return <ErrorNote msg={ep.error} />;
  if (!d.shots.length) return <div className="empty">This episode has no shots yet.</div>;
  const cur = d.shots.find((s) => s.id === curId) ?? d.shots[0];
  const hasClips = d.shots.some((s) => s.clip.url);
  const mode: Mode = picked ?? (hasClips ? "clips" : "keys");
  const decide = async (decision: "approved" | "redo" | null) => {
    setErr(null);
    try { await api.review(slug, "keys", cur.id, decision); ep.reload(); } catch (e) { setErr((e as Error).message); }
  };

  return (
    <>
      {hasClips && (
        <div className="chips" role="group" aria-label="Show">
          <button className="chip-btn" aria-pressed={mode === "clips"} onClick={() => setMode("clips")}>Moving clips</button>
          <button className="chip-btn" aria-pressed={mode === "keys"} onClick={() => setMode("keys")}>Keyframes</button>
        </div>
      )}
      <ErrorNote msg={err ?? ep.error} />
      {d.jobs.map((j) => <JobBar key={j.id} j={j} />)}
      <AnimaticPlayer d={d} start={start} onShot={setCurId} mode={mode} />
      <div className="row between"><span className="faint small">Keyframe {cur.id}</span><ReviewPill s={cur.key.status} /></div>
      <div className="actionbar">
        <a className="btn" style={{ flex: 1 }} href={href("episodes", slug, "options", cur.id)}>Options{cur.options ? ` · ${cur.options}` : ""}</a>
        <a className="btn" style={{ flex: 1 }} href={href("episodes", slug, "director", cur.id)}>Change…</a>
        {cur.key.status === "approved"
          ? <button className="btn btn-soft-go" style={{ flex: 1 }} onClick={() => decide(null)}>Approved</button>
          : <button className="btn btn-go" style={{ flex: 1 }} disabled={!cur.key.url} onClick={() => decide("approved")}>Approve</button>}
      </div>
    </>
  );
}

export const watch = (slug: string, shot?: string) => go(...["episodes", slug, "watch", ...(shot ? [shot] : [])]);
