"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Briefcase, Scale } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { listAdvocatesDirectory, type AdvocateDirectoryItem } from "@/lib/api/client";

function getInitials(name: string | null, email: string): string {
  const text = (name && name.trim()) || email;
  return text
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("")
    .padEnd(1, "?")
    .slice(0, 2);
}

function FeaturedAdvocateSkeleton() {
  return (
    <Card className="overflow-hidden">
      <CardContent className="flex flex-col gap-4 p-5">
        <div className="flex items-center gap-3">
          <Skeleton className="h-11 w-11 rounded-full" />
          <div className="flex flex-1 flex-col gap-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Skeleton className="h-5 w-16 rounded-full" />
          <Skeleton className="h-5 w-12 rounded-full" />
        </div>
        <Skeleton className="h-9 w-full rounded-md" />
      </CardContent>
    </Card>
  );
}

export function FeaturedAdvocates() {
  const [advocates, setAdvocates] = useState<AdvocateDirectoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listAdvocatesDirectory({ sort: "ratings", limit: 3 })
      .then((res) => {
        if (res.ok) {
          setAdvocates(res.data.items);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <Skeleton className="h-6 w-44" />
          <Skeleton className="h-4 w-20" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(3)].map((_, i) => (
            <FeaturedAdvocateSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (advocates.length === 0) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold tracking-tight text-foreground">Featured advocates</h2>
        <Link
          href="/advocates"
          className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
        >
          See all
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {advocates.map((advocate) => {
          const specs = advocate.profile?.specializations ?? [];
          const years = advocate.profile?.years_of_experience;
          return (
            <Card key={advocate.id} className="card-interactive overflow-hidden">
              <CardContent className="flex h-full flex-col gap-4 p-5">
                <div className="flex items-center gap-3">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-primary/30 bg-primary/15 text-sm font-semibold text-primary">
                    {getInitials(advocate.full_name, advocate.email)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-foreground">
                      {advocate.full_name || advocate.email}
                    </p>
                    <p className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Scale className="h-3 w-3" aria-hidden="true" />
                      Verified advocate
                    </p>
                  </div>
                </div>

                {specs.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    <Badge variant="secondary" className="text-[11px] font-medium">
                      {specs[0]}
                    </Badge>
                    {specs.length > 1 ? (
                      <Badge variant="outline" className="text-[11px] font-medium">
                        +{specs.length - 1} more
                      </Badge>
                    ) : null}
                  </div>
                ) : null}

                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Briefcase className="h-3.5 w-3.5" aria-hidden="true" />
                  {years ? `${years} years experience` : "Experience on profile"}
                </div>

                <Button asChild variant="outline" size="sm" className="mt-auto w-full">
                  <Link href="/advocates">View directory</Link>
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
