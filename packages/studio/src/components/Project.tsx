// Projects (channels): which one the studio is showing, the switcher, and project settings.
// The choice is per browser (your phone can look at a different channel than your Mac). The library is shared by
// every project, so a character made for one channel can appear in another.
import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { api, useLoad, type EpisodeSummary, type Project } from "../api";
import { useSaved } from "./Filters";

export const ALL = "all";
const LANG_NAME: Record<string, string> = { en: "English", hi: "हिंदी (Hindi)" };

interface ProjectState {
  projects: Project[];
  current: string;                   // a project id, or ALL
  project: Project | undefined;      // the current project (undefined for ALL)
  setCurrent: (id: string) => void;
  inProject: (e: EpisodeSummary) => boolean;
  counts: Record<string, number>;
}

const Ctx = createContext<ProjectState>({ projects: [], current: "", project: undefined, setCurrent: () => {}, inProject: () => true, counts: {} });
export const useProject = () => useContext(Ctx);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const list = useLoad(api.projects, [], ["projects"]);
  const eps = useLoad(api.episodes, [], ["spec"]);
  const [saved, setSaved] = useSaved<string>("project", "");
  const projects = list.data ?? [];
  const current = saved === ALL && projects.length > 1 ? ALL : projects.find((p) => p.id === saved)?.id ?? projects[0]?.id ?? "";
  const value = useMemo<ProjectState>(() => {
    const counts: Record<string, number> = {};
    for (const e of eps.data ?? []) counts[e.project] = (counts[e.project] ?? 0) + 1;
    return {
      projects, current, counts, setCurrent: setSaved,
      project: projects.find((p) => p.id === current),
      inProject: (e) => current === ALL || !current || e.project === current,
    };
  }, [projects, current, eps.data, setSaved]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** The project's picture, or its first letter on a teal tile. */
export function ProjectAvatar({ project, size = 28 }: { project?: Project; size?: number }) {
  if (project?.icon) return <img src={project.icon} alt="" style={{ width: size, height: size, borderRadius: "50%", objectFit: "cover", flex: "none" }} />;
  return (
    <span aria-hidden="true" style={{ width: size, height: size, borderRadius: "50%", flex: "none", display: "grid", placeItems: "center",
      background: project ? "var(--go)" : "var(--raised)", color: project ? "var(--go-ink)" : "var(--text)", fontWeight: 800, fontSize: size * 0.46 }}>
      {project ? project.name.trim().charAt(0).toUpperCase() : "∗"}
    </span>
  );
}

/** The list of projects with All / settings / new: shared by the sidebar dropdown and the phone sheet. */
export function ProjectMenu({ onDone, onSettings }: { onDone: () => void; onSettings: (id: string) => void }) {
  const { projects, current, setCurrent, counts } = useProject();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const pick = (id: string) => { setCurrent(id); onDone(); };
  const create = async () => {
    try {
      const p = await api.createProject(name.trim());
      setCurrent(p.id);
      onSettings(p.id);
    } catch (e) { setErr((e as Error).message.replace(/^\w+ \S+: /, "")); }
  };
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  return (
    <div className="col" style={{ gap: 2 }} role="menu" aria-label="Projects">
      {projects.map((p) => (
        <button key={p.id} role="menuitemradio" aria-checked={p.id === current} className={`pm-item ${p.id === current ? "on" : ""}`} onClick={() => pick(p.id)}>
          <ProjectAvatar project={p} size={26} />
          <span className="pm-name">{p.name}</span>
          <span className="faint small">{counts[p.id] ?? 0}</span>
          {p.id === current && <Check />}
        </button>
      ))}
      {projects.length > 1 && (
        <button role="menuitemradio" aria-checked={current === ALL} className={`pm-item ${current === ALL ? "on" : ""}`} onClick={() => pick(ALL)}>
          <ProjectAvatar size={26} /><span className="pm-name">All projects</span><span className="faint small">{total}</span>{current === ALL && <Check />}
        </button>
      )}
      <div className="pm-sep" />
      {current !== ALL && (
        <button role="menuitem" className="pm-item" onClick={() => onSettings(current)}>
          <Gear /><span className="pm-name">Project settings</span>
        </button>
      )}
      {adding ? (
        <form className="col" style={{ gap: 8, padding: "6px 8px 8px" }} onSubmit={(e) => { e.preventDefault(); if (name.trim()) create(); }}>
          <label className="label" htmlFor="new-project-name">New project name</label>
          <input id="new-project-name" className="input" autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Bedtime Songs" maxLength={60} />
          {err && <div className="small" style={{ color: "var(--danger)" }}>{err}</div>}
          <div className="row" style={{ gap: 8 }}>
            <button type="submit" className="btn btn-go" disabled={!name.trim()}>Create</button>
            <button type="button" className="btn" onClick={() => { setAdding(false); setName(""); setErr(null); }}>Cancel</button>
          </div>
        </form>
      ) : (
        <button role="menuitem" className="pm-item" onClick={() => setAdding(true)}>
          <Plus /><span className="pm-name">New project</span>
        </button>
      )}
    </div>
  );
}

/** Edit a project: name, tagline, picture, languages and the upload text per language. */
export function ProjectSettings({ id, onClose }: { id: string; onClose: () => void }) {
  const { projects } = useProject();
  const p = projects.find((x) => x.id === id);
  // a project made a moment ago may not be in the list yet: wait for it, then fill the form from it
  return p ? <SettingsForm key={p.id} p={p} onClose={onClose} /> : null;
}

function SettingsForm({ p, onClose }: { p: Project; onClose: () => void }) {
  const id = p.id;
  const lib = useLoad(api.library, []);
  const [name, setName] = useState(p.name);
  const [tagline, setTagline] = useState(p.tagline ?? "");
  const [icon, setIcon] = useState<string | null>(p.icon_path ?? null);
  const [langs, setLangs] = useState<string[]>(p.languages ?? ["en"]);
  const [subscribe, setSubscribe] = useState<Record<string, string>>(p.subscribe ?? {});
  const [playlists, setPlaylists] = useState<Record<string, string>>(p.playlists ?? {});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const first = useRef<HTMLInputElement>(null);
  useEffect(() => {
    first.current?.focus();
    const f = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", f);
    return () => window.removeEventListener("keydown", f);
  }, [onClose]);

  const pictures = [...(lib.data?.cast ?? []), ...(lib.data?.props ?? []), ...(lib.data?.scenes ?? [])].filter((i) => i.path && i.image);
  const extra = p.icon_path && !pictures.some((i) => i.path === p.icon_path) ? [{ path: p.icon_path, image: p.icon, id: "current" }] : [];
  const toggleLang = (l: string) => setLangs(langs.includes(l) ? langs.filter((x) => x !== l) : [...langs, l]);
  const save = async () => {
    setBusy(true); setErr(null);
    try {
      const only = (r: Record<string, string>) => Object.fromEntries(["en", "hi"].map((l) => [l, langs.includes(l) ? (r[l] ?? "") : ""]));
      await api.patchProject(id, { name, tagline, icon, languages: langs, subscribe: only(subscribe), playlists: only(playlists) });
      onClose();
    } catch (e) { setErr((e as Error).message.replace(/^\w+ \S+: /, "")); setBusy(false); }
  };

  // rendered at the page level: the phone top bar's blur would otherwise trap a fixed sheet inside it
  return createPortal(
    <div className="pm-wrap">
      <button className="pm-backdrop" aria-label="Close" onClick={onClose} />
      <section className="pm-panel" role="dialog" aria-modal="true" aria-labelledby="ps-title">
        <div className="row between"><h2 id="ps-title" className="brand" style={{ fontSize: 22, margin: 0 }}>Project settings</h2>
          <button className="btn-quiet" onClick={onClose} aria-label="Close">✕</button></div>
        <p className="muted small" style={{ margin: 0 }}>A project is one channel: its name and picture, its languages, and the text added to every upload. Characters and places are shared by all projects.</p>

        <label className="label" htmlFor="ps-name">Name</label>
        <input id="ps-name" ref={first} className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
        <label className="label" htmlFor="ps-tagline">Tagline (optional)</label>
        <input id="ps-tagline" className="input" value={tagline} onChange={(e) => setTagline(e.target.value)} maxLength={100} placeholder="e.g. Nursery Rhymes & Kids Songs" />

        <div className="label" id="ps-icon">Picture</div>
        <div className="ps-icons" role="radiogroup" aria-labelledby="ps-icon">
          <button role="radio" aria-checked={!icon} className={`ps-icon ${!icon ? "on" : ""}`} onClick={() => setIcon(null)} title="No picture (first letter)">
            <ProjectAvatar project={{ ...p, icon: null, name: name || p.name }} size={44} />
          </button>
          {[...extra, ...pictures].map((i) => (
            <button key={i.path} role="radio" aria-checked={icon === i.path} className={`ps-icon ${icon === i.path ? "on" : ""}`} onClick={() => setIcon(i.path!)} title={i.id}>
              <img src={i.image!} alt={i.id} style={{ width: 44, height: 44, borderRadius: "50%", objectFit: "cover" }} />
            </button>
          ))}
        </div>

        <div className="label">Languages</div>
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          {["en", "hi"].map((l) => (
            <button key={l} className={`chip-btn ${langs.includes(l) ? "on" : ""}`} aria-pressed={langs.includes(l)} onClick={() => toggleLang(l)}>{LANG_NAME[l]}</button>
          ))}
        </div>

        {langs.map((l) => (
          <fieldset key={l} className="ps-lang">
            <legend className="label">Uploads in {LANG_NAME[l]}</legend>
            <label className="small muted" htmlFor={`ps-sub-${l}`}>Last line of the description</label>
            <textarea id={`ps-sub-${l}`} className="textarea" rows={2} value={subscribe[l] ?? ""} onChange={(e) => setSubscribe({ ...subscribe, [l]: e.target.value })}
              placeholder={`Subscribe to ${name || "your channel"} for new songs!`} />
            <label className="small muted" htmlFor={`ps-pl-${l}`}>Playlist</label>
            <input id={`ps-pl-${l}`} className="input" value={playlists[l] ?? ""} onChange={(e) => setPlaylists({ ...playlists, [l]: e.target.value })}
              placeholder={l === "hi" ? "हिंदी बालगीत" : "English Rhymes"} />
          </fieldset>
        ))}

        {err && <div className="small" style={{ color: "var(--danger)" }}>{err}</div>}
        <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-go" onClick={save} disabled={busy || !name.trim() || !langs.length}>{busy ? "Saving…" : "Save"}</button>
        </div>
      </section>
    </div>,
    document.body,
  );
}

/** The project card + dropdown at the top of the desktop sidebar. */
export function ProjectSwitcher() {
  const { project, current } = useProject();
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    window.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); window.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div ref={box} style={{ position: "relative" }}>
      <button className="project" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <ProjectAvatar project={project} size={28} />
        <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", lineHeight: 1.25 }}>
          <span style={{ fontSize: 11, color: "var(--muted)" }}>Project</span>
          <span style={{ fontSize: 14, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{current === ALL ? "All projects" : project?.name ?? "…"}</span>
        </span>
        <Chevron />
      </button>
      {open && (
        <div className="proj-menu">
          <ProjectMenu onDone={() => setOpen(false)} onSettings={(id) => { setOpen(false); setSettings(id); }} />
        </div>
      )}
      {settings && <ProjectSettings id={settings} onClose={() => setSettings(null)} />}
    </div>
  );
}

/** The phone version: the project picture in the top bar opens the same menu as a bottom sheet. */
export function ProjectButton() {
  const { project, current } = useProject();
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState<string | null>(null);
  return (
    <>
      <button className="icon-btn" style={{ background: "none", border: 0, cursor: "pointer" }} onClick={() => setOpen(true)}
        aria-label={`Project: ${current === ALL ? "All projects" : project?.name ?? ""}. Switch project`}>
        <ProjectAvatar project={project} size={30} />
      </button>
      {open && createPortal(
        <div className="pm-wrap">
          <button className="pm-backdrop" aria-label="Close" onClick={() => setOpen(false)} />
          <section className="pm-panel" aria-label="Projects">
            <h2 className="brand" style={{ fontSize: 20, margin: "0 0 4px" }}>Projects</h2>
            <ProjectMenu onDone={() => setOpen(false)} onSettings={(id) => { setOpen(false); setSettings(id); }} />
          </section>
        </div>,
        document.body,
      )}
      {settings && <ProjectSettings id={settings} onClose={() => setSettings(null)} />}
    </>
  );
}

const Check = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--go)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10" /></svg>;
const Chevron = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ color: "var(--muted)", flex: "none" }}><path d="M7 10l5 5 5-5" /></svg>;
const Gear = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ margin: 3 }}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></svg>;
const Plus = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true" style={{ margin: 3 }}><path d="M12 5v14M5 12h14" /></svg>;
