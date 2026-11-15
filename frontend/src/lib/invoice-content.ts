import { Entry } from './finance';

const itemDetails: Record<string, { label: string; description: string; order: number }> = {
  Device: { label: 'GPS_D_V4', description: 'Intelligent GPS Tracker Device for Automobile', order: 0 },
  'GPRS fee': { label: 'GPRS_GSM', description: 'GSM Access Fee for 12 months per module (MTN)', order: 1 },
  'Server fee': { label: 'GPS_Server_Maintenance', description: 'Global Server App License Fee for 1 year per module', order: 2 },
  Installation: { label: 'Installation', description: 'Logistics, Installation', order: 3 },
};
// Presentation only: preserve the amounts stored on historical invoices.
export function invoiceItems(entry: Pick<Entry, 'category' | 'breakdown'>) {
  return entry.breakdown.map(part => ({ ...part, ...(entry.category !== 'special' ? itemDetails[part.label] : {}), order: entry.category !== 'special' ? itemDetails[part.label]?.order ?? 4 : 4 })).sort((a, b) => a.order - b.order);
}
export const salesTerms = [
  'This proposal includes one year warranty in parts - Terms and Conditions Applied.',
  'Handling of any Roie (and its subsidiaries’ company) equipment by anyone other than a Roie technician/engineer will void the warranty.',
  'This proposal includes 90 days of help desk support.',
  'Building licenses, construction permits or any others required are the end user’s responsibility.',
  'Internet WIFI or GPRS communication for the Fuel Shield unit is the customer’s responsibility.',
  'Roie will provide system operational training.',
  'Order cancellation has a 25% restocking fee.',
  'Prices are valid for 30 days after receipt of this proposal.',
  'Lead time is 30 days after payment.',
  'Customer has read, understands and agrees to all sales terms (pricing, shipping and others).',
  'To process your purchase order, please sign this document and return it to Roie.',
  'Confidential use of this document is required.',
  'Fleet Manager is a yearly (12-month) License Software Agreement per Object.',
  'Computer/Phone with Internet is in the client’s scope.',
];
