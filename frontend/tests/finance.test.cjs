const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const ts = require('typescript');
const { webcrypto } = require('node:crypto');
const source = fs.readFileSync(path.join(__dirname, '../src/lib/finance.ts'), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
const sandbox = { exports: {}, crypto: { getRandomValues: bytes => webcrypto.getRandomValues(bytes) } };
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
