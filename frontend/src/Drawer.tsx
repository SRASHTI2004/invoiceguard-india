import { CheckCircle2, RefreshCw, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useApprovalActions } from "./actions";
import { fmtDate } from "./lib";
import { api, inr, Invoice, TimelineStep } from "./api";
import { CloseButton, ErrorState, GstBadge, Overlay, Skeleton, Spinner, StatusBadge, StepIcon, useToast } from "./ui";

function Timeline({ invoice }: { invoice: Invoice }) {
  const [steps, setSteps] = useState<TimelineStep[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setError(null);
    api.timeline(invoice.id).then((t) => live && setSteps(t.steps)).catch((e) => live && setError((e as Error).message));
    return () => { live = false; };
  }, [invoice.id, invoice.status, invoice.payout_status, attempt]);
  if (error) return <ErrorState message={error} onRetry={() => setAttempt(attempt + 1)} />;
  if (!steps) return <div role="status" aria-label="Loading journey" style={{ display: "grid", gap: 16 }}>{[0, 1, 2, 3].map((i) => <Skeleton key={i} h={44} r={10} />)}</div>;
  return (
    <ol className="timeline">
      {steps.map((s) => {
        const { Icon, label } = StepIcon[s.state];
        return (
          <li key={s.key} className={`step tone-${s.state === "pass" ? "green" : s.state === "warn" ? "amber" : s.state === "fail" ? "red" : "grey"}`} data-state={s.state}>
            <span className="step-icon"><Icon size={18} aria-hidden="true" /></span>
            <div>
              <div className="step-title"><strong>{s.title}</strong><span className="step-state">{label}</span></div>
              <div className="step-sum">{s.summary}</div>
              {s.details.length > 0 && s.state !== "pass" && s.state !== "skipped" && (
                <ul className="step-details">{s.details.map((d, i) => <li key={i}>{d}</li>)}</ul>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function GstBreakdown({ inv }: { inv: Invoice }) {
  const cells: [string, number | null][] = [["Taxable value", inv.taxable_paise], ["CGST", inv.cgst_paise], ["SGST", inv.sgst_paise], ["IGST", inv.igst_paise]];
  return (
    <>
      {inv.gst_report.length > 0 && (
        <ul className="gst-list" style={{ marginBottom: 16 }}>
          {inv.gst_report.map((c) => (
            <li key={c.code + c.label} className={c.ok ? "ok" : "no"}>
              {c.ok ? <CheckCircle2 size={16} aria-label="Passed" /> : <XCircle size={16} aria-label="Failed" />}
              <span>{c.label}<span className="m">{c.message}</span></span>
            </li>
          ))}
        </ul>
      )}
      <dl className="tax">
        {cells.map(([k, v]) => (
          <div key={k} className={(v ?? 0) === 0 ? "zero" : ""}><dt>{k}</dt><dd>{v == null ? "–" : inr(v)}</dd></div>
        ))}
        <div className="total"><dt>Invoice total</dt><dd>{inr(inv.total_paise)}</dd></div>
      </dl>
    </>
  );
}

export default function InvoiceDrawer({ invoice, onClose, reload }: { invoice: Invoice; onClose: () => void; reload: () => Promise<void> }) {
  const toast = useToast();
  const { ask, dialog, busyId } = useApprovalActions(reload);
  const [refreshing, setRefreshing] = useState(false);
  const refresh = async () => {
    setRefreshing(true);
    try { await api.refreshPayout(invoice.id); toast("Payout status refreshed.", "green"); } catch (e) { toast((e as Error).message, "red"); }
    setRefreshing(false);
    await reload();
  };
  const held = invoice.status === "HELD";
  return (
    <>
    <Overlay label={`Invoice ${invoice.invoice_number ?? invoice.id} details`} onClose={onClose} variant="drawer">
      <div className="drawer-head">
        <div>
          <h2>{invoice.supplier_name ?? "Unreadable invoice"}</h2>
          <div className="meta-row"><span>Invoice {invoice.invoice_number ?? "?"}</span><span>{fmtDate(invoice.invoice_date)}</span><span>PO {invoice.po_number ?? "none"}</span></div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12, alignItems: "center" }}>
            <span className="amount-big">{inr(invoice.total_paise) || "–"}</span>
            <StatusBadge status={invoice.status} /><GstBadge inv={invoice} />
          </div>
        </div>
        <span data-autofocus tabIndex={-1}><CloseButton onClose={onClose} /></span>
      </div>
      <div className="drawer-body">
        <section aria-labelledby="d-journey">
          <h3 className="sec-title" id="d-journey">Journey</h3>
          <Timeline invoice={invoice} />
        </section>
        <section aria-labelledby="d-gst">
          <h3 className="sec-title" id="d-gst">GST breakdown</h3>
          <GstBreakdown inv={invoice} />
        </section>
        <section aria-labelledby="d-parties">
          <h3 className="sec-title" id="d-parties">Parties</h3>
          <dl className="kv">
            <div><dt>Supplier GSTIN</dt><dd><code>{invoice.supplier_gstin ?? "missing"}</code></dd></div>
            <div><dt>Buyer GSTIN</dt><dd><code>{invoice.buyer_gstin ?? "missing"}</code></dd></div>
            <div><dt>Place of supply</dt><dd>{invoice.place_of_supply ?? "?"}</dd></div>
            <div><dt>Payment printed on invoice</dt><dd>{[invoice.payee_upi, invoice.payee_account && `A/c ${invoice.payee_account}`].filter(Boolean).join(" · ") || "none"}</dd></div>
          </dl>
        </section>
        {invoice.payout_batch_id && (
          <section aria-labelledby="d-pay">
            <h3 className="sec-title" id="d-pay">Payout</h3>
            <dl className="kv">
              <div><dt>Status</dt><dd><StatusBadge status={invoice.payout_status} size="sm" /></dd></div>
              <div><dt>Method</dt><dd>{invoice.payout_method}</dd></div>
              <div><dt>Saved destination</dt><dd><code>{invoice.payout_destination}</code></dd></div>
              <div><dt>Reference</dt><dd><code>{invoice.payout_batch_id}</code></dd></div>
            </dl>
            <p className="muted" style={{ fontSize: "0.8rem", marginTop: 8 }}><span className="sandbox">Simulated sandbox</span> No real money moved.</p>
            <button className="btn btn-sm" style={{ marginTop: 12 }} onClick={refresh} disabled={refreshing}>
              {refreshing ? <Spinner /> : <RefreshCw size={14} aria-hidden="true" />}Check status
            </button>
          </section>
        )}
      </div>
      {held && (
        <div className="drawer-foot">
          <button className="btn btn-primary" disabled={busyId === invoice.id} onClick={() => ask(invoice, "approve")}>Approve &amp; pay</button>
          <button className="btn btn-danger" disabled={busyId === invoice.id} onClick={() => ask(invoice, "reject")}>Reject</button>
        </div>
      )}
    </Overlay>
    {dialog}
    </>
  );
}
