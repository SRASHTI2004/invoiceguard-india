import { CheckCheck, FileSearch, TriangleAlert } from "lucide-react";
import { CorrectionButton, useApprovalActions, useCorrectionAction } from "../actions";
import { inr, Invoice } from "../api";
import { fmtDate, fmtDateTime } from "../lib";
import { EmptyState, GstBadge, MsmeChip, MsmeNotice } from "../ui";

export default function ApprovalsPage({ held, reload, open }: { held: Invoice[]; reload: () => Promise<void>; open: (id: number) => void }) {
  const { ask, dialog, busyId } = useApprovalActions(reload);
  const correction = useCorrectionAction(reload);
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Approvals</h1>
          <p>These invoices were not paid automatically. Approving re-runs every check, then pays the supplier&apos;s <strong>saved</strong> UPI ID or bank account, never details printed on the invoice.</p>
        </div>
      </div>
      {held.length === 0 ? (
        <div className="card"><EmptyState icon={CheckCheck} title="Nothing is waiting for approval" text="When an invoice needs a person, it will show up here with the exact reason." /></div>
      ) : (
        <div className="cards">
          {held.map((inv) => (
            <article key={inv.id} className="card approval" aria-label={`Invoice ${inv.invoice_number} from ${inv.supplier_name}`}>
              <div className="approval-top">
                <div>
                  <h3>{inv.supplier_name ?? "Unreadable invoice"}</h3>
                  <div className="meta-row"><span>Invoice {inv.invoice_number ?? "?"}</span><span>PO {inv.po_number ?? "none"}</span><span>Due {fmtDate(inv.due_date)}</span></div>
                  <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}><GstBadge inv={inv} /><MsmeChip m={inv.msme} /></div>
                </div>
                <div className="amount-big">{inr(inv.total_paise)}</div>
              </div>
              <div className="why"><TriangleAlert size={18} aria-hidden="true" /><div><strong>Why it is on hold</strong><div>{inv.reason}</div>{inv.correction_requested_at && <div className="why-note">Corrected invoice requested on {fmtDateTime(inv.correction_requested_at)}.</div>}</div></div>
              <MsmeNotice m={inv.msme} />
              <div className="row-actions">
                <button className="btn btn-primary" disabled={busyId === inv.id} onClick={() => ask(inv, "approve")}>Approve &amp; pay</button>
                <button className="btn btn-danger" disabled={busyId === inv.id} onClick={() => ask(inv, "reject")}>Reject</button>
                <CorrectionButton inv={inv} action={correction} />
                <button className="btn btn-ghost" onClick={() => open(inv.id)}><FileSearch size={16} aria-hidden="true" />See full journey</button>
              </div>
            </article>
          ))}
        </div>
      )}
      {dialog}
      {correction.dialog}
    </>
  );
}
