'use client';
import { useEffect, useRef, useState } from 'react';
import { Address, Calculation, Category, Customer, Device, Discount, EntryInput, Invoice, Preview, categories, currency, emptyAddress, emptyCustomer, entriesToTasks, financeApi, newEntry, newRequestKey, noDiscount, pendingNames, taskPayload, taskQuantity } from '@/lib/finance';
import { CustomerPicker, Field, VehiclePicker, actionClass, fieldClass, secondaryClass } from './FinanceInputs';
import { InvoicePaper } from './InvoiceDocument';

const steps = ['Customer', 'Task', 'Task list', 'Terms', 'Review'];
export default function InvoiceWizard({ invoice, userId, deviceId, onSaved, onClose }: { invoice: Invoice | null; userId?: number; deviceId?: string; onSaved: (invoice: Invoice) => void; onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [customer, setCustomer] = useState<Customer>(emptyCustomer);
  const [devices, setDevices] = useState<Device[]>([]);
  const [accountPhone, setAccountPhone] = useState('');
  const [tasks, setTasks] = useState<EntryInput[]>(invoice ? entriesToTasks(invoice.entries) : []);
  const [task, setTask] = useState<EntryInput>(newEntry);
  const [editing, setEditing] = useState<number | null>(null);
  const [dueDate, setDueDate] = useState(invoice?.due_date || '');
  const [notes, setNotes] = useState(invoice?.notes || '');
  const [discount, setDiscount] = useState<Discount>(invoice?.discount || noDiscount());
  const [preview, setPreview] = useState<Preview | null>(null);
  const [calculation, setCalculation] = useState<Calculation | null>(null);
  const [calculationError, setCalculationError] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const requestKey = useRef(invoice?.request_key || '');
  async function chooseCustomer(id: number) {
    const data = await financeApi<{ customer: Customer; devices: Device[]; account_phone: string }>(`customers/${id}`);
    setCustomer({ ...data.customer, address: { ...emptyAddress(), ...data.customer.address } });
    setAccountPhone(data.account_phone); setDevices(data.devices); setTasks([]); setTask(newEntry()); setEditing(null); setPreview(null);
  }
  useEffect(() => {
    let active = true;
    const id = invoice?.customer.traccar_user_id || userId;
    if (!id) return;
    setBusy(true);
    financeApi<{ customer: Customer; devices: Device[]; account_phone: string }>(`customers/${id}`).then(data => {
      if (!active) return;
      setCustomer({ ...data.customer, ...(invoice ? { phone: invoice.customer.phone, address: invoice.customer.address } : {}), address: { ...emptyAddress(), ...(invoice?.customer.address || data.customer.address) } });
      setAccountPhone(data.account_phone); setDevices(data.devices);
      if (!invoice && deviceId && data.devices.some(d => String(d.id) === deviceId)) setTask({ ...newEntry(), device_ids: [deviceId] });
    }).catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [invoice, userId, deviceId]);
  useEffect(() => {
    let active = true;
    setCalculation(null); setCalculationError('');
    const entries = step === 1 ? [task] : tasks;
    if (!entries.length || step === 0 || step === 4 || (step === 1 && !taskQuantity(task))) return;
    const timer = setTimeout(() => {
      financeApi<Calculation>('calculate', 'POST', { entries: taskPayload(entries), discount: step === 1 ? noDiscount() : discount }).then(data => { if (active) setCalculation(data); }).catch(err => { if (active) setCalculationError(err.message); });
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [step, task, tasks, discount]);
  function navigate(value: number) { setError(''); setNotice(''); setStep(value); window.scrollTo({ top: 0, behavior: 'smooth' }); }
  async function run(action: () => Promise<void>) { setBusy(true); setError(''); setNotice(''); try { await action(); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }
  const payload = (entries = tasks) => ({ customer, entries: taskPayload(entries), discount, due_date: dueDate, notes });
  const totals = calculation && <div className="rounded-xl bg-slate-50 p-4 text-sm space-y-2"><p className="flex justify-between gap-4"><span>Subtotal</span><strong>{currency(calculation.subtotal_minor)}</strong></p>{calculation.discount_minor > 0 && <p className="flex justify-between gap-4"><span>Discount</span><span>−{currency(calculation.discount_minor)}</span></p>}<p className="flex justify-between gap-4 text-base"><span>{step === 1 ? 'Task total' : 'Invoice total'}</span><strong>{currency(calculation.total_minor)}</strong></p></div>;
  return <div className="space-y-5">
    <div className="finance-no-print flex flex-wrap items-center justify-between gap-3"><div><h1 className="text-2xl font-semibold tracking-tight">{invoice ? 'Edit invoice' : 'Generate invoice'}</h1><p className="mt-1 text-sm text-slate-500">Step {step + 1} of 5 · {steps[step]}</p></div><button className={secondaryClass} onClick={onClose} disabled={busy}>Close</button></div>
    <ol className="finance-no-print grid grid-cols-5 gap-1 sm:gap-3" aria-label="Invoice progress">{steps.map((label, index) => <li key={label} aria-current={step === index ? 'step' : undefined} className={`rounded-lg px-1 py-3 text-center text-xs sm:text-sm ${step === index ? 'bg-teal-800 text-white' : index < step ? 'bg-teal-50 text-teal-900' : 'bg-slate-100 text-slate-500'}`}>{index + 1}<span className="mt-1 block">{label}</span></li>)}</ol>
    {error && <p role="alert" className="finance-error">{error}</p>}{notice && <p role="status" className="finance-notice">{notice}</p>}
    {step === 0 && <section className="finance-card space-y-6">
      <div><h2 className="text-lg font-semibold">Customer details</h2><p className="mt-1 text-sm text-slate-500">Choose an existing account. The last saved billing address is reused.</p></div>
      <CustomerPicker onAccount={chooseCustomer} disabled={busy} />
      {customer.traccar_user_id && <form onSubmit={event => { event.preventDefault(); void run(async () => { const result = await financeApi<{ customer: Customer }>('validate-customer', 'POST', { customer }); setCustomer(result.customer); navigate(tasks.length ? 2 : 1); }); }}><fieldset disabled={busy} className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2"><Field label="Customer name"><input className={fieldClass} readOnly value={customer.name} /></Field><Field label="Email"><input className={fieldClass} readOnly value={customer.email} /></Field></div>
        <div className="grid gap-4 sm:grid-cols-2"><Field label="Phone number"><input required className={fieldClass} type="tel" value={customer.phone} onChange={event => setCustomer({ ...customer, phone: event.target.value })} /></Field><div className="self-end"><button type="button" className={secondaryClass} disabled={!customer.phone || customer.phone === accountPhone} onClick={() => void run(async () => { const result = await financeApi<{ phone: string }>(`customers/${customer.traccar_user_id}/phone`, 'POST', { phone: customer.phone, expected_phone: accountPhone }); setAccountPhone(result.phone); setCustomer({ ...customer, phone: result.phone }); setNotice('Phone updated in RoieTrackers.'); })}>Update phone in RoieTrackers</button></div></div>
        <div className="grid gap-4 sm:grid-cols-2">{([['line1', 'Street address', true], ['line2', 'Address line 2', false], ['city', 'City', true], ['state', 'State / region', true], ['postal_code', 'Postal code', false], ['country', 'Country', true]] as [keyof Address, string, boolean][]).map(([key, label, required]) => <Field key={key} label={label}><input required={required} className={fieldClass} value={customer.address[key]} onChange={event => setCustomer({ ...customer, address: { ...customer.address, [key]: event.target.value } })} /></Field>)}</div>
        <p className="text-xs text-slate-500">Billing address changes are saved with the invoice. Use the phone update button to also update the account.</p><button className={actionClass}>Next: {tasks.length ? 'task list' : 'task'}</button>
      </fieldset></form>}
    </section>}
    {step === 1 && <form className="finance-card space-y-5" onSubmit={event => { event.preventDefault(); void run(async () => {
      if (!taskQuantity(task)) throw new Error('Select at least one vehicle, or enter an installation count.');
      const next = editing === null ? [...tasks, task] : tasks.map((value, index) => index === editing ? task : value);
      await financeApi('preview', 'POST', { ...payload(next), discount: noDiscount() }); setTasks(next); setEditing(null); navigate(2);
    }); }}><fieldset disabled={busy} className="space-y-5">
      <h2 className="text-lg font-semibold">{editing === null ? 'Add a task' : 'Edit task'}</h2>
      <div className="grid gap-4 sm:grid-cols-2"><Field label="Task category"><select className={fieldClass} value={task.category} onChange={event => { const category = event.target.value as Category; setTask({ ...newEntry(), category, total: categories[category].defaultTotal }); }}>{Object.entries(categories).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}</select></Field><Field label={task.category === 'special' ? 'Amount (NGN)' : 'Negotiated price per vehicle (NGN)'}><input className={fieldClass} required type="number" min={task.category === 'installation' ? 15000 : 0.01} step="0.01" value={task.total} onChange={event => setTask({ ...task, total: event.target.value })} /></Field></div>
      {task.category === 'special' ? <div className="space-y-4"><Field label="Item"><input required maxLength={200} className={fieldClass} value={task.item} onChange={event => setTask({ ...task, item: event.target.value })} /></Field><Field label="Description"><textarea required maxLength={2000} rows={3} className={fieldClass} value={task.description} onChange={event => setTask({ ...task, description: event.target.value })} /></Field></div> : <>
        {task.category === 'installation' && <div className="rounded-xl bg-teal-50 p-4 space-y-2"><Field label="Number of vehicles awaiting installation"><input className={fieldClass} type="number" min="0" max="1000" step="1" value={task.pending_count + pendingNames(task.pending_vehicles).length} onChange={event => setTask({ ...task, pending_count: Number(event.target.value), pending_vehicles: '' })} /></Field><p className="text-sm text-teal-900">Enter the number of new vehicles, select already installed vehicles below, or use both. Pending vehicles can be linked after installation.</p></div>}
        <VehiclePicker devices={devices} selected={task.device_ids} onChange={device_ids => setTask({ ...task, device_ids })} />
        <p className="text-sm font-medium">Task quantity: {taskQuantity(task)} vehicle{taskQuantity(task) === 1 ? '' : 's'}</p>
        <Field label="Activity / service period (optional)"><input maxLength={500} className={fieldClass} value={task.activity} onChange={event => setTask({ ...task, activity: event.target.value })} /></Field>
      </>}
      <Field label="Task notes (optional)"><textarea rows={3} maxLength={2000} className={fieldClass} value={task.task_notes} onChange={event => setTask({ ...task, task_notes: event.target.value })} /></Field>
      {calculationError && <p role="alert" className="finance-error">{calculationError}</p>}{totals}
      <div className="flex flex-wrap gap-3"><button type="button" className={secondaryClass} onClick={() => navigate(tasks.length ? 2 : 0)}>Back</button><button className={actionClass} disabled={!taskQuantity(task)}>Save task & continue</button></div>
    </fieldset></form>}
    {step === 2 && <section className="finance-card space-y-5"><h2 className="text-lg font-semibold">Tasks on this invoice</h2>{!tasks.length && <p className="text-sm text-slate-500">Add a task to continue.</p>}{tasks.map((entry, index) => <div key={index} className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 p-4"><div className="min-w-0"><h3 className="font-semibold">{categories[entry.category].label}{entry.item ? ` · ${entry.item}` : ''}</h3><p className="text-sm text-slate-500">{taskQuantity(entry)} {entry.category === 'special' ? 'item' : 'vehicles'} × {currency(Math.round(Number(entry.total) * 100))}</p>{entry.task_notes && <p className="mt-2 text-sm break-words">{entry.task_notes}</p>}</div><div className="flex gap-2"><button className={secondaryClass} onClick={() => { setTask(entry); setEditing(index); navigate(1); }}>Edit task</button><button className={secondaryClass} onClick={() => setTasks(tasks.filter((_, i) => i !== index))}>Remove</button></div></div>)}
      <button className={secondaryClass} onClick={() => { setTask(newEntry()); setEditing(null); navigate(1); }}>Add another task</button>{totals}<div className="flex flex-wrap gap-3"><button className={secondaryClass} onClick={() => navigate(0)}>Back: customer</button><button className={actionClass} disabled={!tasks.length} onClick={() => navigate(3)}>Next: due date & discount</button></div>
    </section>}
    {step === 3 && <form className="finance-card" onSubmit={event => { event.preventDefault(); void run(async () => { setPreview(await financeApi<Preview>('preview', 'POST', payload())); navigate(4); }); }}><fieldset disabled={busy} className="space-y-5"><h2 className="text-lg font-semibold">Due date, discount & notes</h2><Field label="Invoice due date"><input className={fieldClass} type="date" value={dueDate} onChange={event => setDueDate(event.target.value)} /></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Discount type"><select className={fieldClass} value={discount.type} onChange={event => setDiscount({ type: event.target.value as Discount['type'], value: '0' })}><option value="none">No discount</option><option value="percent">Percentage (%)</option><option value="amount">Fixed amount (NGN)</option></select></Field>{discount.type !== 'none' && <Field label={discount.type === 'percent' ? 'Discount (%)' : 'Discount (NGN)'}><input required className={fieldClass} type="number" min="0" max={discount.type === 'percent' ? 100 : undefined} step="0.01" value={discount.value} onChange={event => setDiscount({ ...discount, value: event.target.value })} /></Field>}</div><p className="text-sm text-slate-500">Discount is deducted once from the invoice subtotal.</p><Field label="Invoice notes (optional)"><textarea className={fieldClass} rows={3} maxLength={2000} value={notes} onChange={event => setNotes(event.target.value)} /></Field>{calculationError && <p role="alert" className="finance-error">{calculationError}</p>}{totals}<div className="flex flex-wrap gap-3"><button type="button" className={secondaryClass} onClick={() => navigate(2)}>Back: task list</button><button className={actionClass}>Next: review</button></div></fieldset></form>}
    {step === 4 && preview && <><InvoicePaper invoice={{ ...preview, notes, due_date: dueDate }} /><div className="finance-no-print flex flex-wrap gap-3"><button className={secondaryClass} disabled={busy} onClick={() => navigate(3)}>Back: terms</button><button className={actionClass} disabled={busy} onClick={() => void run(async () => { if (!requestKey.current) requestKey.current = newRequestKey(); const saved = await financeApi<Invoice>(invoice ? `invoices/${invoice.id}` : 'invoices', invoice ? 'PUT' : 'POST', { ...payload(), request_key: requestKey.current, ...(invoice ? { revision: invoice.revision } : {}) }); onSaved(saved); })}>{busy ? 'Saving…' : 'Confirm details & save draft'}</button></div></>}
  </div>;
}
