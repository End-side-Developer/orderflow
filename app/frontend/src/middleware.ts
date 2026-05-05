import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

// Must match settings.orderflow_refresh_cookie_name on the backend
const REFRESH_COOKIE = "orderflow_refresh";

// Paths that require a logged-in session (presence of refresh cookie)
const PROTECTED_PREFIXES = ["/dashboard", "/profile", "/admin"];
const BLOCKED_LEGACY_PREFIXES = ["/document-summary", "/obligations"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const isBlockedLegacy = BLOCKED_LEGACY_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );

  if (isBlockedLegacy) {
    const dashboardUrl = new URL("/dashboard", request.url);
    dashboardUrl.searchParams.set("legacy_flow", "blocked");
    return NextResponse.redirect(dashboardUrl);
  }

  const isProtected = PROTECTED_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );

  if (isProtected && !request.cookies.has(REFRESH_COOKIE)) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Skip Next.js internals and static files
    "/((?!_next/static|_next/image|favicon.ico|api/).*)",
  ],
};
