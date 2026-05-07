"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  getDocumentAdvocateRecommendations,
  type AdvocateRecommendationsData,
} from "@/lib/api/client";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface RecommendedAdvocatesPanelProps {
  documentId: string;
}

function describeFilters(filters: AdvocateRecommendationsData["filters"]): string {
  const bits = [
    filters.specialization ? `specialization: ${filters.specialization}` : null,
    filters.jurisdiction_state ? `state: ${filters.jurisdiction_state}` : null,
    filters.jurisdiction_level ? `court level: ${filters.jurisdiction_level}` : null,
    filters.language ? `language: ${filters.language}` : null,
  ].filter((bit): bit is string => Boolean(bit));
  return bits.length > 0 ? bits.join(" · ") : "No strong case metadata signals were available.";
}

export function RecommendedAdvocatesPanel({ documentId }: RecommendedAdvocatesPanelProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<AdvocateRecommendationsData | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    (async () => {
      const result = await getDocumentAdvocateRecommendations(documentId);
      if (cancelled) return;
      if (result.ok) {
        setData(result.data);
      } else {
        setError(result.error.message);
      }
      setLoading(false);
    })();

    return () => {
      cancelled = true;
    };
  }, [documentId]);

  const filterSummary = useMemo(() => (data ? describeFilters(data.filters) : null), [data]);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">Advocates who can help</CardTitle>
        <CardDescription>Ranked from verified profiles using case-level signals.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 pt-0">
        {loading ? (
          <>
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </>
        ) : null}

        {!loading && error ? (
          <p className="text-sm text-muted-foreground">Could not load recommendations: {error}</p>
        ) : null}

        {!loading && !error && data ? (
          <>
            <p className="text-xs text-muted-foreground">{filterSummary}</p>
            {data.items.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No advocate matched this case profile yet.
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {data.items.map((advocate) => (
                  <Link
                    key={advocate.id}
                    href={`/advocates/${advocate.id}`}
                    className="rounded-md border border-border bg-muted/20 p-3 transition-colors hover:bg-muted/40"
                  >
                    <div className="text-sm font-semibold text-foreground">
                      {advocate.full_name ?? advocate.email}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      {advocate.profile.specializations.slice(0, 2).map((specialization) => (
                        <Badge
                          key={specialization}
                          variant="secondary"
                          className="text-[10px] capitalize"
                        >
                          {specialization}
                        </Badge>
                      ))}
                      {advocate.profile.ratings_count > 0 ? (
                        <span className="text-[11px] text-muted-foreground">
                          ★ {advocate.profile.ratings_avg?.toFixed(1) ?? "—"} (
                          {advocate.profile.ratings_count})
                        </span>
                      ) : null}
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
