import { ReactNode, useState } from "react";
import { api, inr, Invoice } from "./api";
import { ConfirmDialog, useToast } from "./ui";

/** Approve / reject a held invoice with a confirm dialog and toast feedback. Render `dialog` somewhere in the page. */
export function useApprovalActions(reload: () => Promise<void>): {
  ask: (inv: Invoice, kind: "approve" | "reject") => void;
  dialog: ReactNode;
  busyId: number | null;
} {
  const toast = useToast();
  const [pending, setPending] = useState<{ inv: Invoice; kind: "approve" | "reject" } | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const run = async () => {
    if (!pending) return;
    const { inv, kind } = pending;
    setPending(null);
    setBusyId(inv.id);
    try {
      const res = kind === "approve" ? await api.approve(inv.id) : await api.reject(inv.id);
      toast(kind === "approve" ? `Paid ${inr(res.total_paise)} to ${res.supplier_name}.` : `Rejected invoice ${res.invoice_number}.`, kind === "approve" ? "green" : "grey");
    } catch (e) {
      toast((e as Error).message, "red");
    }
    setBusyId(null);
    await reload();
  };

  const dialog = pending && (
    <ConfirmDialog
      title={pending.kind === "approve" ? "Approve and pay?" : "Reject this invoice?"}
      tone={pending.kind === "approve" ? "primary" : "danger"}
      confirmLabel={pending.kind === "approve" ? `Pay ${inr(pending.inv.total_paise)}` : "Reject invoice"}
      body={
        pending.kind === "approve"
          ? <>Every check is re-run now. If it still passes, <strong>{inr(pending.inv.total_paise)}</strong> goes to {pending.inv.supplier_name}&apos;s <strong>saved</strong> payment details (simulated sandbox).</>
          : <>Invoice {pending.inv.invoice_number} from {pending.inv.supplier_name} will be marked rejected and never paid.</>
      }
      onConfirm={run}
      onCancel={() => setPending(null)}
    />
  );
  return { ask: (inv, kind) => setPending({ inv, kind }), dialog, busyId };
}
