export interface GstCheck {
  code: string;
  label: string;
  ok: boolean;
  message: string;
  severity: "BLOCK" | "HOLD" | null;
}

export interface Invoice {
  id: number;
  filename: string | null;
  supplier_name: string | null;
  supplier_gstin: string | null;
  buyer_gstin: string | null;
  place_of_supply: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  due_date: string | null;
  po_number: string | null;
  taxable_paise: number | null;
  cgst_paise: number | null;
  sgst_paise: number | null;
  igst_paise: number | null;
  total_paise: number | null;
  payee_upi: string | null;
  payee_account: string | null;
  payee_ifsc: string | null;
  gst_report: GstCheck[];
  status: string;
  decision: string | null;
  reason: string | null;
  risk_score: number | null;
  payout_batch_id: string | null;
  payout_status: string | null;
  payout_method: string | null;
  payout_destination: string | null;
  paid_at: string | null;
  correction_requested_at: string | null;
  created_at: string;
}

export interface Supplier {
  id: number;
  name: string;
  approved: number;
  gstin: string;
  state: string;
  bank_account: string | null;
  ifsc: string | null;
  upi_id: string | null;
  payout_method: string;
  address: string | null;
}

export interface Summary {
  total_paid_paise: number;
  total_blocked_paise: number;
  total_held_paise: number;
  money_saved_paise: number;
  itc_protected_paise: number;
  itc_protected_count: number;
  itc_at_risk_paise: number;
  itc_at_risk_count: number;
  counts: Record<string, number>;
  invoice_count: number;
}

export type StepState = "pass" | "warn" | "fail" | "skipped" | "pending";

export interface TimelineStep {
  key: string;
  title: string;
  state: StepState;
  summary: string;
  details: string[];
}

export interface CorrectionDraft {
  to: string;
  subject: string;
  body: string;
  issues: string[];
  mailto: string;
  sent: boolean;
}

export interface SampleInvoice {
  file: string;
  title: string;
  description: string;
  expected: string;
  supplier: string;
  invoice_number: string;
  url: string;
}

export interface AppConfig {
  buyer_name: string;
  buyer_gstin: string;
  payout_provider: string;
  payout_label: string;
  currency: string;
}

export interface AuditRow {
  id: number;
  invoice_id: number | null;
  event: string;
  decision: string | null;
  reason: string | null;
  created_at: string;
}

export interface AgentStep {
  tool: string;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
}

export interface ProposalItem {
  invoice: { id: number; supplier: string | null; invoice_number: string | null; amount: string | null; amount_paise: number | null; due_date: string | null } | null;
  reasons: string[];
  recommended: boolean;
}

export interface Proposal {
  recommended: ProposalItem[];
  not_recommended: ProposalItem[];
  total_recommended_paise: number;
}

export interface ConfirmResult {
  invoice_id: number;
  paid: boolean;
  message: string;
}

/** Paise -> "₹1,24,000.00" (Indian digit grouping: lakhs and crores). */
export const inr = (paise: number | null | undefined) =>
  paise == null
    ? ""
    : (paise / 100).toLocaleString("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2 });

/** "₹7.2 L" / "₹1.5 Cr" for the big summary numbers. */
export const inrShort = (paise: number) => {
  const r = paise / 100;
  if (r >= 1e7) return `₹${(r / 1e7).toFixed(2)} Cr`;
  if (r >= 1e5) return `₹${(r / 1e5).toFixed(2)} L`;
  return inr(paise);
};

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`;
    try {
      const d = (await res.json()).detail;
      detail = typeof d === "string" ? d : d ? JSON.stringify(d) : detail;
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return res.json();
}

const post = <T,>(url: string) => call<T>(url, { method: "POST" });

export const api = {
  invoices: () => call<Invoice[]>("/api/invoices"),
  suppliers: () => call<Supplier[]>("/api/suppliers"),
  summary: () => call<Summary>("/api/summary"),
  config: () => call<AppConfig>("/api/config"),
  samples: () => call<SampleInvoice[]>("/api/samples"),
  timeline: (id: number) => call<{ invoice_id: number; steps: TimelineStep[] }>(`/api/invoices/${id}/timeline`),
  audit: () => call<AuditRow[]>("/api/audit"),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return call<Invoice>("/api/invoices/upload", { method: "POST", body: form });
  },
  approve: (id: number, reason?: string) =>
    call<Invoice>(`/api/invoices/${id}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: reason ?? null }) }),
  requestCorrection: (id: number) => post<CorrectionDraft>(`/api/invoices/${id}/request-correction`),
  reject: (id: number) => post<Invoice>(`/api/invoices/${id}/reject`),
  refreshPayout: (id: number) => post<Invoice>(`/api/invoices/${id}/refresh-payout`),
  agent: (message: string) =>
    call<{ reply: string; steps: AgentStep[]; proposal: Proposal }>("/api/agent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    }),
  confirmProposal: (invoice_ids: number[]) =>
    call<{ results: ConfirmResult[] }>("/api/agent/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ invoice_ids }),
    }),
  runSamples: () => post<{ processed: number; summary: Summary; throttled?: boolean; note?: string }>("/api/demo/run-samples"),
};
