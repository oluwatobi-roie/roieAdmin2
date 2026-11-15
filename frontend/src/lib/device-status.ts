export type DeviceHealth = 'passed' | 'failed' | 'offline' | 'infrequent' | 'unknown';
export const deviceHealthInfo: Record<DeviceHealth, { label: string; classes: string }> = {
  passed: { label: 'NOC passed', classes: 'bg-green-50 text-green-800 ring-green-200' },
  failed: { label: 'NOC failed', classes: 'bg-red-50 text-red-800 ring-red-200' },
  offline: { label: 'Offline', classes: 'bg-slate-700 text-white ring-slate-600' },
  infrequent: { label: 'Infrequent updates', classes: 'bg-amber-50 text-amber-900 ring-amber-200' },
  unknown: { label: 'Unknown', classes: 'bg-slate-100 text-slate-600 ring-slate-200' },
};
export function deviceHealth(status?: string): DeviceHealth {
  if (status === 'NOC Passed Online') return 'passed';
  if (status === 'NOC Failed Online') return 'failed';
  if (status === 'Device is Offline') return 'offline';
  if (status === 'Likely Online, but not updating frequently') return 'infrequent';
  return 'unknown';
}
export type DeviceHealthRecord = { device_id: string | number; online_status?: { status: string } };
export function countDeviceHealth(devices: DeviceHealthRecord[]): Record<DeviceHealth, number> {
  const counts = { passed: 0, failed: 0, offline: 0, infrequent: 0, unknown: 0 };
  const unique = new Map(devices.map(device => [String(device.device_id), device]));
  for (const device of unique.values()) counts[deviceHealth(device.online_status?.status)]++;
  return counts;
}
