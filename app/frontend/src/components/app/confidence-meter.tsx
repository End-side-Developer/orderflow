import * as React from "react";

import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

interface ConfidenceMeterProps {
  value: number;
  label?: string;
  compact?: boolean;
  className?: string;
}

export function getConfidenceTone(value: number): {
  label: string;
  textClass: string;
  indicatorClass: string;
} {
  if (value >= 0.7) {
    return { label: "High", textClass: "text-good", indicatorClass: "bg-good" };
  }
  if (value >= 0.4) {
    return { label: "Moderate", textClass: "text-warn", indicatorClass: "bg-warn" };
  }
  return { label: "Low", textClass: "text-destructive", indicatorClass: "bg-destructive" };
}

export function ConfidenceMeter({
  value,
  label,
  compact = false,
  className,
}: ConfidenceMeterProps) {
  const tone = getConfidenceTone(value);
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));

  if (compact) {
    return (
      <div className={cn("flex items-center gap-2", className)}>
        <Progress value={pct} indicatorClassName={tone.indicatorClass} className="h-1.5 w-24" />
        <span className={cn("min-w-[32px] text-right text-xs font-semibold", tone.textClass)}>
          {pct}%
        </span>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold uppercase tracking-wide text-muted-foreground">
          {label ?? "Confidence"}
        </span>
        <span className={cn("font-semibold", tone.textClass)}>
          {pct}% · {tone.label}
        </span>
      </div>
      <Progress value={pct} indicatorClassName={tone.indicatorClass} />
    </div>
  );
}
