import { useEffect, useState } from "react";
import { api, Supplier } from "../api";
import { Gstin } from "../components";

export default function SuppliersPage() {
  const [rows, setRows] = useState<Supplier[]>([]);
  useEffect(() => {
    api.suppliers().then(setRows).catch(() => setRows([]));
  }, []);
  return (
    <section>
      <p className="muted">
        Payments always go to the details saved below, never to anything written on an invoice. An invoice with a different GSTIN,
        UPI ID or bank account is blocked.
      </p>
      <div className="sup-grid">
        {rows.map((s) => (
          <article key={s.id} className={s.approved ? "sup" : "sup sup-off"}>
            <div className="sup-top">
              <h3>{s.name}</h3>
              <span className={s.approved ? "badge PAID" : "badge BLOCKED"}>{s.approved ? "Approved" : "Not approved"}</span>
            </div>
            <div className="muted">{s.state}</div>
            <div className="chips"><Gstin value={s.gstin} /></div>
            <dl className="kv">
              <div><dt>Saved payout</dt><dd>{s.payout_method === "UPI" ? "UPI" : "Bank transfer"}</dd></div>
              {s.upi_id && <div><dt>UPI ID</dt><dd><code>{s.upi_id}</code></dd></div>}
              {s.bank_account && <div><dt>Account</dt><dd><code>{s.bank_account}</code> · <code>{s.ifsc}</code></dd></div>}
            </dl>
          </article>
        ))}
      </div>
    </section>
  );
}
