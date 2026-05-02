"use client";

import { useEffect, useMemo, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { AlertTriangle } from "lucide-react";

import { PageHeader } from "@/components/app/page-header";
import { KpiTile } from "@/components/app/kpi-tile";
import { StatusPill } from "@/components/app/status-pill";
import { EmptyState } from "@/components/app/empty-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { RiskScoreGauge } from "@/components/risk-score-gauge";
import {
  getDocumentWorkbench,
  getIntakeWorkflowStatus,
  getObligationAuditTrail,
  getWorkflowRun,
  listEscalations,
  listObligations,
  type EscalationSummaryItem,
  type ObligationAuditEvent,
  type ObligationRecord,
  type WorkbenchDocumentData,
  type WorkflowRunRecord,
} from "@/lib/api/client";

type LoadState = "idle" | "loading" | "success" | "error";
const RISK_POLL_MS = 15000;

function daysUntilDue(value: string | null): number | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return Math.ceil((parsed.getTime() - Date.now()) / (24 * 60 * 60 * 1000));
}

function formatDateTime(value: string | null): string {
  if (!value) return "n/a";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function formatDueDate(value: string | null): string {
  if (!value) return "No deadline";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString();
}

function formatEscalationReason(reason: string): string {
  return reason.replaceAll("_", " ");
}

function formatAuditPayload(payload: Record<string, unknown> | null): string | null {
  if (!payload) return null;
  const fields = Object.entries(payload)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => `${key}: ${String(value)}`);
  return fields.length === 0 ? null : fields.join(" · ");
}

function formatAuditAction(action: string): string {
  return action.replaceAll(".", " ");
}

import { InfoHint } from "@/components/info-hint";

export default function RiskPage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4">
          <Skeleton className="h-12 w-full max-w-md" />
          <Skeleton className="h-32 w-full" />
        </div>
      }
    >
      <RiskContent />
    </Suspense>
  );
}

function RiskContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const documentId = searchParams.get("document_id")?.trim() ?? "";
  const workflowRunId = searchParams.get("workflow_run_id")?.trim() ?? "";

  useEffect(() => {
    if (!documentId && typeof window !== "undefined") {
      const savedDocumentId = window.localStorage.getItem("orderflow:current_document_id");
      if (savedDocumentId) {
        router.replace(`/risk?document_id=${encodeURIComponent(savedDocumentId)}`);
      }
    }
  }, [documentId, router]);

  const [state, setState] = useState<LoadState>("idle");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [warningText, setWarningText] = useState<string | null>(null);
  const [workflowRun, setWorkflowRun] = useState<WorkflowRunRecord | null>(null);
  const [obligations, setObligations] = useState<ObligationRecord[]>([]);
  const [escalations, setEscalations] = useState<EscalationSummaryItem[]>([]);
  const [criticalEscalations, setCriticalEscalations] = useState(0);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);

  const [auditTargetObligationId, setAuditTargetObligationId] = useState<string | null>(null);
  const [auditTargetTitle, setAuditTargetTitle] = useState<string | null>(null);
  const [auditState, setAuditState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditItems, setAuditItems] = useState<ObligationAuditEvent[]>([]);
  const [documentWorkbench, setDocumentWorkbench] = useState<WorkbenchDocumentData | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load(silent: boolean): Promise<void> {
      if (!documentId && !workflowRunId) {
        setState("idle");
        setErrorText(null);
        setWarningText(null);
        setWorkflowRun(null);
        setObligations([]);
        setEscalations([]);
        setCriticalEscalations(0);
        setLastRefreshedAt(null);
        setAuditTargetObligationId(null);
        setAuditTargetTitle(null);
        setAuditState("idle");
        setAuditError(null);
        setAuditItems([]);
        return;
      }
      if (!silent) {
        setState("loading");
        setErrorText(null);
      }
      const warnings: string[] = [];
      let resolvedRun: WorkflowRunRecord | null = null;
      if (workflowRunId) {
        const byRunId = await getWorkflowRun(workflowRunId);
        if (!byRunId.ok) warnings.push(`Workflow lookup warning: ${byRunId.error.message}`);
        else resolvedRun = byRunId.data;
      }
      if (!resolvedRun && documentId) {
        const byDocument = await getIntakeWorkflowStatus(documentId);
        if (!byDocument.ok) warnings.push(`Workflow status warning: ${byDocument.error.message}`);
        else resolvedRun = byDocument.data;
      }
      let resolvedObligations: ObligationRecord[] = [];
      let resolvedEscalations: EscalationSummaryItem[] = [];
      let resolvedCriticalEscalations = 0;
      if (documentId) {
        const obligationsResult = await listObligations(documentId);
        if (!obligationsResult.ok) {
          if (silent) {
            setWarningText(`Auto-refresh warning: ${obligationsResult.error.message}`);
            return;
          }
          if (!cancelled) {
            setState("error");
            setErrorText(obligationsResult.error.message);
            setWorkflowRun(resolvedRun);
            setObligations([]);
            setEscalations([]);
            setCriticalEscalations(0);
          }
          return;
        }
        resolvedObligations = obligationsResult.data.items;
        const escalationResult = await listEscalations(documentId);
        if (!escalationResult.ok) {
          warnings.push(`Escalation summary warning: ${escalationResult.error.message}`);
        } else {
          resolvedEscalations = escalationResult.data.items;
          resolvedCriticalEscalations = escalationResult.data.critical_total;
        }
      }
      if (cancelled) return;
      setWorkflowRun(resolvedRun);
      setObligations(resolvedObligations);
      setEscalations(resolvedEscalations);
      setCriticalEscalations(resolvedCriticalEscalations);
      setWarningText(warnings.length > 0 ? warnings.join(" ") : null);
      setLastRefreshedAt(new Date().toISOString());
      setState("success");
    }
    void load(false);
    if (!documentId && !workflowRunId) {
      return () => {
        cancelled = true;
      };
    }
    const intervalId = window.setInterval(() => {
      void load(true);
    }, RISK_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [documentId, workflowRunId]);

  useEffect(() => {
    let cancelled = false;
    async function loadWorkbench(): Promise<void> {
      if (!documentId) {
        setDocumentWorkbench(null);
        return;
      }
      const result = await getDocumentWorkbench(documentId);
      if (cancelled || !result.ok) return;
      setDocumentWorkbench(result.data);
    }
    void loadWorkbench();
    return () => {
      cancelled = true;
    };
  }, [documentId, workflowRunId]);

  useEffect(() => {
    if (documentId && typeof window !== "undefined") {
      window.localStorage.setItem("orderflow:current_document_id", documentId);
    }
  }, [documentId]);

  async function toggleAuditTimeline(item: EscalationSummaryItem): Promise<void> {
    if (auditTargetObligationId === item.obligation_id) {
      setAuditTargetObligationId(null);
      setAuditTargetTitle(null);
      setAuditState("idle");
      setAuditError(null);
      setAuditItems([]);
      return;
    }
    setAuditTargetObligationId(item.obligation_id);
    setAuditTargetTitle(item.title);
    setAuditState("loading");
    setAuditError(null);
    setAuditItems([]);
    const result = await getObligationAuditTrail(item.obligation_id);
    if (!result.ok) {
      setAuditState("error");
      setAuditError(result.error.message);
      return;
    }
    setAuditState("ready");
    setAuditItems(result.data.items);
  }

  const metrics = useMemo(() => {
    const activeObligations = obligations.filter(
      (item) => item.status !== "completed" && item.status !== "cancelled",
    );
    const nearBreach = activeObligations.filter((item) => {
      const days = daysUntilDue(item.due_date);
      return days !== null && days <= 3;
    }).length;
    const criticalPaths = activeObligations.filter((item) => item.priority === "critical").length;
    return {
      nearBreach,
      escalationsOpen: escalations.length,
      criticalEscalations,
      criticalPaths,
      totalObligations: obligations.length,
    };
  }, [criticalEscalations, escalations.length, obligations]);

  const escalationQueue = useMemo(() => escalations.slice(0, 8), [escalations]);

  if (state === "idle" && !documentId && !workflowRunId) {
    return (
      <EmptyState
        title="No context selected"
        message="Open Escalate with a document id or workflow run id."
        actionHref="/obligations"
        actionLabel="Pick from Verify"
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={
          <span className="flex items-center gap-1.5">
            Urgent issues <InfoHint glossaryKey="escalate" />
          </span>
        }
        title="Risk and escalation dashboard"
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span>
              Document: <span className="font-mono text-xs">{documentId || "n/a"}</span>
            </span>
            <span>
              Run: <span className="font-mono text-xs">{workflowRunId || workflowRun?.run_id || "n/a"}</span>
            </span>
            <span>
              Polling every {Math.round(RISK_POLL_MS / 1000)}s · Refreshed{" "}
              {lastRefreshedAt ? formatDateTime(lastRefreshedAt) : "n/a"}
            </span>
          </span>
        }
      />

      {state === "loading" ? (
        <section className="grid gap-3 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </section>
      ) : null}

      {state === "error" ? (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>Could not load risk data</AlertTitle>
          <AlertDescription>{errorText}</AlertDescription>
        </Alert>
      ) : null}

      {state === "success" ? (
        <>
          {warningText ? (
            <Alert variant="warn">
              <AlertTriangle />
              <AlertTitle>Warning</AlertTitle>
              <AlertDescription>{warningText}</AlertDescription>
            </Alert>
          ) : null}

          <section className="grid gap-3 md:grid-cols-3">
            <KpiTile
              label="Near-breach"
              value={metrics.nearBreach}
              tone={metrics.nearBreach > 0 ? "warn" : "default"}
              hint="Active obligations due in ≤3 days"
            />
            <KpiTile
              label="Escalations open"
              value={metrics.escalationsOpen}
              tone={metrics.escalationsOpen > 0 ? "warn" : "default"}
            />
            <KpiTile
              label="Critical escalations"
              value={metrics.criticalEscalations}
              tone={metrics.criticalEscalations > 0 ? "destructive" : "default"}
            />
          </section>

          {documentWorkbench?.next_actions.length ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Recommended next moves</CardTitle>
                <CardDescription>
                  Workbench stage: {documentWorkbench.document.stage.replaceAll("_", " ")}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {documentWorkbench.next_actions.map((action) => {
                  const variant: "destructive" | "warn" | "muted" =
                    action.priority === "critical"
                      ? "destructive"
                      : action.priority === "high"
                        ? "warn"
                        : "muted";
                  return (
                    <div
                      key={`${action.priority}-${action.title}`}
                      className="flex flex-col gap-2 rounded-md border border-border p-3 sm:flex-row sm:items-start sm:justify-between"
                    >
                      <div>
                        <div className="text-sm font-semibold text-foreground">{action.title}</div>
                        <p className="mt-1 text-xs text-muted-foreground">{action.detail}</p>
                      </div>
                      <Badge variant={variant} className="uppercase">
                        {action.priority}
                      </Badge>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Escalation queue</CardTitle>
              <CardDescription>Click an item to view its reviewer audit timeline.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {escalationQueue.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No open escalations for this document.
                </p>
              ) : (
                escalationQueue.map((item) => (
                  <div
                    key={item.obligation_id}
                    className="flex flex-col gap-3 rounded-md border border-border p-4 lg:flex-row lg:items-start lg:justify-between"
                  >
                    <div className="flex flex-1 flex-col gap-1.5">
                      <div className="text-sm font-semibold text-foreground">{item.title}</div>
                      <p className="text-xs text-muted-foreground">
                        Due: {formatDueDate(item.due_date)} · Review: {item.review_state.replace("_", " ")}
                      </p>
                      {item.reasons.length > 0 ? (
                        <p className="text-xs text-muted-foreground">
                          Reasons:{" "}
                          {item.reasons.map((reason) => formatEscalationReason(reason)).join(", ")}
                        </p>
                      ) : null}
                      <div className="mt-2">
                        <RiskScoreGauge
                          score={item.risk_score}
                          band={item.risk_band}
                          factors={item.risk_factors}
                        />
                      </div>
                    </div>
                    <div className="flex items-center gap-2 lg:flex-col lg:items-end">
                      <StatusPill kind="escalation" value={item.level} />
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void toggleAuditTimeline(item)}
                      >
                        {auditTargetObligationId === item.obligation_id
                          ? "Hide timeline"
                          : "View audit timeline"}
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Reviewer audit timeline</CardTitle>
              <CardDescription>
                {auditTargetObligationId
                  ? `Showing events for ${auditTargetTitle ?? auditTargetObligationId}`
                  : "Select an escalation item to inspect reviewer audit events."}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {auditState === "loading" ? <Skeleton className="h-12 w-full" /> : null}
              {auditState === "error" ? (
                <p className="text-sm text-destructive">{auditError}</p>
              ) : null}
              {auditState === "ready" ? (
                auditItems.length > 0 ? (
                  <ul className="flex flex-col gap-2">
                    {auditItems.map((event) => (
                      <li
                        key={`${event.id}-${event.created_at}`}
                        className="rounded-md border border-border p-3 text-sm"
                      >
                        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          {formatAuditAction(event.action)}
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Actor: {event.actor_type}
                          {event.actor_id ? ` (${event.actor_id})` : ""} ·{" "}
                          {formatDateTime(event.created_at)}
                        </p>
                        {formatAuditPayload(event.payload) ? (
                          <p className="mt-1 text-xs text-foreground/90">
                            {formatAuditPayload(event.payload)}
                          </p>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No audit events recorded for this obligation yet.
                  </p>
                )
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Workflow run</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2 text-sm sm:grid-cols-2">
              {workflowRun ? (
                <>
                  <RunRow label="Status" value={workflowRun.status} />
                  <RunRow label="Run id" value={<span className="font-mono">{workflowRun.run_id}</span>} />
                  <RunRow label="Task queue" value={workflowRun.task_queue} />
                  <RunRow label="Started" value={formatDateTime(workflowRun.started_at)} />
                  <RunRow label="Completed" value={formatDateTime(workflowRun.completed_at)} />
                </>
              ) : (
                <p className="text-sm text-muted-foreground sm:col-span-2">
                  Workflow status is not available for current query context.
                </p>
              )}
              <RunRow label="Obligations in scope" value={metrics.totalObligations} />
              <RunRow label="Critical priority" value={metrics.criticalPaths} />
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}

function RunRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span className="text-sm text-foreground">{value}</span>
    </div>
  );
}
