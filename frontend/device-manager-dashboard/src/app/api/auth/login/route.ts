import { NextRequest, NextResponse } from 'next/server';

export async function POST(req: NextRequest) {
  try {
    // Get credentials from frontend request
    const body = await req.json();

    // Forward request to your Flask backend
    const backendRes = await fetch(`http://127.0.0.1:5000/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      credentials: 'include', // important: let backend set cookies
    });

    // Forward cookies from backend to client
    const response = NextResponse.json(await backendRes.json(), {
      status: backendRes.status,
    });

    // If backend sets "session_token", forward it to client
    const setCookie = backendRes.headers.get('set-cookie');
    if (setCookie) {
      response.headers.set('set-cookie', setCookie);
    }

    return response;
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Proxy error' },
      { status: 500 }
    );
  }
}
