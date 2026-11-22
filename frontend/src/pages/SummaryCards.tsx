import { inrShort, Invoice, Summary } from "../api";

export default function SummaryCards({ summary, invoices }: { summary: Summary | null; invoices: Invoice[] }) {
  const s = summary;
  const gstCaught = invoices.filter((i) => i.status !== "PAID" && i.gst_report?.some((c) => !c.ok)).length;
  const cards: [string, string, string, string][] = [
    ["Paid", inrShort(s?.total_paid_paise ?? 0), `${s?.counts.PAID ?? 0} invoices passed every check`, "ok"],
    ["Blocked", inrShort(s?.total_blocked_paise ?? 0), `${s?.counts.BLOCKED ?? 0} invoices stopped`, "bad"],
    ["On hold", inrShort(s?.total_held_paise ?? 0), `${s?.counts.HELD ?? 0} waiting for you`, "warn"],
    ["Fraud and errors stopped", inrShort(s?.money_saved_paise ?? 0), `${gstCaught} caught by GST checks`, "saved"],
  ];
  return (
    <section className="cards" aria-label="Summary">
      {cards.map(([title, value, sub, tone]) => (
        <div key={title} className={`card ${tone}`}>
          <div className="card-title">{title}</div>
          <div className="card-value">{value}</div>
          <div className="card-sub">{sub}</div>
        </div>
      ))}
    </section>
  );
}
