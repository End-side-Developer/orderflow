"use client";

import { useEffect } from "react";

import { registerAuthHandlers } from "@/lib/api/client";

import { useAuthStore } from "./store";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const bootstrap = useAuthStore((s) => s.bootstrap);

  useEffect(() => {
    // Wire the store's token getter and refresh function into the API client.
    // Done here (not at module level) to avoid a circular import between client ↔ store.
    registerAuthHandlers(
      () => useAuthStore.getState().accessToken,
      () => useAuthStore.getState().refreshAccessToken(),
    );
    bootstrap();
  }, [bootstrap]);

  return <>{children}</>;
}


