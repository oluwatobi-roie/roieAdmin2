import { NextRequest, NextResponse } from 'next/server';

// ---------- Types ----------
interface LoginRequest {
  email: string;
  password: string;
  // add any other fields your frontend sends
}

interface LoginResponse {
  success: boolean;
  token?: string;
  error?: string;
  // add any other fields your backend returns
}

// ---------- Handler ----------
export async function POST(req: NextRequest) {
  try {
    // Get credentials from frontend request
    const body: LoginRequest = await req.json();

    // Forward request to Flask backend
    const backendRes = await fetch(`http://127.0.0.1:5000/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      credentials: 'include',
    });

    // Get typed backend response
    const data: LoginResponse = await backendRes.json();

    // Forward response to client
    const response = NextResponse.json(data, { status: backendRes.status });

    // Forward "set-cookie" if backend sets it
    const setCookie = backendRes.headers.get('set-cookie');
    if (setCookie) {
      response.headers.set('set-cookie', setCookie);
    }

    return response;
  } catch (err: unknown) {
    console.error("Login proxy error:", err);
    const message = err instanceof Error ? err.message : 'Proxy error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
