import type { NextRequest } from "next/server";

// One line per request, so `fly logs` shows what people actually search for.
// Query strings are public search terms; no cookies or headers are logged.
export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  console.log(`[hit] ${request.method} ${pathname}${search}`);
}

export const config = {
  matcher: ["/", "/api/:path*"],
};
