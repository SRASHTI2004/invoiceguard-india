import { useState } from "react";
import { GstCheck, inr, Invoice } from "./api";

const STATUS: Record<string, [string, string]> = {
  PAID: ["Paid", "✓"],
  HELD: ["On hold", "⏸"],
  BLOCKED: ["Blocked", "⛔"],
  REJECTED: ["Rejected", "✕"],
  PAYING: ["Paying", "…"],
  RECEIVED: ["Received", "•"],
  AUTO_PAY: ["Auto-pay", "✓"],
  HOLD: ["Hold", "⏸"],
  BLOCK: ["Block", "⛔"],
  PENDING: ["Pending", "…"],
  SUCCESS: ["Settled", "✓"],
  FAILED: ["Failed", "✕"],
};

export function Badge({ value }: { value: string | null }) {
  if (!value) return null;
  const [label, icon] = STATUS[value] ?? [value, ""];
  return (
    <span className={`badge ${value}`}>
      <span aria-hidden="true">{icon}</span> {label}
    </span>
  );
}

export function Gstin({ value, label }: { value: string | null; label?: string }) {
  if (!value) return <span className="chip chip-warn">{label ?? "GSTIN"} missing</span>;
  return (
    <span className="chip">
      {label && <span className="chip-label">{label}</span>}
      <code>{value}</code>
    </span>
  );
}

export function TaxBreakdown({ inv }: { inv: Invoice }) {
  const cells: [string, number | null][] = [
    ["Taxable value", inv.taxable_paise],
    ["CGST", inv.cgst_paise],
    ["SGST", inv.sgst_paise],
    ["IGST", inv.igst_paise],
    ["Total", inv.total_paise],
  ];
  return (
    <dl className="tax">
      {cells.map(([k, v]) => (
        <div key={k} className={k === "Total" ? "tax-total" : (v ?? 0) === 0 ? "tax-zero" : ""}>
          <dt>{k}</dt>
          <dd>{v == null ? "–" : inr(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Per-invoice GST check results. Opens by default when something failed. */
export function GstReport({ inv }: { inv: Invoice }) {
  const report: GstCheck[] = inv.gst_report ?? [];
  const failed = report.filter((c) => !c.ok);
  const [open, setOpen] = useState(failed.length > 0);
  if (report.length === 0) {
    return <div className="gst gst-none">GST checks did not run (the invoice could not be read, so it was held).</div>;
  }
  return (
    <div className={`gst ${failed.length ? "gst-bad" : "gst-ok"}`}>
      <button className="gst-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="gst-title">GST checks</span>
        <span className="gst-count">
          {failed.length === 0
            ? `✓ All ${report.length} passed`
            : `✕ ${failed.length} failed · ${report.length - failed.length} passed`}
        </span>
        <span className="caret" aria-hidden="true">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <>
          <ul className="gst-list">
            {report.map((c) => (
              <li key={c.code + c.label} className={c.ok ? "pass" : "fail"}>
                <span className="mark" aria-label={c.ok ? "passed" : "failed"}>{c.ok ? "✓" : "✕"}</span>
                <div>
                  <strong>{c.label}</strong>
                  {!c.ok && c.severity && (
                    <span className={`sev sev-${c.severity}`}>{c.severity === "BLOCK" ? "blocks payment" : "needs a person"}</span>
                  )}
                  <div className="gst-msg">{c.message}</div>
                </div>
              </li>
            ))}
          </ul>
          <TaxBreakdown inv={inv} />
        </>
      )}
    </div>
  );
}

export function PayoutLine({ inv, onRefresh, busy }: { inv: Invoice; onRefresh?: () => void; busy?: boolean }) {
  if (!inv.payout_batch_id) return null;
  return (
    <div className="payout-line">
      <Badge value={inv.payout_status} />
      <span>
        Paid by <strong>{inv.payout_method}</strong> to saved {inv.payout_method === "UPI" ? "UPI ID" : "account"}{" "}
        <code>{inv.payout_destination}</code>
      </span>
      <span className="sandbox-tag" title="No real money moves in this demo">SIMULATED SANDBOX</span>
      {onRefresh && (
        <button className="mini" disabled={busy} onClick={onRefresh}>
          ↻ Check status
        </button>
      )}
    </div>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <span className="spin-wrap" role="status">
      <span className="spinner" aria-hidden="true" /> {label}
    </span>
  );
}
