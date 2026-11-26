import { NextResponse } from "next/server";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const term = searchParams.get("term");
  const userId = searchParams.get("user_id");

  if (userId !== null && !/^[1-9]\d{0,18}$/.test(userId)) {
    return NextResponse.json({ error: "Invalid customer account ID" }, { status: 400 });
  }
  if (userId === null && !term) {
    return NextResponse.json({ error: "Missing search term" }, { status: 400 });
  }

  const query = new URLSearchParams(userId !== null ? { user_id: userId } : { term: term! });

  try {
    // ✅ Use Apache-proxied /api/ path instead of hitting 127.0.0.1:5000 directly
    const response = await fetch(
      `${process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL}/backend/device/search?${query.toString()}`,
      {
        method: "GET",
        cache: "no-store",
        signal: AbortSignal.timeout(20000),
        headers: {
          cookie: req.headers.get("cookie") || "",
        },
      }
    );

    if (!response.ok) {
      console.error(
        "❌ Backend fetch failed:",
        response.status,
        response.statusText
      );
      return NextResponse.json(
        { error: "Failed to fetch data from backend" },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data, { status: 200, headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    console.error("🔥 Unexpected error while fetching backend:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
