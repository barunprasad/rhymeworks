// Tiny hash router: #/, #/library/cast, #/episodes/<slug>, #/episodes/<slug>/review/keys, #/queue
import { useEffect, useState } from "react";

export function useRoute(): string[] {
  const parse = () => window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  const [parts, setParts] = useState(parse);
  useEffect(() => {
    const on = () => { setParts(parse()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return parts;
}

export const href = (...parts: string[]) => "#/" + parts.map(encodeURIComponent).join("/");
export const go = (...parts: string[]) => { window.location.hash = href(...parts); };
