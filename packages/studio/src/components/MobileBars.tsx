// Phone chrome (under 900 px): a top bar and a bottom tab bar. The desktop sidebar replaces both.
import { useEffect, useState } from "react";
import { api, useLoad, workerText } from "../api";
import { href } from "../router";
import { Logo } from "./bits";

export const DESKTOP = "(min-width: 900px)";

/** True when the desktop layout (sidebar) is showing. */
export function useIsDesktop() {
  const [on, setOn] = useState(() => window.matchMedia(DESKTOP).matches);
  useEffect(() => {
    const m = window.matchMedia(DESKTOP);
    const f = () => setOn(m.matches);
    m.addEventListener("change", f);
    return () => m.removeEventListener("change", f);
  }, []);
  return on;
}

function GpuChip() {
  const health = useLoad(api.health, [], ["worker", "job", "settings"]);
  const jobs = useLoad(api.jobs, [], ["job"]);
  const running = jobs.data?.find((j) => j.status === "running");
  const state = health.data?.worker;
  const color = running ? "var(--go)" : state === "idle" ? "var(--faint)" : state ? "var(--gate)" : "var(--danger)";
  const text = running ? `GPU ${Math.round(running.progress * 100)}%` : state === "idle" ? "GPU idle" : state ? "Waiting" : "Offline";
  const label = running ? `GPU busy: ${running.kind} ${running.episode}. Open the queue` : `${state ? workerText[state] : "Studio API not reachable"}. Open the queue`;
  return (
    <a className="gpu-chip" href={href("queue")} aria-label={label}>
      <span className="dot" style={{ background: color }} />{text}
    </a>
  );
}

export function TopBar({ back }: { back?: { to: string; label: string; title: string; sub?: string } }) {
  const projects = useLoad(api.projects, []);
  const project = projects.data?.[0];
  return (
    <header className="topbar">
      {back ? (
        <>
          <a className="icon-btn" href={back.to} aria-label={back.label}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7" /></svg>
          </a>
          <div className="topbar-title">
            {back.sub && <div className="faint" style={{ fontSize: 12 }}>{back.sub}</div>}
            <div>{back.title}</div>
          </div>
        </>
      ) : (
        <>
          <span style={{ paddingLeft: 8 }}><Logo size={38} /></span>
          <span className="brand" style={{ fontSize: 19, flex: 1 }}>Rhymeworks</span>
        </>
      )}
      <GpuChip />
      {project?.icon && !back && (
        <span className="icon-btn" title={`Project: ${project.name}`}><img src={project.icon} alt={`Project: ${project.name}`} style={{ width: 30, height: 30, borderRadius: "50%" }} /></span>
      )}
    </header>
  );
}

const icons = {
  home: <path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />,
  episodes: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M10 9l5 3-5 3z" /></>,
  library: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  queue: <path d="M4 6h16M4 12h16M4 18h10" />,
};

export function TabBar({ section }: { section: string }) {
  const eps = useLoad(api.episodes, [], ["job", "output", "review"]);
  const waiting = (eps.data ?? []).reduce((n, e) => n + (e.keys_to_review ? 1 : 0) + (e.clips_to_review ? 1 : 0), 0);
  const tabs: [keyof typeof icons, string, string][] = [
    ["home", "Home", href()], ["episodes", "Episodes", href("episodes")], ["library", "Library", href("library", "all")], ["queue", "Queue", href("queue")],
  ];
  const cur = section || "home";
  return (
    <nav className="tabbar" aria-label="Studio">
      {tabs.map(([k, label, to]) => (
        <a key={k} href={to} className={cur === k ? "active" : ""} aria-current={cur === k ? "page" : undefined}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{icons[k]}</svg>
          {label}
          {k === "home" && waiting > 0 && <span className="badge" aria-label={`${waiting} waiting for you`}>{waiting}</span>}
        </a>
      ))}
    </nav>
  );
}
