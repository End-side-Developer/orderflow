"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import type { WorkbenchOverviewData } from "@/lib/api/client";
import { getWorkbenchOverview } from "@/lib/api/client";
import { useAuthStore } from "@/lib/auth/store";
import { ROLE_LABELS } from "@/lib/auth/permissions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function DashboardPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const status = useAuthStore((s) => s.status);

  const [overview, setOverview] = useState<WorkbenchOverviewData | null>(null);
  const [loadingOverview, setLoadingOverview] = useState(false);

  useEffect(() => {
    if (status === "anon") {
      router.push("/login?redirect=/dashboard");
    }
  }, [status, router]);

  useEffect(() => {
    if (!user) return;
    if (user.role === "judge" || user.role === "government" || user.role === "advocate") {
      setLoadingOverview(true);
      getWorkbenchOverview()
        .then((r) => {
          if (r.ok) setOverview(r.data);
        })
        .finally(() => setLoadingOverview(false));
    }
  }, [user]);

  if (status === "loading" || !user) {
    return (
      <div className="space-y-4 py-8">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 py-8">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold">
          Welcome, {user.full_name ?? user.email.split("@")[0]}
        </h1>
        <Badge variant="outline">{ROLE_LABELS[user.role]}</Badge>
      </div>

      {/* Citizen dashboard */}
      {user.role === "citizen" && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Your cases</CardTitle>
              <CardDescription>
                View public obligations and case status linked to your matters.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link href="/public">View public obligations</Link>
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Advocate directory</CardTitle>
              <CardDescription>Find and connect with verified advocates.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link href="/advocates">Browse advocates</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Advocate dashboard */}
      {user.role === "advocate" && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle>My profile</CardTitle>
              <CardDescription>View and edit your public advocate profile.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link href="/profile">Edit profile</Link>
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Case analysis</CardTitle>
              <CardDescription>Access document summaries and obligations.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link href="/document-summary">Analyze documents</Link>
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Directory listing</CardTitle>
              <CardDescription>See how your profile appears publicly.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link href="/advocates">View directory</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Judge / Government dashboard */}
      {(user.role === "judge" || user.role === "government") && (
        <>
          {loadingOverview ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[...Array(4)].map((_, i) => (
                <Skeleton key={i} className="h-28 w-full" />
              ))}
            </div>
          ) : overview ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { label: "Total documents", value: overview.summary.total_documents },
                { label: "Pending review", value: overview.summary.pending_review },
                { label: "Open escalations", value: overview.summary.open_escalations },
                { label: "Critical", value: overview.summary.critical_escalations },
              ].map((kpi) => (
                <Card key={kpi.label}>
                  <CardContent className="pt-6">
                    <p className="text-3xl font-bold">{kpi.value}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{kpi.label}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle>Workbench</CardTitle>
                <CardDescription>Full case overview and workflow management.</CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild>
                  <Link href="/">Open workbench</Link>
                </Button>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Intake</CardTitle>
                <CardDescription>Upload new judgments for processing.</CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild variant="outline">
                  <Link href="/upload">Upload document</Link>
                </Button>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Verifications</CardTitle>
                <CardDescription>Review pending advocate registrations.</CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild variant="outline">
                  <Link href="/admin/verifications">Review queue</Link>
                </Button>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
