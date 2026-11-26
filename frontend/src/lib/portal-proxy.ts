import { NextResponse } from 'next/server';

export function sameOriginWrite(req: Request): boolean {
  try {
    const origin = req.headers.get('origin');
    return !!origin && new URL(origin).host === req.headers.get('host');
  } catch { return false; }
}

export function backendBase(): string {
  const base = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL;
  if (!base) throw new Error('Backend unavailable');
  return base.replace(/\/$/, '');
}

export async function portalWrite(req: Request, path: string, wrapped = false) {
  if (!sameOriginWrite(req)) return NextResponse.json({ error: 'Same-origin portal request required.' }, { status: 403 });
  try {
    let size = 0;
    const chunks: Uint8Array[] = [];
    const reader = req.body?.getReader();
    if (reader) {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > 65536) { await reader.cancel(); return NextResponse.json({ error: 'Request is too large.' }, { status: 413 }); }
        chunks.push(value);
      }
    }
    let body;
    try {
      const bytes = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
      body = size ? JSON.parse(new TextDecoder().decode(bytes)) : path === 'auth/logout' ? {} : null;
    } catch { return NextResponse.json({ error: 'A JSON object is required.' }, { status: 400 }); }
    if (!body || typeof body !== 'object' || Array.isArray(body)) return NextResponse.json({ error: 'A JSON object is required.' }, { status: 400 });
    const upstream = await fetch(`${backendBase()}/backend/${path}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Portal-Request': '1', cookie: req.headers.get('cookie') || '' },
      body: JSON.stringify(body), cache: 'no-store', signal: AbortSignal.timeout(45000),
    });
    const data = await upstream.json().catch(() => ({ error: 'The service could not complete this request.' }));
    const response = NextResponse.json(wrapped ? { success: upstream.ok, data, ...(!upstream.ok ? { error: data.error } : {}) } : data,
      { status: upstream.status, headers: { 'Cache-Control': 'no-store' } });
    for (const header of ['set-cookie', 'retry-after']) {
      const value = upstream.headers.get(header);
      if (value) response.headers.set(header, value);
    }
    return response;
  } catch { return NextResponse.json({ error: 'The service is temporarily unavailable.' }, { status: 503 }); }
}
