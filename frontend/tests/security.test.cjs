const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
class NextResponse extends Response {
  static json(body, init) { return new NextResponse(JSON.stringify(body), init); }
  static redirect(url) { return new NextResponse(null, { status: 307, headers: { Location: String(url) } }); }
  static next() { return new NextResponse('allowed', { status: 200 }); }
}
function load(relative, fetch) {
  const source = fs.readFileSync(path.join(__dirname, relative), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const sandbox = { exports: {}, require: () => ({ NextResponse }), fetch, URL, AbortSignal, Uint8Array, TextDecoder,
    process: { env: { BACKEND_URL: 'http://backend:5000' } } };
  vm.runInNewContext(code, sandbox);
  return sandbox.exports;
}
const request = (body = '{}', extra = {}) => new Request('https://portal.test/api/auth/login', {
  method: 'POST', body, headers: { host: 'portal.test', origin: 'https://portal.test', 'content-type': 'application/json', ...extra },
});

test('write proxy rejects cross-origin and forged forwarding-host requests before backend access', async () => {
  let calls = 0;
  const proxy = load('../src/lib/portal-proxy.ts', async () => { calls++; });
  for (const headers of [{ origin: 'https://evil.test' }, { origin: 'https://evil.test', 'x-forwarded-host': 'evil.test' }, { origin: 'not-a-url' }]) {
    assert.equal((await proxy.portalWrite(request('{}', headers), 'auth/login')).status, 403);
  }
  assert.equal(calls, 0);
});

test('proxy forwards throttles and cookies without trusting client IP claims', async () => {
  let captured;
  const proxy = load('../src/lib/portal-proxy.ts', async (url, options) => {
    captured = { url, options };
    return NextResponse.json({ error: 'Too many login attempts.' }, { status: 429, headers: { 'Retry-After': '300' } });
  });
  const result = await proxy.portalWrite(request('{"email":"staff@example.test","password":"test"}', { 'x-forwarded-for': 'fake', authorization: 'Bearer forged' }), 'auth/login');
  assert.equal(result.status, 429);
  assert.equal(result.headers.get('retry-after'), '300');
  assert.equal(captured.options.headers['X-Portal-Request'], '1');
  assert.equal(captured.options.headers['x-forwarded-for'], undefined);
  assert.equal(captured.options.headers.authorization, undefined);
  assert.equal(captured.options.cache, 'no-store');
  const success = load('../src/lib/portal-proxy.ts', async () => NextResponse.json({ message: 'Login successful' }, { headers: { 'set-cookie': 'session_token=abc; HttpOnly' } }));
  assert.match((await success.portalWrite(request(), 'auth/login')).headers.get('set-cookie'), /HttpOnly/);
});

test('proxy bounds input and hides upstream exceptions', async () => {
  let calls = 0;
  const proxy = load('../src/lib/portal-proxy.ts', async () => { calls++; throw new Error('SECRET'); });
  assert.equal((await proxy.portalWrite(request('x'.repeat(65537)), 'auth/login')).status, 413);
  assert.equal((await proxy.portalWrite(request('[]'), 'auth/login')).status, 400);
  assert.equal((await proxy.portalWrite(request('{bad'), 'auth/login')).status, 400);
  assert.equal(calls, 0);
  const result = await proxy.portalWrite(request(), 'auth/login');
  assert.equal(result.status, 503);
  assert.ok(!(await result.text()).includes('SECRET'));
});

test('logout forwards the actual cookie and empty JSON request', async () => {
  let captured;
  const proxy = load('../src/lib/portal-proxy.ts', async (_, options) => { captured = options; return NextResponse.json({ message: 'Logged out' }); });
  assert.equal((await proxy.portalWrite(request('', { cookie: 'session_token=real-session' }), 'auth/logout')).status, 200);
  assert.equal(captured.headers.cookie, 'session_token=real-session');
  assert.equal(captured.body, '{}');
});

test('console middleware requires the staff claim and fails closed when verification is unavailable', async () => {
  const req = { url: 'https://portal.test/search', cookies: { get: () => ({ value: 'session' }) }, headers: new Headers({ cookie: 'session_token=session' }) };
  for (const session of [{ authenticated: true }, { authenticated: true, staff: false }, { authenticated: false }]) {
    const gate = load('../src/middleware.ts', async () => NextResponse.json(session));
    const result = await gate.middleware(req);
    assert.equal(result.status, 307);
    assert.equal(result.headers.get('location'), 'https://portal.test/login');
  }
  const approved = load('../src/middleware.ts', async () => NextResponse.json({ authenticated: true, staff: true }));
  assert.equal((await approved.middleware(req)).status, 200);
  const unavailable = load('../src/middleware.ts', async () => { throw new Error('SECRET'); });
  const response = await unavailable.middleware(req);
  assert.equal(response.status, 503);
  assert.ok(!(await response.text()).includes('SECRET'));
});
