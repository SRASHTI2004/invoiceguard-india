import { ChevronRight, FileSearch, Search, Upload } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { api, inr, Invoice } from "../api";
import { fmtDate } from "../lib";
import { EmptyState, GstBadge, Spinner, StatusBadge, useToast } from "../ui";

const FILTERS: [string, string, (i: Invoice) => boolean][] = [
  ["all", "All", () => true],
  ["PAID", "Paid", (i) => i.status === "PAID"],
  ["HELD", "On hold", (i) => i.status === "HELD"],
  ["BLOCKED", "Blocked", (i) => i.status === "BLOCKED" || i.status === "REJECTED"],
];

const haystack = (i: Invoice) =>
  [i.supplier_name, i.invoice_number, i.po_number, i.supplier_gstin, i.reason, i.status, i.filename].join(" ").toLowerCase();

export default function InvoicesPage({ invoices, reload, openId, open }: {
  invoices: Invoice[]; reload: () => Promise<void>; openId: number | null; open: (id: number) => void;
}) {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");

  const upload = async (f: File) => {
    setBusy(true);
    try {
      const inv = await api.upload(f);
      toast(`Invoice ${inv.invoice_number ?? f.name}: ${inv.status === "PAID" ? "paid" : inv.status.toLowerCase().replace("held", "on hold")}. ${inv.reason ?? ""}`,
        inv.status === "PAID" ? "green" : inv.status === "BLOCKED" ? "red" : "amber");
      await reload();
      if (inv.id) open(inv.id);
    } catch (e) {
      toast((e as Error).message, "red");
    }
    setBusy(false);
  };

  const shown = useMemo(() => {
    const pick = FILTERS.find((f) => f[0] === filter)![2];
    const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
    return invoices.filter((i) => pick(i) && terms.every((t) => haystack(i).includes(t)));
  }, [invoices, filter, q]);

  return (
    <>
      <div className="page-head">
        <div><h1>Invoices</h1><p>Select an invoice to see how it moved through every check.</p></div>
        <div>
          <input ref={fileRef} type="file" accept="application/pdf" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
          <button className="btn btn-brand" disabled={busy} onClick={() => fileRef.current?.click()}>
            {busy ? <Spinner label="Checking invoice…" /> : <><Upload size={16} aria-hidden="true" />Upload invoice (PDF)</>}
          </button>
        </div>
      </div>
      <div className="toolbar">
        <div className="search">
          <Search size={16} aria-hidden="true" />
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search supplier, invoice no, GSTIN, reason…" aria-label="Search invoices" />
        </div>
        <div className="chips" role="group" aria-label="Filter by status">
          {FILTERS.map(([key, label, fn]) => (
            <button key={key} className="chip" aria-pressed={filter === key} onClick={() => setFilter(key)}>
              {label}<span className="n">{invoices.filter(fn).length}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="card table-card">
        {shown.length === 0 ? (
          <EmptyState icon={FileSearch} title={invoices.length === 0 ? "No invoices yet" : "No invoices match"}
            text={invoices.length === 0 ? "Upload a PDF or load the demo data to see InvoiceGuard at work." : "Try a different search or filter."}
            action={invoices.length > 0 ? <button className="btn btn-sm" onClick={() => { setQ(""); setFilter("all"); }}>Clear filters</button> : undefined} />
        ) : (
          <>
            <table className="tbl">
              <caption className="sr-only">Invoices</caption>
              <thead>
                <tr><th scope="col">Supplier</th><th scope="col">Invoice date</th><th scope="col" className="num">Amount</th><th scope="col">GST checks</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Open</span></th></tr>
              </thead>
              <tbody>
                {shown.map((inv) => (
                  <tr key={inv.id} data-selected={openId === inv.id} onClick={() => open(inv.id)} style={{ cursor: "pointer" }}>
                    <td className="c-name">
                      <button className="row-btn" onClick={(e) => { e.stopPropagation(); open(inv.id); }} aria-label={`Open invoice ${inv.invoice_number ?? inv.id} from ${inv.supplier_name ?? "unreadable invoice"}`}>
                        <span className="cell-name">{inv.supplier_name ?? "Unreadable invoice"}</span>
                        <span className="cell-sub" style={{ display: "block" }}>{inv.invoice_number ?? "?"} · PO {inv.po_number ?? "none"}</span>
                      </button>
                    </td>
                    <td className="c-date">{fmtDate(inv.invoice_date)}</td>
                    <td className="num c-amt cell-amt">{inr(inv.total_paise) || "–"}</td>
                    <td className="c-gst"><GstBadge inv={inv} /></td>
                    <td className="c-status"><StatusBadge status={inv.status} /></td>
                    <td className="c-chev cell-chev"><ChevronRight size={18} aria-hidden="true" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="result-count" aria-live="polite">Showing {shown.length} of {invoices.length} invoices</div>
          </>
        )}
      </div>
    </>
  );
}
