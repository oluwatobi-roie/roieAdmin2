import { NextRequest, NextResponse } from 'next/server';

export async function GET(req: NextRequest) {
  try {
    // Forward the request to your backend session check
    const cookie = req.cookies.get('session_token')?.value;

    const res = await fetch(`http://127.0.0.1:5000/api/auth/check-session`, {
      method: 'GET',
      headers: {
        cookie: `session_token=${cookie}`, // forward session cookie
      },
      credentials: 'include',
    });

    const data = await res.json();

    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    console.error("Check session error:", err);
    return NextResponse.json({ authenticated: false }, { status: 500 });
  }
}
