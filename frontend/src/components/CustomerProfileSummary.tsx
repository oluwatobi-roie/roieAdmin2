'use client';
import { useEffect, useState } from 'react';
import { countDeviceHealth, deviceHealthInfo, DeviceHealth, DeviceHealthRecord } from '@/lib/device-status';
import { CustomerSummary, financeApi } from '@/lib/finance';

export default function CustomerProfileSummary({ userId, devices }: { userId: string | number; devices: DeviceHealthRecord[] }) {
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
  const counts = countDeviceHealth(devices);
  const categories: DeviceHealth[] = ['offline', 'passed', 'failed', 'infrequent', ...(counts.unknown ? ['unknown' as const] : [])];
  return <div className="border-t border-slate-100 pt-3 text-sm" aria-label="Account summary">
    {error ? <p role="alert" className="text-red-700">{error}</p> : !summary ? <p className="text-slate-500">Loading account summary…</p> :
      <div className="flex items-start justify-between gap-4"><strong className="text-slate-800">{summary.vehicle_count} {summary.vehicle_count === 1 ? 'Asset' : 'Assets'}</strong><span className="text-right font-medium text-blue-800">{summary.unpaid_invoice_count === 0 ? 'No unpaid invoices' : `${summary.unpaid_invoice_count} unpaid invoice${summary.unpaid_invoice_count === 1 ? '' : 's'}`}</span></div>}
    <dl aria-label="Fleet status" className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
      {categories.map(category => <div key={category} className={`min-w-0 rounded-xl p-3 ring-1 ring-inset ${deviceHealthInfo[category].classes}`}>
        <dt className="text-xs font-medium leading-snug">{deviceHealthInfo[category].label}</dt>
        <dd className="mt-1 text-xl font-semibold tabular-nums">{counts[category]}</dd>
      </div>)}
    </dl>
    <p className="mt-2 text-xs text-slate-500">Device status at the last search.</p>
  </div>;
}
