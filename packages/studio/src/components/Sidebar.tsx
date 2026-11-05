import { api, jobLabel, useLoad, workerText, type Job } from "../api";
import { href } from "../router";
import { useState } from "react";
import { Logo } from "./bits";
import { PhoneSheet } from "./PhoneQR";

const stageDot = (stage: string) => (stage === "published" ? "var(--go)" : stage === "shot list" || stage === "song" ? "#5b6270" : "var(--gate)");

export function Sidebar({ route }: { route: string[] }) {
  const projects = useLoad(api.projects, []);
  const episodes = useLoad(api.episodes, [], ["job", "output", "review", "spec"]);
  const health = useLoad(api.health, [], ["worker", "job", "settings"]);
  const jobs = useLoad(api.jobs, [], ["job"]);
  const running: Job | undefined = jobs.data?.find((j) => j.status === "running");
  const project = projects.data?.[0];
  const [phone, setPhone] = useState(false);
  const active = (...p: string[]) => p.every((x, i) => route[i] === x) && (p.length > 0 || route.length === 0);

  return (
    <nav className="nav" aria-label="Studio">
      <div className="col" style={{ gap: 12, padding: "4px 4px 16px" }}>
        <div className="row" style={{ padding: "0 4px", gap: 12 }}><Logo size={52} /><span className="brand" style={{ fontSize: 23 }}>Rhymeworks</span></div>
        {project && (
          <button className="project" aria-label="Current project">
            {project.icon && <img src={project.icon} alt="" style={{ width: 28, height: 28, borderRadius: "50%" }} />}
            <span style={{ flex: 1, display: "flex", flexDirection: "column", lineHeight: 1.25 }}>
              <span style={{ fontSize: 11, color: "var(--muted)" }}>Project</span>
              <span style={{ fontSize: 14, fontWeight: 700 }}>{project.name}</span>
            </span>
          </button>
        )}
      </div>
      <a className={`nav-link ${active() ? "active" : ""}`} href={href()}>Home</a>
      <div className="nav-label row between" style={{ paddingRight: 4 }}>EPISODES<a href={href("episodes", "new")} aria-label="New episode" className="btn-quiet" style={{ minWidth: 28, minHeight: 28, fontSize: 18, lineHeight: 1, color: "var(--go)" }}>+</a></div>
      <a className={`nav-link ${active("episodes") && route.length === 1 ? "active" : ""}`} href={href("episodes")}>All episodes <span className="faint" style={{ marginLeft: "auto" }}>{episodes.data?.length ?? ""}</span></a>
      {[...(episodes.data ?? [])].sort((a, b) => (b.updated ?? 0) - (a.updated ?? 0)).slice(0, 6).map((e) => (
        <a key={e.slug} className={`nav-link ${active("episodes", e.slug) ? "active" : ""}`} href={href("episodes", e.slug)}>
          <span className="dot" style={{ background: stageDot(e.stage) }} />{e.title}
        </a>
      ))}
      <div className="nav-label">LIBRARY</div>
      <a className={`nav-link ${active("library", "all") || (route[0] === "library" && route.length === 1) ? "active" : ""}`} href={href("library", "all")}>Everything</a>
      <a className={`nav-link ${active("library", "cast") ? "active" : ""}`} href={href("library", "cast")}>Characters</a>
      <a className={`nav-link ${active("library", "scenes") ? "active" : ""}`} href={href("library", "scenes")}>Worlds</a>
      <a className={`nav-link ${active("library", "props") ? "active" : ""}`} href={href("library", "props")}>Props</a>
      <a className={`nav-link ${active("library", "voices") ? "active" : ""}`} href={href("library", "voices")}>Voice styles</a>
      <div className="nav-label">MACHINE</div>
      <a className={`nav-link ${active("queue") ? "active" : ""}`} href={href("queue")}>Render queue</a>
      <button className="nav-link" onClick={() => setPhone(true)} style={{ background: "none", border: 0, width: "100%", textAlign: "left", cursor: "pointer", font: "inherit", marginTop: "auto" }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" style={{ marginRight: 8, verticalAlign: -3 }}><rect x="6" y="2" width="12" height="20" rx="2.5" /><path d="M11 18h2" /></svg>
        Open on your phone
      </button>
      {phone && <PhoneSheet url={health.data?.lan_url ?? null} onClose={() => setPhone(false)} />}
      <a className="gpu" href={href("queue")} style={{ color: "var(--muted)", marginTop: 8 }}>
        <div className="row between"><span style={{ color: "var(--text)", fontWeight: 500 }}>{health.data ? workerText[health.data.worker] : "Connecting…"}</span>
          {running && <span>{Math.round(running.progress * 100)}%</span>}</div>
        {running && <div className="bar" style={{ height: 6 }}><span style={{ width: `${Math.max(3, running.progress * 100)}%` }} /></div>}
        <div>{running ? `${jobLabel[running.kind] ?? running.kind} · ${running.episode}` : health.error ? "Studio API not reachable" : "Nothing rendering"}</div>
      </a>
    </nav>
  );
}
