import { NextResponse } from 'next/server';

export async function POST(req: Request) {
  try {
    const body = await req.json();
    console.log('Received body:', body);

    const res = await fetch('http://127.0.0.1:5000/api/device/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      credentials: 'include',
    });

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('Proxy API error:', error);
    return NextResponse.json({ error: 'Proxy failed' }, { status: 500 });
  }
}
