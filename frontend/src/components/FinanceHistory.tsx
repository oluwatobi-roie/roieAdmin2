'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Invoice, currency, financeApi, vehicleName } from '@/lib/finance';

export default function FinanceHistory({ userId, deviceId }: { userId: string | number; deviceId?: string | number }) {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    financeApi<{ invoices: Invoice[] }>(`invoices?user_id=${encodeURIComponent(userId)}${deviceId ? `&device_id=${encodeURIComponent(deviceId)}` : ''}`)
      .then(data => { if (active) setInvoices(data.invoices); })
      .catch(err => { if (active) setError(err.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [userId, deviceId]);
  const issued = invoices.filter(i => i.status === 'issued');
  return <section className="mt-4 rounded-xl border bg-white p-4 text-sm space-y-3">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 className="font-semibold text-[#414095]">Finance &amp; payment history</h3>
      <Link className="text-[#414095] underline" href={`/finance?user_id=${userId}${deviceId ? `&device_id=${deviceId}` : ''}&new=1`}>Generate invoice</Link>
    </div>
    {loading ? <p>Loading finance history...</p> : error ? <p role="alert" className="text-red-700">{error}</p> : <>
      <p>Received: <strong>{currency(issued.reduce((s, i) => s + i.paid_minor, 0))}</strong> · Outstanding: <strong>{currency(issued.reduce((s, i) => s + i.balance_minor, 0))}</strong></p>
      {deviceId && <p className="text-gray-500">Totals cover whole invoices containing this vehicle; payments are recorded per invoice.</p>}
      {!invoices.length && <p className="text-gray-500">No finance records yet.</p>}
      {invoices.map(i => <Link key={i.id} className="block border-t pt-2 hover:text-[#414095]" href={`/finance?invoice=${i.id}`}>
        {i.number || 'Draft'} · {currency(i.total_minor)} · {i.status === 'issued' ? i.payment_status : i.status}
        <span className="block text-gray-500">{i.entries.map(vehicleName).join(' · ')} · {new Date(i.created_at).toLocaleDateString()}</span>
      </Link>)}
    </>}
  </section>;
}
