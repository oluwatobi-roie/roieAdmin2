'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { CustomerSummary, Invoice, categories, currency, financeApi, statusLabel } from '@/lib/finance';

export default function FinanceHistory({ userId, deviceId }: { userId: string | number; deviceId?: string | number }) {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [summary, setSummary] = useState<CustomerSummary | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    Promise.all([financeApi<{ invoices: Invoice[] }>(`invoices?user_id=${encodeURIComponent(userId)}${deviceId ? `&device_id=${encodeURIComponent(deviceId)}` : ''}`), financeApi<CustomerSummary>(`customers/${encodeURIComponent(userId)}/summary`)])
      .then(([data, stats]) => { if (active) { setInvoices(data.invoices); setSummary(stats); } })
      .catch(err => { if (active) setError(err.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [userId, deviceId]);
  const issued = invoices.filter(i => i.status === 'issued');
  return <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-5 text-sm space-y-3">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 className="font-semibold text-teal-800">Finance &amp; payment history</h3>
      <Link className="text-teal-800 underline" href={`/finance?user_id=${userId}${deviceId ? `&device_id=${deviceId}` : ''}&new=1`}>Generate invoice</Link>
    </div>
    {loading ? <p>Loading finance history...</p> : error ? <p role="alert" className="text-red-700">{error}</p> : <>
      {summary && <div className="grid grid-cols-2 gap-3"><div className="rounded-xl bg-slate-50 p-4"><p className="text-xs text-slate-500">Vehicles on account</p><strong className="mt-1 block text-xl text-slate-800">{summary.vehicle_count}</strong></div><div className="rounded-xl bg-slate-50 p-4"><p className="text-xs text-slate-500">Finance status · whole account</p><strong className="mt-1 block text-base text-teal-800">{statusLabel(summary.finance_status)}</strong><p className="mt-1 text-xs text-slate-500">Outstanding: {currency(summary.balance_minor)}</p></div></div>}
      <p>Received: <strong>{currency(issued.reduce((s, i) => s + i.paid_minor, 0))}</strong> · Outstanding: <strong>{currency(issued.reduce((s, i) => s + i.balance_minor, 0))}</strong></p>
      {deviceId && <p className="text-gray-500">Totals cover whole invoices containing this vehicle; payments are recorded per invoice.</p>}
      {!invoices.length && <p className="text-gray-500">No finance records yet.</p>}
      {invoices.map(i => <Link key={i.id} className="block border-t pt-2 hover:text-teal-800" href={`/finance?invoice=${i.id}`}>
        {i.number || 'Draft'} · {currency(i.total_minor)} · {i.status === 'issued' ? i.payment_status : i.status}
        <span className="block text-gray-500">{[...new Set(i.entries.map(entry => categories[entry.category].label))].join(', ')} · {new Date(i.created_at).toLocaleDateString()}</span>
      </Link>)}
    </>}
  </section>;
}
