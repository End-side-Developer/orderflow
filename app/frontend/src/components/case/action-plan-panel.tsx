"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  FileText,
  Loader2,
  RefreshCw,
  ShieldAlert,
  UserRound,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  CaseActionPlanData,
  ObligationRecord,
  getCaseActionPlan,
} from "@/lib/api/client";

type ActionPlanPanelProps = {
  documentId: string;
  onContinueToReview?: () => void;
};

const EMPTY_ACTION_ITEMS: ObligationRecord[] = [];

export function ActionPlanPanel({
  documentId,
  onContinueToReview,
}: ActionPlanPanelProps) {
  const [actionPlan, setActionPlan] = useState<CaseActionPlanData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadActionPlan = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await getCaseActionPlan(documentId);
      if (response.ok) {
        setActionPlan(response.data);
      } else {
        setActionPlan(null);
        setError(response.error.message);
      }
    } catch (requestError) {
      setActionPlan(null);
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not load the generated action plan.",
      );
    } finally {
      setIsLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    let cancelled = false;

    setIsLoading(true);
    setError(null);

    void getCaseActionPlan(documentId)
      .then((response) => {
        if (cancelled) return;
        if (response.ok) {
          setActionPlan(response.data);
        } else {
          setActionPlan(null);
          setError(response.error.message);
        }
      })
      .catch((requestError) => {
        if (cancelled) return;
        setActionPlan(null);
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Could not load the generated action plan.",
        );
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [documentId]);

  const items = actionPlan?.items ?? EMPTY_ACTION_ITEMS;
  const stats = useMemo(() => buildActionPlanStats(items), [items]);
  const canContinue = items.length > 0 && Boolean(onContinueToReview);

  if (isLoading) {
    return (
      <div className="flex min-h-full items-center justify-center p-6">
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading generated action plan
        </div>
      </div>
    );
  }

  if (!actionPlan) {
    return (
      <div className="flex min-h-full flex-col gap-4 p-6">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Action plan unavailable</AlertTitle>
          <AlertDescription>
            {error ?? "The action plan has not been generated yet."}
          </AlertDescription>
        </Alert>
        <div>
          <Button type="button" variant="outline" onClick={() => void loadActionPlan()}>
            <RefreshCw data-icon="inline-start" />
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-full flex-col gap-5 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-950">
            Generated action plan
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            {actionPlan.total} item{actionPlan.total === 1 ? "" : "s"} extracted for review
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="secondary">{stats.reviewPending} pending review</Badge>
          <Badge variant={stats.criticalOrHigh > 0 ? "warn" : "good"}>
            {stats.criticalOrHigh} high priority
          </Badge>
        </div>
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Refresh failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <section className="rounded-md border border-slate-200 p-4">
        <div className="mb-3 flex items-center gap-2">
          <ClipboardList className="h-4 w-4 text-slate-500" />
          <h3 className="text-sm font-semibold text-slate-900">
            Plan readiness
          </h3>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Metric label="Total items" value={String(actionPlan.total)} />
          <Metric label="Assigned owners" value={String(stats.assignedOwners)} />
          <Metric label="Dated actions" value={String(stats.datedActions)} />
        </div>
      </section>

      {items.length === 0 ? (
        <Alert>
          <CheckCircle2 className="h-4 w-4" />
          <AlertTitle>No action items returned</AlertTitle>
          <AlertDescription>
            Refresh after generation completes, or return to the summary stage and request the action plan again.
          </AlertDescription>
        </Alert>
      ) : (
        <div className="flex flex-col gap-3">
          {items.map((item, index) => (
            <ActionPlanItemCard key={item.id} item={item} index={index} />
          ))}
        </div>
      )}

      <div className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-5">
        <Button type="button" variant="outline" onClick={() => void loadActionPlan()}>
          <RefreshCw data-icon="inline-start" />
          Refresh action plan
        </Button>
        <Button
          type="button"
          onClick={onContinueToReview}
          disabled={!canContinue}
        >
          Continue to Review
          <ArrowRight data-icon="inline-end" />
        </Button>
      </div>
    </div>
  );
}

function ActionPlanItemCard({
  item,
  index,
}: {
  item: ObligationRecord;
  index: number;
}) {
  const confidencePercent =
    item.confidence == null ? null : clampPercent(item.confidence * 100);
  const needsHumanReview =
    confidencePercent != null && confidencePercent < 70;

  return (
    <Card className="shadow-none">
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <CardTitle className="break-words text-sm">
              {index + 1}. {item.title}
            </CardTitle>
            <CardDescription className="mt-1 break-words">
              {item.obligation_code ?? item.id}
            </CardDescription>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <Badge variant={priorityVariant(item.priority)}>
              {formatMachineLabel(item.priority)}
            </Badge>
            <Badge variant="secondary">
              {formatMachineLabel(item.nature_of_action ?? "other")}
            </Badge>
            <Badge variant={stageVariant(item.action_plan_stage)}>
              {formatMachineLabel(item.action_plan_stage)}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {item.description ? (
          <p className="whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">
            {item.description}
          </p>
        ) : (
          <p className="text-sm text-slate-500">No description captured.</p>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <Detail icon={<UserRound className="h-4 w-4 text-slate-500" />} label="Owner">
            {item.owner_hint || "Unassigned"}
          </Detail>
          <Detail icon={<CalendarDays className="h-4 w-4 text-slate-500" />} label="Due date">
            {formatDateText(item.due_date)}
          </Detail>
          <Detail icon={<ShieldAlert className="h-4 w-4 text-slate-500" />} label="Risk">
            <span className="flex flex-wrap gap-2">
              <Badge variant={riskVariant(item.risk_band)}>
                {formatMachineLabel(item.risk_band ?? "not_scored")}
              </Badge>
              {item.risk_score != null ? (
                <Badge variant="outline">{Math.round(item.risk_score)} score</Badge>
              ) : null}
            </span>
          </Detail>
          <Detail icon={<ClipboardList className="h-4 w-4 text-slate-500" />} label="Status">
            {formatMachineLabel(item.status)}
          </Detail>
        </div>

        {confidencePercent != null ? (
          <div className="rounded-md bg-slate-50 p-3">
            <div className="mb-2 flex items-center justify-between gap-3 text-xs font-medium text-slate-600">
              <span>Extraction confidence</span>
              <span className="flex flex-wrap items-center justify-end gap-2">
                {needsHumanReview ? (
                  <Badge variant="warn">Needs human review.</Badge>
                ) : null}
                {confidencePercent}%
              </span>
            </div>
            <Progress value={confidencePercent} className="h-2" />
          </div>
        ) : null}

        <SourceEvidence citation={item.citation} />
      </CardContent>
    </Card>
  );
}

function SourceEvidence({
  citation,
}: {
  citation: ObligationRecord["citation"];
}) {
  if (!citation) {
    return (
      <div className="rounded-md border border-dashed border-slate-200 p-3 text-sm text-slate-500">
        No source evidence attached.
      </div>
    );
  }

  return (
    <div className="rounded-md border border-slate-200 p-3">
      <div className="mb-2 flex items-center gap-2">
        <FileText className="h-4 w-4 text-slate-500" />
        <p className="text-xs font-semibold uppercase text-slate-500">
          Source evidence
        </p>
      </div>
      <div className="mb-2 flex flex-wrap gap-2">
        <Badge variant="outline">
          {citation.page_number ? `Page ${citation.page_number}` : "Page not captured"}
        </Badge>
        {citation.clause_index != null ? (
          <Badge variant="muted">Clause {citation.clause_index}</Badge>
        ) : null}
        {citation.span_start != null || citation.span_end != null ? (
          <Badge variant="muted">
            Span {citation.span_start ?? "?"}-{citation.span_end ?? "?"}
          </Badge>
        ) : null}
      </div>
      {citation.clause_span ? (
        <p className="line-clamp-4 break-words text-xs leading-5 text-slate-600">
          {citation.clause_span}
        </p>
      ) : (
        <p className="text-xs text-slate-500">Citation text was not captured.</p>
      )}
    </div>
  );
}

function Detail({
  icon,
  label,
  children,
}: {
  icon: ReactNode;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-md bg-slate-50 p-3">
      <div className="mb-1 flex items-center gap-2 text-xs font-medium text-slate-500">
        {icon}
        {label}
      </div>
      <div className="break-words text-sm font-semibold text-slate-950">
        {children}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-50 px-3 py-2">
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className="mt-1 text-lg font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function buildActionPlanStats(items: ObligationRecord[]) {
  return items.reduce(
    (stats, item) => {
      if (item.review_state === "pending_review") stats.reviewPending += 1;
      if (item.owner_hint) stats.assignedOwners += 1;
      if (item.due_date) stats.datedActions += 1;
      if (item.priority === "high" || item.priority === "critical") {
        stats.criticalOrHigh += 1;
      }
      return stats;
    },
    {
      reviewPending: 0,
      assignedOwners: 0,
      datedActions: 0,
      criticalOrHigh: 0,
    },
  );
}

function priorityVariant(priority: ObligationRecord["priority"]) {
  if (priority === "critical") return "destructive" as const;
  if (priority === "high") return "warn" as const;
  if (priority === "medium") return "secondary" as const;
  return "good" as const;
}

function stageVariant(stage: ObligationRecord["action_plan_stage"]) {
  if (stage === "rejected") return "destructive" as const;
  if (stage === "approved" || stage === "edited") return "good" as const;
  if (stage === "review_pending") return "warn" as const;
  return "muted" as const;
}

function riskVariant(riskBand: ObligationRecord["risk_band"]) {
  if (riskBand === "critical" || riskBand === "high") return "destructive" as const;
  if (riskBand === "moderate") return "warn" as const;
  if (riskBand === "low") return "good" as const;
  return "muted" as const;
}

function formatDateText(value: string | null) {
  return value || "Not dated";
}

function formatMachineLabel(value: string) {
  return value.replaceAll("_", " ");
}

function clampPercent(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, Math.round(value)));
}
