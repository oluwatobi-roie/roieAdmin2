import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const term = req.nextUrl.searchParams.get("term");
  const session_token = req.cookies.get("session_token")?.value;

  if (!term) {
    return NextResponse.json({ error: "Search term is required" }, { status: 400 });
  }

  try {
    const response = await fetch(
      `http://127.0.0.1:5000/api/device/search?term=${term}`,
      {
        method: "GET",
        headers: {
          cookie: `session_token=${session_token}`, // forward cookie
        },
      }
    );

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error("API error:", error);
    return NextResponse.json({ error: "Failed to fetch data from backend" }, { status: 500 });
  }
}
