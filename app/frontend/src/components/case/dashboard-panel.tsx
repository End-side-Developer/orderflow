"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Building2,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  FileText,
  Loader2,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
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
      <div className="flex min-h-[200px] items-center justify-center p-6">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading trusted dashboard
        </div>
      </div>
    );
  }

  if (!dashboard) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Dashboard unavailable</AlertTitle>
          <AlertDescription>
            {error ?? "Finalize the reviewed case before opening the trusted dashboard."}
          </AlertDescription>
        </Alert>
        <div>
          <Button size="sm" type="button" variant="outline" onClick={() => void loadDashboard()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh dashboard
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
          <h2 className="text-lg font-semibold text-foreground">Trusted dashboard</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Only verified and approved records are shown.
          </p>
        </div>
        <Badge variant="good">
          <ShieldCheck className="mr-1.5 h-3.5 w-3.5" />
          Approved-only view
        </Badge>
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
        <div className="grid gap-3 sm:grid-cols-3">
          <KpiCard label="Verified actions" value={String(dashboard.total)} />
          <KpiCard label="Approved" value={String(dashboard.approved_total)} />
          <KpiCard label="Human edited" value={String(dashboard.edited_total)} />
        </div>

        {/* Department summary */}
        {stats.departmentTotals.length > 0 ? (
          <CollapsibleSection
            icon={<Building2 className="h-4 w-4 text-muted-foreground" />}
            title="Department groups"
            badge={
              <Badge variant="secondary" className="ml-1">
                {stats.departmentTotals.length}
              </Badge>
            }
            defaultOpen
          >
            <div className="grid gap-2 sm:grid-cols-2">
              {stats.departmentTotals.map((group) => (
                <div key={group.name} className="rounded-md bg-muted px-3 py-2.5">
                  <div className="break-words text-sm font-semibold text-foreground">
                    {group.name}
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    {group.total} verified action{group.total === 1 ? "" : "s"}
                  </div>
                </div>
              ))}
            </div>
          </CollapsibleSection>
        ) : null}

        {/* Groups */}
        {dashboard.groups.length === 0 ? (
          <Alert>
            <CheckCircle2 className="h-4 w-4" />
            <AlertTitle>No verified records</AlertTitle>
            <AlertDescription>
              Approved or human-edited records will appear here after finalization.
            </AlertDescription>
          </Alert>
        ) : (
          <div className="flex flex-col gap-3">
            {dashboard.groups.map((group) => (
              <DashboardGroupSection key={group.responsible_department} group={group} />
            ))}
          </div>
        )}

        {/* Footer */}
        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-5">
          <Button size="sm" type="button" variant="outline" onClick={() => void loadDashboard()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh dashboard
          </Button>
        </div>
      </div>
    </div>
  );
}

function CollapsibleSection({
  icon,
  title,
  badge,
  defaultOpen = true,
  children,
}: {
  icon: ReactNode;
  title: string;
  badge?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="rounded-md border border-border overflow-hidden"
    >
      <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-muted/50">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-sm font-semibold text-foreground">{title}</span>
          {badge}
        </div>
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="border-t border-border p-4">{children}</div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function DashboardGroupSection({ group }: { group: CaseDashboardGroup }) {
  const [open, setOpen] = useState(true);
  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="rounded-md border border-border overflow-hidden"
    >
      <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-muted/50">
        <div className="flex items-center gap-3">
          <Building2 className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-semibold text-foreground">
            {group.responsible_department}
          </span>
          <Badge variant="secondary">{group.total}</Badge>
        </div>
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="border-t border-border flex flex-col gap-3 p-4">
          {group.items.map((item) => (
            <VerifiedActionCard key={item.id} item={item} />
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function VerifiedActionCard({ item }: { item: ObligationRecord }) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="rounded-md border border-border overflow-hidden"
    >
      <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-muted/50">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2 pr-3">
          <Badge variant={item.action_plan_stage === "edited" ? "accent" : "good"}>
            {formatMachineLabel(item.action_plan_stage)}
          </Badge>
          <Badge variant={priorityVariant(item.priority)}>
            {formatMachineLabel(item.priority)}
          </Badge>
          <span className="min-w-0 text-sm font-semibold text-foreground line-clamp-1">
            {item.title}
          </span>
        </div>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="border-t border-border p-4 flex flex-col gap-4">
          {item.description ? (
            <p className="whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">
              {item.description}
            </p>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2">
            <SmallFact label="Owner" value={item.owner_hint || "Unassigned"} />
            <SmallFact label="Status" value={formatMachineLabel(item.status)} />
            <SmallFact label="Nature" value={formatMachineLabel(item.nature_of_action ?? "other")} />
            <SmallFact label="Due date" value={item.due_date || "Not dated"} icon="date" />
          </div>

          <div className="flex flex-wrap gap-2">
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

          {item.citation ? (
            <div className="rounded-md bg-muted p-3">
              <div className="mb-1.5 flex items-center gap-2">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Verified source
                </p>
              </div>
              {item.citation.clause_span ? (
                <p className="line-clamp-3 break-words text-xs leading-5 text-muted-foreground">
                  {item.citation.clause_span}
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Source page captured without excerpt text.
                </p>
              )}
            </div>
          ) : null}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border p-4">
      <div className="text-2xl font-semibold text-foreground">{value}</div>
      <div className="mt-1 text-sm text-muted-foreground">{label}</div>
    </div>
  );
}

function SmallFact({ label, value, icon }: { label: string; value: string; icon?: "date" }) {
  return (
    <div className="rounded-md bg-muted px-3 py-2.5">
      <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        {icon === "date" ? <CalendarDays className="h-3.5 w-3.5" /> : null}
        {label}
      </div>
      <div className="break-words text-sm font-semibold text-foreground">{value}</div>
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
