// Shared filter bar: a search box, chip rows (single or multi choice) and a sort menu.
// Used by Episodes, the Library and the Storyboard so every growing list filters the same way.
import { useEffect, useState } from "react";

export interface ChipOption { value: string; label: string; n?: number; image?: string | null }

export function SearchBox({ value, onChange, placeholder, id }: { value: string; onChange: (v: string) => void; placeholder: string; id: string }) {
  return (
    <div className="search">
      <label htmlFor={id} className="visually-hidden">{placeholder}</label>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
      <input id={id} className="input" type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} autoComplete="off" />
    </div>
  );
}

/** One row of chips. `value` "" = "All". */
export function ChipRow({ label, options, value, onChange, all = "All" }: {
  label: string; options: ChipOption[]; value: string; onChange: (v: string) => void; all?: string | null;
}) {
  return (
    <div className="chips" role="group" aria-label={label}>
      {all !== null && <button className="chip-btn" aria-pressed={value === ""} onClick={() => onChange("")}>{all}</button>}
      {options.map((o) => (
        <button key={o.value} className="chip-btn" aria-pressed={value === o.value} onClick={() => onChange(value === o.value ? "" : o.value)}>
          {o.image && <img src={o.image} alt="" />}{o.label}{o.n !== undefined && <span className="n">{o.n}</span>}
        </button>
      ))}
    </div>
  );
}

export function SortSelect<T extends string>({ value, onChange, options, id }: { value: T; onChange: (v: T) => void; options: [T, string][]; id: string }) {
  return (
    <>
      <label htmlFor={id} className="visually-hidden">Sort</label>
      <select id={id} className="select small-select" value={value} onChange={(e) => onChange(e.target.value as T)}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </>
  );
}

/** Filter state that survives reloads (per list), e.g. useSaved("library.kind", ""). */
export function useSaved<T>(key: string, initial: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => {
    try { const raw = localStorage.getItem("rw." + key); return raw === null ? initial : (JSON.parse(raw) as T); } catch { return initial; }
  });
  useEffect(() => { try { localStorage.setItem("rw." + key, JSON.stringify(v)); } catch { /* private mode */ } }, [key, v]);
  return [v, setV];
}

export const matches = (q: string, ...fields: (string | null | undefined)[]) => {
  const t = q.trim().toLowerCase();
  return !t || fields.some((f) => (f ?? "").toLowerCase().includes(t));
};

export function ResultLine({ shown, total, what, onClear }: { shown: number; total: number; what: string; onClear?: () => void }) {
  if (shown === total) return null;
  return (
    <div className="row small muted" style={{ gap: 8 }}>
      Showing {shown} of {total} {what}
      {onClear && <button className="btn-quiet" style={{ color: "var(--go-text)", minWidth: 0, padding: "4px 6px" }} onClick={onClear}>Clear filters</button>}
    </div>
  );
}
