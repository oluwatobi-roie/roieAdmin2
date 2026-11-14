import { NextResponse } from "next/server";

export async function POST() {
  try {
    const backendRes = await fetch(`${process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL}/backend/auth/logout`, {
      method: "POST",
      credentials: "include",
    });

    const data = await backendRes.json();

    // forward cookies (delete session_token)
    const response = NextResponse.json(data, { status: backendRes.status });
    const setCookie = backendRes.headers.get("set-cookie");
    if (setCookie) {
      response.headers.set("set-cookie", setCookie);
    }

    return response;
  } catch (err) {
    console.error("Logout error:", err);
    return NextResponse.json({ error: "Logout failed" }, { status: 500 });
  }
}
