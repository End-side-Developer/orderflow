import * as React from "react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type KpiTone = "default" | "warn" | "destructive" | "good" | "accent" | "muted";

interface KpiTileProps {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  tone?: KpiTone;
  icon?: React.ReactNode;
  className?: string;
}

const TONE_VALUE: Record<KpiTone, string> = {
  default: "text-foreground",
  warn: "text-warn",
  destructive: "text-destructive",
  good: "text-good",
  accent: "text-accent",
  muted: "text-muted-foreground",
};

export function KpiTile({ label, value, hint, tone = "default", icon, className }: KpiTileProps) {
  return (
    <Card className={cn("flex h-full flex-col", className)}>
      <CardContent className="flex flex-col gap-2 p-5 pt-5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {label}
          </span>
          {icon ? <span className="text-muted-foreground">{icon}</span> : null}
        </div>
        <div
          className={cn("text-3xl font-semibold leading-tight tracking-tight", TONE_VALUE[tone])}
        >
          {value}
        </div>
        {hint ? <p className="text-sm text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}
