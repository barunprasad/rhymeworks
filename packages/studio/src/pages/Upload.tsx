import { useState } from "react";
import { api, useLoad, type UploadPack } from "../api";
import { go, href } from "../router";
import { ErrorNote } from "../components/bits";
import { useIsDesktop } from "../components/MobileBars";
import { JobBar } from "./Episode";

/** Copy that also works over plain http on the Wi-Fi (navigator.clipboard needs a secure page). */
async function copyText(text: string) {
  try {
    if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true; }
  } catch { /* fall through */ }
  const ta = document.createElement("textarea");
  ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select();
  const ok = document.execCommand("copy");
  ta.remove();
  return ok;
}

/** Upload pack (mock-up P10): pick a thumbnail, copy title/description/tags, tick the YouTube checklist, mark as published. */
export function UploadPage({ slug }: { slug: string }) {
  const up = useLoad(() => api.upload(slug), [slug], ["spec", "job", "output"], slug);
  const desktop = useIsDesktop();
  const [copied, setCopied] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pick, setPick] = useState<"original" | "intro" | null>(null);
  const d = up.data;
  if (!d) return <ErrorNote msg={up.error} />;
  const variant = pick ?? (d.videos.some((v) => v.variant === "intro") ? "intro" : "original");
  const shown = d.videos.find((v) => v.variant === variant);
  const description = shown?.description ?? d.text?.description ?? "";
  const introName = d.intro?.project ? `${d.intro.project} intro` : "channel intro";

  const act = async (f: () => Promise<unknown>) => {
    setBusy(true); setErr(null);
    try { await f(); up.reload(); } catch (e) { setErr((e as Error).message.replace(/^\w+ \S+: /, "")); } finally { setBusy(false); }
  };
  const copy = async (what: string, text: string) => { if (await copyText(text)) { setCopied(what); window.setTimeout(() => setCopied(null), 1800); } };
  const toggle = (id: string) => act(() => api.saveUpload(slug, { checks: d.checks.filter((c) => (c.id === id ? !c.on : c.on)).map((c) => c.id) }));
  const done = d.checks.filter((c) => c.on).length;
  const all = done === d.checks.length;
  const working = d.jobs.some((j) => j.kind === "upload" || j.kind === "package");
  const packing = d.jobs.some((j) => j.kind === "package");
  const missing = [!d.video && "the 1080p file", !d.text && "the upload text", !d.thumbs.length && "thumbnails"].filter(Boolean) as string[];

  const makeAll = () => act(async () => {
    if (!d.video) await api.pack(slug, false);
    if (!d.text || !d.thumbs.length) await api.run(slug, "upload");
  });

  const cta = d.published
    ? <div className="row between" style={{ flex: 1, flexWrap: "nowrap" }}>
        <span className="pill go" style={{ fontSize: 14, padding: "6px 12px" }}>✓ Published</span>
        <button className="btn btn-quiet" disabled={busy} onClick={() => act(() => api.publish(slug, false))}>Mark as not published</button>
      </div>
    : <button className="btn btn-go" style={{ flex: 1, justifyContent: "center" }} disabled={!all || busy || !d.video}
        onClick={() => act(async () => { await api.publish(slug, true); go("episodes", slug); })}>
        {!d.video ? "Make the upload file first" : all ? "Mark as published" : `Tick the checklist to finish (${done}/${d.checks.length})`}
      </button>;

  return (
    <>
      <div className="crumbs only-desktop"><a href={href("episodes", slug)}>{d.title}</a> / Upload pack</div>
      <header className="row between">
        <div>
          <h1 className="only-desktop">Upload pack</h1>
          <p className="muted small" style={{ margin: "4px 0 0" }}>Upload by hand in YouTube Studio (or the YouTube Studio app on your phone). Everything to paste is here.</p>
        </div>
        {desktop && <div className="row">{cta}</div>}
      </header>
      <ErrorNote msg={err ?? up.error} />
      {d.jobs.map((j) => <JobBar key={j.id} j={j} />)}

      {missing.length > 0 && !working && (
        <div className="card pad col" style={{ gap: 10, borderColor: "var(--gate-line)" }}>
          <b>Still to make: {missing.join(", ")}</b>
          <span className="muted small" style={{ lineHeight: 1.45 }}>
            {d.episode_ready ? "The 1080p file is the episode as it is (CPU, a few minutes); a version with your channel intro is one tap below. The text and thumbnails come from the local writer model and your keyframes (about a minute)."
              : "Assemble the episode first (episode page, step 05)."}
          </span>
          <button className="btn btn-go" style={{ alignSelf: "flex-start" }} disabled={busy || !d.episode_ready} onClick={makeAll}>Make {missing.join(" + ")}</button>
        </div>
      )}

      <div className="split">
        <div className="grow">
          {(d.video || d.intro) && d.episode_ready && (
            <section className="col" aria-labelledby="vid">
              <h2 id="vid" className="section-title">VIDEO FILE</h2>
              <div className="chips" role="tablist" aria-labelledby="vid">
                <button role="tab" className="chip-btn" aria-selected={variant === "original"} aria-pressed={variant === "original"} onClick={() => setPick("original")}>Original</button>
                {(d.intro || d.videos.some((v) => v.variant === "intro")) && (
                  <button role="tab" className="chip-btn" aria-selected={variant === "intro"} aria-pressed={variant === "intro"} onClick={() => setPick("intro")}>With {introName}</button>
                )}
              </div>
              {shown ? (<>
                <video key={shown.url} src={shown.url} controls playsInline preload="metadata" className="thumb" />
                <div className="row between small">
                  <span className="mono faint" style={{ overflowWrap: "anywhere" }}>{shown.name} · {shown.mb} MB</span>
                  <a className="btn" href={shown.url} download={shown.name}>Download</a>
                </div>
                {shown.old && (
                  <div className="row between small" style={{ color: "var(--gate-text)" }}>
                    <span>The episode changed since this file was made.</span>
                    <button className="btn" disabled={busy || packing} onClick={() => act(() => api.pack(slug, variant === "intro"))}>Make it again</button>
                  </div>
                )}
              </>) : (
                <div className="card pad col" style={{ gap: 8 }}>
                  <span className="muted small" style={{ lineHeight: 1.45 }}>
                    {variant === "intro"
                      ? `The same 1080p file with the ${introName} (${d.intro?.name}) at the start, for YouTube. The original stays as it is. CPU, a few minutes.`
                      : "The episode as it is, at 1080p. CPU, a few minutes."}
                  </span>
                  <button className="btn btn-go" style={{ alignSelf: "flex-start" }} disabled={busy || packing || (variant === "intro" && !d.intro)}
                    onClick={() => act(() => api.pack(slug, variant === "intro"))}>
                    {packing ? "Making…" : variant === "intro" ? `Make the version with the ${introName}` : "Make the 1080p file"}
                  </button>
                </div>
              )}
              {!d.intro && <span className="faint small">No channel intro yet: pick a clip in Project settings → Channel intro to get a version that opens with it.</span>}
            </section>
          )}

          {d.thumbs.length > 0 && (
            <section className="col" aria-labelledby="th">
              <div className="row between">
                <h2 id="th" className="section-title">THUMBNAIL · PICK ONE</h2>
                <button className="btn btn-quiet" style={{ color: "var(--go)" }} disabled={busy || working} onClick={() => act(() => api.run(slug, "upload", undefined, undefined, true))}>Remake</button>
              </div>
              <div className="scroller" role="radiogroup" aria-labelledby="th" style={{ gap: 10 }}>
                {d.thumbs.map((t) => {
                  const on = d.thumbnail === t.name;
                  return (
                    <button key={t.name} role="radio" aria-checked={on} onClick={() => act(() => api.saveUpload(slug, { thumbnail: t.name }))}
                      style={{ width: desktop ? 300 : 248, padding: 0, borderRadius: 12, overflow: "hidden", cursor: "pointer", background: "var(--panel)", textAlign: "left",
                        border: on ? "2px solid var(--go)" : "1px solid var(--line)", color: "var(--text-2)" }}>
                      <img src={t.url} alt={`Thumbnail ${t.name}`} style={{ display: "block", width: "100%", aspectRatio: "16/9", objectFit: "cover" }} />
                      <span className="row between" style={{ padding: "6px 10px", fontSize: 12.5 }}>
                        <span className="mono">{t.name}</span>{on && <span style={{ color: "var(--go-text)", fontWeight: 700 }}>Chosen</span>}
                      </span>
                    </button>
                  );
                })}
              </div>
              {d.thumbnail && <a className="small" href={d.thumbs.find((t) => t.name === d.thumbnail)?.url} download={d.thumbnail}>Download the chosen thumbnail</a>}
            </section>
          )}

          {d.text && (
            <>
              <CopyBlock label="TITLE" text={d.text.title} copied={copied === "title"} onCopy={() => copy("title", d.text!.title)} lang={d.lang} />
              <CopyBlock label={d.videos.length > 1 ? `DESCRIPTION · CHAPTERS FOR ${variant === "intro" ? "THE INTRO VERSION" : "THE ORIGINAL"}` : "DESCRIPTION"}
                text={description} copied={copied === "desc"} onCopy={() => copy("desc", description)} long lang={d.lang} />
              <CopyBlock label="TAGS" text={d.text.tags} copied={copied === "tags"} onCopy={() => copy("tags", d.text!.tags)} lang={d.lang} />
            </>
          )}
        </div>

        <aside className={desktop ? "side panel" : "col"} aria-labelledby="chk" style={desktop ? { position: "sticky", top: 24 } : undefined}>
          <h2 id="chk" className="section-title">YOUTUBE CHECKLIST · {done} OF {d.checks.length}</h2>
          <Checklist d={d} busy={busy} toggle={toggle} />
          {d.published && <p className="faint small" style={{ margin: 0 }}>This episode is marked as published, so nothing in it waits for review any more.</p>}
        </aside>
      </div>
      {!desktop && <div className="actionbar">{cta}</div>}
    </>
  );
}

function Checklist({ d, busy, toggle }: { d: UploadPack; busy: boolean; toggle: (id: string) => void }) {
  return (
    <div className="card" style={{ overflow: "hidden" }}>
      {d.checks.map((c, i) => (
        <label key={c.id} className="row" style={{ alignItems: "flex-start", gap: 12, padding: "12px 14px", minHeight: 52, cursor: "pointer", flexWrap: "nowrap",
          borderTop: i ? "1px solid var(--line)" : undefined }}>
          <input type="checkbox" checked={c.on} disabled={busy} onChange={() => toggle(c.id)} style={{ width: 22, height: 22, marginTop: 1, accentColor: "var(--go)", flex: "none" }} />
          <span className="col" style={{ gap: 2 }}>
            <span style={{ fontWeight: 500, textDecoration: c.on ? "none" : undefined }}>{c.title}</span>
            <span className="faint small">{c.detail}</span>
          </span>
        </label>
      ))}
    </div>
  );
}

function CopyBlock({ label, text, copied, onCopy, long, lang }: { label: string; text: string; copied: boolean; onCopy: () => void; long?: boolean; lang: string }) {
  const [open, setOpen] = useState(!long);
  return (
    <section className="card pad col" style={{ gap: 8 }}>
      <div className="row between">
        <h2 className="section-title" style={{ margin: 0 }}>{label}{label === "TITLE" ? ` · ${text.length}/100` : ""}</h2>
        <button className={`btn ${copied ? "btn-soft-go" : ""}`} onClick={onCopy} aria-live="polite">{copied ? "Copied" : "Copy"}</button>
      </div>
      <div lang={lang} style={{ whiteSpace: "pre-wrap", lineHeight: 1.5, color: "var(--text-2)", overflowWrap: "anywhere", maxHeight: open ? undefined : 132, overflow: "hidden",
        fontWeight: label === "TITLE" ? 700 : undefined, fontSize: label === "TAGS" ? 13.5 : undefined }}>{text}</div>
      {long && <button className="btn btn-quiet" style={{ alignSelf: "flex-start", color: "var(--go)", padding: 0 }} onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Show less" : "Show all"}</button>}
    </section>
  );
}
