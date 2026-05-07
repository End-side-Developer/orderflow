"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { LogOut, Settings, User } from "lucide-react";

import { ROUTES, WORKFLOW_STAGES, visibleRoutes } from "@/lib/labels";
import { useAuthStore } from "@/lib/auth/store";
import { ROLE_LABELS } from "@/lib/auth/permissions";
import { logoutUser } from "@/lib/api/client";
import { Badge } from "@/components/ui/badge";
import { InfoHint } from "@/components/info-hint";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

function isRouteActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`) || pathname.startsWith(`${href}?`);
}

function UserInitials({ name, email }: { name: string | null; email: string }) {
  const text = name ?? email;
  const initials = text
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
  return (
    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
      {initials || "U"}
    </span>
  );
}

export function TopNav() {
  const pathname = usePathname();
  const router = useRouter();
  const [currentDocumentId, setCurrentDocumentId] = useState<string | null>(null);

  const storedUser = useAuthStore((s) => s.user);
  const status = useAuthStore((s) => s.status);
  const clearSession = useAuthStore((s) => s.clearSession);
  const user = status === "authed" ? storedUser : null;

  // Demo mode (no user): show the original workflow routes (no dashboard/admin).
  // Logged in: filter by the user's role so each role sees only their routes.
  const displayRoutes = useMemo(() => {
    if (!user) {
      return ROUTES.filter((r) => r.key !== "dashboard" && r.key !== "admin");
    }
    return visibleRoutes(user.role);
  }, [user]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const sync = (): void => {
      setCurrentDocumentId(
        window.localStorage.getItem("orderflow:current_document_id") ??
          window.localStorage.getItem("orderflow:last_uploaded_document_id"),
      );
    };
    sync();
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("storage", sync);
    };
  }, [pathname]);

  const currentStageIndex = useMemo(() => {
    const idx = WORKFLOW_STAGES.findIndex((stage) => isRouteActive(pathname, stage.href));
    return idx === -1 ? -1 : idx;
  }, [pathname]);

  async function handleLogout() {
    await logoutUser();
    clearSession();
    router.push("/login");
  }

  if (pathname === "/login" || pathname === "/register") {
    return null;
  }

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex w-full max-w-[1380px] flex-col gap-3 px-6 py-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-6">
          <Link href="/" className="text-lg font-semibold tracking-tight text-foreground">
            OrderFlow
          </Link>
          <nav aria-label="Primary" className="flex flex-wrap items-center gap-1">
            {displayRoutes.map((route) => {
              const active = isRouteActive(pathname, route.href);
              return (
                <Link
                  key={route.href}
                  href={route.href}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    active
                      ? "bg-secondary text-foreground"
                      : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                  )}
                  aria-current={active ? "page" : undefined}
                >
                  {route.simpleLabel ?? route.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center gap-3">
          <ol
            aria-label="Workflow stages"
            className="hidden items-center gap-1 text-xs font-semibold lg:flex"
          >
            {WORKFLOW_STAGES.map((stage, index) => {
              const reached = currentStageIndex !== -1 && index <= currentStageIndex;
              const active = currentStageIndex === index;
              return (
                <li key={stage.href} className="flex items-center gap-1">
                  <Link
                    href={stage.href}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 transition-colors",
                      active
                        ? "border-primary/40 bg-primary/15 text-primary"
                        : reached
                          ? "border-border bg-secondary/50 text-foreground"
                          : "border-border bg-transparent text-muted-foreground",
                    )}
                  >
                    <span
                      className={cn(
                        "flex h-4 w-4 items-center justify-center rounded-full text-[10px]",
                        active
                          ? "bg-primary text-primary-foreground"
                          : reached
                            ? "bg-foreground/20 text-foreground"
                            : "bg-muted text-muted-foreground",
                      )}
                    >
                      {index + 1}
                    </span>
                    {stage.simpleLabel ?? stage.label}
                  </Link>
                  <div className="hidden lg:block">
                    <InfoHint glossaryKey={stage.key} side="bottom" />
                  </div>
                  {index < WORKFLOW_STAGES.length - 1 ? (
                    <span aria-hidden="true" className="text-muted-foreground">
                      ›
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ol>

          <div className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-1.5 text-xs">
            <span className="font-semibold uppercase tracking-wide text-muted-foreground">
              Document
            </span>
            <span className="font-mono text-foreground">
              {currentDocumentId ? currentDocumentId.slice(0, 8) : "none"}
            </span>
          </div>

          {/* User menu — shown when auth status is resolved */}
          {status !== "loading" &&
            (user ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    className="flex items-center gap-2 rounded-md p-1 transition-colors hover:bg-secondary/60"
                    aria-label="User menu"
                  >
                    <UserInitials name={user.full_name} email={user.email} />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuLabel className="flex flex-col gap-1">
                    <span className="truncate font-medium">{user.full_name ?? user.email}</span>
                    <span className="truncate text-xs font-normal text-muted-foreground">
                      {user.email}
                    </span>
                    <Badge variant="outline" className="mt-1 w-fit text-xs">
                      {ROLE_LABELS[user.role]}
                    </Badge>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem asChild>
                    <Link href="/dashboard" className="flex items-center gap-2">
                      <User className="h-4 w-4" />
                      Dashboard
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link href="/profile" className="flex items-center gap-2">
                      <Settings className="h-4 w-4" />
                      Profile
                    </Link>
                  </DropdownMenuItem>
                  {(user.role === "judge" || user.role === "government") && (
                    <DropdownMenuItem asChild>
                      <Link href="/admin/verifications" className="flex items-center gap-2">
                        <Settings className="h-4 w-4" />
                        Admin
                      </Link>
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    className="flex items-center gap-2 text-destructive focus:text-destructive"
                    onClick={() => void handleLogout()}
                  >
                    <LogOut className="h-4 w-4" />
                    Sign out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Link
                href="/login"
                className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
              >
                Sign in
              </Link>
            ))}
        </div>
      </div>
    </header>
  );
}
