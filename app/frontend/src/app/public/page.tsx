"use client";

import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";

import { PageHeader } from "@/components/app/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  listPublicObligations,
  type PublicObligationItem,
  type PublicObligationsData,
} from "@/lib/api/client";

type LoadState = "idle" | "loading" | "ready" | "error";

function formatDate(value: string | null): string {
  if (!value) return "No deadline";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString();
}

export default function PublicTrustPage() {
  const [state, setState] = useState<LoadState>("idle");
  const [data, setData] = useState<PublicObligationsData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setState("loading");
      setError(null);
      const result = await listPublicObligations(200);
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
        eyebrow="Public"
        title="Public-trust view"
        subtitle={
          data
            ? `${data.total} obligations on display · ${data.redacted_count_summary.total ?? 0} PII elements redacted (${Object.entries(
                data.redacted_count_summary,
              )
                .filter(([key]) => key !== "total")
                .map(([key, count]) => `${count} ${key}`)
                .join(", ")})`
            : "A read-only window into court-ordered obligations and how compliance is tracking. Personal names, contact details, Aadhaar/PAN, and case identifiers are masked. No PII leaves the platform."
        }
      />

      {state === "loading" ? <Skeleton className="h-64 w-full" /> : null}

      {state === "error" ? (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>Could not load public obligations</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {state === "ready" && data ? (
        data.items.length === 0 ? (
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">
              No obligations published yet.
            </CardContent>
          </Card>
        ) : (
          <div className="flex flex-col gap-3">
            {data.items.map((item) => (
              <PublicObligationCard key={item.id} item={item} />
            ))}
          </div>
        )
      ) : null}
    </div>
  );
}

function PublicObligationCard({ item }: { item: PublicObligationItem }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-2 p-4">
        <h3 className="text-base font-semibold text-foreground">{item.title}</h3>
        {item.description ? (
          <p className="text-sm leading-relaxed text-muted-foreground">{item.description}</p>
        ) : null}
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>
            <strong className="text-foreground">Status:</strong> {item.status ?? "n/a"}
          </span>
          <span>
            <strong className="text-foreground">Priority:</strong> {item.priority ?? "n/a"}
          </span>
          <span>
            <strong className="text-foreground">Due:</strong> {formatDate(item.due_date)}
          </span>
          {item.risk_score !== null ? (
            <span>
              <strong className="text-foreground">Risk:</strong> {item.risk_score}/100 (
              {item.risk_band})
            </span>
          ) : null}
        </div>
        {item.redaction.total ? (
          <p className="text-xs italic text-muted-foreground">
            {item.redaction.total} PII element(s) masked in this entry.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
