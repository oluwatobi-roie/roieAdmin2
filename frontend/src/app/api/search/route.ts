import { NextResponse } from "next/server";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const term = searchParams.get("term");

  if (!term) {
    return NextResponse.json({ error: "Missing search term" }, { status: 400 });
  }

  try {
    // ✅ Use Apache-proxied /api/ path instead of hitting 127.0.0.1:5000 directly
    const response = await fetch(
      `${process.env.NEXT_PUBLIC_BACKEND_URL}/backend/device/search?term=${encodeURIComponent(term)}`,
      {
        method: "GET",
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
    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error("🔥 Unexpected error while fetching backend:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
