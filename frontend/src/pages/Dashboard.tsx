import { CheckCircle2, ClipboardCheck, PauseCircle, PiggyBank, ReceiptIndianRupee, ShieldX, type LucideIcon } from "lucide-react";
import { useApprovalActions } from "../actions";
import { inr, inrShort, Invoice, Summary } from "../api";
import { hrefFor, useMedia } from "../lib";
import { EmptyState, SkeletonCards } from "../ui";

/** Input tax credit protected: GST on blocked invoices with an invalid GSTIN or GST error. */
function ItcCard({ s }: { s: Summary | null }) {
  const n = s?.itc_protected_count ?? 0;
  const risk = s?.itc_at_risk_paise ?? 0;
  return (
    <div className="card kpi kpi-itc tone-green">
      <div className="kpi-top"><span>ITC protected</span><span className="kpi-icon"><ReceiptIndianRupee size={18} aria-hidden="true" /></span></div>
      <div className="kpi-value">{inr(s?.itc_protected_paise ?? 0)}</div>
      <div className="kpi-sub">GST on {n} blocked {n === 1 ? "invoice" : "invoices"} with an invalid GSTIN or GST error. Paying these would put your input tax credit at risk.</div>
      {risk > 0 && <div className="kpi-note">{inr(risk)} more is at risk on {s?.itc_at_risk_count} held {s?.itc_at_risk_count === 1 ? "invoice" : "invoices"} until you decide.</div>}
    </div>
  );
}

function Kpi({ title, value, sub, tone, Icon, href }: { title: string; value: string; sub: string; tone: string; Icon: LucideIcon; href: string }) {
  return (
    <a className={`card kpi tone-${tone}`} href={href} style={{ textDecoration: "none", color: "inherit" }}>
      <div className="kpi-top"><span>{title}</span><span className="kpi-icon"><Icon size={18} aria-hidden="true" /></span></div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-sub">{sub}</div>
    </a>
  );
}

/** Cumulative money protected (blocked + rejected invoices) by invoice date. Plain SVG, no chart library. */
function ProtectedChart({ invoices }: { invoices: Invoice[] }) {
  const narrow = useMedia("(max-width: 719px)");
  const byDate = new Map<string, number>();
  for (const i of invoices)
    if ((i.status === "BLOCKED" || i.status === "REJECTED") && i.invoice_date && i.total_paise)
      byDate.set(i.invoice_date, (byDate.get(i.invoice_date) ?? 0) + i.total_paise);
  const days = [...byDate.keys()].sort();
  let run = 0;
  const pts = days.map((d) => ({ d, v: (run += byDate.get(d)!) }));
  if (pts.length === 0) return <EmptyState icon={PiggyBank} title="Nothing protected yet" text="Blocked and rejected invoices will show up here as money kept in your account." />;

  const W = narrow ? 320 : 560, H = narrow ? 210 : 250, L = 52, R = 16, T = 12, B = 32;
  const max = pts[pts.length - 1].v;
  const step = niceStep(max / 4) * 100; // paise
  const top = Math.ceil(max / step) * step;
  const x = (i: number) => (pts.length === 1 ? (L + W - R) / 2 : L + (i * (W - L - R)) / (pts.length - 1));
  const y = (v: number) => H - B - (v / top) * (H - B - T);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
  const area = `${line} L${x(pts.length - 1)},${H - B} L${x(0)},${H - B} Z`;
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
  const fmt = (d: string) => new Date(d + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  return (
    <>
      <div className="chart-sum"><strong>{inr(max)}</strong><span className="muted">protected across {byDate.size} invoice dates</span></div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Cumulative money protected, reaching ${inr(max)}`}>
        <defs>
          <linearGradient id="fillg" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="var(--brand)" stopOpacity="0.28" /><stop offset="1" stopColor="var(--brand)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid" x1={L} x2={W - R} y1={y(t)} y2={y(t)} />
            <text x={L - 8} y={y(t) + 4} textAnchor="end">{t === 0 ? "₹0" : inrShort(t)}</text>
          </g>
        ))}
        {pts.length > 1 && <path className="area" d={area} />}
        {pts.length > 1 && <path className="line" d={line} />}
        {pts.map((p, i) => (
          <g key={p.d}>
            <circle className="dot" cx={x(i)} cy={y(p.v)} r="4.5"><title>{`${fmt(p.d)}: ${inr(p.v)} protected so far`}</title></circle>
            {(pts.length <= (narrow ? 4 : 6) || i % 2 === 0 || i === pts.length - 1) && <text x={x(i)} y={H - 10} textAnchor="middle">{fmt(p.d)}</text>}
          </g>
        ))}
      </svg>
      <table className="sr-only">
        <caption>Cumulative money protected by invoice date</caption>
        <tbody>{pts.map((p) => <tr key={p.d}><td>{fmt(p.d)}</td><td>{inr(p.v)}</td></tr>)}</tbody>
      </table>
    </>
  );
}

/** Round a step up to 1, 2, 2.5 or 5 x 10^n so axis labels are tidy (rupees, not paise). */
function niceStep(raw: number): number {
  const rupees = Math.max(raw / 100, 1);
  const p = 10 ** Math.floor(Math.log10(rupees));
  const f = rupees / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
}

export default function Dashboard({ invoices, summary, loaded, reload, open }: {
  invoices: Invoice[]; summary: Summary | null; loaded: boolean; reload: () => Promise<void>; open: (id: number) => void;
}) {
  const { ask, dialog, busyId } = useApprovalActions(reload);
  const held = invoices.filter((i) => i.status === "HELD");
  const s = summary;
  const gstCaught = invoices.filter((i) => i.status !== "PAID" && i.gst_report?.some((c) => !c.ok)).length;
  return (
    <>
      <div className="page-head">
        <div><h1>Dashboard</h1><p>What was paid, what was stopped, and what needs you.</p></div>
      </div>
      {!loaded ? <SkeletonCards /> : (
        <section className="kpis" aria-label="Summary">
          <Kpi title="Paid" tone="green" Icon={CheckCircle2} value={inrShort(s?.total_paid_paise ?? 0)} sub={`${s?.counts.PAID ?? 0} invoices passed every check`} href={hrefFor("invoices")} />
          <Kpi title="Blocked" tone="red" Icon={ShieldX} value={inrShort(s?.total_blocked_paise ?? 0)} sub={`${s?.counts.BLOCKED ?? 0} invoices stopped`} href={hrefFor("invoices")} />
          <Kpi title="On hold" tone="amber" Icon={PauseCircle} value={inrShort(s?.total_held_paise ?? 0)} sub={`${s?.counts.HELD ?? 0} waiting for you`} href={hrefFor("approvals")} />
          <Kpi title="Money saved" tone="grey" Icon={PiggyBank} value={inrShort(s?.money_saved_paise ?? 0)} sub={`${gstCaught} caught by GST checks`} href={hrefFor("invoices")} />
          <ItcCard s={s} />
        </section>
      )}
      <div className="grid-2">
        <section className="card card-pad" aria-labelledby="h-chart">
          <div className="card-head"><div><h2 id="h-chart">Money protected over time</h2><p>Cumulative value of blocked and rejected invoices, by invoice date.</p></div></div>
          <ProtectedChart invoices={invoices} />
        </section>
        <section className="card card-pad" aria-labelledby="h-attn">
          <div className="card-head">
            <div><h2 id="h-attn">Needs your attention</h2><p>{held.length ? `${held.length} invoice${held.length > 1 ? "s" : ""} on hold` : "You are all caught up"}</p></div>
            {held.length > 0 && <a className="linkbtn" href={hrefFor("approvals")}>View all</a>}
          </div>
          {held.length === 0 ? (
            <EmptyState icon={ClipboardCheck} title="Nothing to approve" text="Invoices that need a person will appear here with one-tap actions." />
          ) : (
            <ul className="attn">
              {held.slice(0, 4).map((inv) => (
                <li key={inv.id}>
                  <div className="attn-top"><span className="attn-name">{inv.supplier_name ?? "Unreadable invoice"}</span><span className="attn-amt">{inr(inv.total_paise)}</span></div>
                  <div className="attn-why">{inv.reason}</div>
                  <div className="attn-actions">
                    <button className="btn btn-sm btn-primary" disabled={busyId === inv.id} onClick={() => ask(inv, "approve")}>Approve &amp; pay</button>
                    <button className="btn btn-sm btn-danger" disabled={busyId === inv.id} onClick={() => ask(inv, "reject")}>Reject</button>
                    <button className="btn btn-sm btn-ghost" onClick={() => open(inv.id)}>Details</button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
      {dialog}
    </>
  );
}
