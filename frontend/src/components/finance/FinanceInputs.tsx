'use client';

import { FormEvent, ReactElement, ReactNode, cloneElement, isValidElement, useId, useState } from 'react';
import Link from 'next/link';
import { Account, Device, financeApi } from '@/lib/finance';

export const fieldClass = 'finance-field';
export const actionClass = 'finance-button';
export const secondaryClass = 'finance-secondary';
export function Field({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  return <div className="block text-sm font-medium text-slate-700"><label htmlFor={id}>{label}</label>{isValidElement(children) ? cloneElement(children as ReactElement<{ id?: string }>, { id }) : children}</div>;
}
export function CustomerPicker({ onAccount, disabled = false }: { onAccount: (id: number) => Promise<void>; disabled?: boolean }) {
  const [term, setTerm] = useState('');
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function search(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { setAccounts((await financeApi<{ accounts: Account[] }>(`customers?term=${encodeURIComponent(term)}`)).accounts); }
    catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="space-y-3">
    <form onSubmit={search} className="flex flex-wrap items-end gap-3"><div className="min-w-0 grow"><Field label="Find a customer by name, email or phone"><input className={fieldClass} value={term} onChange={event => setTerm(event.target.value)} /></Field></div><button className={secondaryClass} disabled={disabled || busy || !term.trim()}>{busy ? 'Searching…' : 'Find customer'}</button></form>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {accounts && <div className="max-h-60 overflow-auto rounded-xl border border-slate-200 divide-y divide-slate-100">
      {!accounts.length && <p className="p-4 text-sm text-slate-600">No account found. <Link className="font-semibold text-teal-800 underline" href="/onboard_user?returnTo=finance">Onboard the customer</Link>, then return to create their invoice.</p>}
      {accounts.map(account => <button key={account.id} className="block w-full p-4 text-left text-sm hover:bg-slate-50" disabled={disabled || busy} onClick={async () => {
        setBusy(true); setError('');
        try { await onAccount(account.id); setAccounts(null); } catch (error) { setError((error as Error).message); } finally { setBusy(false); }
      }}><strong className="block text-slate-800">{account.name}</strong><span className="text-slate-500">{account.email}</span></button>)}
    </div>}
    <p className="text-sm text-slate-500">New customer? <Link className="text-teal-800 font-medium underline" href="/onboard_user?returnTo=finance">Onboard a customer first</Link>.</p>
  </div>;
}
export function VehiclePicker({ devices, selected, onChange }: { devices: Device[]; selected: string[]; onChange: (ids: string[]) => void }) {
  const [search, setSearch] = useState('');
  const matches = devices.filter(device => `${device.name} ${device.imei}`.toLowerCase().includes(search.toLowerCase()));
  return <div className="space-y-3">
    <Field label="Find vehicles for this task"><input className={fieldClass} value={search} onChange={event => setSearch(event.target.value)} placeholder="Vehicle name or IMEI" /></Field>
    <div className="flex flex-wrap items-center gap-2 text-sm"><button type="button" className={secondaryClass} disabled={!matches.length} onClick={() => onChange([...new Set([...selected, ...matches.map(device => String(device.id))])])}>Select all matching ({matches.length})</button><button type="button" className={secondaryClass} disabled={!selected.length} onClick={() => onChange([])}>Clear selection</button><span className="text-slate-500">{selected.length} selected</span></div>
    <div className="grid max-h-64 gap-2 overflow-y-auto rounded-xl border border-slate-200 p-3 sm:grid-cols-2">
      {!matches.length && <p className="p-2 text-sm text-slate-500">No matching vehicles on this account.</p>}
      {matches.map(device => <label key={device.id} className="flex min-w-0 items-start gap-3 rounded-lg p-2 text-sm hover:bg-slate-50"><input type="checkbox" className="mt-1 accent-teal-700" checked={selected.includes(String(device.id))} onChange={event => onChange(event.target.checked ? [...selected, String(device.id)] : selected.filter(id => id !== String(device.id)))} /><span className="break-words">{device.name}<span className="block text-xs text-slate-400">IMEI {device.imei}</span></span></label>)}
    </div>
  </div>;
}
