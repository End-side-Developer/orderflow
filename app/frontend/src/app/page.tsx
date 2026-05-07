"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Plus } from "lucide-react";

import { PageHeader } from "@/components/app/page-header";
import { KpiTile } from "@/components/app/kpi-tile";
import { StatusPill } from "@/components/app/status-pill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  getApiHealth,
  getWorkbenchOverview,
  type HealthPayload,
  type WorkbenchActivityItem,
  type WorkbenchDocumentCard,
  type WorkbenchOverviewData,
} from "@/lib/api/client";

type LoadState = "idle" | "loading" | "ready" | "error";

function formatDateTime(value: string | null): string {
  if (!value) return "n/a";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function formatStage(stage: WorkbenchDocumentCard["stage"]): string {
  return stage.replaceAll("_", " ");
}

function formatDocumentStatus(document: WorkbenchDocumentCard): string {
  if (document.workflow_status === "completed" && document.stage === "intake_running") {
    return "ready for extraction";
  }

  if (document.workflow_status === "failed" && document.stage === "intake_running") {
    return "intake failed";
  }

  return formatStage(document.stage);
}

function formatAction(action: string): string {
  return action.replaceAll(".", " ");
}

export default function OverviewPage() {
  const [state, setState] = useState<LoadState>("idle");
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [overview, setOverview] = useState<WorkbenchOverviewData | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load(): Promise<void> {
      setState("loading");
      setErrorText(null);
      const [healthResult, overviewResult] = await Promise.all([
        getApiHealth(),
        getWorkbenchOverview(),
      ]);
      if (cancelled) return;
      if (healthResult.ok) setHealth(healthResult.data);
      if (!overviewResult.ok) {
        setState("error");
        setErrorText(overviewResult.error.message);
        setOverview(null);
        return;
      }
      setOverview(overviewResult.data);
      setState("ready");
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const priorityDocuments = useMemo(() => overview?.documents.slice(0, 5) ?? [], [overview]);
  const recentActivity = useMemo(() => overview?.recent_activity.slice(0, 8) ?? [], [overview]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Overview"
        title="Judgment-to-action workflow at a glance"
        subtitle="OrderFlow turns court judgments into a verifiable execution queue. Intake, analyze, verify, escalate."
        actions={
          <>
            <Button asChild>
              <Link href="/upload">
                <Plus />
                Start intake
              </Link>
            </Button>
          </>
        }
      />

      <section className="grid gap-3 sm:grid-cols-2">
        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              API status
            </span>
            <div className="flex items-baseline gap-2">
              <span className="text-base font-semibold text-foreground">
                {health?.status ?? "loading"}
              </span>
              <span className="text-xs text-muted-foreground">
                {health ? `${health.service} ${health.version}` : "Connecting"}
              </span>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Environment
            </span>
            <div className="flex items-baseline gap-2">
              <span className="text-base font-semibold text-foreground">
                {health?.environment ?? "n/a"}
              </span>
              <span className="text-xs text-muted-foreground">
                {health ? `Uptime ${health.uptime_seconds}s` : "Waiting for health check"}
              </span>
            </div>
          </CardContent>
        </Card>
      </section>

      {state === "loading" ? (
        <section className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </section>
      ) : null}

      {state === "error" ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load workbench</AlertTitle>
          <AlertDescription>{errorText}</AlertDescription>
        </Alert>
      ) : null}

      {state === "ready" && overview ? (
        <>
          <section className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
            <KpiTile
              label="Documents in system"
              value={overview.summary.total_documents}
              hint={`Ready: ${overview.summary.ready_documents}`}
            />
            <KpiTile
              label="Pending review"
              value={overview.summary.pending_review}
              hint="Reviewer gate across all live cases"
              tone="warn"
            />
            <KpiTile
              label="Workflow in flight"
              value={overview.summary.in_flight_documents}
              hint={`Obligation ledger items: ${overview.summary.total_obligations}`}
              tone="accent"
            />
            <KpiTile
              label="Active escalations"
              value={overview.summary.open_escalations}
              hint={`Critical: ${overview.summary.critical_escalations}`}
              tone="destructive"
            />
          </section>

          <Card>
            <CardHeader className="flex-row items-start justify-between gap-3">
              <div>
                <CardTitle className="text-lg">Cases that need attention next</CardTitle>
                <CardDescription>Highest-pressure documents in the priority queue.</CardDescription>
              </div>
              <Button asChild variant="outline" size="sm">
                <Link href="/upload">
                  <Plus />
                  Add another judgment
                </Link>
              </Button>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {priorityDocuments.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No persisted cases yet. Upload a judgment to start the workbench.
                </p>
              ) : (
                priorityDocuments.map((document) => (
                  <DocumentRow key={document.document_id} document={document} />
                ))
              )}
            </CardContent>
          </Card>

          <section className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Recent reviewer activity</CardTitle>
                <CardDescription>Audit trail without opening each case.</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                {recentActivity.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Reviewer actions will appear here as the board is used.
                  </p>
                ) : (
                  recentActivity.map((item, index) => (
                    <ActivityRow
                      key={`${item.document_id}-${item.obligation_id ?? index}-${item.created_at}`}
                      item={item}
                    />
                  ))
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Workflow intelligence</CardTitle>
                <CardDescription>
                  How OrderFlow keeps every screen looking at the same truth.
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3 text-sm">
                <Feature
                  title="Server-side workbench scoring"
                  body="Pressure, review backlog, and escalation signals are computed in the API, so every screen sees the same truth."
                />
                <Feature
                  title="Prior-case recommendations"
                  body="Similar cases are ranked using obligation language, owner overlap, and priority patterns to speed up reviewer judgment."
                />
                <Feature
                  title="Operational UI, not demos"
                  body="The shell is tuned for scanning, triage, and moving into action quickly."
                />
              </CardContent>
            </Card>
          </section>
        </>
      ) : null}
    </div>
  );
}

function DocumentRow({ document }: { document: WorkbenchDocumentCard }) {
  return (
    <div className="grid gap-3 rounded-md border border-border bg-muted/20 p-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(220px,0.9fr)_auto] lg:items-center">
      <div className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-foreground">{document.source_file_name}</span>
          <StatusPill kind="pressure" value={document.pressure_level} />
          <Badge
            variant={
              document.workflow_status === "completed"
                ? "good"
                : document.workflow_status === "failed"
                  ? "destructive"
                  : document.workflow_status === "started"
                    ? "warn"
                    : "muted"
            }
          >
            {formatDocumentStatus(document)}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          {document.court_name ?? "Court metadata pending"} ·{" "}
          {document.department ?? "Department pending"} · Last activity{" "}
          {formatDateTime(document.last_activity_at)}
        </p>
        <p className="text-sm text-foreground/90">{document.next_action}</p>
      </div>
      <div className="grid grid-cols-3 gap-3 text-sm">
        <Metric label="Pending review" value={document.metrics.pending_review} />
        <Metric label="Completed" value={document.metrics.completed} />
      </div>
      <div className="flex flex-col gap-2 lg:flex-row">
        <Button asChild variant="outline" size="sm">
          <Link href={`/case/${encodeURIComponent(document.document_id)}`}>
            View the case
            <ArrowRight />
          </Link>
        </Button>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <strong className="text-base text-foreground">{value}</strong>
    </div>
  );
}

function ActivityRow({ item }: { item: WorkbenchActivityItem }) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-md border border-border bg-muted/20 p-3">
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-foreground">{item.title}</span>
          <StatusPill kind="pressure" value={item.level} />
        </div>
        <p className="text-xs text-muted-foreground">
          {formatAction(item.action)} · {item.actor_type} · {formatDateTime(item.created_at)}
        </p>
        {item.detail ? <p className="text-sm text-foreground/90">{item.detail}</p> : null}
      </div>
      <Button asChild variant="outline" size="sm">
        <Link href={`/obligations?document_id=${encodeURIComponent(item.document_id)}`}>Open</Link>
      </Button>
    </div>
  );
}

function Feature({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <strong className="text-sm font-semibold text-foreground">{title}</strong>
      <p className="mt-1 text-sm text-muted-foreground">{body}</p>
    </div>
  );
}
