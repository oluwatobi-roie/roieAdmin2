'use client';
import { useEffect, useState } from 'react';
import { CustomerSummary, financeApi } from '@/lib/finance';

export default function CustomerProfileSummary({ userId }: { userId: string | number }) {
  const [summary, setSummary] = useState<CustomerSummary | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setSummary(null); setError('');
    financeApi<CustomerSummary>(`customers/${encodeURIComponent(userId)}/summary`)
      .then(data => { if (active) setSummary(data); })
      .catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [userId]);
  return <div className="border-t border-slate-100 pt-3 text-sm" aria-label="Account summary">
    {error ? <p role="alert" className="text-red-700">{error}</p> : !summary ? <p className="text-slate-500">Loading account summary…</p> :
      <div className="flex items-start justify-between gap-4"><strong className="text-slate-800">{summary.vehicle_count} {summary.vehicle_count === 1 ? 'Asset' : 'Assets'}</strong><span className="text-right font-medium text-blue-800">{summary.unpaid_invoice_count === 0 ? 'No unpaid invoices' : `${summary.unpaid_invoice_count} unpaid invoice${summary.unpaid_invoice_count === 1 ? '' : 's'}`}</span></div>}
  </div>;
}
