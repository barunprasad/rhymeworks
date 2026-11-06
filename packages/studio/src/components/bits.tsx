import type { ReactNode } from "react";
import type { AutoCheck, JobStatus, ReviewStatus } from "../api";

export function Logo({ size = 32 }: { size?: number }) {
  // The Rhymeworks mark: a camera with a gramophone horn, music pouring out (public/logo-128.png).
  return <img src="/logo-128.png" width={size} height={size} alt="" aria-hidden="true" style={{ display: "block", borderRadius: size * 0.19 }} />;
}

const reviewPill: Record<ReviewStatus, [string, string]> = {
  missing: ["Not made", "idle"], to_review: ["To review", "gate"], approved: ["Approved", "go"], redo: ["Redo queued", "auto"],
};
export const ReviewPill = ({ s }: { s: ReviewStatus }) => <span className={`pill ${reviewPill[s][1]}`}>{reviewPill[s][0]}</span>;

/** The auto-check result as one short label: "Auto-check ✓", "Auto-check: look at this", "Auto-checking…". */
export function checkLabel(c: AutoCheck | undefined, stage: "keys" | "clips"): [string, string] | null {
  if (!c || c.state === "none") return null;
  if (c.state === "flag") return [`⚠ Look at this${c.flags.length > 1 ? ` (${c.flags.length})` : ""}`, "gate"];
  if (c.state === "ok") return ["✓ Auto-check passed", "check-ok"];
  if (c.state === "checking") return ["Auto-checking…", "idle"];
  return [stage === "clips" && c.passed.length ? "✓ Moves · pictures not checked" : "Not auto-checked", "idle"];
}
export function CheckPill({ c, stage }: { c?: AutoCheck; stage: "keys" | "clips" }) {
  const l = checkLabel(c, stage);
  return l ? <span className={`pill ${l[1]}`} title={c?.flags.join("\n") || c?.passed.join(" · ")}>{l[0]}</span> : null;
}

/** What the auto-check found for the selected shot, in plain words. */
export function CheckDetails({ c, stage, onAgain }: { c?: AutoCheck; stage: "keys" | "clips"; onAgain?: () => void }) {
  if (!c || c.state === "none") return null;
  return (
    <section className="autocheck" aria-label="Auto-check">
      <div className="row between"><span className="label">AUTO-CHECK</span>{onAgain && <button className="btn btn-quiet small" onClick={onAgain}>Check again</button>}</div>
      <ul>
        {c.flags.map((f) => <li key={f} className="ac-flag"><span aria-hidden="true">⚠</span>{f}</li>)}
        {c.passed.map((f) => <li key={f} className="ac-pass"><span aria-hidden="true">✓</span>{f}</li>)}
        {c.state === "checking" && <li className="ac-wait"><span aria-hidden="true">…</span>Checking the pictures (queued)</li>}
        {c.state === "partial" && <li className="ac-wait"><span aria-hidden="true">–</span>Pictures not checked yet</li>}
      </ul>
      <p className="faint small" style={{ margin: 0 }}>
        {stage === "clips" ? "Movement is checked instantly; pictures (who appears, extra hands, melted faces) at five moments from start to end." : "Checks who appears and how often, extra hands and melted faces."} Hints only: you still decide.
      </p>
    </section>
  );
}

const jobPill: Record<JobStatus, [string, string]> = {
  queued: ["Queued", "idle"], running: ["Running", "go"], done: ["Done", "go"], failed: ["Failed", "bad"], cancelled: ["Cancelled", "idle"],
};
export const JobPill = ({ s }: { s: JobStatus }) => <span className={`pill ${jobPill[s][1]}`}>{jobPill[s][0]}</span>;

export function Steps({ done, now, total = 8 }: { done: number; now?: boolean; total?: number }) {
  return (
    <div className="steps" role="img" aria-label={`Step ${Math.min(done + 1, total)} of ${total}`}>
      {Array.from({ length: total }, (_, i) => <span key={i} className={i < done ? "done" : i === done && now ? "now" : ""} />)}
    </div>
  );
}

export const Empty = ({ children }: { children: ReactNode }) => <div className="empty">{children}</div>;
export const ErrorNote = ({ msg }: { msg: string | null }) => (msg ? <div className="notice" role="alert">{msg}</div> : null);
