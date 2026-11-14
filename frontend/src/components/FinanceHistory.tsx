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
  return <details className="mt-4 rounded-2xl border border-slate-200 bg-white p-5 text-sm">
    <summary className="cursor-pointer font-semibold text-blue-900">Finance history</summary>
    <div className="mt-4 space-y-3">
      <Link className="inline-block font-medium text-blue-800 underline" href={`/finance?user_id=${userId}&new=1`}>Generate invoice</Link>
      {loading ? <p>Loading finance history…</p> : error ? <p role="alert" className="text-red-700">{error}</p> : <>
        <div className="grid gap-3 sm:grid-cols-2"><p className="rounded-xl bg-slate-50 p-3 text-slate-500">Received<strong className="mt-1 block text-slate-800">{currency(issued.reduce((sum, invoice) => sum + invoice.paid_minor, 0))}</strong></p><p className="rounded-xl bg-slate-50 p-3 text-slate-500">Outstanding<strong className="mt-1 block text-slate-800">{currency(issued.reduce((sum, invoice) => sum + invoice.balance_minor, 0))}</strong></p></div>
        {!invoices.length && <p className="text-slate-500">No finance records yet.</p>}
        {invoices.map(invoice => <Link key={invoice.id} className="block border-t border-slate-100 pt-3 hover:text-blue-800" href={`/finance?invoice=${invoice.id}`}>
          {invoice.number || 'Draft'} · {currency(invoice.total_minor)} · {invoice.status === 'issued' ? statusLabel(invoice.payment_status) : invoice.status}
          <span className="mt-1 block text-slate-500">{[...new Set(invoice.entries.map(entry => categories[entry.category].label))].join(', ')} · {new Date(invoice.created_at).toLocaleDateString()}</span>
        </Link>)}
      </>}
    </div>
  </details>;
}
