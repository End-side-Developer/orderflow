"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
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
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import { CaseActionPlanData, ObligationRecord, getCaseActionPlan } from "@/lib/api/client";

type ActionPlanPanelProps = {
  documentId: string;
  onContinueToReview?: () => void;
};

const EMPTY_ACTION_ITEMS: ObligationRecord[] = [];

export function ActionPlanPanel({ documentId, onContinueToReview }: ActionPlanPanelProps) {
  const [actionPlan, setActionPlan] = useState<CaseActionPlanData | null>(null);
  // Start false so the panel shows the "generating" state immediately instead of
  // a spinner — only explicit user-triggered refreshes set this true.
  const [isLoading, setIsLoading] = useState(false);
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

  // Silent initial fetch — does not touch isLoading so the "generating" state
  // is shown immediately without a spinner blocking the view.
  useEffect(() => {
    let cancelled = false;

    void getCaseActionPlan(documentId)
      .then((response) => {
        if (cancelled) return;
        if (response.ok) {
          setActionPlan(response.data);
        } else {
          setError(response.error.message);
        }
      })
      .catch((requestError) => {
        if (cancelled) return;
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Could not load the generated action plan.",
        );
      });

    return () => {
      cancelled = true;
    };
  }, [documentId]);

  // Poll every 4 s while the plan hasn't arrived yet (generation is async).
  // Clears automatically once the plan is set or the component unmounts.
  useEffect(() => {
    if (isLoading || actionPlan) return;

    let cancelled = false;
    const interval = setInterval(() => {
      void getCaseActionPlan(documentId).then((response) => {
        if (cancelled) return;
        if (response.ok) {
          setActionPlan(response.data);
          setError(null);
        }
      });
    }, 4000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [documentId, isLoading, actionPlan]);

  const items = actionPlan?.items ?? EMPTY_ACTION_ITEMS;
  const stats = useMemo(() => buildActionPlanStats(items), [items]);
  const canContinue = items.length > 0 && Boolean(onContinueToReview);

  if (isLoading) {
    return (
      <div className="flex min-h-[200px] items-center justify-center p-6">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading generated action plan
        </div>
      </div>
    );
  }

  if (!actionPlan) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Action plan generating…</AlertTitle>
          <AlertDescription>
            {error
              ? `${error} — checking again automatically.`
              : "The action plan has not been generated yet. Checking automatically every few seconds."}
          </AlertDescription>
        </Alert>
        <div>
          <Button size="sm" type="button" variant="outline" onClick={() => void loadActionPlan()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Check now
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-0">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Generated action plan</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
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

      <div className="flex flex-col gap-4 p-6">
        {error ? (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Refresh failed</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        {/* KPI row */}
        <div className="rounded-md border border-border p-4">
          <div className="mb-3 flex items-center gap-2">
            <ClipboardList className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold text-foreground">Plan readiness</h3>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Metric label="Total items" value={String(actionPlan.total)} />
            <Metric label="Assigned owners" value={String(stats.assignedOwners)} />
            <Metric label="Dated actions" value={String(stats.datedActions)} />
          </div>
        </div>

        {/* Items */}
        {items.length === 0 ? (
          <Alert>
            <CheckCircle2 className="h-4 w-4" />
            <AlertTitle>No action items returned</AlertTitle>
            <AlertDescription>
              Refresh after generation completes, or return to the summary stage and request the
              action plan again.
            </AlertDescription>
          </Alert>
        ) : (
          <div className="flex flex-col gap-2">
            {items.map((item, index) => (
              <ActionPlanItemCard key={item.id} item={item} index={index} />
            ))}
          </div>
        )}

        {/* Footer */}
        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-5">
          <Button size="sm" type="button" variant="outline" onClick={() => void loadActionPlan()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh action plan
          </Button>
          <Button
            size="sm"
            type="button"
            variant="good"
            className="ml-auto"
            onClick={onContinueToReview}
            disabled={!canContinue}
          >
            Continue to Review
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

function ActionPlanItemCard({ item, index }: { item: ObligationRecord; index: number }) {
  const [open, setOpen] = useState(false);
  const confidencePercent = item.confidence == null ? null : clampPercent(item.confidence * 100);
  const needsHumanReview = confidencePercent != null && confidencePercent < 70;

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="rounded-md border border-border overflow-hidden"
    >
      <CollapsibleTrigger className="flex w-full items-start justify-between px-4 py-3 text-left transition-colors hover:bg-muted/50">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5 pr-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-foreground">
              {index + 1}. {item.title}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">{item.obligation_code ?? item.id}</p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Badge variant={priorityVariant(item.priority)}>
            {formatMachineLabel(item.priority)}
          </Badge>
          <Badge variant="secondary">{formatMachineLabel(item.nature_of_action ?? "other")}</Badge>
          <Badge variant={stageVariant(item.action_plan_stage)}>
            {formatMachineLabel(item.action_plan_stage)}
          </Badge>
          <ChevronDown
            className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          />
        </div>
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className="border-t border-border flex flex-col gap-4 p-4">
          {item.description ? (
            <p className="whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">
              {item.description}
            </p>
          ) : (
            <p className="text-sm text-muted-foreground/60">No description captured.</p>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <Detail icon={<UserRound className="h-4 w-4" />} label="Owner">
              {item.owner_hint || "Unassigned"}
            </Detail>
            <Detail icon={<CalendarDays className="h-4 w-4" />} label="Due date">
              {item.due_date || "Not dated"}
            </Detail>
            <Detail icon={<ShieldAlert className="h-4 w-4" />} label="Risk">
              <span className="flex flex-wrap gap-2">
                <Badge variant={riskVariant(item.risk_band)}>
                  {formatMachineLabel(item.risk_band ?? "not scored")}
                </Badge>
                {item.risk_score != null ? (
                  <Badge variant="outline">{Math.round(item.risk_score)} score</Badge>
                ) : null}
              </span>
            </Detail>
            <Detail icon={<ClipboardList className="h-4 w-4" />} label="Status">
              {formatMachineLabel(item.status)}
            </Detail>
          </div>

          {confidencePercent != null ? (
            <ConfidenceBlock
              percent={confidencePercent}
              needsReview={needsHumanReview}
              annotations={item.confidence_annotations}
            />
          ) : null}

          <SourceEvidenceBlock citation={item.citation} />
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function ConfidenceBlock({
  percent,
  needsReview,
  annotations,
}: {
  percent: number;
  needsReview: boolean;
  annotations: ObligationRecord["confidence_annotations"];
}) {
  return (
    <div className="rounded-md bg-muted p-3">
      <div className="mb-2 flex items-center justify-between gap-3 text-xs font-medium text-muted-foreground">
        <span>Extraction confidence</span>
        <span className="flex flex-wrap items-center justify-end gap-2">
          {needsReview ? <Badge variant="warn">Needs human review</Badge> : null}
          {percent}%
        </span>
      </div>
      <Progress value={percent} className="h-2" />
      {annotations?.components && Object.keys(annotations.components).length > 0 ? (
        <div className="mt-3 space-y-1.5">
          {Object.entries(annotations.components).map(([key, val]) => (
            <div key={key} className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="w-28 shrink-0 capitalize">{key.replace(/_/g, " ")}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-border">
                <div
                  className={`h-full rounded-full ${val < 0.5 ? "bg-warn" : "bg-good"}`}
                  style={{ width: `${Math.round(val * 100)}%` }}
                />
              </div>
              <span className="w-8 text-right tabular-nums">{Math.round(val * 100)}%</span>
            </div>
          ))}
        </div>
      ) : null}
      {needsReview && annotations?.rationale?.length ? (
        <ul className="mt-2 space-y-0.5 text-xs text-warn-foreground">
          {annotations.rationale.map((r, i) => (
            <li key={i} className="flex gap-1">
              <span className="shrink-0 text-warn">•</span>
              <span className="text-muted-foreground">{r}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function SourceEvidenceBlock({ citation }: { citation: ObligationRecord["citation"] }) {
  if (!citation) {
    return (
      <div className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">
        No source evidence attached.
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border p-3">
      <div className="mb-2 flex items-center gap-2">
        <FileText className="h-4 w-4 text-muted-foreground" />
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
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
            Span {citation.span_start ?? "?"}–{citation.span_end ?? "?"}
          </Badge>
        ) : null}
      </div>
      {citation.clause_span ? (
        <p className="line-clamp-4 break-words text-xs leading-5 text-muted-foreground">
          {citation.clause_span}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">Citation text was not captured.</p>
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
    <div className="rounded-md bg-muted p-3">
      <div className="mb-1 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <span className="text-muted-foreground">{icon}</span>
        {label}
      </div>
      <div className="break-words text-sm font-semibold text-foreground">{children}</div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-muted px-3 py-2.5">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-semibold text-foreground">{value}</div>
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
    { reviewPending: 0, assignedOwners: 0, datedActions: 0, criticalOrHigh: 0 },
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

function formatMachineLabel(value: string) {
  return value.replaceAll("_", " ");
}

function clampPercent(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, Math.round(value)));
}
