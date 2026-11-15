'use client';
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { Account, Device, Invoice, Receipt, categories, currency, financeApi, statusLabel, vehicleName } from '@/lib/finance';
import InvoiceWizard from '@/components/finance/InvoiceWizard';
import { InvoicePaper, ReceiptPaper } from '@/components/finance/InvoiceDocument';
import PaymentPanel from '@/components/finance/PaymentPanel';
import { CustomerPicker, Field, actionClass, fieldClass, secondaryClass } from '@/components/finance/FinanceInputs';
import './print.css';

const tasksLabel = (invoice: Invoice) => [...new Set(invoice.entries.map(entry => categories[entry.category].label))].join(', ');
export default function FinancePage() {
  const { auth_loading, authenticated } = useAuth();
  const [mode, setMode] = useState<'list' | 'form' | 'detail' | 'receipt'>('list');
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [selected, setSelected] = useState<Invoice | null>(null);
  const [editing, setEditing] = useState<Invoice | null>(null);
  const [userId, setUserId] = useState<number>();
  const [deviceId, setDeviceId] = useState<string>();
  const [devices, setDevices] = useState<Device[]>([]);
  const [links, setLinks] = useState<Record<string, string>>({});
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [canCancel, setCanCancel] = useState(false);
  const [reason, setReason] = useState('');
  const [filter, setFilter] = useState('');
  const [status, setStatus] = useState('all');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => { const result = await financeApi<{ invoices: Invoice[] }>('invoices'); setInvoices(result.invoices); }, []);
  const openInvoice = useCallback(async (invoice: Invoice) => {
    setSelected(invoice); setMode('detail'); setError(''); setReason(''); setLinks({}); setDevices([]);
    if (invoice.customer.traccar_user_id) {
      try { setDevices((await financeApi<{ devices: Device[] }>(`customers/${invoice.customer.traccar_user_id}`)).devices); } catch (err) { setError((err as Error).message); }
    }
  }, []);
  useEffect(() => {
    if (!authenticated) return;
    let active = true;
    async function load() {
      try {
        const [list, permissions] = await Promise.all([financeApi<{ invoices: Invoice[] }>('invoices'), financeApi<{ can_cancel: boolean }>('permissions')]);
        if (!active) return;
        setInvoices(list.invoices); setCanCancel(permissions.can_cancel);
        const query = new URLSearchParams(window.location.search);
        if (query.get('invoice')) await openInvoice(await financeApi<Invoice>(`invoices/${query.get('invoice')}`));
        else if (query.get('new')) {
          let id = Number(query.get('user_id')) || undefined;
          const email = query.get('customer_email');
          if (!id && email) { const data = await financeApi<{ accounts: Account[] }>(`customers?term=${encodeURIComponent(email)}`); id = data.accounts.find(account => account.email.toLowerCase() === email.toLowerCase())?.id; }
          if (!active) return;
          setUserId(id); setDeviceId(query.get('device_id') || undefined); setMode('form');
        }
      } catch (err) { if (active) setError((err as Error).message); } finally { if (active) setLoading(false); }
    }
    void load(); return () => { active = false; };
  }, [authenticated, openInvoice]);
  async function run(action: () => Promise<void>) { setBusy(true); setError(''); try { await action(); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }
  async function update(invoice: Invoice) { setSelected(invoice); await refresh(); }
  async function action(path: string, body: object = {}) { if (!selected) return; await update(await financeApi<Invoice>(`invoices/${selected.id}/${path}`, 'POST', { ...body, revision: selected.revision })); }
  async function showReceipt(paymentId?: string) { if (!selected) return; await run(async () => { setReceipt(await financeApi<Receipt>(`invoices/${selected.id}/receipts${paymentId ? `?payment_id=${paymentId}` : ''}`)); setMode('receipt'); window.scrollTo(0, 0); }); }
  if (auth_loading || loading && authenticated) return <main className="p-8 text-center text-slate-500">Loading finance…</main>;
  if (!authenticated) return null;
  const issued = invoices.filter(invoice => invoice.status === 'issued');
  const filtered = invoices.filter(invoice => (status === 'all' || invoice.status === status || invoice.status === 'issued' && invoice.payment_status === status) && `${invoice.number || 'Draft'} ${invoice.customer.name} ${invoice.customer.email} ${tasksLabel(invoice)} ${invoice.entries.map(vehicleName).join(' ')}`.toLowerCase().includes(filter.toLowerCase()));
  return <main className="finance-page min-h-screen bg-slate-50 px-3 py-7 text-slate-800 sm:px-6"><div className="mx-auto max-w-6xl space-y-6">
    {error && <p role="alert" className="finance-error finance-no-print">{error}</p>}
    {mode === 'list' && <>
      <div className="flex flex-wrap items-center justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-widest text-blue-800">RoieTrackers</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">Finance</h1><p className="mt-2 text-sm text-slate-500">Invoices, payments and customer records in one place.</p></div><button className={actionClass} onClick={() => { setSelected(null); setEditing(null); setUserId(undefined); setDeviceId(undefined); setError(''); setMode('form'); }}>Generate invoice</button></div>
      <div className="grid gap-3 sm:grid-cols-3">{[['Invoiced', issued.reduce((sum, invoice) => sum + invoice.total_minor, 0)], ['Received', issued.reduce((sum, invoice) => sum + invoice.paid_minor, 0)], ['Outstanding', issued.reduce((sum, invoice) => sum + invoice.balance_minor, 0)]].map(([label, amount]) => <div key={label} className="finance-card"><p className="text-sm text-slate-500">{label}</p><p className="mt-2 text-xl font-semibold tracking-tight">{currency(Number(amount))}</p></div>)}</div>
      <section className="finance-card space-y-5"><div className="grid gap-4 sm:grid-cols-[1fr_200px]"><Field label="Search invoices"><input className={fieldClass} placeholder="Customer, invoice or vehicle" value={filter} onChange={event => setFilter(event.target.value)} /></Field><Field label="Status"><select className={fieldClass} value={status} onChange={event => setStatus(event.target.value)}>{['all', 'draft', 'unpaid', 'partial', 'paid', 'void'].map(value => <option key={value} value={value}>{value === 'all' ? 'All statuses' : statusLabel(value)}</option>)}</select></Field></div>
        {!filtered.length && <p className="py-8 text-center text-sm text-slate-500">No invoices found. Generate an invoice to get started.</p>}
        <div className="space-y-3">{filtered.map(invoice => <button key={invoice.id} className="invoice-list-row w-full rounded-xl border border-slate-200 p-4 text-left transition hover:border-blue-300 hover:bg-blue-50/30" onClick={() => void run(() => openInvoice(invoice))}><div className="min-w-0"><span className="invoice-list-label">Customer</span><strong className="block break-words text-sm">{invoice.customer.name}</strong><span className="mt-1 block text-xs text-slate-500">{invoice.number || 'Draft invoice'}</span></div><div className="min-w-0"><span className="invoice-list-label">Services</span><span className="block text-sm">{tasksLabel(invoice)}</span></div><div className="invoice-list-amount"><strong className="block text-sm tabular-nums">{currency(invoice.total_minor)}</strong><span className={`mt-2 inline-block rounded-full px-2.5 py-1 text-xs status-${invoice.status === 'issued' ? invoice.payment_status : invoice.status}`}>{invoice.status === 'issued' ? statusLabel(invoice.payment_status) : invoice.status}</span></div></button>)}</div>
      </section>
    </>}
    {mode === 'form' && <InvoiceWizard invoice={editing} userId={userId} deviceId={deviceId} onClose={() => setMode(selected ? 'detail' : 'list')} onSaved={invoice => { void run(async () => { await openInvoice(invoice); await refresh(); }); }} />}
    {mode === 'detail' && selected && <>
      <div className="finance-no-print flex flex-wrap items-center justify-between gap-3"><button className={secondaryClass} onClick={() => setMode('list')}>All invoices</button><div className="flex flex-wrap gap-2"><button className={secondaryClass} disabled={busy} onClick={() => void run(async () => { await openInvoice(await financeApi<Invoice>(`invoices/${selected.id}`)); })}>Reload</button><button className={secondaryClass} onClick={() => window.print()}>Print / save PDF</button>{selected.status === 'draft' && <><button className={secondaryClass} onClick={() => { setEditing(selected); setUserId(undefined); setDeviceId(undefined); setMode('form'); }}>Edit draft</button><button className={actionClass} disabled={busy} onClick={() => void run(() => action('finalize'))}>Finalize invoice</button></>}</div></div>
      <InvoicePaper invoice={selected} />
      <div className="finance-no-print space-y-5">
        {!selected.customer.traccar_user_id && selected.status !== 'void' && <section className="finance-card space-y-3"><h2 className="font-semibold">Link an existing customer account</h2><CustomerPicker disabled={busy} onAccount={async id => { await action('link-customer', { user_id: id }); setDevices((await financeApi<{ devices: Device[] }>(`customers/${id}`)).devices); }} /></section>}
        {selected.status !== 'void' && selected.entries.some(entry => entry.category === 'installation' && !entry.device) && <section className="finance-card space-y-4"><h2 className="font-semibold">Link vehicles after installation</h2><p className="text-sm text-slate-500">Match each pending installation to a vehicle on this customer’s account.</p>{selected.entries.filter(entry => entry.category === 'installation' && !entry.device).map(entry => <form key={entry.id} className="flex flex-wrap items-end gap-3" onSubmit={event => { event.preventDefault(); void run(() => action('link-device', { entry_id: entry.id, device_id: links[entry.id] })); }}><div className="min-w-0 grow"><Field label={vehicleName(entry)}><select required className={fieldClass} value={links[entry.id] || ''} onChange={event => setLinks({ ...links, [entry.id]: event.target.value })}><option value="">Select an account vehicle</option>{devices.map(device => <option key={device.id} value={device.id}>{device.name}</option>)}</select></Field></div><button className={secondaryClass} disabled={busy || !links[entry.id]}>Link device</button></form>)}</section>}
        <PaymentPanel key={selected.id} invoice={selected} onUpdated={update} onReceipt={id => void showReceipt(id)} />
        <details className="finance-card text-sm"><summary className="cursor-pointer font-semibold">Activity history</summary><div className="mt-4 space-y-2">{selected.events.map((event, index) => <p key={index} className="text-slate-500">{new Date(event.at).toLocaleString()} · {event.action.replaceAll('_', ' ')} · {event.actor.name}{event.reason ? ` · ${event.reason}` : ''}</p>)}</div></details>
        {canCancel && selected.status !== 'void' && !selected.paid_minor && <details className="finance-card"><summary className="cursor-pointer text-sm font-medium text-red-800">Cancel invoice</summary><form className="mt-4 space-y-3" onSubmit={event => { event.preventDefault(); void run(() => action('void', { reason })); }}><Field label="Reason for cancellation"><input required maxLength={500} className={fieldClass} value={reason} onChange={event => setReason(event.target.value)} /></Field><p className="text-sm text-slate-500">The invoice will remain in the history, marked as cancelled.</p><button className={secondaryClass} disabled={busy}>Confirm cancellation</button></form></details>}
      </div>
    </>}
    {mode === 'receipt' && receipt && <><div className="finance-no-print flex flex-wrap justify-between gap-3"><button className={secondaryClass} onClick={() => setMode('detail')}>Back to invoice</button><button className={actionClass} onClick={() => window.print()}>Print / save receipt</button></div><ReceiptPaper receipt={receipt} /></>}
  </div></main>;
}
