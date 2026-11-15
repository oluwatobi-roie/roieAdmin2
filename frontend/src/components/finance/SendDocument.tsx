"use client";

import { useRef, useState } from 'react';
import { FiMail, FiSend, FiCheckCircle, FiAlertCircle, FiLoader } from 'react-icons/fi';
import { EmailDelivery, Invoice, Receipt, financeApi, newRequestKey } from '@/lib/finance';
import { actionClass, secondaryClass } from './FinanceInputs';

export default function SendDocument({ invoice, receipt, onUpdated }: {
  invoice: Invoice; receipt?: Receipt; onUpdated: (invoice: Invoice) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [confirmResend, setConfirmResend] = useState(false);
  const requestKey = useRef('');
  if (invoice.status !== 'issued') return null;
  const kind = receipt ? 'receipt' : 'invoice';
  const paymentId = receipt?.kind === 'payment' ? receipt.payments[0].id : null;
  const number = receipt?.number || invoice.number;
  const attempts = (invoice.email_deliveries || []).filter(item => item.kind === kind && (item.payment_id || null) === paymentId);
  const latest = attempts.at(-1);
  const uncertain = latest?.state === 'unknown' || latest?.state === 'pending';
  const label = receipt ? receipt.kind === 'payment' ? 'Payment receipt' : 'Combined payment receipt' : 'Invoice';
  async function send() {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    requestKey.current ||= newRequestKey();
    try {
      const result = await financeApi<{ invoice: Invoice; delivery: EmailDelivery }>(`invoices/${invoice.id}/email`, 'POST', {
        kind, payment_id: paymentId, revision: invoice.revision,
        request_key: requestKey.current, confirm_resend: confirmResend,
      });
      await onUpdated(result.invoice);
      setNotice(result.delivery.state === 'sent' ? 'Email sent.' : result.delivery.message);
      if (result.delivery.state === 'sent') setOpen(false);
      requestKey.current = '';
      setConfirmResend(false);
    } catch (err) {
      // Keep this key on a lost response: retry asks for the same operation and
      // cannot send a second message if the backend already accepted it.
      setError((err as Error).message + ' Reload the invoice to check email history if the request timed out.');
    } finally { setBusy(false); }
  }
  return <section aria-label="Email customer document" className="finance-no-print min-w-0 space-y-3">
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
      {latest && <p className="min-w-0 text-xs text-slate-500 sm:mr-auto">{latest.state === 'sent' ? 'Email sent' : latest.state === 'failed' ? 'Last email failed' : 'Email outcome unconfirmed'}: {new Date(latest.requested_at).toLocaleString()}</p>}
      <button type="button" className={`${actionClass} w-full justify-center sm:w-auto`} disabled={busy || !invoice.customer.email} aria-expanded={open} onClick={() => { setOpen(!open); setError(''); }}>
        <FiMail aria-hidden="true" />Send to customer
      </button>
    </div>
    {notice && <p role="status" className={`flex items-start gap-2 rounded-xl border p-3 text-sm ${latest?.state === 'sent' ? 'border-blue-200 bg-blue-50 text-blue-900' : 'border-amber-200 bg-amber-50 text-amber-900'}`}>{latest?.state === 'sent' ? <FiCheckCircle className="mt-0.5 shrink-0" aria-hidden="true" /> : <FiAlertCircle className="mt-0.5 shrink-0" aria-hidden="true" />}{notice}</p>}
    {open && <div className="finance-card min-w-0 space-y-4 border-blue-200">
      <div><h2 className="font-semibold">Email {label.toLowerCase()}</h2><p className="mt-1 break-all text-sm text-slate-600">To: <strong>{invoice.customer.email}</strong></p><p className="mt-1 break-words text-xs text-slate-500">PDF attachment: {number}.pdf</p></div>
      {uncertain && <label className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900"><input type="checkbox" className="mt-1" checked={confirmResend} onChange={event => setConfirmResend(event.target.checked)} />I checked the sender&apos;s mailbox. Send another copy if the previous request cannot be confirmed.</label>}
      {latest?.state === 'sent' && <p className="text-sm text-slate-600">This email was already sent. Confirm to send another copy.</p>}
      {error && <p role="alert" className="finance-error break-words">{error}</p>}
      <div className="flex flex-wrap gap-2"><button type="button" className={`${actionClass} flex-1 justify-center sm:flex-none`} disabled={busy || (uncertain && !confirmResend)} onClick={() => void send()}>{busy ? <FiLoader className="animate-spin" aria-hidden="true" /> : <FiSend aria-hidden="true" />}{busy ? 'Sending...' : 'Confirm send'}</button><button type="button" className={secondaryClass} disabled={busy} onClick={() => setOpen(false)}>Cancel</button></div>
    </div>}
    {attempts.length > 0 && <details className="text-xs text-slate-500"><summary className="cursor-pointer py-1">Email history ({attempts.length})</summary><ul className="mt-2 space-y-2">{[...attempts].reverse().map(item => <li key={item.id} className="break-words rounded-lg border border-slate-200 bg-white p-3"><strong>{item.state === 'sent' ? 'Email sent' : item.state === 'failed' ? 'Not sent' : 'Unconfirmed'}</strong> &middot; {new Date(item.requested_at).toLocaleString()}<span className="mt-1 block break-all">{item.recipient} &middot; {item.document_number}</span><span className="mt-1 block">{item.state === 'sent' ? 'Email sent.' : item.message}</span></li>)}</ul></details>}
  </section>;
}
