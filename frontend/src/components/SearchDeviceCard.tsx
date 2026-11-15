import { FiCpu, FiHash, FiInfo, FiMapPin, FiSmartphone, FiUsers, FiAlertTriangle, FiUserPlus } from 'react-icons/fi';
import { deviceHealth, deviceHealthInfo } from '@/lib/device-status';
import { expiryLabel } from '@/lib/finance';

export interface SearchUserProfile {
  id: string; name: string; email: string; phone?: string; status: string; expiry: string | null;
}
export interface SearchDevice {
  device_id: string; device_name: string; imei: string; model: string; phone?: string;
  position_address?: string;
  online_status?: { status: string; recommendation?: string };
  user_profiles?: SearchUserProfile[];
}

export default function SearchDeviceCard({ device, onAssign }: { device: SearchDevice; onAssign: (device: SearchDevice) => void }) {
  const status = device.online_status?.status || 'Status unavailable';
  const recommendation = device.online_status?.recommendation;
  return <article aria-label={`Device ${device.device_name}`} className="roie-card min-w-0 p-4 sm:p-5">
    <div className="flex items-start gap-3">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-700"><FiCpu size={20} aria-hidden="true" /></span>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Vehicle / device</p>
        <h3 className="mt-1 break-words text-lg font-semibold leading-snug text-slate-900 [overflow-wrap:anywhere]">{device.device_name || 'Unnamed device'}</h3>
      </div>
    </div>
    <p className={`mt-4 inline-flex max-w-full rounded-lg px-3 py-1.5 text-xs font-medium leading-relaxed ring-1 ring-inset ${deviceHealthInfo[deviceHealth(status)].classes}`}>{status}</p>
    <dl className="mt-5 grid min-w-0 gap-x-5 gap-y-4 text-sm sm:grid-cols-2">
      {[{ label: 'IMEI', value: device.imei, Icon: FiHash }, { label: 'Model', value: device.model, Icon: FiInfo }, { label: 'Device phone', value: device.phone, Icon: FiSmartphone }].map(({ label, value, Icon }) => <div key={label} className="min-w-0">
        <dt className="flex items-center gap-2 text-xs font-medium text-slate-500"><Icon className="shrink-0" aria-hidden="true" />{label}</dt>
        <dd className="mt-1.5 break-words font-medium text-slate-800 [overflow-wrap:anywhere]">{value || 'Not available'}</dd>
      </div>)}
      <div className="min-w-0 sm:col-span-2">
        <dt className="flex items-center gap-2 text-xs font-medium text-slate-500"><FiMapPin className="shrink-0" aria-hidden="true" />Last known address</dt>
        <dd className="mt-1.5 break-words leading-relaxed text-slate-700 [overflow-wrap:anywhere]">{device.position_address || 'No address available'}</dd>
      </div>
    </dl>
    {recommendation && recommendation !== 'None' && <div className="mt-4 flex items-start gap-2 rounded-xl bg-amber-50 p-3 text-sm leading-relaxed text-amber-900"><FiAlertTriangle className="mt-0.5 shrink-0" aria-hidden="true" /><p className="min-w-0 break-words [overflow-wrap:anywhere]">{recommendation}</p></div>}
    <details className="mt-5 border-t border-slate-100 pt-4 text-sm">
      <summary className="cursor-pointer rounded-md font-medium text-blue-900 focus-visible:outline-2 focus-visible:outline-blue-600"><FiUsers className="mr-2 inline" aria-hidden="true" />Attached users ({device.user_profiles?.length || 0})</summary>
      <div className="mt-3 space-y-3">
        {!device.user_profiles?.length && <p className="text-slate-500">No users attached to this device.</p>}
        {device.user_profiles?.map(user => <div key={user.id} className="min-w-0 rounded-xl bg-slate-50 p-3">
          <p className="break-words font-semibold text-slate-800 [overflow-wrap:anywhere]">{user.name}</p>
          <p className="mt-1 break-words text-slate-600 [overflow-wrap:anywhere]">{user.email}</p>
          <div className="mt-3 space-y-1 text-xs text-slate-500"><p>Status: <span className="font-medium text-slate-700">{user.status}</span></p><p>Expiry: {expiryLabel(user.expiry)}</p></div>
        </div>)}
      </div>
    </details>
    <button type="button" onClick={() => onAssign(device)} className="roie-button roie-secondary mt-5 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl border border-blue-200 px-4 py-2.5 text-sm font-medium text-blue-800 transition-colors hover:bg-blue-50 focus-visible:outline-2 focus-visible:outline-blue-600 sm:w-auto"><FiUserPlus aria-hidden="true" />Assign to a User</button>
  </article>;
}
