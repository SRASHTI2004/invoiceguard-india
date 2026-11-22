import { useState } from "react";
import { api, inr, Invoice } from "../api";
import { Gstin, GstReport } from "../components";

export default function ApprovalsPage({ held, reload }: { held: Invoice[]; reload: () => Promise<void> }) {
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const act = async (id: number, fn: (id: number) => Promise<unknown>) => {
    setBusyId(id);
    setError(null);
    try {
      await fn(id);
    } catch (e) {
      setError((e as Error).message);
    }
    setBusyId(null);
    await reload();
  };

  if (held.length === 0) return <p className="empty">Nothing is waiting for approval.</p>;
  return (
    <section>
      <p className="muted">
        These invoices were not paid automatically. Approving re-runs every check, then pays the supplier&apos;s <strong>saved</strong> UPI
        ID or bank account, never details printed on the invoice.
      </p>
      {error && <div className="banner error">{error}</div>}
      <div className="inv-list">
        {held.map((inv) => (
          <article key={inv.id} className="inv inv-HELD">
            <div className="inv-top">
              <div className="inv-id">
                <h3>{inv.supplier_name ?? "Unreadable invoice"}</h3>
                <div className="meta">
                  <span>Invoice {inv.invoice_number ?? "?"}</span>
                  <span>PO {inv.po_number ?? "none"}</span>
                  <span>due {inv.due_date ?? "?"}</span>
                </div>
                <div className="chips"><Gstin value={inv.supplier_gstin} label="Supplier" /></div>
              </div>
              <div className="inv-amount">
                <div className="amt">{inr(inv.total_paise)}</div>
              </div>
            </div>
            <p className="reason reason-HOLD"><strong>Why it is on hold:</strong> {inv.reason}</p>
            <GstReport inv={inv} />
            <div className="actions">
              <button
                className="primary"
                disabled={busyId === inv.id}
                onClick={() => window.confirm(`Pay ${inr(inv.total_paise)} to ${inv.supplier_name}?`) && act(inv.id, api.approve)}
              >
                Approve &amp; pay
              </button>
              <button className="danger" disabled={busyId === inv.id} onClick={() => act(inv.id, api.reject)}>
                Reject
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
