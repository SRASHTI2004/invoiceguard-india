import { useEffect, useState } from "react";
import { api, AuditRow, Invoice } from "../api";
import { Badge } from "../components";

// `invoices` changes whenever something happens, so the log reloads with it.
export default function AuditPage({ invoices }: { invoices: Invoice[] }) {
  const [rows, setRows] = useState<AuditRow[]>([]);
  useEffect(() => {
    api.audit().then(setRows).catch(() => setRows([]));
  }, [invoices]);
  return (
    <section>
      <p className="muted">Every decision and action, newest first.</p>
      {rows.length === 0 && <p className="empty">Nothing logged yet.</p>}
      <ul className="audit">
        {rows.map((r) => (
          <li key={r.id}>
            <div className="audit-head">
              <span className="audit-event">{r.event.replace(/_/g, " ")}</span>
              {r.invoice_id != null && <span className="chip">Invoice #{r.invoice_id}</span>}
              <Badge value={r.decision} />
              <time className="muted">{r.created_at} UTC</time>
            </div>
            {r.reason && <div className="audit-reason">{r.reason}</div>}
          </li>
        ))}
      </ul>
    </section>
  );
}
