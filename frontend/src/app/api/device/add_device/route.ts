import { NextResponse } from 'next/server';

// ---------- Types ----------
interface AddDeviceRequest {
  device_name: string;
  imei: string;
  model: string;
  phone?: string;
  position_address?: string;
  // add any other fields your API expects
}

interface AddDeviceResponse {
  success: boolean;
  device_id?: string;
  error?: string;
  // add any other fields returned by your API
}

// ---------- Handler ----------
export async function POST(req: Request) {
  try {
    const body: AddDeviceRequest = await req.json(); // <-- typed body
    console.log('Received body:', body);

    const res = await fetch(`${process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL}/backend/device/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' ,
        cookie: req.headers.get("cookie") || ""
      },
      body: JSON.stringify(body),
    });

    const data: AddDeviceResponse = await res.json(); // <-- typed response
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('Proxy API error:', error);
    return NextResponse.json({ error: 'Proxy failed' }, { status: 500 });
  }
}
