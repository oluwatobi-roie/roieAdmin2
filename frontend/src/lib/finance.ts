export type Category = 'renewal' | 'installation' | 'maintenance' | 'special';
export type Address = { line1: string; line2: string; city: string; state: string; postal_code: string; country: string };
export type Customer = { profile_id?: string; traccar_user_id: number | null; name: string; email: string; phone: string; address: Address; formatted_address?: string };
export type Device = { id: number; name: string; imei: string };
export type Account = { id: number; name: string; email: string; phone: string };
export type EntryInput = { category: Category; total: string; device_ids: string[]; pending_vehicles: string; pending_count: number; activity: string; task_notes: string; item: string; description: string };
export type Entry = { id: string; category: Category; total_minor: number; device: Device | null; vehicle_label?: string; activity: string; task_notes?: string; link_status: string; breakdown: { label: string; description?: string; amount_minor: number }[] };
export type Discount = { type: 'none' | 'percent' | 'amount'; value: string };
export type Totals = { subtotal_minor: number; discount_minor: number; discount: Discount; total_minor: number };
export type Preview = Totals & { customer: Customer; entries: Entry[] };
export type Payment = { id: string; receipt_number?: string; amount_minor: number; method: string; paid_on: string; reference: string; recorded_by: { name: string }; proof?: { sha256: string; name: string } };
export type Receipt = { number: string; invoice_number: string; invoice_id: string; customer: Customer; as_of: string; kind: string; payments: Payment[]; invoice_total_minor: number; received_minor: number; cumulative_paid_minor: number; balance_minor: number };
export type ProofInput = { name: string; data_url: string };
export type CustomerSummary = { vehicle_count: number; unpaid_invoice_count: number; finance_status: string; paid_minor: number; balance_minor: number };
export type Invoice = Preview & {
  id: string; number: string | null; revision: number; request_key: string;
  status: 'draft' | 'issued' | 'void'; currency: string; created_at: string; issued_at?: string;
  due_date: string; notes: string; paid_minor: number; balance_minor: number; payment_status: string;
  payments: Payment[];
  events: { at: string; action: string; actor: { name: string }; reason?: string }[];
};
export const categories: Record<Category, { label: string; defaultTotal: string }> = {
  renewal: { label: 'Renewal', defaultTotal: '15000.00' },
  installation: { label: 'New installation', defaultTotal: '140000.00' },
  maintenance: { label: 'Maintenance', defaultTotal: '20000.00' },
  special: { label: 'Special Service', defaultTotal: '0.00' },
};
export const emptyAddress = (): Address => ({ line1: '', line2: '', city: '', state: '', postal_code: '', country: 'Nigeria' });
export const emptyCustomer = (): Customer => ({ traccar_user_id: null, name: '', email: '', phone: '', address: emptyAddress() });
export const newEntry = (): EntryInput => ({ category: 'renewal', total: '15000.00', device_ids: [], pending_vehicles: '', pending_count: 0, activity: '', task_notes: '', item: '', description: '' });
export const currency = (minor: number) => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(minor / 100);
export async function financeApi<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const res = await fetch(`/api/finance/${path}`, {
    method, cache: 'no-store', headers: { 'Content-Type': 'application/json', 'X-Finance-Request': '1' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Finance request failed.');
  return data as T;
}

// randomUUID is unavailable on some HTTP/LAN browser contexts. getRandomValues
// remains available there and supplies cryptographically random UUID v4 bytes.
export function newRequestKey(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID();
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function pendingNames(value: string): string[] {
  const names: string[] = [];
  let name = '', quoted = false;
  for (let index = 0; index < value.length; index++) {
    const character = value[index];
    if (character === '"' && (quoted || !name.trim())) {
      if (quoted && value[index + 1] === '"') { name += '"'; index++; }
      else quoted = !quoted;
    } else if (!quoted && (character === ',' || character === '\n')) {
      if (name.trim()) names.push(name.trim());
      name = '';
    } else name += character;
  }
  if (name.trim()) names.push(name.trim());
  return names;
}
const quoteVehicleName = (name: string) => /[",\n]/.test(name) ? `"${name.replaceAll('"', '""')}"` : name;
export const taskQuantity = (entry: EntryInput) => entry.category === 'special' ? 1 : entry.device_ids.length + pendingNames(entry.pending_vehicles).length + (entry.pending_count || 0);
export const taskPayload = (entries: EntryInput[]) => entries.map(entry => ({ ...entry, pending_vehicles: pendingNames(entry.pending_vehicles), quantity: taskQuantity(entry) }));
export const vehicleName = (entry: Entry) => entry.device?.name || entry.vehicle_label || entry.activity;
export type TaskGroup = { category: Category; activity: string; task_notes: string; entries: Entry[]; unit_total_minor: number; total_minor: number; breakdown: Entry['breakdown'] };
export type Calculation = Totals & { entries: { quantity: number; unit_total_minor: number; total_minor: number; breakdown: { label: string; amount_minor: number; unit_amount_minor: number }[] }[]; total_minor: number };

// Group only identical stored prices and service periods. Never recalculate an
// issued invoice using today's defaults; old invoices need no ledger migration.
export function groupEntries(entries: Entry[]): TaskGroup[] {
  const groups = new Map<string, TaskGroup>();
  for (const [entryIndex, entry] of entries.entries()) {
    const key = JSON.stringify([entry.category, entry.activity, entry.task_notes || '', entry.total_minor, entry.breakdown, entry.category === 'special' ? entryIndex : null]);
    const group = groups.get(key);
    if (group) { group.entries.push(entry); group.total_minor += entry.total_minor; }
    else groups.set(key, { category: entry.category, activity: entry.activity, task_notes: entry.task_notes || '', entries: [entry], unit_total_minor: entry.total_minor, total_minor: entry.total_minor, breakdown: entry.breakdown });
  }
  return [...groups.values()];
}

export function entriesToTasks(entries: Entry[]): EntryInput[] {
  return groupEntries(entries).map(group => ({ category: group.category, total: (group.unit_total_minor / 100).toFixed(2),
    device_ids: group.entries.filter(entry => entry.device).map(entry => String(entry.device!.id)),
    pending_vehicles: group.category === 'special' ? '' : group.entries.filter(entry => !entry.device).map(vehicleName).map(quoteVehicleName).join(', '), pending_count: 0, task_notes: group.task_notes, activity: group.activity, item: group.category === 'special' ? group.breakdown[0].label : '', description: group.category === 'special' ? group.breakdown[0].description || '' : '' }));
}

export const noDiscount = (): Discount => ({ type: 'none', value: '0' });
export const statusLabel = (status: string) => ({ paid: 'Paid in full', partial: 'Partially paid', unpaid: 'Unpaid', no_invoices: 'No invoices' }[status] || status);
export function readProof(file: File): Promise<ProofInput> {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 4 * 1024 * 1024) return Promise.reject(new Error('Choose a PNG, JPEG or WebP screenshot up to 4 MB.'));
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({ name: file.name, data_url: String(reader.result) });
    reader.onerror = () => reject(new Error('Could not read the screenshot.'));
    reader.readAsDataURL(file);
  });
}
