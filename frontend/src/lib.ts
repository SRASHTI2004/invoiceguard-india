import { useCallback, useEffect, useState } from "react";

/* ---- hash router: #/invoices, #/invoices/7 (drawer open), #/approvals ... ---------------------------------------- */
export type Page = "dashboard" | "invoices" | "approvals" | "agent" | "suppliers" | "audit";
export const PAGES: Page[] = ["dashboard", "invoices", "approvals", "agent", "suppliers", "audit"];

export interface Route {
  page: Page;
  invoiceId: number | null;
}

export const parseHash = (hash: string): Route => {
  const [page, id] = hash.replace(/^#\/?/, "").split("/");
  const known = PAGES.includes(page as Page) ? (page as Page) : "dashboard";
  const n = Number(id);
  return { page: known, invoiceId: known === "invoices" && Number.isInteger(n) && n > 0 ? n : null };
};

export const hrefFor = (page: Page, invoiceId?: number | null) => `#/${page}${invoiceId ? `/${invoiceId}` : ""}`;

export function useRoute(): [Route, (page: Page, invoiceId?: number | null) => void] {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const on = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const go = useCallback((page: Page, invoiceId?: number | null) => {
    window.location.hash = hrefFor(page, invoiceId);
  }, []);
  return [route, go];
}

/* ---- theme: light by default, optional dark, remembered when storage is available ------------------------------- */
export type Theme = "light" | "dark";

const readTheme = (): Theme => {
  try {
    return window.localStorage.getItem("ig-theme") === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
};

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(readTheme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem("ig-theme", theme);
    } catch {
      /* private mode: the choice just is not remembered */
    }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "light" ? "dark" : "light"))];
}

/** "2026-11-04" -> "4 Nov 2026" (Indian day-first style). Anything unparseable is shown as is. */
export const fmtDate = (iso: string | null | undefined) => {
  if (!iso) return "?";
  const d = new Date(iso + "T00:00:00");
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
};

/** SQLite timestamps are UTC ("2026-11-24 11:43:22"). Show them in IST: "24 Nov 2026, 5:13 pm IST". */
export const fmtDateTime = (utc: string | null | undefined) => {
  if (!utc) return "";
  const d = new Date(utc.replace(" ", "T") + "Z");
  if (Number.isNaN(d.getTime())) return utc;
  const s = d.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true });
  return `${s.replace(/am/i, "am").replace(/pm/i, "pm")} IST`;
};

/* ---- small helpers ----------------------------------------------------------------------------------------------- */
export const failedChecks = (inv: { gst_report?: { ok: boolean }[] }) => (inv.gst_report ?? []).filter((c) => !c.ok).length;

export function useMedia(query: string): boolean {
  const [on, setOn] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const m = window.matchMedia(query);
    const h = () => setOn(m.matches);
    m.addEventListener("change", h);
    return () => m.removeEventListener("change", h);
  }, [query]);
  return on;
}
