"use client";

import { Progress } from "@/components/ui/progress";
import type { ObligationRiskBand, ObligationRiskFactor } from "@/lib/api/client";
import { cn } from "@/lib/utils";

type RiskScoreGaugeProps = {
  score: number | null;
  band: ObligationRiskBand | null;
  factors?: ObligationRiskFactor[];
  compact?: boolean;
};

const BAND_TEXT: Record<ObligationRiskBand, string> = {
  low: "text-good",
  moderate: "text-warn",
  high: "text-warn",
  critical: "text-destructive",
};

const BAND_INDICATOR: Record<ObligationRiskBand, string> = {
  low: "bg-good",
  moderate: "bg-warn",
  high: "bg-warn",
  critical: "bg-destructive",
};

const BAND_LABEL: Record<ObligationRiskBand, string> = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
  critical: "Critical",
};

function deriveBand(score: number | null): ObligationRiskBand {
  if (score === null || score === undefined) return "low";
  if (score >= 75) return "critical";
  if (score >= 50) return "high";
  if (score >= 25) return "moderate";
  return "low";
}

function formatFactorName(name: string): string {
  return name
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function RiskScoreGauge({ score, band, factors, compact = false }: RiskScoreGaugeProps) {
  const resolvedScore = score ?? 0;
  const resolvedBand: ObligationRiskBand = band ?? deriveBand(score);
  const widthPct = Math.max(0, Math.min(100, resolvedScore));
  const tone = BAND_TEXT[resolvedBand];

  return (
    <div className={cn("flex flex-col gap-1.5", compact ? "min-w-[140px]" : "min-w-[200px]")}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-semibold text-foreground">Contempt-Risk</span>
        <span
          className={cn("font-semibold tabular-nums", tone, compact ? "text-base" : "text-xl")}
          aria-label={`Risk score ${resolvedScore} out of 100`}
        >
          {resolvedScore}
          <span className="ml-1 text-[11px] text-muted-foreground">/100</span>
        </span>
      </div>
      <Progress
        value={widthPct}
        indicatorClassName={BAND_INDICATOR[resolvedBand]}
        className={compact ? "h-1.5" : "h-2"}
      />
      <span className={cn("text-[11px] font-semibold uppercase tracking-wide", tone)}>
        {BAND_LABEL[resolvedBand]} risk band
      </span>
      {!compact && factors && factors.length > 0 ? (
        <ul className="mt-1 flex flex-col gap-1 text-xs text-muted-foreground">
          <li className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Top contributing factors
          </li>
          {factors.slice(0, 3).map((factor) => (
            <li key={factor.name} className="flex gap-2 leading-snug">
              <span className="whitespace-nowrap font-semibold text-foreground">
                {formatFactorName(factor.name)}
              </span>
              <span className="text-muted-foreground">
                +{factor.contribution.toFixed(1)} pts — {factor.detail}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}


