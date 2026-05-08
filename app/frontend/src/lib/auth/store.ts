import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { UserRole } from "./permissions";

export type UserSummary = {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  status: string;
};

type AuthStatus = "loading" | "authed" | "anon";

type AuthState = {
  accessToken: string | null;
  user: UserSummary | null;
  status: AuthStatus;
};

type AuthActions = {
  setSession: (token: string, user: UserSummary) => void;
  clearSession: () => void;
  bootstrap: () => Promise<void>;
  refreshAccessToken: () => Promise<string | null>;
};

// Always same-origin so the orderflow_refresh cookie is reachable. The
// Next.js rewrite in next.config.mjs proxies /api/v1/* to the backend.
// NEXT_PUBLIC_ORDERFLOW_API_BASE_URL is intentionally NOT honored — see
// the matching note in lib/api/client.ts.
const API_BASE = "/api/v1";

// Simple lock to prevent parallel refresh calls
let refreshPromise: Promise<string | null> | null = null;

async function callRefresh(): Promise<{ token: string; user: UserSummary } | null> {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) return null;
    const body = (await res.json()) as { data?: { access_token?: string; user?: UserSummary } };
    const token = body?.data?.access_token;
    const user = body?.data?.user;
    if (token && user) return { token, user };
  } catch {
    // network error
  }
  return null;
}

export const useAuthStore = create<AuthState & AuthActions>()(
  persist(
    (set, get) => ({
      accessToken: null,
      user: null,
      status: "loading" as AuthStatus,

      setSession(token, user) {
        set({ accessToken: token, user, status: "authed" });
      },

      clearSession() {
        set({ accessToken: null, user: null, status: "anon" });
      },

      async bootstrap() {
        // Use the locked refresh method to avoid double-fetching on mount
        await get().refreshAccessToken();
        
        // If we still don't have a token after refresh, but we have a persisted user,
        // the status will be "anon" (via refreshAccessToken's failure path).
        // If it succeeded, status will be "authed".
      },

      async refreshAccessToken() {
        // Atomic refresh to prevent race conditions on page load/parallel requests
        if (refreshPromise) return refreshPromise;

        refreshPromise = (async () => {
          try {
            const result = await callRefresh();
            if (result) {
              set({ accessToken: result.token, user: result.user, status: "authed" });
              return result.token;
            }
            // Refresh failed — clear session
            set({ accessToken: null, user: null, status: "anon" });
            if (typeof window !== "undefined") {
              window.dispatchEvent(new Event("auth:logout"));
            }
            return null;
          } finally {
            refreshPromise = null;
          }
        })();

        return refreshPromise;
      },
    }),
    {
      name: "orderflow-auth",
      storage: createJSONStorage(() => {
        if (typeof window === "undefined") {
          return {
            getItem: () => null,
            setItem: () => {},
            removeItem: () => {},
          };
        }
        return localStorage;
      }),
      // Only persist the user summary — access token stays in memory
      partialize: (state) => ({ user: state.user }),
    },
  ),
);

// Convenience selectors
export const selectUser = (s: AuthState & AuthActions) => s.user;
export const selectRole = (s: AuthState & AuthActions) => s.user?.role ?? null;
export const selectIsAuthed = (s: AuthState & AuthActions) => s.status === "authed";
export const selectIsLoading = (s: AuthState & AuthActions) => s.status === "loading";
