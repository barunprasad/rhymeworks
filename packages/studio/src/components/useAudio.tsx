// One shared audio player for a page of takes/samples: tapping another one stops the first.
import { useEffect, useRef, useState } from "react";

export function useAudio() {
  const el = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    const a = new Audio();
    a.preload = "none";
    const tick = () => setProgress(a.duration ? a.currentTime / a.duration : 0);
    const end = () => { setPlaying(null); setProgress(0); };
    a.addEventListener("timeupdate", tick);
    a.addEventListener("ended", end);
    el.current = a;
    return () => { a.pause(); a.removeEventListener("timeupdate", tick); a.removeEventListener("ended", end); };
  }, []);
  const toggle = (url: string) => {
    const a = el.current;
    if (!a) return;
    if (playing === url) { a.pause(); setPlaying(null); return; }
    a.src = url;
    setProgress(0);
    a.play().then(() => setPlaying(url)).catch(() => setPlaying(null));
  };
  const stop = () => { el.current?.pause(); setPlaying(null); };
  return { playing, progress, toggle, stop };
}

export const PlayIcon = ({ on }: { on: boolean }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    {on ? <path d="M6 5h4v14H6zM14 5h4v14h-4z" /> : <path d="M7 4v16l13-8z" />}
  </svg>
);
