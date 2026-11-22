import { useRef, useState } from "react";
import { api, inr, Invoice } from "../api";
import { Badge, Gstin, GstReport, PayoutLine, Spinner } from "../components";

const FILTERS: [string, string, (i: Invoice) => boolean][] = [
  ["all", "All", () => true],
  ["PAID", "Paid", (i) => i.status === "PAID"],
  ["HELD", "On hold", (i) => i.status === "HELD"],
  ["BLOCKED", "Blocked", (i) => i.status === "BLOCKED" || i.status === "REJECTED"],
];

function InvoiceCard({ inv, reload }: { inv: Invoice; reload: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const refresh = async () => {
    setBusy(true);
    try {
      await api.refreshPayout(inv.id);
    } catch {
      /* the badge simply stays as it was */
    }
    setBusy(false);
    await reload();
  };
  return (
    <article className={`inv inv-${inv.status}`}>
      <div className="inv-top">
        <div className="inv-id">
          <h3>{inv.supplier_name ?? "Unreadable invoice"}</h3>
          <div className="meta">
            <span>#{inv.id}</span>
            <span>Invoice {inv.invoice_number ?? "?"}</span>
            <span>{inv.invoice_date ?? "?"}</span>
            <span>PO {inv.po_number ?? "none"}</span>
          </div>
          <div className="chips">
            <Gstin value={inv.supplier_gstin} label="Supplier" />
            {inv.place_of_supply && <span className="chip"><span className="chip-label">Supply to</span>{inv.place_of_supply}</span>}
          </div>
        </div>
        <div className="inv-amount">
          <div className="amt">{inr(inv.total_paise) || "–"}</div>
          <Badge value={inv.status} />
        </div>
      </div>
      {inv.reason && <p className={`reason reason-${inv.decision}`}>{inv.reason}</p>}
      <GstReport inv={inv} />
      <PayoutLine inv={inv} onRefresh={refresh} busy={busy} />
    </article>
  );
}

export default function InvoicesPage({ invoices, reload }: { invoices: Invoice[]; reload: () => Promise<void> }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [filter, setFilter] = useState("all");

  const upload = async (f: File) => {
    setBusy(true);
    setMessage(null);
    try {
      const inv = await api.upload(f);
      setMessage(`Invoice ${inv.invoice_number ?? f.name}: ${inv.status.toLowerCase()}. ${inv.reason ?? ""}`);
    } catch (e) {
      setMessage(`Error: ${(e as Error).message}`);
    }
    setBusy(false);
    await reload();
  };

  const pick = FILTERS.find((f) => f[0] === filter)![2];
  const shown = invoices.filter(pick);
  return (
    <section>
      <div className="toolbar">
        <div className="filters" role="tablist" aria-label="Filter invoices">
          {FILTERS.map(([key, label, fn]) => (
            <button key={key} role="tab" aria-selected={filter === key} className={filter === key ? "filter on" : "filter"} onClick={() => setFilter(key)}>
              {label} <span className="count">{invoices.filter(fn).length}</span>
            </button>
          ))}
        </div>
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) upload(f);
            e.target.value = "";
          }}
        />
        <button className="primary" disabled={busy} onClick={() => fileRef.current?.click()}>
          {busy ? <Spinner label="Checking invoice…" /> : "Upload an invoice (PDF)"}
        </button>
      </div>
      {message && <div className="note">{message}</div>}
      {shown.length === 0 ? (
        <p className="empty">No invoices here yet. Upload a PDF or load the demo data.</p>
      ) : (
        <div className="inv-list">
          {shown.map((inv) => (
            <InvoiceCard key={inv.id} inv={inv} reload={reload} />
          ))}
        </div>
      )}
    </section>
  );
}
