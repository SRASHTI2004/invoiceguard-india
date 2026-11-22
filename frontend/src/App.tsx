import { useCallback, useEffect, useState } from "react";
import { api, AppConfig, Invoice, Summary } from "./api";
import { Spinner } from "./components";
import AgentPage from "./pages/Agent";
import ApprovalsPage from "./pages/Approvals";
import AuditPage from "./pages/Audit";
import InvoicesPage from "./pages/Invoices";
import SuppliersPage from "./pages/Suppliers";
import SummaryCards from "./pages/SummaryCards";

type Tab = "invoices" | "approvals" | "agent" | "suppliers" | "audit";

const STEPS: [string, string][] = [
  ["Read", "AI reads the invoice PDF"],
  ["GST checks", "GSTIN, tax type, arithmetic"],
  ["AI review", "scams and hidden instructions"],
  ["Decide", "pay, hold or block"],
  ["Pay", "saved UPI ID or bank account"],
];

export default function App() {
  const fromHash = window.location.hash.slice(1) as Tab;  // e.g. /#suppliers opens that tab
  const [tab, setTab] = useState<Tab>(["invoices", "approvals", "agent", "suppliers", "audit"].includes(fromHash) ? fromHash : "invoices");
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [cfg, setCfg] = useState<AppConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [demoBusy, setDemoBusy] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [inv, sum] = await Promise.all([api.invoices(), api.summary()]);
      setInvoices(inv);
      setSummary(sum);
      setError(null);
      setLoaded(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    reload();
    api.config().then(setCfg).catch(() => undefined);
  }, [reload]);

  const runDemo = async () => {
    setDemoBusy(true);
    setDemoError(null);
    try {
      await api.runSamples();
      setTab("invoices");
    } catch (e) {
      setDemoError((e as Error).message);
    }
    setDemoBusy(false);
    await reload();
  };

  const held = invoices.filter((i) => i.status === "HELD");
  const unfunded = held.filter((i) => i.reason?.includes("insufficient funds"));
  const empty = loaded && invoices.length === 0;
  const tabs: [Tab, string][] = [
    ["invoices", "Invoices"],
    ["approvals", `Approvals${held.length ? ` (${held.length})` : ""}`],
    ["agent", "AP agent"],
    ["suppliers", "Suppliers"],
    ["audit", "Audit log"],
  ];

  return (
    <div className="app">
      <div className="tricolour" aria-hidden="true" />
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden="true">₹</span>
          <div>
            <h1>InvoiceGuard <span className="india">India</span></h1>
            {cfg && <div className="buyer">{cfg.buyer_name} · GSTIN <code>{cfg.buyer_gstin}</code></div>}
          </div>
        </div>
        <span className="sandbox-tag big-tag" title="Payouts are simulated. No real money moves.">SIMULATED SANDBOX · no real money</span>
      </header>

      {empty ? (
        <section className="hero">
          <h2>Stop fake and wrong GST invoices before you pay them.</h2>
          <p>
            InvoiceGuard reads each supplier invoice, verifies the GSTIN, tax type and GST arithmetic in code, then pays or holds it.
          </p>
          <button className="primary huge" disabled={demoBusy} onClick={runDemo}>
            {demoBusy ? <Spinner label="Checking 13 invoices…" /> : "Try with demo data"}
          </button>
          <div className="hero-sub">13 sample invoices: 5 valid, 7 fraud or error cases, 1 partial delivery. Takes a few seconds.</div>
          {demoError && <div className="banner error">Demo failed: {demoError}</div>}
          <ol className="steps-strip" aria-label="How it works">
            {STEPS.map(([title, sub], i) => (
              <li key={title}>
                <span className="step-n">{i + 1}</span>
                <strong>{title}</strong>
                <span>{sub}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : (
        loaded && (
          <div className="slim">
            <span>Demo data is loaded. Open an invoice&apos;s GST checks below, or approve the held ones.</span>
            <button disabled={demoBusy} onClick={runDemo}>
              {demoBusy ? <Spinner label="Reloading…" /> : "Reload demo data"}
            </button>
          </div>
        )
      )}
      {demoError && !empty && <div className="banner error">Demo failed: {demoError}</div>}
      {!loaded && !error && <p className="muted"><Spinner label="Loading… the free server can take up to a minute to wake up." /></p>}
      {error && <div className="banner error">Could not reach the server: {error}</div>}

      {!empty && loaded && (
        <>
          <SummaryCards summary={summary} invoices={invoices} />
          <nav aria-label="Sections">
            {tabs.map(([key, label]) => (
              <button key={key} className={tab === key ? "tab active" : "tab"} onClick={() => setTab(key)}>
                {label}
              </button>
            ))}
          </nav>
          {unfunded.length > 0 && (
            <div className="banner funds" role="alert">
              <strong>{unfunded.length} invoice{unfunded.length > 1 ? "s" : ""} could not be paid: the payout wallet has insufficient funds.</strong>
              <div>
                Nothing is lost and each invoice already passed every check. Top up the wallet, then open{" "}
                <button className="link" onClick={() => setTab("approvals")}>Approvals</button> and click Approve.
              </div>
            </div>
          )}
          {tab === "invoices" && <InvoicesPage invoices={invoices} reload={reload} />}
          {tab === "approvals" && <ApprovalsPage held={held} reload={reload} />}
          {tab === "agent" && <AgentPage reload={reload} />}
          {tab === "suppliers" && <SuppliersPage />}
          {tab === "audit" && <AuditPage invoices={invoices} />}
        </>
      )}
      <footer className="foot">
        Prototype for Prasunex Innovathon. All companies, GSTINs, accounts and UPI IDs are fictional.
      </footer>
    </div>
  );
}
