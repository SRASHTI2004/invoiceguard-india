import { Bot, Building2, ClipboardCheck, Database, FileText, FlaskConical, LayoutDashboard, Moon, ScrollText, Sun, type LucideIcon } from "lucide-react";
import { ReactNode } from "react";
import { AppConfig } from "./api";
import { hrefFor, Page, Theme } from "./lib";
import { Spinner } from "./ui";

const NAV: { page: Page; label: string; Icon: LucideIcon }[] = [
  { page: "dashboard", label: "Dashboard", Icon: LayoutDashboard },
  { page: "invoices", label: "Invoices", Icon: FileText },
  { page: "approvals", label: "Approvals", Icon: ClipboardCheck },
  { page: "agent", label: "AP Agent", Icon: Bot },
  { page: "suppliers", label: "Suppliers", Icon: Building2 },
  { page: "audit", label: "Audit log", Icon: ScrollText },
  { page: "evaluation", label: "How well it works", Icon: FlaskConical },
];

export function Logo({ size = 40 }: { size?: number }) {
  return (
    <span className="logo" style={{ width: size, height: size }} aria-hidden="true">
      <svg width={size * 0.55} height={size * 0.55} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2.5 4 5.5v6c0 5 3.4 8.6 8 10 4.6-1.4 8-5 8-10v-6l-8-3Z" />
        <path d="M9 8.5h6M9 12h6M11.5 12c2.5 0 3.5 1.6 3.5 3L9 16" />
      </svg>
    </span>
  );
}

export function ThemeToggle({ theme, toggle }: { theme: Theme; toggle: () => void }) {
  return (
    <button className="icon-btn" onClick={toggle} aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}>
      {theme === "light" ? <Moon size={18} aria-hidden="true" /> : <Sun size={18} aria-hidden="true" />}
    </button>
  );
}

export default function Shell({ page, cfg, heldCount, theme, toggleTheme, onLoadDemo, demoBusy, children }: {
  page: Page; cfg: AppConfig | null; heldCount: number; theme: Theme; toggleTheme: () => void;
  onLoadDemo: () => void; demoBusy: boolean; children: ReactNode;
}) {
  return (
    <div className="shell">
      <a className="skip" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>Skip to content</a>
      <aside className="sidebar">
        <a className="brand" href={hrefFor("dashboard")} aria-label="InvoiceGuard India home">
          <Logo />
          <span className="brand-name">InvoiceGuard<span>India</span></span>
        </a>
        <nav className="nav" aria-label="Main">
          {NAV.map(({ page: p, label, Icon }) => (
            <a key={p} href={hrefFor(p)} aria-current={page === p ? "page" : undefined} title={label}>
              <Icon size={18} aria-hidden="true" />
              <span className="lbl">{label}</span>
              {p === "approvals" && heldCount > 0 && (<><span className="count" aria-label={`${heldCount} waiting`}>{heldCount}</span><span className="dot" aria-hidden="true" /></>)}
            </a>
          ))}
        </nav>
        <div className="side-foot">
          <span className="sandbox" title="Payouts are simulated. No real money moves.">Simulated sandbox</span>
          <span>All companies, GSTINs and accounts are fictional.</span>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="biz">
            <div className="biz-name">{cfg?.buyer_name ?? "Your business"}</div>
            <div className="biz-sub">GSTIN <code>{cfg?.buyer_gstin ?? "…"}</code></div>
          </div>
          <ThemeToggle theme={theme} toggle={toggleTheme} />
          <button className="btn" onClick={onLoadDemo} disabled={demoBusy}>
            {demoBusy ? <Spinner /> : <Database size={16} aria-hidden="true" />}
            <span className="lbl">{demoBusy ? "Loading…" : "Load demo data"}</span>
            <span className="sr-only">{demoBusy ? "" : "Load demo data"}</span>
          </button>
        </header>
        <main id="main" className="content" tabIndex={-1}>{children}</main>
      </div>
      <nav className="tabbar" aria-label="Main">
        {NAV.filter((n) => n.page !== "evaluation").map(({ page: p, label, Icon }) => (
          <a key={p} href={hrefFor(p)} aria-current={page === p ? "page" : undefined}>
            <Icon size={20} aria-hidden="true" />
            {label.replace("AP ", "").replace(" log", "")}
            {p === "approvals" && heldCount > 0 && <span className="dot" aria-label={`${heldCount} waiting`} />}
          </a>
        ))}
      </nav>
    </div>
  );
}
