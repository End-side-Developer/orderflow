"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { use } from "react";

import type { AdvocateCaseLink, AdvocateDirectoryItem } from "@/lib/api/client";
import { getAdvocate, listAdvocateCases } from "@/lib/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

export default function AdvocateDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [advocate, setAdvocate] = useState<AdvocateDirectoryItem | null>(null);
  const [cases, setCases] = useState<AdvocateCaseLink[]>([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([getAdvocate(id), listAdvocateCases(id)])
      .then(([advocateResult, casesResult]) => {
        if (advocateResult.ok) setAdvocate(advocateResult.data);
        else setNotFound(true);
        if (casesResult.ok) setCases(casesResult.data.items);
      })
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 py-8">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (notFound || !advocate) {
    return (
      <div className="mx-auto max-w-2xl py-16 text-center">
        <p className="text-lg font-medium">Advocate not found</p>
        <p className="mt-2 text-sm text-muted-foreground">
          This profile may not exist or is not yet verified.
        </p>
        <Button asChild variant="outline" className="mt-4">
          <Link href="/advocates">Back to directory</Link>
        </Button>
      </div>
    );
  }

  const p = advocate.profile;

  return (
    <div className="mx-auto max-w-2xl space-y-6 py-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{advocate.full_name ?? advocate.email}</h1>
          <p className="text-sm text-muted-foreground font-mono mt-0.5">{p.bar_council_id}</p>
        </div>
        {p.ratings_count > 0 && (
          <Badge variant="secondary" className="text-sm">
            â˜… {p.ratings_avg?.toFixed(1)} ({p.ratings_count})
          </Badge>
        )}
      </div>

      {p.bio && (
        <Card>
          <CardContent className="pt-6 text-sm leading-relaxed text-muted-foreground">
            {p.bio}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4 text-sm">
          {p.years_of_experience !== null && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">Experience</span>
              <span>{p.years_of_experience} years</span>
            </div>
          )}

          {p.specializations.length > 0 && (
            <>
              <Separator />
              <div>
                <p className="text-muted-foreground mb-2">Specializations</p>
                <div className="flex flex-wrap gap-1.5">
                  {p.specializations.map((s) => (
                    <Badge key={s} variant="secondary" className="capitalize">
                      {s}
                    </Badge>
                  ))}
                </div>
              </div>
            </>
          )}

          {p.languages.length > 0 && (
            <>
              <Separator />
              <div className="flex justify-between">
                <span className="text-muted-foreground">Languages</span>
                <span>{p.languages.join(", ").toUpperCase()}</span>
              </div>
            </>
          )}

          {p.jurisdictions.length > 0 && (
            <>
              <Separator />
              <div>
                <p className="text-muted-foreground mb-2">Jurisdictions</p>
                <div className="flex flex-col gap-1">
                  {p.jurisdictions.map((j, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <Badge variant="outline" className="capitalize text-xs">
                        {j.level}
                      </Badge>
                      <span>
                        {j.name}
                        {j.state ? `, ${j.state}` : ""}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {(p.consultation_fee_min_inr !== null || p.consultation_fee_max_inr !== null) && (
            <>
              <Separator />
              <div className="flex justify-between">
                <span className="text-muted-foreground">Consultation fee</span>
                <span>
                  {p.consultation_fee_min_inr !== null
                    ? `â‚¹${p.consultation_fee_min_inr.toLocaleString()}`
                    : "â€”"}
                  {p.consultation_fee_max_inr !== null
                    ? ` â€“ â‚¹${p.consultation_fee_max_inr.toLocaleString()}`
                    : ""}
                </span>
              </div>
            </>
          )}

          {advocate.phone && (
            <>
              <Separator />
              <div className="flex justify-between">
                <span className="text-muted-foreground">Contact</span>
                <span>{advocate.phone}</span>
              </div>
            </>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Cases</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          {cases.length === 0 ? (
            <p className="text-muted-foreground">No linked cases yet.</p>
          ) : (
            cases.map((item) => (
              <Link
                key={item.id}
                href={`/document-summary?document_id=${encodeURIComponent(item.document_id)}`}
                className="rounded-md border border-border bg-muted/30 px-3 py-2 transition-colors hover:bg-muted/50"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-foreground">
                    {item.document_title ?? "Untitled case document"}
                  </span>
                  <Badge variant={item.status === "verified" ? "good" : "warn"}>
                    {item.status}
                  </Badge>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {item.court_name ?? "Court unknown"}
                  {item.order_date ? ` · ${item.order_date}` : ""}
                </div>
              </Link>
            ))
          )}
        </CardContent>
      </Card>

      <Button asChild variant="outline">
        <Link href="/advocates">Back to directory</Link>
      </Button>
    </div>
  );
}
