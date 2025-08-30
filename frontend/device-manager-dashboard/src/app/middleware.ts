// import { NextResponse } from 'next/server'
// import type { NextRequest } from 'next/server'

// export function middleware(request: NextRequest) {
//   console.log("Middleware running on:", request.nextUrl.pathname)

//   const token = request.cookies.get("session")?.value

//   if (!token) {
//     return NextResponse.redirect(new URL("/login", request.url))
//   }

//   return NextResponse.next()
// }

// export const config = {
//   matcher: [
//     "/((?!_next/static|_next/image|favicon.ico|login).*)",
//   ],
// }


import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(req: NextRequest) {
  try {
    console.error("🔒 Middleware hit:", req.nextUrl.pathname);
  } catch (err) {}

  return NextResponse.next();
}

