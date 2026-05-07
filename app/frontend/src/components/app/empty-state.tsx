import * as React from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  message?: React.ReactNode;
  detail?: React.ReactNode;
  requestId?: string;
  actionHref?: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  message,
  detail,
  requestId,
  actionHref,
  actionLabel,
  onAction,
  className,
}: EmptyStateProps) {
  return (
    <Card className={cn("mx-auto w-full max-w-xl", className)}>
      <CardContent className="flex flex-col items-center gap-4 px-8 py-10 text-center">
        {icon ? <div className="text-muted-foreground">{icon}</div> : null}
        <div className="flex flex-col gap-2">
          <h2 className="text-lg font-semibold text-foreground">{title}</h2>
          {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
        </div>
        {detail || requestId ? (
          <div className="w-full rounded-md border border-border bg-muted/30 p-3 text-left">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Cause
            </div>
            {detail ? (
              <p className="mt-1 text-sm leading-relaxed text-foreground/90">{detail}</p>
            ) : null}
            {requestId ? (
              <p className="mt-2 text-xs text-muted-foreground">Request id: {requestId}</p>
            ) : null}
          </div>
        ) : null}
        {actionHref && actionLabel ? (
          <Button asChild>
            <Link href={actionHref}>{actionLabel}</Link>
          </Button>
        ) : null}
        {onAction && actionLabel ? <Button onClick={onAction}>{actionLabel}</Button> : null}
      </CardContent>
    </Card>
  );
}
