import { CheckCircle2, FlaskConical, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api, EvaluationReport, inr, inrShort } from "../api";
import { fmtDateTime } from "../lib";
import { EmptyState, ErrorState, Skeleton, StatusBadge } from "../ui";

const CATEGORY: Record<string, string> = {
  valid_igst: "Valid invoice (IGST)", valid_cgst_sgst: "Valid invoice (CGST + SGST)", duplicate: "Duplicate invoice",
  fake_gstin: "Fake GSTIN", wrong_tax_type: "Wrong tax type", prompt_injection: "Hidden prompt injection",
  wrong_gst_total: "Wrong GST total", changed_payee: "Changed payee details", unapproved_supplier: "Unapproved supplier",
};

function Meter({ value, total, tone }: { value: number; total: number; tone: "green" | "red" }) {
  return (
    <div className={`meter tone-${tone}`} role="img" aria-label={`${value} of ${total}`}>
      <span style={{ width: total ? `${(value / total) * 100}%` : 0 }} />
    </div>
  );
}

export default function EvaluationPage() {
  const [data, setData] = useState<EvaluationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => { setError(null); api.evaluation().then(setData).catch((e) => setError((e as Error).message)); };
  useEffect(load, []);

  const s = data?.summary;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>How well it works</h1>
          <p>Every labelled sample invoice was run through the real pipeline. Here is what was caught, what was wrongly held, and which check did the catching.</p>
        </div>
      </div>
      {error ? <ErrorState message={error} onRetry={load} /> : !data ? (
        <div className="kpis" role="status" aria-label="Loading results">{[0, 1, 2].map((i) => <div key={i} className="card kpi"><Skeleton h={12} w="50%" /><Skeleton h={30} w="60%" r={10} /></div>)}</div>
      ) : !data.available || !s ? (
        <div className="card"><EmptyState icon={FlaskConical} title="No evaluation results yet" text="Run `python -m eval.run_eval --write` in the backend to generate them." /></div>
      ) : (
        <>
          <section className="eval-kpis" aria-label="Evaluation summary">
            <div className="card kpi tone-green">
              <div className="kpi-top"><span>Fraud and errors caught</span></div>
              <div className="kpi-value">{s.fraud_caught} <span className="of">/ {s.fraud_total}</span></div>
              <Meter value={s.fraud_caught} total={s.fraud_total} tone="green" />
              <div className="kpi-sub">Caught means not paid automatically: blocked, or held for a person.</div>
            </div>
            <div className="card kpi tone-green">
              <div className="kpi-top"><span>Valid invoices wrongly held</span></div>
              <div className="kpi-value">{s.valid_wrongly_held} <span className="of">/ {s.valid_total}</span></div>
              <Meter value={s.valid_total - s.valid_wrongly_held} total={s.valid_total} tone="green" />
              <div className="kpi-sub">Good invoices that should have been paid but were stopped.</div>
            </div>
            <div className="card kpi tone-grey">
              <div className="kpi-top"><span>Fraudulent money stopped</span></div>
              <div className="kpi-value">{inrShort(s.fraud_stopped_paise)}</div>
              <div className="kpi-sub">{inr(s.fraud_stopped_paise)} of {inr(s.fraud_amount_paise)}. Valid invoices paid: {inr(s.valid_paid_paise)}.</div>
            </div>
          </section>

          <div className="card table-card">
            <table className="tbl eval-tbl">
              <caption className="sr-only">Evaluation results, one row per labelled invoice</caption>
              <thead>
                <tr><th scope="col">Case</th><th scope="col">Label</th><th scope="col" className="num">Amount</th><th scope="col">Which check caught it</th><th scope="col">Result</th></tr>
              </thead>
              <tbody>
                {data.cases.map((c) => (
                  <tr key={c.file}>
                    <td className="c-name">
                      <span className="cell-name">{c.n}. {CATEGORY[c.category] ?? c.category}</span>
                      <span className="cell-sub" style={{ display: "block" }}>{c.supplier} · {c.invoice_number}</span>
                    </td>
                    <td className="c-date"><span className={`badge badge-sm tone-${c.is_fraud ? "red" : "green"}`}>{c.is_fraud ? "Fraud or error" : "Valid"}</span></td>
                    <td className="num c-amt cell-amt">{inr(c.amount_paise)}</td>
                    <td className="c-gst">
                      {c.primary_check ? (
                        <>
                          <span className="cell-name" style={{ fontSize: "0.9rem" }}>{c.primary_check}</span>
                          {c.checks.length > 1 && <span className="cell-sub" style={{ display: "block" }}>also: {c.checks.slice(1).map((x) => x.name).join(", ")}</span>}
                        </>
                      ) : <span className="muted">Nothing raised: every check passed</span>}
                    </td>
                    <td className="c-status">
                      <span style={{ display: "grid", gap: 4, justifyItems: "start" }}>
                        <StatusBadge status={c.status} />
                        <span className={`verdict ${c.correct ? "ok" : "no"}`}>
                          {c.correct ? <CheckCircle2 size={14} aria-hidden="true" /> : <XCircle size={14} aria-hidden="true" />}
                          {c.correct ? (c.is_fraud ? "Caught" : "Paid, as it should be") : (c.is_fraud ? "Missed" : "Wrongly held")}
                        </span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <section className="card card-pad eval-notes" aria-labelledby="h-method">
            <h2 id="h-method">How this was measured</h2>
            <p>{data.method}</p>
            <p>Generated {fmtDateTime(data.generated_at)} by <code>{data.generator}</code>. A test fails if this file ever differs from a fresh run, so this page cannot drift from the code.</p>
            <p className="muted"><strong>Read it honestly:</strong> this is a small, hand-built set of {s.cases} invoices made to exercise each check, not a measurement of production accuracy. Wrong tax type and wrong GST total are <em>held</em> for a person (they can be honest mistakes); the rest are <em>blocked</em>.</p>
          </section>
        </>
      )}
    </>
  );
}
