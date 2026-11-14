import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

async function proxy(req: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (path.some(segment => !/^[a-zA-Z0-9-]+$/.test(segment))) {
    return NextResponse.json({ error: 'Invalid finance path.' }, { status: 400 });
  }
  if (req.method !== 'GET') {
    const origin = req.headers.get('origin');
    const host = req.headers.get('x-forwarded-host') || req.headers.get('host');
    if (!origin || new URL(origin).host !== host || req.headers.get('x-finance-request') !== '1') {
      return NextResponse.json({ error: 'Same-origin finance request required.' }, { status: 403 });
    }
  }
  const base = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL;
  if (!base) return NextResponse.json({ error: 'Backend URL is not configured.' }, { status: 503 });
  try {
    const response = await fetch(`${base.replace(/\/$/, '')}/backend/finance/${path.join('/')}${req.nextUrl.search}`, {
      method: req.method,
      headers: { cookie: req.headers.get('cookie') || '', 'Content-Type': 'application/json', 'X-Finance-Request': '1' },
      body: req.method === 'GET' ? undefined : await req.text(),
      cache: 'no-store',
      signal: AbortSignal.timeout(45000),
    });
    if (response.ok && req.method === 'GET' && path.at(-1) === 'proof' && response.headers.get('content-type')?.startsWith('image/png')) {
      return new NextResponse(await response.arrayBuffer(), { status: response.status, headers: { 'Content-Type': 'image/png', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
    }
    const data = await response.json().catch(() => ({ error: 'Finance service could not complete this request.' }));
    return NextResponse.json(data, { status: response.status, headers: { 'Cache-Control': 'no-store' } });
  } catch {
    return NextResponse.json({ error: 'Finance service unavailable. Reload before retrying a saved action.' }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
