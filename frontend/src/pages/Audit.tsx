import { AlertCircle, CheckCircle2, CircleDot, ScrollText, XCircle, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { api, AuditRow, Invoice } from "../api";
import { hrefFor } from "../lib";
import { EmptyState, ErrorState, Skeleton, StatusBadge } from "../ui";

const TONE: Record<string, [string, LucideIcon]> = {
  AUTO_PAY: ["green", CheckCircle2], APPROVED: ["green", CheckCircle2],
  HOLD: ["amber", AlertCircle], NOT_RECOMMENDED: ["amber", AlertCircle],
  BLOCK: ["red", XCircle], REJECTED: ["red", XCircle],
};

// `invoices` changes whenever something happens, so the log reloads with it.
export default function AuditPage({ invoices }: { invoices: Invoice[] }) {
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => { setError(null); api.audit().then(setRows).catch((e) => setError((e as Error).message)); };
  useEffect(load, [invoices]);
  return (
    <>
      <div className="page-head"><div><h1>Audit log</h1><p>Every decision and action, newest first. Nothing is paid without a line here.</p></div></div>
      <div className="card">
        {error ? <div style={{ padding: 16 }}><ErrorState message={error} onRetry={load} /></div> : !rows ? (
          <div style={{ padding: 24, display: "grid", gap: 16 }} role="status" aria-label="Loading audit log">{[0, 1, 2, 3].map((i) => <Skeleton key={i} h={40} />)}</div>
        ) : rows.length === 0 ? (
          <EmptyState icon={ScrollText} title="Nothing logged yet" text="Decisions and actions will be recorded here as invoices are processed." />
        ) : (
          <ul className="feed">
            {rows.map((r) => {
              const [tone, Icon] = TONE[r.decision ?? ""] ?? ["grey", CircleDot];
              return (
                <li key={r.id}>
                  <span className={`feed-dot tone-${tone}`}><Icon size={16} aria-hidden="true" /></span>
                  <div>
                    <div className="feed-head">
                      <strong>{r.event.replace(/_/g, " ")}</strong>
                      <StatusBadge status={r.decision} size="sm" />
                      {r.invoice_id != null && <a className="linkbtn" href={hrefFor("invoices", r.invoice_id)}>Invoice #{r.invoice_id}</a>}
                      <time className="feed-time">{r.created_at} UTC</time>
                    </div>
                    {r.reason && <div className="feed-reason">{r.reason}</div>}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </>
  );
}
