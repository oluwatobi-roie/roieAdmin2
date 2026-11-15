'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { financeApi, expiryLabel, newRequestKey, ProfileExtension, RenewalOptions } from '@/lib/finance';
import ExtensionAudit from '@/components/finance/ExtensionAudit';

const button = 'roie-button roie-primary rounded-lg bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50';
const secondary = 'roie-button roie-secondary rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-blue-800 hover:bg-blue-50 disabled:opacity-50';

export default function ProfileRenewal({ userId, onUpdated }: { userId: string; onUpdated: (expiry: string, disabled: boolean) => void }) {
  const [options, setOptions] = useState<RenewalOptions | null>(null);
  const [invoiceId, setInvoiceId] = useState('');
  const [deviceIds, setDeviceIds] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const requestKey = useRef('');
  const running = useRef(false);
  const invoice = options?.invoices.find(item => item.id === invoiceId);
  const pending = options?.history.some(item => item.state === 'pending');
  const stillExpired = !!options?.proposed_expiration_time && new Date(options.proposed_expiration_time).getTime() <= Date.now();

  const load = useCallback(async () => {
    const result = await financeApi<RenewalOptions>(`customers/${userId}/renewal-options`);
    setOptions(result); setInvoiceId(''); setDeviceIds([]); requestKey.current = '';
    if (result.expiration_time) onUpdated(result.expiration_time, result.disabled);
  }, [userId, onUpdated]);
  const refresh = useCallback(async () => {
    if (running.current) return;
    running.current = true; setBusy(true); setError(''); setOptions(null);
    try { await load(); } catch (err) { setError((err as Error).message); }
    finally { running.current = false; setBusy(false); }
  }, [load]);
  useEffect(() => { void refresh(); }, [refresh]);
  async function extend(prior?: ProfileExtension) {
    if (running.current || (!prior && (!invoice || !deviceIds.length || !options))) return;
    running.current = true; setBusy(true); setError(''); setMessage('');
    if (!requestKey.current) requestKey.current = newRequestKey();
    try {
      const response = await financeApi<{ extension: ProfileExtension; error?: string }>(`customers/${userId}/extend-expiry`, 'POST', {
        invoice_id: prior?.invoice_id || invoice!.id, revision: invoice?.revision,
        request_key: prior?.request_key || requestKey.current,
        device_ids: prior?.device_ids || deviceIds,
        expected_expiration_time: prior?.previous_expiration_time || options!.expiration_time,
      });
      if (response.extension.state === 'applied') {
        onUpdated(response.extension.expiration_time, !!response.extension.disabled);
        setMessage(`Profile extended to ${expiryLabel(response.extension.expiration_time)}. The invoice and selected vehicles are recorded below.`);
      } else setError(response.error || 'Extension pending. Verify / retry below.');
    } catch (err) { setError((err as Error).message); }
    finally {
      // A request may have succeeded even if the browser lost its response.
      // Reload durable history before enabling a new extension.
      try { await load(); } catch { setOptions(null); setError(previous => `${previous ? previous + ' ' : ''}Reload renewal details before continuing.`); }
      running.current = false; setBusy(false);
    }
  }
  return <section aria-label="Profile renewal" className="min-w-0 space-y-4 text-sm">
      <p className="text-slate-600">Add one year to the existing expiry date using a fully paid Renewal invoice. This changes expiry for the whole account. Select the vehicles due for renewal to record the invoice link for audit.</p>
      {busy && <p role="status" className="text-blue-700">Checking renewal details...</p>}
      {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-800">{error}</p>}
      {message && <p role="status" className="rounded-lg bg-blue-50 p-3 text-blue-900">{message}</p>}
      {!options && !busy && <button type="button" className={secondary} onClick={() => void refresh()}>Reload renewal details</button>}
      {options && <>
        {options.unavailable_reason && <p className="text-amber-800">{options.unavailable_reason}</p>}
        {options.disabled && <p className="text-amber-800">This account is disabled. Extending its expiry will leave it disabled.</p>}
        {pending && <p className="text-amber-800">Resolve the pending extension in renewal history before starting another.</p>}
        {!pending && options.proposed_expiration_time && <>
          {!options.invoices.length ? <p className="text-slate-600">No unused, fully paid Renewal invoice has vehicles on this account. <a href={`/finance?new=1&user_id=${userId}`} className="text-blue-700 underline">Create a renewal invoice</a>, then record full payment.</p> : <>
            <label className="block space-y-1 font-medium">Paid renewal invoice
              <select className="block w-full rounded-lg border border-slate-300 bg-white p-3" disabled={busy} value={invoiceId} onChange={event => { setInvoiceId(event.target.value); setDeviceIds([]); requestKey.current = ''; }}>
                <option value="">Select an invoice</option>
                {options.invoices.map(item => <option key={item.id} value={item.id}>{item.number} | {item.devices.length} renewal vehicles</option>)}
              </select>
            </label>
            {invoice && <fieldset disabled={busy} className="min-w-0 space-y-3">
              <legend className="font-semibold">Vehicles due for renewal</legend>
              <p className="text-slate-500">Only vehicles in this invoice&apos;s Renewal section and still on this account are available.</p>
              <button type="button" className={secondary} onClick={() => { setDeviceIds(deviceIds.length === invoice.devices.length ? [] : invoice.devices.map(device => device.id)); requestKey.current = ''; }}>{deviceIds.length === invoice.devices.length ? 'Clear selection' : 'Select all renewal vehicles'}</button>
              <div className="max-h-64 space-y-2 overflow-y-auto rounded-xl border border-slate-200 p-3">
                {invoice.devices.map(device => <label key={device.id} className="flex items-start gap-3 rounded-lg p-2 hover:bg-blue-50">
                  <input className="mt-1 h-4 w-4 accent-blue-700" type="checkbox" checked={deviceIds.includes(device.id)} onChange={event => { setDeviceIds(previous => event.target.checked ? [...previous, device.id] : previous.filter(id => id !== device.id)); requestKey.current = ''; }} />
                  <span className="min-w-0 break-words">{device.name}<span className="block text-xs text-slate-500">{device.imei || `ID ${device.id}`}</span></span>
                </label>)}
              </div>
              <p className="text-slate-600">{deviceIds.length} of {invoice.devices.length} vehicles selected. This invoice can extend the profile only once.</p>
              <div className="rounded-xl bg-blue-50 p-4 text-blue-950">
                <p>Current expiry: {expiryLabel(options.expiration_time)}</p>
                <p className="mt-1 font-semibold">New expiry: {expiryLabel(options.proposed_expiration_time)}</p>
              </div>
              {stillExpired && <p className="rounded-lg bg-amber-50 p-3 text-amber-900">The profile will still be expired after this one-year extension because renewal starts from the old expiry date.</p>}
              <button type="button" className={button} disabled={busy || !deviceIds.length} onClick={() => void extend()}>Confirm one-year extension</button>
            </fieldset>}
          </>}
        </>}
        {!!options.history.length && <details className="rounded-xl border border-slate-200 p-4" open={pending || !!message}>
          <summary className="cursor-pointer font-semibold text-blue-900">Profile renewal history ({options.history.length})</summary>
          <div className="mt-4 space-y-4">{options.history.map(item => <div key={item.id} className="space-y-2">
            <ExtensionAudit extension={item} />
            {item.state === 'pending' && <button type="button" className={secondary} disabled={busy} onClick={() => void extend(item)}>Verify / retry extension</button>}
          </div>)}</div>
        </details>}
      </>}
  </section>;
}
