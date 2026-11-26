import { NextResponse } from 'next/server';
import { backendBase } from '@/lib/portal-proxy';

export async function GET(req: Request) {
  try {
    const upstream = await fetch(`${backendBase()}/backend/auth/check-session`, {
      headers: { cookie: req.headers.get('cookie') || '' }, cache: 'no-store', signal: AbortSignal.timeout(12000),
    });
    return NextResponse.json(await upstream.json(), { status: upstream.status, headers: { 'Cache-Control': 'no-store' } });
  } catch { return NextResponse.json({ authenticated: false }, { status: 503, headers: { 'Cache-Control': 'no-store' } }); }
}
