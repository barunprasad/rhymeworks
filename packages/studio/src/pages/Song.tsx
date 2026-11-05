import { useEffect, useState } from "react";
import { api, useLoad, type SongStep } from "../api";
import { href } from "../router";
import { ErrorNote } from "../components/bits";
import { useIsDesktop } from "../components/MobileBars";
import { PlayIcon, useAudio } from "../components/useAudio";
import { JobBar } from "./Episode";

const pitchWord = (hz: number | null) => (!hz ? "" : hz >= 330 ? "child-like voice" : hz >= 240 ? "high voice" : "low voice");

/** Song step (mock-up P4): voice style + tempo + lyrics → ACE-Step takes; your ears pick one; it is mastered onto the shot grid. */
export function SongPage({ slug }: { slug: string }) {
  const sg = useLoad(() => api.song(slug), [slug], ["spec", "job", "output"], slug);
  const desktop = useIsDesktop();
  const audio = useAudio();
  const [pick, setPick] = useState<string | null>(null);
  const [setup, setSetup] = useState<boolean | null>(null);   // settings panel open (default: open until there are takes)
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const d = sg.data;
  useEffect(() => { if (d && pick === null && d.chosen) setPick(d.chosen); }, [d, pick]);
  if (!d) return <ErrorNote msg={sg.error} />;

  const act = async (f: () => Promise<unknown>) => {
    setBusy(true); setErr(null);
    try { await f(); sg.reload(); } catch (e) { setErr((e as Error).message.replace(/^\w+ \S+: /, "")); } finally { setBusy(false); }
  };
  const making = d.jobs.some((j) => j.kind === "song");
  const mastering = d.jobs.some((j) => j.kind === "master" || j.kind === "import");
  const best = d.takes.reduce<string | null>((b, t) => (t.words !== null && (b === null || t.words > (d.takes.find((x) => x.name === b)?.words ?? -1)) ? t.name : b), null);
  const secs = Math.round(d.lines * d.line_seconds + 2 * d.line_seconds + 6);
  const showSetup = setup ?? d.takes.length === 0;
  const voice = d.voices.find((v) => v.id === d.voice);
  const done = !!d.master && (d.chosen === pick || (!!d.imported && !pick));

  const cta = mastering ? <button className="btn btn-go" style={{ flex: 1, justifyContent: "center" }} disabled>Mastering…</button>
    : done ? <a className="btn btn-go" style={{ flex: 1, justifyContent: "center" }} href={href("episodes", slug)}>Song is ready · back to episode</a>
    : !pick && !d.takes.length ? <button className="btn btn-go" style={{ flex: 1, justifyContent: "center" }} disabled>Make takes or use an existing song</button>
    : <button className="btn btn-go" style={{ flex: 1, justifyContent: "center" }} disabled={!pick || busy}
        onClick={() => act(async () => { audio.stop(); await api.masterTake(slug, pick!); })}>
        {pick ? `Use take ${d.takes.find((t) => t.name === pick)?.n ?? ""} and master it` : "Pick a take to continue"}
      </button>;

  return (
    <>
      <div className="crumbs only-desktop"><a href={href("episodes", slug)}>{d.title}</a> / Song</div>
      <header className="row between">
        <div>
          <h1 className="only-desktop">Pick the song take</h1>
          <p className="muted small" style={{ margin: "4px 0 0" }}>
            {voice?.name ?? "No voice style yet"} · {d.bpm} bpm · {d.lines} sung lines · about {Math.floor(secs / 60)}:{String(secs % 60).padStart(2, "0")}. Scores are automatic; your ears decide.
          </p>
        </div>
        {desktop && <div className="row">{cta}</div>}
      </header>
      <ErrorNote msg={err ?? sg.error} />
      {d.jobs.map((j) => <JobBar key={j.id} j={j} />)}

      {d.master && (
        <section className="card pad col" style={{ gap: 8, borderColor: "#1f4a47" }}>
          <div className="row between"><b>Mastered song</b><span className="pill go">{d.chosen ? `take ${d.chosen.replace(/\D+/g, "")}` : d.imported ? "Existing song" : "Ready"}</span></div>
          <audio controls src={d.master} className="song-player" aria-label="Mastered song" />
          <span className="faint small">{d.imported ? `From ${d.imported}. Each shot now starts on the downbeat of its line (shots are 1–3 bars); the vocal for lip-sync is isolated too.`
            : "The first sung line now starts exactly on a shot boundary; the vocal for lip-sync is isolated too."}</span>
        </section>
      )}

      <section className="card" style={{ overflow: "hidden" }}>
        <button className="row between" onClick={() => setSetup(!showSetup)} aria-expanded={showSetup}
          style={{ width: "100%", background: "none", border: 0, padding: "14px 16px", cursor: "pointer", color: "var(--text)", flexWrap: "nowrap" }}>
          <span style={{ fontWeight: 700 }}>Voice, tempo and lyrics</span>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--faint)" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><path d={showSetup ? "M6 15l6-6 6 6" : "M6 9l6 6 6-6"} /></svg>
        </button>
        {showSetup && <SongSetup d={d} audio={audio} disabled={making || mastering} onSaved={sg.reload} setErr={setErr} />}
      </section>

      <section className="col" style={{ gap: 10 }} aria-labelledby="takes">
        <h2 id="takes" className="section-title">TAKES</h2>
        {d.takes.length === 0 && !making && <div className="empty">No takes yet. Pick a voice style above, then make 4 takes (about {Math.max(2, Math.round(secs / 40))} min on this Mac).</div>}
        <div role="radiogroup" aria-labelledby="takes" className="col" style={{ gap: 10 }}>
          {d.takes.map((t) => {
            const on = audio.playing === t.url, picked = pick === t.name;
            return (
              <div key={t.name} className="row" style={{ gap: 10, flexWrap: "nowrap", background: "var(--panel)", borderRadius: 14, padding: "10px 12px",
                border: picked ? "2px solid var(--go)" : "1px solid var(--line)" }}>
                <button onClick={() => audio.toggle(t.url)} aria-label={`${on ? "Pause" : "Play"} take ${t.n}`}
                  style={{ flex: "none", width: 44, height: 44, borderRadius: 22, border: 0, display: "grid", placeItems: "center", cursor: "pointer",
                    background: on ? "var(--go)" : "var(--panel-2)", color: on ? "var(--go-ink)" : "var(--text)" }}><PlayIcon on={on} /></button>
                <div style={{ flex: 1, minWidth: 0 }} className="col">
                  <div className="row between" style={{ gap: 6 }}>
                    <span style={{ fontWeight: 700, fontSize: 15 }}>Take {t.n}{t.name === best && d.takes.length > 1 && <span className="pill go" style={{ marginLeft: 6 }}>Clearest</span>}</span>
                    <span className="small muted">{t.words !== null ? `words ${t.words}%` : "scoring…"}{t.pitch_hz ? ` · ${pitchWord(t.pitch_hz)}` : ""}</span>
                  </div>
                  <div className="bar" style={{ height: 5 }} aria-hidden="true"><span style={{ width: `${on ? audio.progress * 100 : 0}%` }} /></div>
                </div>
                <button role="radio" aria-checked={picked} aria-label={`Use take ${t.n}`} onClick={() => setPick(t.name)} className={`btn ${picked ? "btn-soft-go" : ""}`}
                  style={{ flex: "none", minWidth: 68, justifyContent: "center" }}>{picked ? "Picked" : "Use"}</button>
              </div>
            );
          })}
        </div>
        <button className="btn" style={{ justifyContent: "center", borderStyle: "dashed", minHeight: 48 }} disabled={busy || making || mastering || !d.voice}
          onClick={() => act(() => api.makeTakes(slug, 4))}>
          {making ? "Making takes…" : !d.voice ? "Pick a voice style first" : `Make ${d.takes.length ? "4 more" : "4"} takes · about ${Math.max(3, Math.round(secs / 30))} min`}
        </button>
      </section>

      <ExistingSongs slug={slug} audio={audio} disabled={busy || making || mastering} act={act} current={d.imported} />

      <section className="card pad col" style={{ gap: 4 }}>
        <div className="label">LYRICS</div>
        <div lang={d.lang} style={{ whiteSpace: "pre-wrap", lineHeight: 1.7, color: "var(--text-2)" }}>
          {d.lyrics.split("\n").map((ln, i) => <div key={i} style={ln.startsWith("[") ? { color: "var(--faint)", fontSize: 13, marginTop: i ? 8 : 0 } : undefined}>{ln || " "}</div>)}
        </div>
      </section>
      {!desktop && <div className="actionbar">{cta}</div>}
    </>
  );
}

function SongSetup({ d, audio, disabled, onSaved, setErr }: { d: SongStep; audio: ReturnType<typeof useAudio>; disabled: boolean; onSaved: () => void; setErr: (e: string | null) => void }) {
  const [bpm, setBpm] = useState(d.bpm);
  const [bars, setBars] = useState(d.bars_per_line);
  const [lyrics, setLyrics] = useState(d.lyrics);
  const [busy, setBusy] = useState(false);
  const save = async (b: Parameters<typeof api.saveSong>[1]) => {
    setBusy(true); setErr(null);
    try { await api.saveSong(d.slug, b); onSaved(); } catch (e) { setErr((e as Error).message.replace(/^\w+ \S+: /, "")); } finally { setBusy(false); }
  };
  const voices = [...d.voices].sort((a, b) => Number(b.langs?.includes(d.lang)) - Number(a.langs?.includes(d.lang)) || Number(b.status === "approved") - Number(a.status === "approved"));
  const changedTempo = bpm !== d.bpm || bars !== d.bars_per_line;
  return (
    <div className="col" style={{ gap: 16, padding: "0 16px 16px" }}>
      <div className="col" style={{ gap: 8 }}>
        <span className="label" id="voice-l">VOICE STYLE</span>
        <div role="radiogroup" aria-labelledby="voice-l" className="col" style={{ gap: 8 }}>
          {voices.map((v) => {
            const on = d.voice === v.id, playing = !!v.sample && audio.playing === v.sample;
            const fits = v.langs?.includes(d.lang);
            return (
              <div key={v.id} className="row" style={{ gap: 10, flexWrap: "nowrap", padding: "8px 10px", borderRadius: 12, background: "var(--panel-2)",
                border: on ? "2px solid var(--go)" : "1px solid var(--line)", opacity: fits ? 1 : 0.6 }}>
                <button disabled={!v.sample} onClick={() => v.sample && audio.toggle(v.sample)} aria-label={v.sample ? `${playing ? "Pause" : "Play"} sample of ${v.name}` : `No sample of ${v.name} yet`}
                  style={{ flex: "none", width: 40, height: 40, borderRadius: 20, border: 0, display: "grid", placeItems: "center", cursor: v.sample ? "pointer" : "default",
                    background: playing ? "var(--go)" : "var(--raised)", color: playing ? "var(--go-ink)" : v.sample ? "var(--text)" : "var(--faint)" }}><PlayIcon on={playing} /></button>
                <button role="radio" aria-checked={on} disabled={disabled || busy} onClick={() => save({ voice: v.id })}
                  style={{ flex: 1, minWidth: 0, background: "none", border: 0, padding: 0, textAlign: "left", cursor: "pointer", color: "var(--text)" }}>
                  <span className="row" style={{ gap: 6 }}><b>{v.name}</b>{v.status === "approved" ? <span className="pill go">Approved</span> : <span className="pill idle">Draft</span>}</span>
                  <span className="faint small" style={{ display: "block" }}>{v.desc}{!fits ? ` · not made for ${d.lang === "hi" ? "Hindi" : "English"}` : ""}</span>
                </button>
              </div>
            );
          })}
        </div>
        <a className="small" href={href("library", "voices")}>Manage voice styles</a>
      </div>

      <div className="row" style={{ gap: 12, alignItems: "flex-end" }}>
        <label className="col" style={{ gap: 6, flex: "1 1 110px" }}>
          <span className="label">TEMPO (BPM)</span>
          <input className="input" type="number" inputMode="numeric" min={50} max={200} value={bpm} onChange={(e) => setBpm(Number(e.target.value) || d.bpm)} />
        </label>
        <label className="col" style={{ gap: 6, flex: "1 1 110px" }}>
          <span className="label">BARS PER SHOT</span>
          <select className="select" value={bars} onChange={(e) => setBars(Number(e.target.value))}>{[1, 2, 4].map((b) => <option key={b} value={b}>{b}</option>)}</select>
        </label>
        {changedTempo && <button className="btn" disabled={busy || disabled} onClick={() => save({ bpm, bars_per_line: bars })}>Save tempo</button>}
      </div>
      <span className="faint small" style={{ marginTop: -8 }}>One shot = {((bars * 240) / bpm).toFixed(2)} s. Changing it after keyframes exist re-times the shot list.</span>

      <label className="col" style={{ gap: 6 }}>
        <span className="label">LYRICS · [VERSE] / [CHORUS] TAGS HELP THE SINGER</span>
        <textarea className="textarea" rows={8} lang={d.lang} value={lyrics} onChange={(e) => setLyrics(e.target.value)} style={{ lineHeight: 1.6, resize: "vertical" }} />
      </label>
      {lyrics.trim() !== d.lyrics.trim() && (
        <button className="btn" style={{ alignSelf: "flex-start" }} disabled={busy || disabled} onClick={() => save({ lyrics })}>Save lyrics</button>
      )}
      <span className="faint small">Original or traditional lyrics only. New takes use what is saved here.</span>
    </div>
  );
}

function ExistingSongs({ slug, audio, disabled, act, current }: { slug: string; audio: ReturnType<typeof useAudio>; disabled: boolean; act: (f: () => Promise<unknown>) => void; current: string | null }) {
  const [open, setOpen] = useState(false);
  const songs = useLoad(api.existingSongs, []);
  const list = (songs.data ?? []).filter((s) => s.episode !== slug);
  return (
    <section className="card" style={{ overflow: "hidden" }}>
      <button className="row between" onClick={() => setOpen(!open)} aria-expanded={open}
        style={{ width: "100%", background: "none", border: 0, padding: "14px 16px", cursor: "pointer", color: "var(--text)", flexWrap: "nowrap", textAlign: "left" }}>
        <span className="col" style={{ gap: 2 }}><span style={{ fontWeight: 700 }}>Use an existing song</span>
          <span className="faint small">A song that is already mastered, like the Jagannath bhajan.</span></span>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--faint)" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><path d={open ? "M6 15l6-6 6 6" : "M6 9l6 6 6-6"} /></svg>
      </button>
      {open && (
        <div className="col" style={{ gap: 8, padding: "0 16px 16px" }}>
          <span className="faint small">The studio finds the beat and where each line is sung, isolates the vocal, and rebuilds the shot list so every shot starts on its line's downbeat. Prompts you already wrote are kept for the same lyric. About 2 minutes.</span>
          {list.length === 0 && <span className="muted small">No mastered songs found in other episodes.</span>}
          {list.map((s) => {
            const on = audio.playing === s.url;
            return (
              <div key={s.path} className="row" style={{ gap: 10, flexWrap: "nowrap", padding: "8px 10px", borderRadius: 12, background: "var(--panel-2)",
                border: current === s.path ? "2px solid var(--go)" : "1px solid var(--line)" }}>
                <button onClick={() => audio.toggle(s.url)} aria-label={`${on ? "Pause" : "Play"} ${s.episode}`}
                  style={{ flex: "none", width: 40, height: 40, borderRadius: 20, border: 0, display: "grid", placeItems: "center", cursor: "pointer",
                    background: on ? "var(--go)" : "var(--raised)", color: on ? "var(--go-ink)" : "var(--text)" }}><PlayIcon on={on} /></button>
                <span className="col" style={{ flex: 1, minWidth: 0, gap: 2 }}>
                  <b style={{ overflowWrap: "anywhere" }}>{s.episode.replace(/-/g, " ")}</b>
                  <span className="faint small mono" style={{ overflowWrap: "anywhere" }}>{s.name} · {Math.floor(s.seconds / 60)}:{String(Math.round(s.seconds % 60)).padStart(2, "0")}</span>
                </span>
                <button className="btn" disabled={disabled} onClick={() => act(async () => { audio.stop(); await api.importSong(slug, s.path); })}>{current === s.path ? "Redo" : "Use"}</button>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
