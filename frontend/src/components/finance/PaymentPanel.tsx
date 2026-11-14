'use client';

import { useRef, useState } from 'react';
import { Invoice, ProofInput, currency, financeApi, newRequestKey, readProof } from '@/lib/finance';
import { Field, actionClass, fieldClass, secondaryClass } from './FinanceInputs';

const today = () => { const date = new Date(); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`; };

export default function PaymentPanel({ invoice, onUpdated, onReceipt }: { invoice: Invoice; onUpdated: (invoice: Invoice) => Promise<void>; onReceipt: (paymentId?: string) => void }) {
  const [payment, setPayment] = useState({ amount: '', method: 'bank_transfer', reference: '', paid_on: today() });
  const [proof, setProof] = useState<ProofInput | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const requestKey = useRef('');
  const fileInput = useRef<HTMLInputElement>(null);
  return <section className="finance-card space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-semibold">Payment history</h2><p className="mt-1 text-sm text-slate-500">Record payments and keep the supporting screenshot with each transaction.</p></div>{invoice.payments.length > 0 && <button className={secondaryClass} onClick={() => onReceipt()}>Combined receipt</button>}</div>
    {!invoice.payments.length && <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">No payments recorded yet.</p>}
    {invoice.payments.map(p => <div key={p.id} className="flex flex-wrap justify-between gap-3 rounded-xl border border-slate-200 p-4 text-sm"><div><strong className="text-base">{currency(p.amount_minor)}</strong><p className="mt-1 text-slate-500">{p.paid_on} · {p.method.replaceAll('_', ' ')}</p><p className="mt-1 break-words">{p.reference}</p></div><div className="flex flex-wrap items-center gap-2">{p.proof && <a className={secondaryClass} target="_blank" rel="noreferrer" href={`/api/finance/invoices/${invoice.id}/payments/${p.id}/proof`}>View screenshot</a>}<button className={secondaryClass} onClick={() => onReceipt(p.id)}>Receipt</button></div></div>)}
    {error && <p role="alert" className="finance-error">{error}</p>}{notice && <p role="status" className="finance-notice">{notice}</p>}
    {invoice.status === 'issued' && invoice.balance_minor > 0 && <form onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError(''); setNotice('');
      try {
        if (!proof) throw new Error('Attach a payment screenshot first.');
        if (!requestKey.current) requestKey.current = newRequestKey();
        const updated = await financeApi<Invoice>(`invoices/${invoice.id}/payments`, 'POST', { ...payment, proof, revision: invoice.revision, request_key: requestKey.current });
        await onUpdated(updated); requestKey.current = ''; setPayment({ ...payment, amount: '', reference: '' }); setProof(null); if (fileInput.current) fileInput.current.value = ''; setNotice('Payment recorded. Your receipt is ready.');
      } catch (error) { setError((error as Error).message); } finally { setBusy(false); }
    }}><fieldset disabled={busy} className="grid gap-4 sm:grid-cols-2">
      <Field label="Amount received (NGN)"><input required className={fieldClass} type="number" min="0.01" step="0.01" max={invoice.balance_minor / 100} value={payment.amount} onChange={event => setPayment({ ...payment, amount: event.target.value })} /></Field>
      <Field label="Payment method"><select className={fieldClass} value={payment.method} onChange={event => setPayment({ ...payment, method: event.target.value })}>{['bank_transfer', 'cash', 'pos', 'other'].map(method => <option key={method} value={method}>{method.replaceAll('_', ' ')}</option>)}</select></Field>
      <Field label="Payment date"><input required className={fieldClass} type="date" max={today()} value={payment.paid_on} onChange={event => setPayment({ ...payment, paid_on: event.target.value })} /></Field>
      <Field label="Transaction / receipt reference"><input required className={fieldClass} value={payment.reference} onChange={event => setPayment({ ...payment, reference: event.target.value })} /></Field>
      <div className="sm:col-span-2"><Field label="Payment screenshot (required)"><input ref={fileInput} required type="file" accept="image/png,image/jpeg,image/webp" className={fieldClass} onChange={async event => {
        setProof(null); setError(''); const file = event.target.files?.[0]; if (!file) return;
        setBusy(true); try { setProof(await readProof(file)); } catch (error) { setError((error as Error).message); if (fileInput.current) fileInput.current.value = ''; } finally { setBusy(false); }
      }} /></Field><p className="mt-2 text-xs text-slate-500">PNG, JPEG or WebP, up to 4 MB. Stored privately for staff; excluded from customer receipts.</p>{proof && <p className="mt-2 text-sm text-blue-800">Ready to attach: {proof.name}</p>}</div>
      <div className="sm:col-span-2"><button className={actionClass} disabled={!proof}>{busy ? 'Saving…' : 'Record payment'}</button></div>
    </fieldset></form>}
  </section>;
}
