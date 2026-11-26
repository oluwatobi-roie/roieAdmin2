import { NextRequest, NextResponse } from 'next/server';

export async function middleware(request: NextRequest) {
  const login = () => NextResponse.redirect(new URL('/login', request.url));
  const token = request.cookies.get('session_token')?.value;
  if (!token) return login();
  const base = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL;
  try {
    if (!base) throw new Error('Backend unavailable');
    const response = await fetch(`${base.replace(/\/$/, '')}/backend/auth/check-session`, {
      headers: { cookie: request.headers.get('cookie') || '' }, cache: 'no-store', signal: AbortSignal.timeout(12000),
    });
    if (response.status === 401 || response.status === 403) return login();
    const session = await response.json();
    if (!response.ok) throw new Error('Session verification unavailable');
    if (session.authenticated !== true || session.staff !== true) return login();
    const next = NextResponse.next();
    next.headers.set('Cache-Control', 'no-store');
    return next;
  } catch {
    return new NextResponse('Staff session verification is temporarily unavailable. Please reload shortly.', {
      status: 503, headers: { 'Content-Type': 'text/plain', 'Cache-Control': 'no-store' },
    });
  }
}

export const config = { matcher: ['/', '/search/:path*', '/finance/:path*', '/onboard_user/:path*', '/add-device/:path*'] };
