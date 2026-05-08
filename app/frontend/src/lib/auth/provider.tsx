"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

import { registerAuthHandlers } from "@/lib/api/client";

import { useAuthStore } from "./store";

// Routes that should NOT trigger a logout-redirect (we are already on the
// login surface, or on a public page that does not need a session).
const NO_REDIRECT_PATHS = ["/login", "/register", "/public", "/"];

function shouldRedirectOnLogout(pathname: string): boolean {
  if (NO_REDIRECT_PATHS.includes(pathname)) return false;
  if (pathname.startsWith("/login/")) return false;
  if (pathname.startsWith("/register/")) return false;
  if (pathname.startsWith("/public/")) return false;
  // The root path is public in this app
  if (pathname === "/") return false;
  return true;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const bootstrap = useAuthStore((s) => s.bootstrap);
  const status = useAuthStore((s) => s.status);
  const pathname = usePathname();

  useEffect(() => {
    // Wire the store's token getter and refresh function into the API client.
    // Done here (not at module level) to avoid a circular import between client ↔ store.
    registerAuthHandlers(
      () => useAuthStore.getState().accessToken,
      () => useAuthStore.getState().refreshAccessToken(),
    );
    bootstrap();

    // Hard-redirect to /login on logout / refresh-failure events. The store
    // dispatches `auth:logout` whenever the session is cleared (manual logout
    // or token refresh failure), so any open protected page bounces out.
    function onLogout() {
      if (typeof window === "undefined") return;
      if (!shouldRedirectOnLogout(window.location.pathname)) return;
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.replace(`/login?redirect=${next}`);
    }
    window.addEventListener("auth:logout", onLogout);
    return () => {
      window.removeEventListener("auth:logout", onLogout);
    };
  }, [bootstrap]);

  // If we are on a protected route and still loading the session,
  // block rendering to prevent race conditions in child component useEffects.
  if (status === "loading" && shouldRedirectOnLogout(pathname)) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-2">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <p className="animate-pulse text-sm text-muted-foreground">Initializing session...</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}


