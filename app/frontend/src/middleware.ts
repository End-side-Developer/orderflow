import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

// Must match settings.orderflow_refresh_cookie_name on the backend
const REFRESH_COOKIE = "orderflow_refresh";

// Routes anyone can reach without logging in. Everything else requires
// the refresh cookie. Match on full path or as a prefix.
const PUBLIC_PATHS = new Set<string>([
  "/",
  "/login",
  "/register",
  "/public",
]);
const PUBLIC_PREFIXES = ["/login/", "/register/", "/public/"];

const BLOCKED_LEGACY_PREFIXES = ["/document-summary", "/obligations"];

function isPublic(pathname: string): boolean {
  if (PUBLIC_PATHS.has(pathname)) return true;
  return PUBLIC_PREFIXES.some((p) => pathname.startsWith(p));
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Legacy routes that have been retired — bounce to dashboard so we never
  // ship two stale UIs in parallel.
  const isBlockedLegacy = BLOCKED_LEGACY_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );
  if (isBlockedLegacy) {
    const dashboardUrl = new URL("/dashboard", request.url);
    dashboardUrl.searchParams.set("legacy_flow", "blocked");
    return NextResponse.redirect(dashboardUrl);
  }

  if (isPublic(pathname)) {
    return NextResponse.next();
  }

  if (!request.cookies.has(REFRESH_COOKIE)) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Skip Next.js internals, static assets, and api proxy paths.
    "/((?!_next/static|_next/image|favicon.ico|api/|demo/).*)",
  ],
};
