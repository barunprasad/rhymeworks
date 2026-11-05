import type { ReactNode } from "react";
import type { JobStatus, ReviewStatus } from "../api";

export function Logo({ size = 32 }: { size?: number }) {
  // The Rhymeworks mark: a camera with a gramophone horn, music pouring out (public/logo-128.png).
  return <img src="/logo-128.png" width={size} height={size} alt="" aria-hidden="true" style={{ display: "block", borderRadius: size * 0.19 }} />;
}

const reviewPill: Record<ReviewStatus, [string, string]> = {
  missing: ["Not made", "idle"], to_review: ["To review", "gate"], approved: ["Approved", "go"], redo: ["Redo queued", "auto"],
};
export const ReviewPill = ({ s }: { s: ReviewStatus }) => <span className={`pill ${reviewPill[s][1]}`}>{reviewPill[s][0]}</span>;

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
