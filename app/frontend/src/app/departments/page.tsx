"use client";

import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";

import { PageHeader } from "@/components/app/page-header";
import { InfoHint } from "@/components/info-hint";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  listDepartmentHealth,
  type DepartmentHealthBand,
  type DepartmentHealthData,
  type DepartmentHealthItem,
} from "@/lib/api/client";
import { cn } from "@/lib/utils";

type LoadState = "idle" | "loading" | "ready" | "error";

const BAND_VARIANT: Record<DepartmentHealthBand, "good" | "accent" | "warn" | "destructive"> = {
  excellent: "good",
  healthy: "accent",
  watch: "warn",
  at_risk: "destructive",
};

const BAND_INDICATOR: Record<DepartmentHealthBand, string> = {
  excellent: "bg-good",
  healthy: "bg-accent",
  watch: "bg-warn",
  at_risk: "bg-destructive",
};

const BAND_TEXT: Record<DepartmentHealthBand, string> = {
  excellent: "text-good",
  healthy: "text-accent",
  watch: "text-warn",
  at_risk: "text-destructive",
};

const BAND_LABEL: Record<DepartmentHealthBand, string> = {
  excellent: "Excellent",
  healthy: "Healthy",
  watch: "Watch",
  at_risk: "At risk",
};

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

export default function DepartmentsPage() {
  const [state, setState] = useState<LoadState>("idle");
  const [data, setData] = useState<DepartmentHealthData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setState("loading");
      setError(null);
      const result = await listDepartmentHealth();
      if (cancelled) return;
      if (!result.ok) {
        setError(result.error.message);
        setState("error");
        return;
      }
      setData(result.data);
      setState("ready");
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={
          <span className="flex items-center gap-1.5">
            Department health <InfoHint glossaryKey="departments" />
          </span>
        }
        title="Department performance"
        subtitle={
          data
            ? `Tracking ${data.total_departments} departments · average health ${data.avg_health_score.toFixed(1)}/100`
            : "Compliance, breach rate, escalations, and average contempt-risk rolled up by department."
        }
      />

      {state === "loading" ? <Skeleton className="h-64 w-full" /> : null}

      {state === "error" ? (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>Could not load departments</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {state === "ready" && data ? (
        data.items.length === 0 ? (
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">
              No departments have obligations yet. Upload a judgment and run extraction to populate
              the leaderboard.
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Department</TableHead>
                    <TableHead>Health</TableHead>
                    <TableHead>Compliance</TableHead>
                    <TableHead>Breach</TableHead>
                    <TableHead>Avg risk</TableHead>
                    <TableHead>Pending</TableHead>
                    <TableHead>Critical</TableHead>
                    <TableHead>Total</TableHead>
                    <TableHead>Why</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((item) => (
                    <DepartmentRow key={item.code} item={item} />
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )
      ) : null}
    </div>
  );
}

function DepartmentRow({ item }: { item: DepartmentHealthItem }) {
  const bandText = BAND_TEXT[item.band];
  return (
    <TableRow>
      <TableCell>
        <div className="font-semibold text-foreground">{item.name}</div>
        <div className="text-xs text-muted-foreground">{item.code}</div>
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <span className={cn("text-base font-semibold tabular-nums", bandText)}>
            {item.health_score}
          </span>
          <Badge variant={BAND_VARIANT[item.band]}>{BAND_LABEL[item.band]}</Badge>
        </div>
        <Progress
          value={item.health_score}
          indicatorClassName={BAND_INDICATOR[item.band]}
          className="mt-1.5 h-1 w-32"
        />
      </TableCell>
      <TableCell className="tabular-nums">{formatPercent(item.compliance_rate)}</TableCell>
      <TableCell className="tabular-nums">{formatPercent(item.breach_rate)}</TableCell>
      <TableCell className="tabular-nums">{item.avg_risk_score.toFixed(0)}</TableCell>
      <TableCell className="tabular-nums">{item.pending_review}</TableCell>
      <TableCell className="tabular-nums">{item.critical_escalations}</TableCell>
      <TableCell className="tabular-nums">{item.total_obligations}</TableCell>
      <TableCell>
        <ul className="ml-4 list-disc text-xs text-muted-foreground">
          {item.rationale.slice(0, 2).map((line, idx) => (
            <li key={idx}>{line}</li>
          ))}
        </ul>
      </TableCell>
    </TableRow>
  );
}


