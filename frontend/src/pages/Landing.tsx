import { FileSearch, Landmark, ShieldCheck, Sparkles, Zap } from "lucide-react";
import { Logo, ThemeToggle } from "../Shell";
import { Theme } from "../lib";
import { Spinner, StatusBadge } from "../ui";

const VALUES: [typeof ShieldCheck, string, string][] = [
  [FileSearch, "GST rules checked in code", "GSTIN check character, CGST/SGST vs IGST, HSN/SAC and the arithmetic, on every invoice."],
  [ShieldCheck, "Fraud stopped, not just flagged", "Duplicates, changed bank details and hidden instructions to AI are blocked before payment."],
  [Landmark, "Paid only to saved details", "UPI, IMPS or RTGS to the supplier's saved account. Never to what an invoice says."],
];

const SAMPLE: [string, string, string, string][] = [
  ["Summit IT Services", "SIT/0342 · GST 9/9", "₹2,83,200.00", "PAID"],
  ["Pinnacle Print & Design", "PP/2217 · Wrong tax type", "₹1,43,700.00", "HELD"],
  ["Atlas Industrial Parts", "AIP/30918 · Fake GSTIN", "₹3,07,380.00", "BLOCKED"],
];

export default function Landing({ theme, toggleTheme, onDemo, busy, error }: {
  theme: Theme; toggleTheme: () => void; onDemo: () => void; busy: boolean; error: string | null;
}) {
  return (
    <div className="landing land">
      <header className="land-nav">
        <span className="brand"><Logo /><span className="brand-name">InvoiceGuard<span>India</span></span></span>
        <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className="sandbox">Simulated sandbox · no real money</span>
          <ThemeToggle theme={theme} toggle={toggleTheme} />
        </span>
      </header>
      <main className="land-main" id="main">
        <div>
          <span className="eyebrow"><Sparkles size={14} aria-hidden="true" />AI accounts payable for Indian businesses</span>
          <h1>Stop fraud <em>before money moves.</em></h1>
          <p className="lead">InvoiceGuard India reads every supplier invoice, verifies the GST in code, and pays only what is safe to pay.</p>
          <button className="btn btn-primary btn-lg" onClick={onDemo} disabled={busy}>
            {busy ? <Spinner label="Checking 20 invoices…" /> : <><Zap size={20} aria-hidden="true" />Try with demo data</>}
          </button>
          <p className="land-sub">Two client businesses and 20 sample invoices: valid ones, fraud and GST errors, a partial delivery. Takes a few seconds, no sign-up.</p>
          {error && <div className="alert tone-red" role="alert" style={{ marginTop: 16 }}><div><strong>Demo failed</strong>{error}</div></div>}
          <ul className="values">
            {VALUES.map(([Icon, title, text]) => (
              <li key={title}>
                <span className="vi"><Icon size={20} aria-hidden="true" /></span>
                <div><strong>{title}</strong><span>{text}</span></div>
              </li>
            ))}
          </ul>
        </div>
        <div aria-hidden="true">
          <div className="card preview">
            {SAMPLE.map(([name, sub, amt, status]) => (
              <div className="p-row" key={name}>
                <div><div className="p-name">{name}</div><div className="p-sub">{sub}</div></div>
                <div className="p-amt"><span>{amt}</span><StatusBadge status={status} size="sm" /></div>
              </div>
            ))}
          </div>
          <p className="preview-cap" style={{ marginTop: 16 }}>What you will see after loading the demo data</p>
        </div>
      </main>
      <footer className="land-foot">Prototype for Prasunex Innovathon. All companies, GSTINs, accounts and UPI IDs are fictional.</footer>
    </div>
  );
}
