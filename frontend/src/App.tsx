import { useCallback, useEffect, useState } from "react";
import { api, AppConfig, Invoice, Summary } from "./api";
import InvoiceDrawer from "./Drawer";
import { useRoute, useTheme } from "./lib";
import AgentPage from "./pages/Agent";
import ApprovalsPage from "./pages/Approvals";
import AuditPage from "./pages/Audit";
import Dashboard from "./pages/Dashboard";
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

  useEffect(() => {
    reload();
    api.config().then(setCfg).catch(() => undefined);
  }, [reload]);

  const runDemo = async () => {
    setConfirmReload(false);
    setDemoBusy(true);
    setDemoError(null);
    try {
      const r = await api.runSamples();
      const c = r.summary.counts;
      toast(r.throttled ? r.note ?? "Demo data was loaded recently." : `Loaded ${r.processed} invoices: ${c.PAID ?? 0} paid, ${c.BLOCKED ?? 0} blocked, ${c.HELD ?? 0} on hold.`, "green");
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
    <Shell page={route.page} cfg={cfg} heldCount={held.length} theme={theme} toggleTheme={toggleTheme} onLoadDemo={() => setConfirmReload(true)} demoBusy={demoBusy}>
      {error && <div style={{ marginBottom: 16 }}><ErrorState message={`Could not reach the server: ${error}`} onRetry={reload} /></div>}
      {route.page === "dashboard" && <Dashboard invoices={invoices} summary={summary} loaded={loaded} reload={reload} open={open} />}
      {route.page === "invoices" && <InvoicesPage invoices={invoices} reload={reload} openId={route.invoiceId} open={open} />}
      {route.page === "approvals" && <ApprovalsPage held={held} reload={reload} open={open} />}
      {route.page === "agent" && <AgentPage reload={reload} />}
      {route.page === "suppliers" && <SuppliersPage />}
      {route.page === "audit" && <AuditPage invoices={invoices} />}
      {route.page === "invoices" && route.invoiceId && drawerInvoice && <InvoiceDrawer key={drawerInvoice.id} invoice={drawerInvoice} onClose={close} reload={reload} />}
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
