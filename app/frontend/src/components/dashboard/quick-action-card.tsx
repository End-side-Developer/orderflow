import { ReactNode } from "react";
import { ChevronRight } from "lucide-react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface QuickActionCardProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  onClick?: () => void;
  tone?: "primary" | "accent" | "warn" | "good";
}

const TONE_TO_CHIP: Record<NonNullable<QuickActionCardProps["tone"]>, string> = {
  primary: "icon-chip",
  accent: "icon-chip icon-chip-accent",
  warn: "icon-chip icon-chip-warn",
  good: "icon-chip icon-chip-good",
};

export function QuickActionCard({
  icon,
  title,
  description,
  onClick,
  tone = "primary",
}: QuickActionCardProps) {
  return (
    <Card
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      className={cn(
        "card-interactive group cursor-pointer border-border bg-card",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
      )}
    >
      <div className="flex items-center justify-between gap-4 p-5">
        <div className="flex items-center gap-4">
          {icon ? (
            <div className={cn(TONE_TO_CHIP[tone], "[&_svg]:h-4 [&_svg]:w-4")}>{icon}</div>
          ) : null}
          <div className="flex flex-col gap-1">
            <span className="text-sm font-semibold leading-tight text-foreground">{title}</span>
            {description ? (
              <span className="text-xs leading-snug text-muted-foreground">{description}</span>
            ) : null}
          </div>
        </div>
        <ChevronRight
          aria-hidden="true"
          className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground"
        />
      </div>
    </Card>
  );
}
