// Typed client for the Rhymeworks studio API (pipeline/kidzone/studio/app.py) + live events.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

export type ReviewStatus = "missing" | "to_review" | "approved" | "redo";
export type Phase = "keys" | "clips" | "assemble" | "package";
export type JobKind = Phase | "draft" | "upload" | "asset" | "song" | "master" | "import" | "voice" | "options" | "director";
export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";
export type WorkerState = "idle" | "running" | "paused" | "waiting_hours" | "waiting_memory";

export interface Project {
  id: string; name: string; tagline?: string; icon: string | null; icon_path?: string | null; languages?: string[];
  subscribe?: Record<string, string>; playlists?: Record<string, string>;
}
export interface ProjectPatch { name?: string; tagline?: string; icon?: string | null; languages?: string[]; subscribe?: Record<string, string>; playlists?: Record<string, string> }
export interface Usage { shots: number; episodes: { slug: string; title: string; shots: string[] }[] }
export interface LibraryItem { id: string; kind: "cast" | "prop" | "scene"; token?: string; ref?: string | null; style?: string | null; person?: boolean; image: string | null; path?: string; added: number | null; used: Usage }
export interface Library { cast: LibraryItem[]; props: LibraryItem[]; scenes: LibraryItem[] }
export interface EpisodeSummary {
  slug: string; title: string; lang?: string; project: string; shots: number; keys: number; clips: number;
  keys_to_review: number; clips_to_review: number; empty_shots: number; has_song: boolean;
  stage: string; output: string | null; film: string | null; contact: string | null; poster: string | null; updated: number | null; scenes: string[]; cast: string[];
}
export interface Output { url: string | null; status: ReviewStatus; note?: string | null }
export interface Shot {
  id: string; start: number; dur: number; frames: number; sing: boolean; end: string | null; scene: string; seed: number;
  cast: string[]; key_prompt: string; motion: string; key: Output; clip: Output; lyric: string | null; feel: string | null; options: number;
}
export interface Job {
  id: number; kind: JobKind; episode: string; args: { only?: string[] | null; redo?: string[] | null; shot?: string; n?: number; ask?: string; shots?: string[] | null }; status: JobStatus;
  position: number; progress: number; message: string; log: string; created: number; started: number | null; finished: number | null;
}
export interface EpisodeDetail extends Omit<EpisodeSummary, "shots"> { width: number; height: number; song: string | null; shots: Shot[]; jobs: Job[] }
export type EndSpec = "same" | { seed: number; key: string } | null;
/** One [[shot]] as written in episode.toml (raw prompts with {tokens}), plus its timing and keyframe. */
export interface ShotRow {
  id: string; lyric: string | null; scene: string; seed: number; key: string; motion: string; feel: string | null; sing: boolean; end: EndSpec;
  lines: number | null; frames: number | null; clip_seed: number | null;
  start?: number; dur?: number; image: string | null; empty: boolean;
}
export type ShotFields = Partial<Pick<ShotRow, "lyric" | "scene" | "seed" | "key" | "motion" | "feel" | "sing" | "end" | "lines" | "frames">>;
export interface TokenInfo { token: string; label: string; kind: "cast" | "prop" | "var"; image: string | null }
export interface ShotList {
  slug: string; episode: { title: string; lang?: string; status?: string }; song: { line_seconds?: number; audio?: string };
  vars: Record<string, string>; shots: ShotRow[]; tokens: TokenInfo[]; scenes: { id: string; image: string | null }[]; jobs: Job[];
}
export interface NewEpisodeReq { title: string; lang: "en" | "hi"; lyrics: string; line_seconds: number; bpm?: number; scene: string; slug?: string; project?: string }
export interface UploadPack {
  slug: string; title: string; lang: string; playlist: string; published: boolean; episode_ready: boolean;
  video: { url: string; name: string; mb: number } | null;
  text: { title: string; description: string; tags: string; meta: string } | null;
  thumbs: { name: string; url: string }[]; thumbnail: string | null;
  checks: { id: string; title: string; detail: string; on: boolean }[]; jobs: Job[];
}
export type AssetKind = "cast" | "props" | "scenes";
export interface AssetDraft {
  id: string; kind: AssetKind; name: string; description: string; person: boolean; created: string;
  ref: string | null; style: string | null; candidates: { name: string; url: string }[]; jobs: Job[];
  saved: { id: string; file: string } | null; suggested_id: string;
}
export interface Voice {
  id: string; name: string; desc?: string; langs?: string[]; bpm?: number[]; mood?: string; status: "draft" | "approved";
  caption: string; sample: string | null; job?: Job | null;
}
export interface Take { name: string; url: string; n: number; words: number | null; pitch_hz: number | null }
export interface SongStep {
  slug: string; title: string; lang: string; voice: string | null; bpm: number; key: string | null; line_seconds: number; bars_per_line: number;
  lyrics: string; lines: number; takes: Take[]; chosen: string | null; imported: string | null; master: string | null; vocals: string | null; voices: Voice[]; jobs: Job[];
}
export interface ExistingSong { path: string; episode: string; name: string; seconds: number; url: string }
export interface OptionSet { shot: ShotRow; current: { seed: number; url: string | null }; options: { seed: number; url: string }[]; waiting: number; jobs: Job[] }
export interface DirectorChange { id: string; why: string; fields: Partial<Record<"key" | "motion" | "feel" | "sing" | "scene" | "end" | "lines", unknown>>; before: Record<string, unknown>; image: string | null }
export interface DirectorProposal {
  ask: string; shots: string[]; reply: string; changes: DirectorChange[]; moves: { id: string; before: string | null }[];
  created: string; status: "proposed" | "applied" | "discarded" | "replaced"; errors?: string[]; remake?: string[];
}
export interface Director { proposal: DirectorProposal | null; history: DirectorProposal[]; jobs: Job[]; result?: { applied: string[]; errors: string[]; remake: string[] } }
export interface Settings { paused: boolean; work_hours: string; daytime_only: boolean; yield_to_ollama: boolean; worker: WorkerState }
export interface Health { ok: boolean; worker: WorkerState; running_job: number | null; lan_url: string | null }
export interface StudioEvent { type: string; at?: number; job?: Job; episode?: string; [k: string]: unknown }

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, { method, headers: body ? { "content-type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) {
    let detail = r.statusText;
    let locked = false;
    try { const j = await r.json(); detail = j.detail ?? detail; locked = !!j.locked; } catch { /* not JSON */ }
    if (locked) throw new Error(detail);   // a phone that hasn't scanned the link: say so plainly
    throw new Error(`${method} ${url}: ${detail}`);
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () => req<Health>("GET", "/api/health"),
  projects: () => req<Project[]>("GET", "/api/projects"),
  createProject: (name: string, languages?: string[]) => req<Project>("POST", "/api/projects", { name, languages }),
  patchProject: (id: string, body: ProjectPatch) => req<Project>("PATCH", `/api/projects/${id}`, body),
  library: () => req<Library>("GET", "/api/library"),
  episodes: () => req<EpisodeSummary[]>("GET", "/api/episodes"),
  episode: (slug: string) => req<EpisodeDetail>("GET", `/api/episodes/${slug}`),
  run: (slug: string, phase: JobKind, only?: string[], redo?: string[], all = false) => req<Job>("POST", `/api/episodes/${slug}/run`, { phase, only, redo, all }),
  upload: (slug: string) => req<UploadPack>("GET", `/api/episodes/${slug}/upload`),
  saveUpload: (slug: string, s: { thumbnail?: string; checks?: string[] }) => req<{ ok: boolean }>("PUT", `/api/episodes/${slug}/upload`, s),
  publish: (slug: string, published = true) => req<EpisodeSummary>("POST", `/api/episodes/${slug}/publish`, { published }),
  drafts: () => req<AssetDraft[]>("GET", "/api/drafts"),
  draft: (id: string) => req<AssetDraft>("GET", `/api/drafts/${id}`),
  newDraft: (b: { kind: AssetKind; name: string; description: string; person: boolean }) => req<AssetDraft>("POST", "/api/drafts", b),
  patchDraft: (id: string, b: Partial<Pick<AssetDraft, "description" | "ref" | "style" | "person">>) => req<AssetDraft>("PATCH", `/api/drafts/${id}`, b),
  moreOptions: (id: string) => req<Job>("POST", `/api/drafts/${id}/more`),
  saveAsset: (id: string, b: { candidate: string; id: string; ref?: string; style?: string; person?: boolean; keep?: string }) =>
    req<{ id: string; kind: AssetKind; file: string }>("POST", `/api/drafts/${id}/save`, b),
  discardDraft: (id: string) => req<{ ok: boolean }>("DELETE", `/api/drafts/${id}`),
  song: (slug: string) => req<SongStep>("GET", `/api/episodes/${slug}/song`),
  saveSong: (slug: string, b: { voice?: string; bpm?: number; bars_per_line?: number; lyrics?: string }) => req<SongStep>("PUT", `/api/episodes/${slug}/song`, b),
  makeTakes: (slug: string, n = 4) => req<Job>("POST", `/api/episodes/${slug}/run`, { phase: "song", n }),
  masterTake: (slug: string, take: string) => req<Job>("POST", `/api/episodes/${slug}/run`, { phase: "master", take }),
  existingSongs: () => req<ExistingSong[]>("GET", "/api/songs/existing"),
  importSong: (slug: string, path: string) => req<Job>("POST", `/api/episodes/${slug}/run`, { phase: "import", path }),
  voices: () => req<Voice[]>("GET", "/api/voices"),
  patchVoice: (id: string, b: Partial<Pick<Voice, "name" | "desc" | "caption" | "status">>) => req<Voice[]>("PATCH", `/api/voices/${id}`, b),
  lanReset: () => req<{ lan_url: string | null }>("POST", "/api/lan/reset"),
  newVoice: (b: { name: string; caption: string; desc?: string; langs?: string[] }) => req<Voice[]>("POST", "/api/voices", b),
  voiceSample: (id: string) => req<Job>("POST", `/api/voices/${id}/sample`),
  createEpisode: (body: NewEpisodeReq) => req<EpisodeSummary>("POST", "/api/episodes", body),
  shotlist: (slug: string) => req<ShotList>("GET", `/api/episodes/${slug}/shotlist`),
  saveShot: (slug: string, id: string, fields: ShotFields) => req<ShotRow>("PATCH", `/api/episodes/${slug}/shots/${id}`, { fields }),
  addShot: (slug: string, opts: { after?: string; copy_of?: string }) => req<ShotRow>("POST", `/api/episodes/${slug}/shots`, opts),
  deleteShot: (slug: string, id: string) => req<{ ok: boolean }>("DELETE", `/api/episodes/${slug}/shots/${id}`),
  moveShot: (slug: string, id: string, before: string | null) => req<{ ok: boolean }>("POST", `/api/episodes/${slug}/shots/${id}/move`, { before }),
  review: (slug: string, stage: "keys" | "clips", shot: string, decision: "approved" | "redo" | null, note = "") =>
    req<{ ok: boolean; job: Job | null }>("POST", `/api/episodes/${slug}/review`, { stage, shot, decision, note }),
  options: (slug: string, sid: string) => req<OptionSet>("GET", `/api/episodes/${slug}/shots/${sid}/options`),
  makeOptions: (slug: string, sid: string, n = 4) => req<Job>("POST", `/api/episodes/${slug}/shots/${sid}/options`, { n }),
  useOption: (slug: string, sid: string, seed: number) => req<OptionSet>("POST", `/api/episodes/${slug}/shots/${sid}/options/use`, { seed }),
  director: (slug: string) => req<Director>("GET", `/api/episodes/${slug}/director`),
  askDirector: (slug: string, ask: string, shots?: string[]) => req<Director>("POST", `/api/episodes/${slug}/director`, { ask, shots }),
  applyDirector: (slug: string) => req<Director>("POST", `/api/episodes/${slug}/director/apply`),
  discardDirector: (slug: string) => req<Director>("POST", `/api/episodes/${slug}/director/discard`),
  jobs: () => req<Job[]>("GET", "/api/jobs"),
  clearHistory: () => req<{ cleared: number }>("DELETE", "/api/jobs/history"),
  cancel: (id: number) => req<Job>("POST", `/api/jobs/${id}/cancel`),
  move: (id: number, before: number | null) => req<Job[]>("POST", `/api/jobs/${id}/move`, { before }),
  settings: () => req<Settings>("GET", "/api/settings"),
  saveSettings: (s: Partial<Settings>) => req<Settings>("PUT", "/api/settings", s),
};

// ---------------------------------------------------------------- live events (one EventSource for the app)
type Listener = (e: StudioEvent) => void;
export class EventHub {
  private listeners = new Set<Listener>();
  private es: EventSource | null = null;
  connected = false;
  start() {
    this.es = new EventSource("/api/events");
    this.es.onopen = () => { this.connected = true; };
    this.es.onerror = () => { this.connected = false; };   // EventSource reconnects by itself
    this.es.onmessage = (m) => {
      try {
        const e = JSON.parse(m.data) as StudioEvent;
        this.listeners.forEach((l) => l(e));
      } catch { /* ignore keep-alives */ }
    };
    return () => this.es?.close();
  }
  on(l: Listener) { this.listeners.add(l); return () => { this.listeners.delete(l); }; }
}
export const HubContext = createContext<EventHub | null>(null);

/** Call `fn` for live events whose type is in `types` (and, if given, for this episode only). */
export function useEvents(types: string[], fn: (e: StudioEvent) => void, episode?: string) {
  const hub = useContext(HubContext);
  const ref = useRef(fn);
  ref.current = fn;
  const key = types.join(",");
  useEffect(() => hub?.on((e) => {
    if (!key.split(",").includes(e.type)) return;
    const ep = e.episode ?? e.job?.episode;
    if (episode && ep && ep !== episode) return;
    ref.current(e);
  }), [hub, key, episode]);
}

/** Load data, reload when any of `liveTypes` events arrive (debounced). */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[], liveTypes: string[] = [], episode?: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const reload = useCallback(() => load().then((d) => { setData(d); setError(null); }).catch((e: Error) => setError(e.message)), deps);
  useEffect(() => { reload(); }, [reload]);
  useEvents(liveTypes, () => { window.clearTimeout(timer.current); timer.current = window.setTimeout(reload, 250); }, episode);
  return { data, error, reload };
}

export const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
export const ago = (t: number | null) => {
  if (!t) return "";
  const s = Date.now() / 1000 - t;
  return s < 60 ? "just now" : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86400 ? `${Math.floor(s / 3600)} h ago` : `${Math.floor(s / 86400)} d ago`;
};
export const jobLabel: Record<JobKind, string> = {
  keys: "Keyframes", clips: "Clips", assemble: "Assemble", package: "1080p upload file",
  draft: "Drafting shots", upload: "Upload text + thumbnails", asset: "Drawing options",
  song: "Song takes", master: "Mastering the song", import: "Fitting the song to shots", voice: "Voice samples",
  options: "Keyframe options", director: "Director",
};
export const workerText: Record<WorkerState, string> = {
  idle: "GPU idle", running: "GPU busy", paused: "Queue paused",
  waiting_hours: "Waiting for work hours", waiting_memory: "Waiting for memory (Ollama)",
};
