'use client';

import { FormEvent, ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { Account, Address, Category, Customer, Device, EntryInput, Calculation, Invoice, Preview,
  categories, currency, emptyAddress, emptyCustomer, financeApi, newEntry, newRequestKey, groupEntries, entriesToTasks, taskPayload, taskQuantity, pendingNames, vehicleName } from '@/lib/finance';
import './print.css';

const fieldClass = 'mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900';
const actionClass = 'rounded-lg bg-[#414095] px-4 py-2 text-sm font-medium text-white hover:bg-[#333078] disabled:opacity-50 disabled:cursor-not-allowed';
const secondaryClass = 'rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm text-[#414095] hover:bg-indigo-50 disabled:opacity-50';
function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block text-sm font-medium text-gray-700">{label}{children}</label>;
}

function CustomerPicker({ onAccount, onProfile, disabled = false }: {
  onAccount: (id: number) => Promise<void>; onProfile?: (profile: Customer) => void; disabled?: boolean;
}) {
  const [term, setTerm] = useState('');
  const [results, setResults] = useState<{ accounts: Account[]; profiles: Customer[] } | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function search(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { setResults(await financeApi(`customers?term=${encodeURIComponent(term)}`)); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="space-y-3">
    <form onSubmit={search} className="flex flex-wrap items-end gap-2">
      <div className="grow"><Field label="Find a customer by name, email or phone"><input className={fieldClass} value={term} onChange={e => setTerm(e.target.value)} /></Field></div>
      <button className={secondaryClass} disabled={disabled || busy}>{busy ? 'Searching...' : 'Find customer'}</button>
    </form>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {results && <div className="max-h-64 overflow-auto rounded-lg border divide-y">
      {!results.accounts.length && !results.profiles.length && <p className="p-3 text-sm">No customers found. You can enter new customer details below.</p>}
      {results.accounts.map(a => <button key={a.id} type="button" disabled={disabled || busy} className="block w-full p-3 text-left text-sm hover:bg-indigo-50" onClick={async () => {
        setBusy(true); setError('');
        try { await onAccount(a.id); setResults(null); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
      }}><strong>{a.name}</strong> · {a.email}<span className="block text-gray-500">Traccar account #{a.id}</span></button>)}
      {onProfile && results.profiles.filter(p => !results.accounts.some(a => a.id === p.traccar_user_id)).map(p =>
        <button key={p.profile_id} type="button" disabled={disabled || busy} className="block w-full p-3 text-left text-sm hover:bg-indigo-50" onClick={async () => {
          setBusy(true); setError('');
          try { if (p.traccar_user_id) await onAccount(p.traccar_user_id); else onProfile(p); setResults(null); }
          catch (err) { setError((err as Error).message); } finally { setBusy(false); }
        }}><strong>{p.name}</strong> · {p.email}<span className="block text-gray-500">Saved billing profile</span></button>)}
    </div>}
  </div>;
}

function VehiclePicker({ devices, selected, onChange }: { devices: Device[]; selected: string[]; onChange: (ids: string[]) => void }) {
  const [search, setSearch] = useState('');
  const matches = devices.filter(device => `${device.name} ${device.imei}`.toLowerCase().includes(search.toLowerCase()));
  return <div className="space-y-2">
    <Field label="Find vehicles for this task"><input className={fieldClass} value={search} onChange={event => setSearch(event.target.value)} placeholder="Search vehicle name or IMEI" /></Field>
    <div className="flex flex-wrap items-center gap-3 text-sm"><button type="button" className={secondaryClass} disabled={!matches.length} onClick={() => onChange([...new Set([...selected, ...matches.map(device => String(device.id))])])}>Select all matching ({matches.length})</button><button type="button" className={secondaryClass} disabled={!selected.length} onClick={() => onChange([])}>Clear selection</button><span>{selected.length} account vehicles selected</span></div>
    <div className="max-h-52 overflow-y-auto rounded-lg border p-3 grid gap-2 sm:grid-cols-2">
      {!matches.length && <p className="text-sm text-gray-500">No matching account vehicles. You can name pending vehicles below.</p>}
      {matches.map(device => <label key={device.id} className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={selected.includes(String(device.id))} onChange={event => onChange(event.target.checked ? [...selected, String(device.id)] : selected.filter(id => id !== String(device.id)))} /><span>{device.name}<span className="block text-xs text-gray-500">IMEI {device.imei}</span></span></label>)}
    </div>
  </div>;
}

function InvoicePaper({ invoice }: { invoice: Preview & Partial<Invoice> }) {
  return <article className="invoice-paper space-y-6 rounded-xl border bg-white p-5 sm:p-9 text-gray-900">
    <div className="flex flex-wrap justify-between gap-4 border-b pb-5">
      <div><h2 className="text-2xl font-bold text-[#414095]">ROIE TECHNOLOGIES</h2><p className="text-sm text-gray-500">Customer invoice · NGN</p></div>
      <div><h3 className="text-xl font-semibold">{invoice.number || 'DRAFT INVOICE'}</h3>
        <p className="text-sm capitalize">{invoice.status || 'Review before saving'}</p>
        {invoice.issued_at && <p className="text-sm">Issued: {new Date(invoice.issued_at).toLocaleDateString()}</p>}
        {invoice.due_date && <p className="text-sm">Due: {invoice.due_date}</p>}
      </div>
    </div>
    <div><p className="text-xs uppercase tracking-wide text-gray-500">Bill to</p><h3 className="font-semibold text-lg">{invoice.customer.name}</h3>
      <p>{invoice.customer.email}</p><p>{invoice.customer.phone}</p><p className="whitespace-pre-line">{invoice.customer.formatted_address}</p>
    </div>
    <div className="space-y-6">{(['installation', 'renewal', 'maintenance'] as Category[]).map(category => {
      const groups = groupEntries(invoice.entries).filter(group => group.category === category);
      if (!groups.length) return null;
      const title = category === 'installation' ? 'Installations' : category === 'renewal' ? 'Renewal' : 'Maintenance';
      return <section className="invoice-task space-y-4" key={category}>
        <h4 className="invoice-task-heading bg-indigo-50 p-3 font-semibold">{title}</h4>
        {groups.map((group, index) => <div className="invoice-rate-group" key={index}>
          {group.activity && <p className="mb-2 text-sm text-gray-600">{group.activity}</p>}
          {groups.length > 1 && <p className="mb-2 text-xs text-gray-500">Rate group {index + 1} - {currency(group.unit_total_minor)} per vehicle</p>}
          <table className="invoice-breakdown w-full text-sm"><thead><tr className="border-b text-left text-gray-500"><th className="p-2">Breakdown</th><th className="p-2 text-right">Qty</th><th className="p-2 text-right">Unit price</th><th className="p-2 text-right">Total</th></tr></thead>
            <tbody>{group.breakdown.map(part => <tr key={part.label} className="border-b border-gray-100"><td className="p-2">{part.label}</td><td className="p-2 text-right tabular-nums">{group.entries.length}</td><td className="p-2 text-right tabular-nums">{currency(part.amount_minor)}</td><td className="p-2 text-right tabular-nums">{currency(part.amount_minor * group.entries.length)}</td></tr>)}</tbody>
          </table>
          <div className="invoice-vehicles mt-3 text-sm leading-relaxed"><strong>Vehicles for {title.toLowerCase()} ({group.entries.length}): </strong>
            {group.entries.map((entry, vehicleIndex) => <span key={entry.id || vehicleIndex}>{vehicleIndex > 0 ? ', ' : ''}<span className="invoice-vehicle-name">{vehicleName(entry)}{!entry.device ? ' (device pending)' : ''}</span></span>)}
          </div>
          {groups.length > 1 && <p className="mt-2 text-right text-sm font-medium">Rate group total: {currency(group.total_minor)}</p>}
        </div>)}
        <p className="invoice-task-subtotal flex justify-between gap-3 border-t pt-3 font-semibold"><span>{title} subtotal</span><span>{currency(groups.reduce((sum, group) => sum + group.total_minor, 0))}</span></p>
      </section>;
    })}</div>
    <div className="invoice-totals ml-auto max-w-sm space-y-2 border-t pt-4"><p className="flex justify-between text-xl font-bold"><span>Total</span><span>{currency(invoice.total_minor)}</span></p>
      {invoice.paid_minor !== undefined && <><p className="flex justify-between"><span>Paid</span><span>{currency(invoice.paid_minor)}</span></p><p className="flex justify-between font-semibold"><span>Balance</span><span>{currency(invoice.balance_minor || 0)}</span></p></>}
    </div>
    {invoice.notes && <p className="whitespace-pre-wrap border-t pt-4 text-sm">{invoice.notes}</p>}
    <p className="text-xs text-gray-500">{invoice.status === 'void' ? 'VOID — this invoice is cancelled.' : invoice.status !== 'issued' ? 'Draft for review. This is not an issued invoice.' : 'Payment records are shown separately in your account history.'}</p>
  </article>;
}

export default function FinancePage() {
  const { auth_loading, authenticated } = useAuth();
  const [mode, setMode] = useState<'list' | 'form' | 'detail'>('list');
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [selected, setSelected] = useState<Invoice | null>(null);
  const [customer, setCustomer] = useState<Customer>(emptyCustomer);
  const [devices, setDevices] = useState<Device[]>([]);
  const [traccarPhone, setTraccarPhone] = useState('');
  const [entries, setEntries] = useState<EntryInput[]>([newEntry()]);
  const [notes, setNotes] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [calculation, setCalculation] = useState<Calculation | null>(null);
  const [calculationError, setCalculationError] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [filter, setFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [payment, setPayment] = useState({ amount: '', method: 'bank_transfer', reference: '', paid_on: new Date().toISOString().slice(0, 10) });
  const [linkDevices, setLinkDevices] = useState<Record<string, string>>({});
  const [voidReason, setVoidReason] = useState('');
  const requestKey = useRef('');
  const paymentKey = useRef('');
  const initialized = useRef(false);

  const refresh = useCallback(async () => {
    const data = await financeApi<{ invoices: Invoice[] }>('invoices'); setInvoices(data.invoices);
  }, []);
  const loadAccount = useCallback(async (id: number) => {
    const data = await financeApi<{ customer: Customer; devices: Device[]; traccar_phone: string }>(`customers/${id}`);
    setCustomer({ ...data.customer, address: { ...emptyAddress(), ...data.customer.address } });
    setDevices(data.devices); setTraccarPhone(data.traccar_phone); setPreview(null);
    setEntries(previous => previous.map(e => ({ ...e, device_ids: [] })));
    return data;
  }, []);
  const openInvoice = useCallback(async (id: string) => {
    const invoice = await financeApi<Invoice>(`invoices/${id}`);
    setSelected(invoice); setMode('detail'); setDevices([]); setLinkDevices({}); setVoidReason('');
    setPayment({ amount: '', method: 'bank_transfer', reference: '', paid_on: new Date().toISOString().slice(0, 10) });
    paymentKey.current = newRequestKey();
    if (invoice.customer.traccar_user_id) {
      const data = await financeApi<{ devices: Device[] }>(`customers/${invoice.customer.traccar_user_id}`);
      setDevices(data.devices);
    }
  }, []);
  useEffect(() => {
    if (!authenticated || initialized.current) return;
    initialized.current = true;
    setBusy(true);
    const params = new URLSearchParams(window.location.search);
    (async () => {
      await refresh();
      if (params.get('invoice')) { await openInvoice(params.get('invoice')!); return; }
      if (params.get('user_id')) {
        await loadAccount(Number(params.get('user_id')));
        if (params.get('device_id')) setEntries([{ ...newEntry(), device_ids: [params.get('device_id')!] }]);
      }
      if (params.get('new')) { requestKey.current = newRequestKey(); setMode('form'); }
    })().catch(err => setError(err.message)).finally(() => setBusy(false));
  }, [authenticated, refresh, loadAccount, openInvoice]);

  useEffect(() => {
    setPreview(null);
  }, [customer, entries, notes, dueDate]);
  useEffect(() => {
    if (mode !== 'form') return;
    let active = true;
    setCalculation(null); setCalculationError('');
    const timer = setTimeout(() => {
      financeApi<Calculation>('calculate', 'POST', { entries: taskPayload(entries) })
        .then(data => { if (active) setCalculation(data); })
        .catch(err => { if (active) setCalculationError(err.message); });
    }, 350);
    return () => { active = false; clearTimeout(timer); };
  }, [entries, mode]);

  async function run(task: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('');
    try { await task(); } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  function startNew() {
    setSelected(null); setCustomer(emptyCustomer()); setDevices([]); setTraccarPhone('');
    setEntries([newEntry()]); setNotes(''); setDueDate(''); setPreview(null); setError(''); setNotice('');
    requestKey.current = newRequestKey(); setMode('form');
  }
  function updateEntry(index: number, update: Partial<EntryInput>) {
    setEntries(previous => previous.map((entry, i) => i === index ? { ...entry, ...update } : entry));
  }
  const payload = () => ({ customer, entries: taskPayload(entries), notes, due_date: dueDate, request_key: requestKey.current, revision: selected?.revision });
  async function save() {
    const invoice = await financeApi<Invoice>(selected ? `invoices/${selected.id}` : 'invoices', selected ? 'PUT' : 'POST', payload());
    setSelected(invoice); setMode('detail'); setPreview(null); await refresh();
    setNotice('Draft saved. Review the invoice, then finalize it.');
  }
  async function action(endpoint: string, body: object) {
    if (!selected) return;
    const result = await financeApi<Invoice>(`invoices/${selected.id}/${endpoint}`, 'POST', { revision: selected.revision, ...body });
    setSelected(result); await refresh();
  }
  async function editDraft() {
    if (!selected) return;
    if (selected.customer.traccar_user_id) await loadAccount(selected.customer.traccar_user_id);
    else setDevices([]);
    setCustomer(selected.customer); setNotes(selected.notes); setDueDate(selected.due_date);
    setEntries(entriesToTasks(selected.entries));
    requestKey.current = selected.request_key; setPreview(null); setMode('form');
  }

  if (auth_loading) return <p className="p-8 text-center">Checking session...</p>;
  if (!authenticated) return null;
  const filtered = invoices.filter(i => (statusFilter === 'all' || i.status === statusFilter || (i.status === 'issued' && i.payment_status === statusFilter)) &&
    `${i.number || 'draft'} ${i.customer.name} ${i.customer.email} ${i.entries.map(e => `${vehicleName(e)} ${e.activity}`).join(' ')}`.toLowerCase().includes(filter.toLowerCase()));
  const issued = filtered.filter(i => i.status === 'issued');
  return <main className="finance-page min-h-screen bg-gray-50 px-4 py-8 sm:px-8 text-gray-900">
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="finance-no-print flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-3xl font-bold text-[#414095]">Finance</h1><p className="mt-1 text-sm text-gray-500">Invoices, customer billing and payment history</p></div>
        <div className="flex gap-2"><button disabled={busy} className={secondaryClass} onClick={() => run(async () => { await refresh(); setMode('list'); })}>All invoices</button><button disabled={busy} className={actionClass} onClick={startNew}>Generate invoice</button></div>
      </div>
      {error && <p role="alert" className="finance-no-print rounded-lg bg-red-50 p-4 text-red-800">{error}</p>}
      {notice && <p role="status" className="finance-no-print rounded-lg bg-green-50 p-4 text-green-800">{notice}</p>}
      {busy && <p role="status" className="finance-no-print text-sm text-indigo-700">Working...</p>}

      {mode === 'list' && <>
        <div className="grid gap-4 sm:grid-cols-3">{[['Invoiced', issued.reduce((s, i) => s + i.total_minor, 0)], ['Received', issued.reduce((s, i) => s + i.paid_minor, 0)], ['Outstanding', issued.reduce((s, i) => s + i.balance_minor, 0)]].map(([label, total]) =>
          <div key={label} className="rounded-xl border bg-white p-5"><p className="text-sm text-gray-500">{label}</p><p className="mt-2 text-2xl font-semibold text-[#414095]">{currency(Number(total))}</p></div>)}</div>
        <p className="text-xs text-gray-500">Totals reflect the current filters and exclude drafts and void invoices.</p>
        <div className="flex flex-wrap gap-3"><div className="grow"><Field label="Search invoice, customer, vehicle or activity"><input className={fieldClass} value={filter} onChange={e => setFilter(e.target.value)} /></Field></div><Field label="Status"><select className={fieldClass} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>{['all', 'draft', 'issued', 'unpaid', 'partial', 'paid', 'void'].map(s => <option key={s} value={s}>{s}</option>)}</select></Field></div>
        <div className="overflow-x-auto rounded-xl border bg-white"><table className="w-full text-left text-sm"><thead className="bg-indigo-50 text-[#414095]"><tr>{['Invoice', 'Customer / activity', 'Total', 'Balance', 'Status', ''].map((h, i) => <th key={i} className="p-4">{h}</th>)}</tr></thead><tbody>
          {filtered.map(i => <tr key={i.id} className="border-t"><td className="p-4 font-medium">{i.number || 'Draft'}<span className="block text-xs text-gray-500">{new Date(i.created_at).toLocaleDateString()}</span></td><td className="p-4">{i.customer.name}<span className="block text-xs text-gray-500">{i.entries.map(vehicleName).join(' · ')}</span></td><td className="p-4 whitespace-nowrap">{currency(i.total_minor)}</td><td className="p-4 whitespace-nowrap">{i.status === 'issued' ? currency(i.balance_minor) : '—'}</td><td className="p-4 capitalize">{i.status === 'issued' ? i.payment_status : i.status}</td><td className="p-4"><button disabled={busy} className={secondaryClass} onClick={() => run(() => openInvoice(i.id))}>Open</button></td></tr>)}
          {!filtered.length && <tr><td colSpan={6} className="p-10 text-center text-gray-500">No invoices found. Generate an invoice to get started.</td></tr>}
        </tbody></table></div>
      </>}

      {mode === 'form' && <div className="space-y-6">
        <section className="rounded-xl border bg-white p-5 space-y-4">
          <h2 className="text-xl font-semibold text-[#414095]">1. Customer &amp; billing details</h2>
          <CustomerPicker disabled={busy} onAccount={async id => { await loadAccount(id); }} onProfile={p => { setCustomer(p); setDevices([]); setEntries(previous => previous.map(e => ({ ...e, device_ids: [] }))); }} />
          <p className="text-sm text-gray-500">{customer.traccar_user_id ? `Linked to Traccar customer #${customer.traccar_user_id}` : 'New customer billing profile. You can link a Traccar account after onboarding.'}</p>
          <fieldset disabled={busy} className="grid gap-4 sm:grid-cols-2">
            {(['name', 'email', 'phone'] as const).map(key => <Field key={key} label={`${key === 'name' ? 'Customer name' : key === 'email' ? 'Email' : 'Phone number'} *`}><input className={fieldClass} type={key === 'email' ? 'email' : key === 'phone' ? 'tel' : 'text'} value={customer[key]} onChange={e => setCustomer({ ...customer, [key]: e.target.value })} /></Field>)}
            {customer.traccar_user_id && <div className="self-end"><button type="button" className={secondaryClass} disabled={!customer.phone || customer.phone === traccarPhone} onClick={() => run(async () => {
              const data = await financeApi<{ phone: string }>(`customers/${customer.traccar_user_id}/phone`, 'POST', { phone: customer.phone, expected_phone: traccarPhone });
              setTraccarPhone(data.phone); setCustomer({ ...customer, phone: data.phone }); setNotice('Customer phone updated in Traccar.');
            })}>Update phone in Traccar</button><p className="mt-1 text-xs text-gray-500">Only the phone number is updated in Traccar.</p></div>}
            {(Object.entries({ line1: 'Street address *', line2: 'Address line 2', city: 'City *', state: 'State / region *', postal_code: 'Postal code', country: 'Country *' }) as [keyof Address, string][]).map(([key, label]) => <Field key={key} label={label}><input className={fieldClass} value={customer.address[key]} onChange={e => setCustomer({ ...customer, address: { ...customer.address, [key]: e.target.value } })} /></Field>)}
          </fieldset>
          <p className="text-xs text-gray-500">Billing details are saved for future invoices. Existing issued invoices keep their original details.</p>
        </section>
        <section className="rounded-xl border bg-white p-5 space-y-4">
          <h2 className="text-xl font-semibold text-[#414095]">2. Tasks &amp; vehicles</h2>
          <p className="text-sm text-gray-500">Choose a task, set its price per vehicle, then select all vehicles for that task. Quantity is counted automatically.</p>
          {entries.map((entry, index) => <fieldset disabled={busy} key={index} className="rounded-xl border p-4 space-y-4">
            <div className="flex items-center justify-between"><h3 className="font-medium">Task {index + 1} - {taskQuantity(entry)} vehicles / activities</h3>{entries.length > 1 && <button className="text-sm text-red-700" onClick={() => setEntries(entries.filter((_, i) => i !== index))}>Remove task</button>}</div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Invoice category"><select className={fieldClass} value={entry.category} onChange={e => { const category = e.target.value as Category; updateEntry(index, { category, total: categories[category].defaultTotal }); }}>{Object.entries(categories).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}</select></Field>
              <Field label="Negotiated price per vehicle (NGN)"><input className={fieldClass} type="number" min={entry.category === 'installation' ? '15000' : '0.01'} step="0.01" value={entry.total} onChange={e => updateEntry(index, { total: e.target.value })} /></Field>
              <Field label="Quantity (from vehicle list)"><input className={fieldClass} readOnly value={taskQuantity(entry)} /></Field>
              <Field label="Activity / service period (optional)"><input className={fieldClass} placeholder="e.g. Annual renewal for 2027" value={entry.activity} onChange={e => updateEntry(index, { activity: e.target.value })} /></Field>
            </div>
            <VehiclePicker devices={devices} selected={entry.device_ids} onChange={ids => updateEntry(index, { device_ids: ids })} />
            <Field label="Vehicles / activities without devices (comma-separated)"><textarea className={fieldClass} rows={2} placeholder="e.g. New Corolla, New Hilux" value={entry.pending_vehicles} onChange={e => updateEntry(index, { pending_vehicles: e.target.value })} /></Field>
            <p className="text-xs text-gray-500">Name each pending vehicle separately. You can link its device after installation. Each name counts as one unit.</p>
            <p className="rounded-lg bg-gray-50 p-3 text-sm leading-relaxed break-words"><strong>Vehicles ({taskQuantity(entry)}): </strong>{[...entry.device_ids.map(id => devices.find(device => String(device.id) === id)?.name || `Device #${id}`), ...pendingNames(entry.pending_vehicles)].join(', ') || 'Select vehicles or enter their names above.'}</p>
            <p className="text-xs text-gray-500">{entry.category === 'installation' ? 'Per vehicle: GPRS 8.6% (minimum NGN 12,000), server 2.4% (minimum NGN 3,000). Split the remainder 14:75 between installation and device.' : entry.category === 'renewal' ? 'Per vehicle: GPRS fee 80% / Server fee 20%' : 'Per vehicle: Service fee 60% / Logistics 40%'}</p>
            {calculation?.entries[index] && <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="bg-indigo-50 text-left"><tr><th className="p-2">Breakdown</th><th className="p-2 text-right">Qty</th><th className="p-2 text-right">Unit price</th><th className="p-2 text-right">Total</th></tr></thead><tbody>{calculation.entries[index].breakdown.map(part => <tr key={part.label} className="border-b"><td className="p-2">{part.label}</td><td className="p-2 text-right">{calculation.entries[index].quantity}</td><td className="p-2 text-right">{currency(part.unit_amount_minor)}</td><td className="p-2 text-right">{currency(part.amount_minor)}</td></tr>)}</tbody></table><p className="mt-3 text-right font-semibold">Task subtotal: {currency(calculation.entries[index].total_minor)}</p></div>}
          </fieldset>)}
          <button disabled={busy || entries.length >= 50} className={secondaryClass} onClick={() => setEntries([...entries, newEntry()])}>Add task</button>
          {calculationError && <p role="alert" className="text-sm text-red-700">{calculationError}</p>}
          {calculation && <p className="text-right text-xl font-semibold">Invoice total: {currency(calculation.total_minor)}</p>}
        </section>
        <section className="rounded-xl border bg-white p-5 space-y-4"><h2 className="text-xl font-semibold text-[#414095]">3. Review &amp; save</h2>
          <fieldset disabled={busy} className="grid gap-4 sm:grid-cols-2"><Field label="Due date (optional)"><input type="date" className={fieldClass} value={dueDate} onChange={e => setDueDate(e.target.value)} /></Field><Field label="Customer notes / payment instructions"><textarea className={fieldClass} rows={3} value={notes} maxLength={2000} onChange={e => setNotes(e.target.value)} /></Field></fieldset>
          <button disabled={busy} className={actionClass} onClick={() => run(async () => { setPreview(await financeApi<Preview>('preview', 'POST', payload())); })}>Review invoice</button>
        </section>
        {preview && <><InvoicePaper invoice={{ ...preview, notes, due_date: dueDate }} /><div className="flex justify-end"><button disabled={busy} className={actionClass} onClick={() => run(save)}>Confirm details &amp; save draft</button></div></>}
      </div>}

      {mode === 'detail' && selected && <>
        <div className="finance-no-print flex flex-wrap gap-2">
          <button className={secondaryClass} disabled={busy} onClick={() => run(() => openInvoice(selected.id))}>Reload invoice &amp; devices</button>
          <button className={secondaryClass} disabled={busy} onClick={() => window.print()}>Print / save PDF</button>
          {selected.status === 'draft' && <><button className={secondaryClass} disabled={busy} onClick={() => run(editDraft)}>Edit draft</button><button className={actionClass} disabled={busy} onClick={() => run(async () => { await action('finalize', {}); setNotice('Invoice finalized. Its billing details and prices are now fixed.'); })}>Finalize invoice</button></>}
        </div>
        <InvoicePaper invoice={selected} />
        <div className="finance-no-print space-y-6">
          {!selected.customer.traccar_user_id && selected.status !== 'void' && <section className="rounded-xl border bg-white p-5 space-y-3"><h2 className="text-lg font-semibold">Link customer after onboarding</h2><p className="text-sm text-gray-500">Choose the customer account that owns this invoice. Printed billing details stay unchanged.</p><CustomerPicker disabled={busy} onAccount={async id => { await run(async () => { await action('link-customer', { user_id: id }); const data = await financeApi<{ devices: Device[] }>(`customers/${id}`); setDevices(data.devices); }); }} /></section>}
          {selected.status !== 'void' && selected.entries.some(e => !e.device) && <section className="rounded-xl border bg-white p-5 space-y-4"><h2 className="text-lg font-semibold">Vehicle links</h2><p className="text-sm text-gray-500">After installation, assign the device to the customer in the usual workflow, then reload this invoice to link it. This adds a finance reference only.</p>
            {selected.entries.filter(e => !e.device).map(e => <div key={e.id} className="flex flex-wrap items-end gap-3"><div className="grow"><Field label={`${categories[e.category].label} · ${vehicleName(e)}`}><select className={fieldClass} value={linkDevices[e.id] || ''} disabled={busy} onChange={event => setLinkDevices({ ...linkDevices, [e.id]: event.target.value })}><option value="">Select a customer device</option>{devices.map(d => <option key={d.id} value={d.id}>{d.name} · {d.imei}</option>)}</select></Field></div><button disabled={busy || !linkDevices[e.id]} className={secondaryClass} onClick={() => run(async () => { await action('link-device', { entry_id: e.id, device_id: linkDevices[e.id] }); })}>Link device</button></div>)}
          </section>}
          <section className="rounded-xl border bg-white p-5 space-y-4"><h2 className="text-lg font-semibold">Payment history</h2><p className="text-sm text-gray-500">Payments apply to this invoice and its listed vehicles / activities. Recording a payment does not charge the customer or renew Traccar service.</p>
            {!selected.payments.length && <p className="text-sm text-gray-500">No payments recorded.</p>}
            {selected.payments.map(p => <div key={p.id} className="flex flex-wrap justify-between gap-2 border-t py-3 text-sm"><div><strong>{currency(p.amount_minor)}</strong> · {p.paid_on} · {p.method.replaceAll('_', ' ')}<p className="text-gray-500">{p.reference} · Recorded by {p.recorded_by.name}</p></div></div>)}
            {selected.status === 'issued' && selected.balance_minor > 0 && <form onSubmit={event => { event.preventDefault(); run(async () => {
              if (!paymentKey.current) paymentKey.current = newRequestKey();
              await action('payments', { ...payment, request_key: paymentKey.current });
              paymentKey.current = newRequestKey(); setPayment({ ...payment, amount: '', reference: '' }); setNotice('Payment recorded.');
            }); }}><fieldset disabled={busy} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Field label="Amount received (NGN)"><input required className={fieldClass} type="number" min="0.01" max={selected.balance_minor / 100} step="0.01" value={payment.amount} onChange={e => setPayment({ ...payment, amount: e.target.value })} /></Field>
              <Field label="Payment method"><select className={fieldClass} value={payment.method} onChange={e => setPayment({ ...payment, method: e.target.value })}>{['bank_transfer', 'cash', 'pos', 'other'].map(m => <option key={m} value={m}>{m.replaceAll('_', ' ')}</option>)}</select></Field>
              <Field label="Payment date"><input required className={fieldClass} type="date" max={new Date().toISOString().slice(0, 10)} value={payment.paid_on} onChange={e => setPayment({ ...payment, paid_on: e.target.value })} /></Field>
              <Field label="Transaction / receipt reference"><input required className={fieldClass} value={payment.reference} onChange={e => setPayment({ ...payment, reference: e.target.value })} /></Field>
              <button className={actionClass}>Record payment</button>
            </fieldset></form>}
          </section>
          <section className="rounded-xl border bg-white p-5 space-y-3"><h2 className="text-lg font-semibold">Invoice activity</h2>{selected.events.map((e, index) => <p key={index} className="text-sm text-gray-600">{new Date(e.at).toLocaleString()} · {e.action.replaceAll('_', ' ')} · {e.actor.name}{e.reason && ` · ${e.reason}`}</p>)}</section>
          {selected.status !== 'void' && !selected.payments.length && <details className="rounded-xl border bg-white p-5"><summary className="cursor-pointer text-sm text-red-700">Cancel this invoice</summary><form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={event => { event.preventDefault(); run(async () => { await action('void', { reason: voidReason }); setNotice('Invoice voided. The record remains in finance history.'); }); }}><div className="grow"><Field label="Reason for cancellation"><input required className={fieldClass} value={voidReason} onChange={e => setVoidReason(e.target.value)} /></Field></div><button disabled={busy} className={secondaryClass}>Void invoice</button></form></details>}
        </div>
      </>}
    </div>
  </main>;
}
