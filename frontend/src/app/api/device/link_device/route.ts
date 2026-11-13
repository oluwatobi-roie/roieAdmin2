import { NextResponse } from 'next/server';

export async function POST(req: Request) {
  try {
    const body = await req.json();
    console.log('Proxy received body:', body);

    const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/backend/device/link_device`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        cookie: req.headers.get("cookie") || ""
      },
      body: JSON.stringify(body),
    });

    const contentType = res.headers.get("content-type") || "";
    let data;

    if (contentType.includes("application/json")) {
      data = await res.json();
    } else {
      data = await res.text(); // capture the HTML or plain text
    }

    console.log('Proxy response:', data);

    return NextResponse.json(
      { success: true, data },
      { status: res.status }
    );
  } catch (error) {
    console.error('Proxy API error:', error);
    return NextResponse.json({ error: 'Proxy failed' }, { status: 500 });
  }
}
