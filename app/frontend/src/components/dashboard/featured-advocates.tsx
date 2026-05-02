"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { listAdvocatesDirectory, type AdvocateDirectoryItem } from "@/lib/api/client";

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
      <div className="grid gap-4 sm:grid-cols-3">
        {[...Array(3)].map((_, i) => (
          <Skeleton key={i} className="h-32 w-full" />
        ))}
      </div>
    );
  }

  if (advocates.length === 0) return null;

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">Featured advocates</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {advocates.map((advocate) => (
          <Card key={advocate.id}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base truncate">
                {advocate.full_name || advocate.email}
              </CardTitle>
              {advocate.profile?.specializations && advocate.profile.specializations.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  <Badge variant="secondary" className="text-xs font-normal">
                    {advocate.profile.specializations[0]}
                  </Badge>
                  {advocate.profile.specializations.length > 1 && (
                    <Badge variant="outline" className="text-xs font-normal">
                      +{advocate.profile.specializations.length - 1}
                    </Badge>
                  )}
                </div>
              )}
            </CardHeader>
            <CardContent>
              <div className="text-xs text-muted-foreground mb-4">
                {advocate.profile?.years_of_experience 
                  ? `${advocate.profile.years_of_experience} years experience`
                  : "Verified Advocate"}
              </div>
              <Button asChild variant="outline" size="sm" className="w-full">
                <Link href={`/advocates`}>View directory</Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
