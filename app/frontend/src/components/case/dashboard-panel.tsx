"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Building2,
  CalendarDays,
  CheckCircle2,
  FileText,
  Loader2,
  RefreshCw,
  ShieldCheck,
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
import {
  CaseDashboardData,
  CaseDashboardGroup,
  ObligationRecord,
  getCaseDashboard,
} from "@/lib/api/client";

type DashboardPanelProps = {
  documentId: string;
};

export function DashboardPanel({ documentId }: DashboardPanelProps) {
  const [dashboard, setDashboard] = useState<CaseDashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await getCaseDashboard(documentId);
      if (response.ok) {
        setDashboard(response.data);
      } else {
        setDashboard(null);
        setError(response.error.message);
      }
    } catch (requestError) {
      setDashboard(null);
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not load the trusted dashboard.",
      );
    } finally {
      setIsLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    let cancelled = false;

    setIsLoading(true);
    setError(null);

    void getCaseDashboard(documentId)
      .then((response) => {
        if (cancelled) return;
        if (response.ok) {
          setDashboard(response.data);
        } else {
          setDashboard(null);
          setError(response.error.message);
        }
      })
      .catch((requestError) => {
        if (cancelled) return;
        setDashboard(null);
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Could not load the trusted dashboard.",
        );
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [documentId]);

  const stats = useMemo(() => buildDashboardStats(dashboard), [dashboard]);

  if (isLoading) {
    return (
      <div className="flex min-h-full items-center justify-center p-6">
        <div className="flex items-center gap-2 text-sm text-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading trusted dashboard
        </div>
      </div>
    );
  }

  if (!dashboard) {
    return (
      <div className="flex min-h-full flex-col gap-4 p-6">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Dashboard unavailable</AlertTitle>
          <AlertDescription>
            {error ?? "Finalize the reviewed case before opening the trusted dashboard."}
          </AlertDescription>
        </Alert>
        <div>
          <Button type="button" variant="outline" onClick={() => void loadDashboard()}>
            <RefreshCw data-icon="inline-start" />
            Refresh dashboard
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-full flex-col gap-5 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground">
            Trusted dashboard
          </h2>
          <p className="mt-1 text-sm text-foreground">
            Only verified records are shown in the dashboard.
          </p>
        </div>
        <Badge variant="good">
          <ShieldCheck data-icon="inline-start" />
          Approved-only view
        </Badge>
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Refresh failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-3">
        <Metric label="Verified actions" value={String(dashboard.total)} />
        <Metric label="Approved" value={String(dashboard.approved_total)} />
        <Metric label="Human edited" value={String(dashboard.edited_total)} />
      </section>

      <section className="rounded-md border border-slate-200 p-4">
        <div className="mb-3 flex items-center gap-2">
          <Building2 className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">
            Department groups
          </h3>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {stats.departmentTotals.map((group) => (
            <div key={group.name} className="rounded-md bg-muted px-3 py-2">
              <div className="break-words text-sm font-semibold text-foreground">
                {group.name}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                {group.total} verified action{group.total === 1 ? "" : "s"}
              </div>
            </div>
          ))}
        </div>
      </section>

      {dashboard.groups.length === 0 ? (
        <Alert>
          <CheckCircle2 className="h-4 w-4" />
          <AlertTitle>No verified records</AlertTitle>
          <AlertDescription>
            Approved or human-edited records will appear here after finalization.
          </AlertDescription>
        </Alert>
      ) : (
        <div className="flex flex-col gap-4">
          {dashboard.groups.map((group) => (
            <DashboardGroupCard key={group.responsible_department} group={group} />
          ))}
        </div>
      )}

      <div className="mt-auto flex flex-wrap gap-3 border-t border-slate-200 pt-5">
        <Button type="button" variant="outline" onClick={() => void loadDashboard()}>
          <RefreshCw data-icon="inline-start" />
          Refresh dashboard
        </Button>
      </div>
    </div>
  );
}

function DashboardGroupCard({ group }: { group: CaseDashboardGroup }) {
  return (
    <Card className="shadow-none">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <CardTitle className="break-words text-base">
              {group.responsible_department}
            </CardTitle>
            <CardDescription>
              {group.total} verified action{group.total === 1 ? "" : "s"}
            </CardDescription>
          </div>
          <Badge variant="secondary">{group.total}</Badge>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {group.items.map((item) => (
          <VerifiedActionCard key={item.id} item={item} />
        ))}
      </CardContent>
    </Card>
  );
}

function VerifiedActionCard({ item }: { item: ObligationRecord }) {
  return (
    <div className="rounded-md border border-slate-200 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="break-words text-sm font-semibold text-foreground">
            {item.title}
          </p>
          {item.description ? (
            <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-foreground">
              {item.description}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <Badge variant={item.action_plan_stage === "edited" ? "accent" : "good"}>
            {formatMachineLabel(item.action_plan_stage)}
          </Badge>
          <Badge variant={priorityVariant(item.priority)}>
            {formatMachineLabel(item.priority)}
          </Badge>
        </div>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <SmallFact label="Owner" value={item.owner_hint || "Unassigned"} />
        <SmallFact label="Status" value={formatMachineLabel(item.status)} />
        <SmallFact label="Nature" value={formatMachineLabel(item.nature_of_action ?? "other")} />
        <SmallFact label="Due date" value={item.due_date || "Not dated"} icon="date" />
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {item.risk_band ? (
          <Badge variant={riskVariant(item.risk_band)}>
            Risk {formatMachineLabel(item.risk_band)}
          </Badge>
        ) : null}
        {item.risk_score != null ? (
          <Badge variant="outline">{Math.round(item.risk_score)} risk score</Badge>
        ) : null}
        {item.citation?.page_number ? (
          <Badge variant="outline">Page {item.citation.page_number}</Badge>
        ) : null}
      </div>

      <SourceEvidence item={item} />
    </div>
  );
}

function SourceEvidence({ item }: { item: ObligationRecord }) {
  if (!item.citation) {
    return null;
  }

  return (
    <div className="mt-3 rounded-md bg-slate-800 p-3">
      <div className="mb-1 flex items-center gap-2">
        <FileText className="h-4 w-4 text-muted-foreground" />
        <p className="text-xs font-semibold uppercase text-muted-foreground">
          Verified source
        </p>
      </div>
      {item.citation.clause_span ? (
        <p className="line-clamp-3 break-words text-xs leading-5 text-foreground">
          {item.citation.clause_span}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">
          Source page captured without excerpt text.
        </p>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 p-4">
      <div className="text-2xl font-semibold text-foreground">{value}</div>
      <div className="mt-1 text-sm text-foreground">{label}</div>
    </div>
  );
}

function SmallFact({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon?: "date";
}) {
  return (
    <div className="rounded-md bg-muted px-3 py-2">
      <div className="mb-1 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        {icon === "date" ? <CalendarDays className="h-4 w-4" /> : null}
        {label}
      </div>
      <div className="break-words text-sm font-semibold text-foreground">
        {value}
      </div>
    </div>
  );
}

function buildDashboardStats(dashboard: CaseDashboardData | null) {
  return {
    departmentTotals:
      dashboard?.groups.map((group) => ({
        name: group.responsible_department,
        total: group.total,
      })) ?? [],
  };
}

function priorityVariant(priority: ObligationRecord["priority"]) {
  if (priority === "critical") return "destructive" as const;
  if (priority === "high") return "warn" as const;
  if (priority === "medium") return "secondary" as const;
  return "good" as const;
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


