import { Fragment, useCallback, useEffect, useState } from "react";
import { api, AppConfig, Business, Invoice, setBusiness, Summary } from "./api";
import InvoiceDrawer from "./Drawer";
import { useRoute, useTheme } from "./lib";
import AgentPage from "./pages/Agent";
import ApprovalsPage from "./pages/Approvals";
import AuditPage from "./pages/Audit";
import Dashboard from "./pages/Dashboard";
import EvaluationPage from "./pages/Evaluation";
import InvoicesPage from "./pages/Invoices";
import Landing from "./pages/Landing";
import SuppliersPage from "./pages/Suppliers";
import Shell from "./Shell";
import { ConfirmDialog, ErrorState, Skeleton, ToastProvider, useToast } from "./ui";

function Root() {
  const toast = useToast();
  const [route, go] = useRoute();
  const [theme, toggleTheme] = useTheme();
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [cfg, setCfg] = useState<AppConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [demoBusy, setDemoBusy] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);
  const [confirmReload, setConfirmReload] = useState(false);
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [businessId, setBusinessId] = useState<number>(() => {
    try { const n = Number(window.localStorage.getItem("ig-business")); return n > 0 ? n : 1; } catch { return 1; }
  });
  setBusiness(businessId); // every API call below is for this client business

  const reload = useCallback(async () => {
    try {
      const [inv, sum] = await Promise.all([api.invoices(), api.summary()]);
      setInvoices(inv);
      setSummary(sum);
      setError(null);
      setLoaded(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const loadBusinesses = useCallback(async () => {
    try {
      const list = await api.businesses();
      setBusinesses(list);
      return list;
    } catch {
      return [] as Business[];
    }
  }, []);

  useEffect(() => {
    (async () => {
      const list = await loadBusinesses();
      if (list.length && !list.some((b) => b.id === businessId)) { setBusiness(1); setBusinessId(1); }  // a remembered id that no longer exists
      reload();
      api.config().then(setCfg).catch(() => undefined);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload]);

  const switchBusiness = async (id: number) => {
    setBusiness(id);
    setBusinessId(id);
    try { window.localStorage.setItem("ig-business", String(id)); } catch { /* not remembered */ }
    setLoaded(false);
    setInvoices([]);
    setSummary(null);
    go(route.page === "invoices" ? "invoices" : route.page); // closes any open invoice drawer
    await Promise.all([reload(), api.config().then(setCfg).catch(() => undefined), loadBusinesses()]);
    const name = businesses.find((b) => b.id === id)?.name;
    if (name) toast(`Switched to ${name}.`, "grey");
  };

  const runDemo = async () => {
    setConfirmReload(false);
    setDemoBusy(true);
    setDemoError(null);
    try {
      const r = await api.runSamples();
      const c = r.summary.counts;
      const list = await loadBusinesses();
      toast(r.throttled ? r.note ?? "Demo data was loaded recently."
        : `Loaded ${r.processed} invoices across ${list.length || 2} client businesses. ${businesses.find((b) => b.id === businessId)?.short_name ?? "This business"}: ${c.PAID ?? 0} paid, ${c.BLOCKED ?? 0} blocked, ${c.HELD ?? 0} on hold.`, "green");
      go("dashboard");
    } catch (e) {
      setDemoError((e as Error).message);
      toast(`Demo failed: ${(e as Error).message}`, "red");
    }
    setDemoBusy(false);
    await reload();
  };

  const held = invoices.filter((i) => i.status === "HELD");
  const open = (id: number) => go("invoices", id);
  const close = () => go("invoices");
  const drawerInvoice = route.invoiceId ? invoices.find((i) => i.id === route.invoiceId) ?? null : null;

  // First visit (nothing loaded yet): show the landing page, never an empty dashboard.
  if (!loaded && !error)
    return <div className="content" role="status" aria-label="Loading"><Skeleton h={40} w="40%" /><p className="muted" style={{ margin: "16px 0" }}>Loading… the free server can take up to a minute to wake up.</p><Skeleton h={160} r={14} /></div>;
  if (!loaded && error)
    return <div className="content"><ErrorState message={`Could not reach the server: ${error}`} onRetry={reload} /></div>;
  if (invoices.length === 0)
    return <Landing theme={theme} toggleTheme={toggleTheme} onDemo={runDemo} busy={demoBusy} error={demoError} />;

  return (
    <Shell page={route.page} cfg={cfg} businesses={businesses} businessId={businessId} onBusiness={switchBusiness} heldCount={held.length} theme={theme} toggleTheme={toggleTheme} onLoadDemo={() => setConfirmReload(true)} demoBusy={demoBusy}>
      <Fragment key={businessId}>
      {error && <div style={{ marginBottom: 16 }}><ErrorState message={`Could not reach the server: ${error}`} onRetry={reload} /></div>}
      {route.page === "dashboard" && <Dashboard invoices={invoices} summary={summary} loaded={loaded} reload={reload} open={open} />}
      {route.page === "invoices" && <InvoicesPage invoices={invoices} reload={reload} openId={route.invoiceId} open={open} />}
      {route.page === "approvals" && <ApprovalsPage held={held} reload={reload} open={open} />}
      {route.page === "agent" && <AgentPage reload={reload} />}
      {route.page === "suppliers" && <SuppliersPage />}
      {route.page === "audit" && <AuditPage invoices={invoices} />}
      {route.page === "evaluation" && <EvaluationPage />}
      {route.page === "invoices" && route.invoiceId && drawerInvoice && <InvoiceDrawer key={drawerInvoice.id} invoice={drawerInvoice} onClose={close} reload={reload} />}
      </Fragment>
      {confirmReload && (
        <ConfirmDialog title="Reload the demo data?" confirmLabel="Reload demo data" onConfirm={runDemo} onCancel={() => setConfirmReload(false)}
          body="This clears all invoices and the audit log, then processes the 13 sample invoices again." />
      )}
    </Shell>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <Root />
    </ToastProvider>
  );
}
