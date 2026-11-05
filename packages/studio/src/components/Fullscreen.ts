// Full screen for a player box: the browser's real full screen where it is allowed (desktop, Android, iPad),
// otherwise ("page") a fixed layer that covers the whole screen (iPhone Safari only allows <video> to go full screen).
import { useCallback, useEffect, useRef, useState } from "react";

type Mode = false | "native" | "page";
/* eslint-disable @typescript-eslint/no-explicit-any */
const doc = document as any;
const fsElement = () => doc.fullscreenElement ?? doc.webkitFullscreenElement ?? null;

export function useFullscreen<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [full, setFull] = useState<Mode>(false);

  useEffect(() => {   // Esc / the browser's own exit
    const f = () => setFull((x) => (fsElement() ? "native" : x === "native" ? false : x));
    document.addEventListener("fullscreenchange", f);
    document.addEventListener("webkitfullscreenchange", f);
    return () => { document.removeEventListener("fullscreenchange", f); document.removeEventListener("webkitfullscreenchange", f); };
  }, []);
  useEffect(() => {   // the page fallback: Esc closes it, the page underneath does not scroll
    if (full !== "page") return;
    const f = (e: KeyboardEvent) => { if (e.key === "Escape") setFull(false); };
    window.addEventListener("keydown", f);
    const was = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", f); document.body.style.overflow = was; };
  }, [full]);

  const enter = useCallback(async () => {
    const el = ref.current as any;
    if (!el) return;
    const req = el.requestFullscreen ?? el.webkitRequestFullscreen;
    if (req && (doc.fullscreenEnabled ?? doc.webkitFullscreenEnabled)) {
      try {
        await req.call(el);
        setFull("native");
        (screen.orientation as any)?.lock?.("landscape")?.catch?.(() => {});   // phones: turn sideways where allowed
        return;
      } catch { /* refused: use the page layer */ }
    }
    setFull("page");
  }, []);
  const exit = useCallback(() => {
    if (fsElement()) (doc.exitFullscreen ?? doc.webkitExitFullscreen)?.call(doc);
    setFull(false);
  }, []);
  return { ref, full, enter, exit, toggle: () => (full ? exit() : enter()) };
}

/** True after `ms` without pointer movement while `active` (YouTube-style hiding controls). poke() shows them again. */
export function useIdle(active: boolean, ms = 2500) {
  const [idle, setIdle] = useState(false);
  const timer = useRef<number>(0);
  const poke = useCallback(() => {
    setIdle(false);
    window.clearTimeout(timer.current);
    if (active) timer.current = window.setTimeout(() => setIdle(true), ms);
  }, [active, ms]);
  useEffect(() => { poke(); return () => window.clearTimeout(timer.current); }, [poke]);
  return { idle: active && idle, poke };
}
