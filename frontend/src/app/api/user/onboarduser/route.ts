// app/api/user/onboarduser/route.ts
import { NextResponse } from 'next/server';

export async function POST(req: Request) {
  try {
    const body = await req.json();

    // Forward the request to the backend API
    const res = await fetch(`${process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL}/backend/user/onboard_user`, {
      method: 'POST',
      body: JSON.stringify(body),
      headers: {
          cookie: req.headers.get("cookie") || "",
          'Content-Type': 'application/json'
        },
    });

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('Proxy API error:', error);
    return NextResponse.json({ error: 'Proxy failed' }, { status: 500 });
  }
}
