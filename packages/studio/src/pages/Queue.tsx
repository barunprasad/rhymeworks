import { useState } from "react";
import { ago, api, jobLabel, useLoad, workerText, type Job, type Settings } from "../api";
import { href } from "../router";
import { ErrorNote, JobPill } from "../components/bits";

export function QueuePage() {
  const jobs = useLoad(api.jobs, [], ["job", "queue"]);
  const settings = useLoad(api.settings, [], ["settings", "worker"]);
  const [err, setErr] = useState<string | null>(null);
  const all = jobs.data ?? [];
  const running = all.find((j) => j.status === "running");
  const queued = all.filter((j) => j.status === "queued");
  const history = all.filter((j) => !["running", "queued"].includes(j.status)).slice(0, 15);
  const s = settings.data;

  const act = async (f: () => Promise<unknown>) => { setErr(null); try { await f(); jobs.reload(); settings.reload(); } catch (e) { setErr((e as Error).message); } };
  const save = (patch: Partial<Settings>) => act(() => api.saveSettings(patch));

  return (
    <>
      <header className="row between">
        <div><h1>Render queue</h1><p className="muted" style={{ margin: "4px 0 0" }}>One heavy job at a time (32 GB machine). {s ? workerText[s.worker] + "." : ""}</p></div>
        {s && <button className="btn" onClick={() => save({ paused: !s.paused })}>{s.paused ? "Resume queue" : "Pause after this job"}</button>}
      </header>
      <ErrorNote msg={err ?? jobs.error} />

      <section className="card pad col" style={{ borderColor: running ? "#1f4a47" : undefined }} aria-labelledby="now">
        <div className="row between"><h2 id="now">{running ? `${jobLabel[running.kind] ?? running.kind} · ${running.episode}` : "Nothing rendering"}</h2>{running && <JobPill s="running" />}</div>
        {running ? (
          <>
            <div className="muted small">{running.message} · started {ago(running.started)}{running.args.only ? ` · shots ${running.args.only.join(", ")}` : ""}</div>
            <div className="bar" style={{ height: 10 }}><span style={{ width: `${Math.max(2, running.progress * 100)}%` }} /></div>
            <div className="row"><a className="btn" href={href("episodes", running.episode)}>Open episode</a><button className="btn" onClick={() => act(() => api.cancel(running.id))}>Cancel this job</button></div>
          </>
        ) : <div className="muted small">{s?.worker === "waiting_hours" ? `Queued jobs will start at ${s.work_hours.split("-")[0]}.` : queued.length ? "Starting the next job…" : "The GPU is free."}</div>}
      </section>

      <div className="split">
        <section className="grow" aria-labelledby="next">
          <h2 id="next" className="section-title">UP NEXT</h2>
          {queued.length === 0 && <div className="empty">The queue is empty.</div>}
          {queued.map((j, i) => (
            <QueueRow key={j.id} j={j} up={i > 0 ? () => act(() => api.move(j.id, queued[i - 1].id)) : undefined}
              down={i < queued.length - 1 ? () => act(() => api.move(queued[i + 1].id, j.id)) : undefined}
              cancel={() => act(() => api.cancel(j.id))} />
          ))}
          <div className="row between" style={{ marginTop: 12 }}>
            <h2 className="section-title" style={{ margin: 0 }}>HISTORY</h2>
            {history.length > 0 && <button className="btn btn-quiet small" onClick={() => act(api.clearHistory)}>Clear history</button>}
          </div>
          {history.length === 0 && <div className="empty">No finished jobs.</div>}
          {history.map((j) => (
            <div key={j.id} className="card row" style={{ padding: "10px 14px" }}>
              <JobPill s={j.status} />
              <span style={{ fontWeight: 500 }}>{jobLabel[j.kind] ?? j.kind} · {j.episode}{j.args.only ? ` · ${j.args.only.join(", ")}` : ""}</span>
              <span className="faint small" style={{ marginLeft: "auto" }}>{j.started && j.finished ? `${Math.round((j.finished - j.started) / 60)} min · ` : ""}{ago(j.finished ?? j.created)}</span>
              {j.status === "failed" && <div className="small" style={{ color: "var(--danger)", flexBasis: "100%", whiteSpace: "pre-wrap" }}>{j.message.slice(-300)}</div>}
            </div>
          ))}
        </section>

        {s && (
          <aside className="side panel" aria-labelledby="rules">
            <h2 id="rules">When the GPU may work</h2>
            <Toggle on={s.daytime_only} onClick={() => save({ daytime_only: !s.daytime_only })} title={`Daytime only, ${s.work_hours}`} text="Jobs wait at night and continue in the morning." />
            <label className="col" style={{ gap: 6 }}>
              <span className="small muted">Work hours</span>
              <input className="input" defaultValue={s.work_hours} onBlur={(e) => e.target.value !== s.work_hours && save({ work_hours: e.target.value })} aria-describedby="hours-help" />
              <span id="hours-help" className="faint small">Format 09:00-22:00</span>
            </label>
            <Toggle on={s.yield_to_ollama} onClick={() => save({ yield_to_ollama: !s.yield_to_ollama })} title="Make room for other apps" text="Waits while another large Ollama model is loaded." />
          </aside>
        )}
      </div>
    </>
  );
}

function Toggle({ on, onClick, title, text }: { on: boolean; onClick: () => void; title: string; text: string }) {
  return (
    <button role="switch" aria-checked={on} onClick={onClick} style={{ display: "flex", gap: 12, alignItems: "flex-start", background: "none", border: 0, padding: 0, textAlign: "left", cursor: "pointer" }}>
      <span className={`switch ${on ? "on" : ""}`} />
      <span><b>{title}</b><br /><span className="muted small">{text}</span></span>
    </button>
  );
}

function QueueRow({ j, up, down, cancel }: { j: Job; up?: () => void; down?: () => void; cancel: () => void }) {
  return (
    <div className="card row" style={{ padding: "12px 14px" }}>
      <span className={`pill ${j.kind === "clips" ? "go" : j.kind === "keys" ? "auto" : "idle"}`}>{jobLabel[j.kind] ?? j.kind}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 700 }}>{j.episode}{j.args.only ? ` · ${j.args.only.join(", ")}` : " · all missing"}</div>
        <div className="faint small">{j.args.redo ? "redo · " : ""}queued {ago(j.created)}</div>
      </div>
      <button className="btn btn-quiet" onClick={up} disabled={!up} aria-label="Move up">↑</button>
      <button className="btn btn-quiet" onClick={down} disabled={!down} aria-label="Move down">↓</button>
      <button className="btn btn-quiet" onClick={cancel} aria-label={`Cancel job ${j.id}`}>✕</button>
    </div>
  );
}
