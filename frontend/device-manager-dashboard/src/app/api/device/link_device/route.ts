import { NextResponse } from 'next/server';

export async function POST(req: Request) {
  try {
    const body = await req.json();
    console.log('Proxy received body:', body); // <--- log to verify

    const res = await fetch('http://127.0.0.1:5000/api/device/link_device', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    const data = await res.json();
    console.log('Proxy response:', data);

    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('Proxy API error:', error);
    return NextResponse.json({ error: 'Proxy failed' }, { status: 500 });
  }
}
