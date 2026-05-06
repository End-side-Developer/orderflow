import * as React from "react";

import { Badge, type BadgeProps } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type Variant = NonNullable<BadgeProps["variant"]>;

type Pressure = "stable" | "watch" | "urgent" | "critical";
type Priority = "critical" | "high" | "medium" | "low";
type Escalation = "none" | "watch" | "escalated" | "critical";
type Review = "pending_review" | "approved" | "rejected";

const PRESSURE: Record<Pressure, { variant: Variant; label: string }> = {
  stable: { variant: "good", label: "Stable" },
  watch: { variant: "warn", label: "Watch" },
  urgent: { variant: "warn", label: "Urgent" },
  critical: { variant: "destructive", label: "Critical" },
};

const PRIORITY: Record<Priority, { variant: Variant; label: string }> = {
  critical: { variant: "destructive", label: "Critical" },
  high: { variant: "warn", label: "High" },
  medium: { variant: "accent", label: "Medium" },
  low: { variant: "muted", label: "Low" },
};

const ESCALATION: Record<Escalation, { variant: Variant; label: string }> = {
  none: { variant: "muted", label: "None" },
  watch: { variant: "warn", label: "Watch" },
  escalated: { variant: "warn", label: "Escalated" },
  critical: { variant: "destructive", label: "Critical" },
};

const REVIEW: Record<Review, { variant: Variant; label: string }> = {
  pending_review: { variant: "warn", label: "Pending review" },
  approved: { variant: "good", label: "Approved" },
  rejected: { variant: "destructive", label: "Rejected" },
};

type StatusPillProps =
  | { kind: "pressure"; value: Pressure; className?: string }
  | { kind: "priority"; value: Priority; className?: string }
  | { kind: "escalation"; value: Escalation; className?: string }
  | { kind: "review"; value: Review; className?: string };

export function StatusPill(props: StatusPillProps) {
  const map = {
    pressure: PRESSURE,
    priority: PRIORITY,
    escalation: ESCALATION,
    review: REVIEW,
  } as const;

  const dictionary = map[props.kind] as Record<string, { variant: Variant; label: string }>;
  const entry = dictionary[props.value as string] ?? { variant: "muted" as Variant, label: String(props.value) };

  return <Badge variant={entry.variant} className={cn(props.className)}>{entry.label}</Badge>;
}


