import { Building2, Landmark, Search, Smartphone } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, Supplier } from "../api";
import { EmptyState, ErrorState, Skeleton } from "../ui";

const initials = (name: string) => name.split(/\s+/).filter((w) => /[A-Za-z]/.test(w)).slice(0, 2).map((w) => w[0].toUpperCase()).join("");

export default function SuppliersPage() {
  const [rows, setRows] = useState<Supplier[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const load = () => { setError(null); api.suppliers().then(setRows).catch((e) => setError((e as Error).message)); };
  useEffect(load, []);
  const shown = useMemo(() => (rows ?? []).filter((s) => `${s.name} ${s.state} ${s.gstin}`.toLowerCase().includes(q.toLowerCase())), [rows, q]);
  return (
    <>
      <div className="page-head">
        <div><h1>Suppliers</h1><p>Payments always go to the details saved here, never to anything written on an invoice. An invoice with a different GSTIN, UPI ID or bank account is blocked.</p></div>
      </div>
      <div className="toolbar">
        <div className="search"><Search size={16} aria-hidden="true" /><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name, state or GSTIN" aria-label="Search suppliers" /></div>
      </div>
      {error ? <ErrorState message={error} onRetry={load} /> : !rows ? (
        <div className="sup-grid" role="status" aria-label="Loading suppliers">{[0, 1, 2].map((i) => <div key={i} className="card sup"><Skeleton h={40} /><Skeleton h={14} w="60%" /><Skeleton h={14} /></div>)}</div>
      ) : shown.length === 0 ? (
        <div className="card"><EmptyState icon={Building2} title="No suppliers match" text="Try a different search." /></div>
      ) : (
        <div className="sup-grid">
          {shown.map((s) => (
            <article key={s.id} className={s.approved ? "card sup" : "card sup off"}>
              <div className="sup-top">
                <div className="sup-id"><span className="avatar" aria-hidden="true">{initials(s.name)}</span><div><h3>{s.name}</h3><div className="cell-sub">{s.state}</div></div></div>
                <span className={`badge badge-sm tone-${s.approved ? "green" : "red"}`}>{s.approved ? "Approved" : "Not approved"}</span>
              </div>
              <div><span className="pill mono">{s.gstin}</span></div>
              <dl className="kv">
                <div><dt>Saved payout</dt><dd style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>{s.payout_method === "UPI" ? <Smartphone size={14} aria-hidden="true" /> : <Landmark size={14} aria-hidden="true" />}{s.payout_method === "UPI" ? "UPI" : "Bank transfer"}</dd></div>
                {s.upi_id && <div><dt>UPI ID</dt><dd><code>{s.upi_id}</code></dd></div>}
                {s.bank_account && <div><dt>Account</dt><dd><code>{s.bank_account}</code> · <code>{s.ifsc}</code></dd></div>}
              </dl>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
