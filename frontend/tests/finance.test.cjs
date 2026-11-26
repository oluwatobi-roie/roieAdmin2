const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const ts = require('typescript');
const { webcrypto } = require('node:crypto');
const source = fs.readFileSync(path.join(__dirname, '../src/lib/finance.ts'), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
const sandbox = { exports: {}, URLSearchParams, crypto: { getRandomValues: bytes => webcrypto.getRandomValues(bytes) } };
vm.runInNewContext(compiled, sandbox);
const finance = sandbox.exports;
const makeEntry = (id, overrides = {}) => ({ id: String(id), category: 'renewal', total_minor: 1500000, device: { id, name: `Vehicle ${id}`, imei: String(id) }, activity: '2027 renewal', link_status: 'linked', breakdown: [{ label: 'GPRS fee', amount_minor: 1200000 }, { label: 'Server fee', amount_minor: 300000 }], ...overrides });

test('UUID fallback works without randomUUID and produces unique v4 identifiers', () => {
  const keys = Array.from({ length: 1000 }, () => finance.newRequestKey());
  assert.equal(new Set(keys).size, 1000);
  for (const key of keys) assert.match(key, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});
test('68 saved entries render as one pricing group with exact quantities and total', () => {
  const entries = Array.from({ length: 68 }, (_, i) => makeEntry(i + 1));
  const groups = finance.groupEntries(entries);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].entries.length, 68);
  assert.equal(groups[0].total_minor, 102000000);
  const tasks = finance.entriesToTasks(entries);
  assert.equal(tasks.length, 1);
  assert.equal(finance.taskQuantity(tasks[0]), 68);
  assert.equal(finance.taskPayload(tasks)[0].quantity, 68);
});
test('different rates and service periods are not averaged together', () => {
  const groups = finance.groupEntries([makeEntry(1), makeEntry(2, { total_minor: 2000000 }), makeEntry(3, { activity: '2028 renewal' })]);
  assert.equal(groups.length, 3);
});
test('pending names and device selections round-trip without changing quantity', () => {
  const tasks = finance.entriesToTasks([makeEntry(1), makeEntry(2, { device: null, vehicle_label: 'New Hilux', link_status: 'pending_installation' })]);
  assert.equal(tasks.length, 1);
  assert.equal(tasks[0].pending_vehicles, 'New Hilux');
  assert.equal(finance.taskPayload(tasks)[0].pending_vehicles[0], 'New Hilux');
  assert.equal(finance.taskQuantity(tasks[0]), 2);
});

test('legacy pending names containing commas and quotes do not inflate quantity on edit', () => {
  const name = 'Corolla, "Lagos"';
  const tasks = finance.entriesToTasks([makeEntry(1, { device: null, vehicle_label: name })]);
  const payload = finance.taskPayload(tasks)[0];
  assert.equal(payload.quantity, 1);
  assert.equal(payload.pending_vehicles[0], name);
});

test('pending installation count and linked vehicles sum to the billed quantity', () => {
  const task = { ...finance.newEntry(), category: 'installation', pending_count: 3, device_ids: ['1', '2'] };
  assert.equal(finance.taskQuantity(task), 5);
  assert.equal(finance.taskPayload([task])[0].quantity, 5);
});
test('special services retain item and description across draft editing', () => {
  const entry = makeEntry(1, { category: 'special', device: null, breakdown: [{ label: 'Wiring repair', description: 'Replace damaged cable', amount_minor: 1500000 }] });
  const task = finance.entriesToTasks([entry])[0];
  assert.equal(task.item, 'Wiring repair');
  assert.equal(task.description, 'Replace damaged cable');
  assert.equal(task.pending_vehicles, '');
  assert.equal(finance.taskQuantity(task), 1);
});
test('task explanations keep separate pricing groups', () => {
  assert.equal(finance.groupEntries([makeEntry(1, { task_notes: 'First year' }), makeEntry(2, { task_notes: 'Additional coverage' })]).length, 2);
});
const contentSource = fs.readFileSync(path.join(__dirname, '../src/lib/invoice-content.ts'), 'utf8');
const contentSandbox = { exports: {} };
vm.runInNewContext(ts.transpileModule(contentSource, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, contentSandbox);
test('installation items use requested code order without changing stored amounts', () => {
  const breakdown = [{ label: 'GPRS fee', amount_minor: 1204000 }, { label: 'Server fee', amount_minor: 336000 }, { label: 'Installation', amount_minor: 1960000 }, { label: 'Device', amount_minor: 10500000 }];
  const rows = contentSandbox.exports.invoiceItems({ category: 'installation', breakdown });
  assert.equal(rows.map(row => row.label).join(','), 'GPS_D_V4,GPRS_GSM,GPS_Server_Maintenance,Installation');
  assert.equal(rows.map(row => row.amount_minor).join(','), '10500000,1204000,336000,1960000');
  assert.equal(breakdown[0].label, 'GPRS fee');
});

test('identical special services remain separate editable items', () => {
  const entry = makeEntry(1, { category: 'special', device: null, breakdown: [{ label: 'Call out', description: 'Technician visit', amount_minor: 1500000 }] });
  const tasks = finance.entriesToTasks([entry, { ...entry, id: '2' }]);
  assert.equal(tasks.length, 2);
  assert.equal(tasks.reduce((sum, task) => sum + finance.taskQuantity(task), 0), 2);
});

test('expiry dates preserve UTC across SQL timestamps, account API offsets and invalid data', () => {
  const expected = finance.expiryLabel('2020-02-29T12:34:56Z');
  assert.equal(finance.expiryLabel('2020-02-29T12:34:56'), expected);
  assert.equal(finance.expiryLabel('2020-02-29T13:34:56+01:00'), expected);
  assert.match(expected, /29 Feb 2020.*12:34 UTC/);
  assert.equal(finance.expiryLabel(null), 'No expiry');
  assert.equal(finance.expiryLabel('not-a-date'), 'Invalid expiry date');
});

test('fleet counts use unique devices and keep warning states separate from NOC passed', () => {
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/lib/device-status.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const context = { exports: {} };
  vm.runInNewContext(code, context);
  const count = context.exports.countDeviceHealth;
  const device = (id, status) => ({ device_id: id, online_status: { status } });
  const result = count([device(1, 'NOC Passed Online'), device('1', 'NOC Passed Online'), device(2, 'Device is Offline'), device(3, 'NOC Failed Online'), device(4, 'Likely Online, but not updating frequently'), { device_id: 5 }]);
  assert.deepEqual(JSON.parse(JSON.stringify(result)), { passed: 1, failed: 1, offline: 1, infrequent: 1, unknown: 1 });
  assert.equal(Object.values(count([])).reduce((sum, value) => sum + value, 0), 0);
});


test('WhatsApp normalizes Nigerian mobile phone formats and rejects ambiguous numbers', () => {
  for (const input of ['08012345678', '8012345678', '2348012345678', '+2348012345678', '0801 234 5678', '+234 (0) 801-234-5678', '002348012345678']) {
    assert.equal(finance.whatsappPhone(input), '2348012345678', input);
  }
  for (const input of ['', '1234', '080123456789', '08012345678/09012345678', '08012345678 ext 2', '23412345', 'hello', '+08012345678']) {
    assert.equal(finance.whatsappPhone(input), null, input);
  }
  assert.equal(finance.whatsappPhone('+1 (780) 555-0123'), '17805550123');
});

test('WhatsApp message contains amounts and bank details, and the URL encodes text safely', () => {
  const invoice = { customer: { name: 'Ada & Sons' }, number: 'ROIE-2026-019674', total_minor: 1500000, balance_minor: 500000, due_date: '2026-12-01' };
  const message = finance.whatsappMessage(invoice);
  for (const value of ['Ada & Sons', 'NGN 15,000.00', 'NGN 5,000.00', 'GTBank', '0421439134', 'Roie Technologies Ltd']) assert.ok(message.includes(value));
  const url = new URL(finance.whatsappLink('08012345678', message));
  assert.equal(url.origin, 'https://wa.me');
  assert.equal(url.pathname, '/2348012345678');
  assert.equal(url.searchParams.get('text'), message);
  assert.throws(() => finance.whatsappLink('bad', message));
});

test('receipt download selects the actual payment and message preserves its historical balance', () => {
  const invoice = { id: 'invoice-id', revision: 3, customer: { name: 'Ada' }, number: 'INV', total_minor: 1500000, balance_minor: 0 };
  const receipt = { kind: 'payment', number: 'INV-R001', invoice_total_minor: 1500000, received_minor: 500000, balance_minor: 1000000, payments: [{ id: 'p1' }] };
  const url = new URL(finance.documentPdfUrl(invoice, receipt), 'https://example.test');
  assert.equal(url.searchParams.get('payment_id'), 'p1');
  assert.equal(url.searchParams.get('revision'), '3');
  assert.match(finance.whatsappMessage(invoice, receipt), /Balance: NGN 10,000.00/);
});
