import { ProfileExtension, expiryLabel } from '@/lib/finance';


export default function ExtensionAudit({ extension, link = true }: { extension: ProfileExtension; link?: boolean }) {
  return <div className="min-w-0 space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
    <div className="flex flex-wrap items-center justify-between gap-2">
      {link ? <a className="font-semibold text-blue-700 underline" href={`/finance?invoice=${extension.invoice_id}`}>{extension.invoice_number}</a> : <strong>Profile expiry extension</strong>}
      <span className={extension.state === 'applied' ? 'font-medium text-blue-700' : 'font-medium text-amber-800'}>{extension.state === 'applied' ? 'Applied' : 'Pending verification'}</span>
    </div>
    <p className="text-slate-700">{expiryLabel(extension.previous_expiration_time)} to {expiryLabel(extension.expiration_time)}</p>
    <p className="break-words text-slate-600">Renewal vehicles ({extension.devices.length}): {extension.devices.map(device => `${device.name} (${device.imei || `ID ${device.id}`})`).join(', ')}</p>
    <p className="text-xs text-slate-500">Requested by {extension.actor.name} | {expiryLabel(extension.requested_at)}{extension.applied_at ? ` | Verified ${expiryLabel(extension.applied_at)} by ${extension.verified_by?.name || extension.actor.name}` : ''}</p>
    <p className="break-all text-xs text-slate-400">Audit reference: {extension.id}</p>
  </div>;
}
