"use client";

import type { ReactNode } from "react";

import type { UserRole } from "./permissions";
import { useAuthStore } from "./store";

interface RequireRoleProps {
  roles: UserRole[];
  fallback?: ReactNode;
  children: ReactNode;
}

export function RequireRole({ roles, fallback = null, children }: RequireRoleProps) {
  const user = useAuthStore((s) => s.user);
  if (!user || !roles.includes(user.role)) {
    return <>{fallback}</>;
  }
  return <>{children}</>;
}


