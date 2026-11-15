'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Invoice, categories, currency, financeApi, statusLabel } from '@/lib/finance';

export default function FinanceHistory({ userId }: { userId: string | number }) {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    financeApi<{ invoices: Invoice[] }>(`invoices?user_id=${encodeURIComponent(userId)}`)
      .then(data => { if (active) setInvoices(data.invoices); })
      .catch(err => { if (active) setError(err.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [userId]);
  const issued = invoices.filter(invoice => invoice.status === 'issued');
  return <section aria-label="Finance records" className="min-w-0 space-y-5 text-sm">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-slate-500">Invoices and payments for this customer.</p>
      <Link className="rounded-lg border border-blue-200 px-3 py-2 font-medium text-blue-700 hover:bg-blue-50 focus-visible:outline-2 focus-visible:outline-blue-600" href={`/finance?user_id=${userId}&new=1`}>Generate invoice</Link>
    </div>
    {loading ? <p role="status" className="text-slate-500">Loading finance history...</p> : error ? <p role="alert" className="text-red-700">{error}</p> : <>
      <div className="grid gap-3 sm:grid-cols-2">
        <p className="min-w-0 rounded-xl bg-slate-50 p-4 text-slate-500">Received<strong className="mt-1 block break-words text-lg text-slate-900">{currency(issued.reduce((sum, invoice) => sum + invoice.paid_minor, 0))}</strong></p>
        <p className="min-w-0 rounded-xl bg-blue-50 p-4 text-blue-700">Outstanding<strong className="mt-1 block break-words text-lg text-blue-950">{currency(issued.reduce((sum, invoice) => sum + invoice.balance_minor, 0))}</strong></p>
      </div>
      {!invoices.length && <p className="rounded-xl border border-dashed border-slate-200 p-5 text-slate-500">No finance records yet.</p>}
      <div className="space-y-2">{invoices.map(invoice => <Link key={invoice.id} className="block rounded-xl border border-slate-200 p-4 transition-colors hover:border-blue-300 hover:bg-blue-50/40 focus-visible:outline-2 focus-visible:outline-blue-600" href={`/finance?invoice=${invoice.id}`}>
        <div className="flex flex-wrap items-start justify-between gap-2"><strong className="break-all text-blue-900">{invoice.number || 'Draft'}</strong><span className="font-semibold text-slate-900">{currency(invoice.total_minor)}</span></div>
        <p className="mt-2 text-slate-600">{[...new Set(invoice.entries.map(entry => categories[entry.category].label))].join(', ')}</p>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs"><span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-700">{invoice.status === 'issued' ? statusLabel(invoice.payment_status) : invoice.status}</span><span className="text-slate-500">{new Date(invoice.created_at).toLocaleDateString()}</span></div>
      </Link>)}</div>
    </>}
  </section>;
}
