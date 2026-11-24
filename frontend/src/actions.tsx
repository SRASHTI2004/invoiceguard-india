import { Copy, Mail, MailPlus } from "lucide-react";
import { ReactNode, useState } from "react";
import { api, CorrectionDraft, inr, Invoice } from "./api";
import { ConfirmDialog, Overlay, Spinner, useToast } from "./ui";

export const failedGst = (inv: Invoice) => (inv.gst_report ?? []).filter((c) => !c.ok);
const MIN_REASON = 8;

/** Approve / reject a held invoice. Approving past a GST failure asks for a short reason, saved in the audit log. */
export function useApprovalActions(reload: () => Promise<void>): {
  ask: (inv: Invoice, kind: "approve" | "reject") => void;
  dialog: ReactNode;
  busyId: number | null;
} {
  const toast = useToast();
  const [pending, setPending] = useState<{ inv: Invoice; kind: "approve" | "reject" } | null>(null);
  const [reason, setReason] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  const close = () => { setPending(null); setReason(""); };
  const run = async () => {
    if (!pending) return;
    const { inv, kind } = pending;
    const why = reason.trim();
    close();
    setBusyId(inv.id);
    try {
      const res = kind === "approve" ? await api.approve(inv.id, why || undefined) : await api.reject(inv.id);
      toast(kind === "approve" ? `Paid ${inr(res.total_paise)} to ${res.supplier_name}.` : `Rejected invoice ${res.invoice_number}.`, kind === "approve" ? "green" : "grey");
    } catch (e) {
      toast((e as Error).message, "red");
    }
    setBusyId(null);
    await reload();
  };

  const gstProblem = pending?.kind === "approve" && failedGst(pending.inv).length > 0;
  let dialog: ReactNode = null;
  if (pending && !gstProblem)
    dialog = (
      <ConfirmDialog
        title={pending.kind === "approve" ? "Approve and pay?" : "Reject this invoice?"}
        tone={pending.kind === "approve" ? "primary" : "danger"}
        confirmLabel={pending.kind === "approve" ? `Pay ${inr(pending.inv.total_paise)}` : "Reject invoice"}
        body={pending.kind === "approve"
          ? <>Every check is re-run now. If it still passes, <strong>{inr(pending.inv.total_paise)}</strong> goes to {pending.inv.supplier_name}&apos;s <strong>saved</strong> payment details (simulated sandbox).</>
          : <>Invoice {pending.inv.invoice_number} from {pending.inv.supplier_name} will be marked rejected and never paid.</>}
        onConfirm={run}
        onCancel={close}
      />
    );
  if (pending && gstProblem) {
    const failed = failedGst(pending.inv);
    const ok = reason.trim().length >= MIN_REASON;
    dialog = (
      <Overlay label="Approve despite a GST problem" onClose={close} variant="center" wide>
        <h2 className="dialog-title">Approve despite a GST problem?</h2>
        <div className="dialog-body">
          <p>This invoice failed {failed.length === 1 ? "a GST check" : `${failed.length} GST checks`}:</p>
          <ul className="issue-list">{failed.map((f) => <li key={f.code}><strong>{f.label}.</strong> {f.message}</li>)}</ul>
          <p>Paying it may put your input tax credit at risk. A better path is to ask the supplier for a corrected invoice. If you still approve, say why; it is saved in the audit log.</p>
          <label className="field">
            <span>Reason for approving anyway</span>
            <textarea data-autofocus value={reason} onChange={(e) => setReason(e.target.value)} rows={3} maxLength={300}
              placeholder="For example: supplier confirmed by phone, credit note to follow" aria-describedby="reason-help" />
          </label>
          <span id="reason-help" className="field-help">{ok ? "Saved in the audit log with your approval." : `At least ${MIN_REASON} characters required.`}</span>
        </div>
        <div className="dialog-actions">
          <button className="btn" onClick={close}>Cancel</button>
          <button className="btn btn-primary" disabled={!ok} onClick={run}>Approve and pay {inr(pending.inv.total_paise)}</button>
        </div>
      </Overlay>
    );
  }
  return { ask: (inv, kind) => setPending({ inv, kind }), dialog, busyId };
}

/** "Ask supplier for a corrected invoice": drafts the email, logs the request, lets the owner copy it or open it in mail. */
export function useCorrectionAction(reload: () => Promise<void>): {
  ask: (inv: Invoice) => void;
  dialog: ReactNode;
  busyId: number | null;
} {
  const toast = useToast();
  const [draft, setDraft] = useState<CorrectionDraft | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const ask = async (inv: Invoice) => {
    setBusyId(inv.id);
    try {
      setDraft(await api.requestCorrection(inv.id));
      await reload();
    } catch (e) {
      toast((e as Error).message, "red");
    }
    setBusyId(null);
  };
  const copy = async () => {
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(`To: ${draft.to}\nSubject: ${draft.subject}\n\n${draft.body}`);
      toast("Email copied to the clipboard.", "green");
    } catch {
      toast("Could not copy. Select the text and copy it manually.", "amber");
    }
  };
  const dialog = draft && (
    <Overlay label="Draft email to the supplier" onClose={() => setDraft(null)} variant="center" wide>
      <h2 className="dialog-title">Draft: ask for a corrected invoice</h2>
      <div className="dialog-body">
        <dl className="kv draft-meta">
          <div><dt>To</dt><dd>{draft.to || "(no email saved for this supplier)"}</dd></div>
          <div><dt>Subject</dt><dd>{draft.subject}</dd></div>
        </dl>
        <pre className="draft" tabIndex={0} aria-label="Email body">{draft.body}</pre>
        <p className="field-help">This is a draft. Nothing was sent: copy it or open it in your mail app. The request is recorded in the audit log, and the invoice stays on hold.</p>
      </div>
      <div className="dialog-actions">
        <button className="btn" onClick={() => setDraft(null)}>Close</button>
        <button className="btn" onClick={copy}><Copy size={16} aria-hidden="true" />Copy email</button>
        <a className="btn btn-brand" data-autofocus href={draft.mailto}><Mail size={16} aria-hidden="true" />Open in mail app</a>
      </div>
    </Overlay>
  );
  return { ask, dialog, busyId };
}

export function CorrectionButton({ inv, action, size = "md" }: { inv: Invoice; action: ReturnType<typeof useCorrectionAction>; size?: "sm" | "md" }) {
  if (inv.status !== "HELD" || failedGst(inv).length === 0) return null;
  return (
    <button className={size === "sm" ? "btn btn-sm" : "btn"} disabled={action.busyId === inv.id} onClick={() => action.ask(inv)}
      title="Drafts an email to the supplier naming the GST issue. Nothing is sent.">
      {action.busyId === inv.id ? <Spinner /> : <MailPlus size={16} aria-hidden="true" />}
      {inv.correction_requested_at ? "Ask again for a corrected invoice" : "Ask supplier for a corrected invoice"}
    </button>
  );
}
