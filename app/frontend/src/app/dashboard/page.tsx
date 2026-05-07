"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ClipboardCheck,
  FileText,
  Gavel,
  LayoutDashboard,
  MessageCircle,
  Plus,
  Scale,
  ShieldCheck,
  UserCog,
  Users,
} from "lucide-react";

import type { WorkbenchOverviewData } from "@/lib/api/client";
import { getWorkbenchOverview } from "@/lib/api/client";
import { QuickActionCard } from "@/components/dashboard/quick-action-card";
import { FeaturedAdvocates } from "@/components/dashboard/featured-advocates";
import { useAuthStore } from "@/lib/auth/store";
import { ROLE_LABELS } from "@/lib/auth/permissions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoHint } from "@/components/info-hint";
import { PageHeader } from "@/components/app/page-header";
import { KpiTile, type KpiTone } from "@/components/app/kpi-tile";

type Kpi = {
  label: string;
  value: number;
  tone: KpiTone;
  icon: React.ReactNode;
  hint?: string;
};

function DashboardLoadingSkeleton() {
  return (
    <div className="flex flex-col gap-6 py-6">
      <div className="rounded-xl border border-border bg-surface px-6 py-7">
        <div className="flex flex-col gap-3">
          <Skeleton className="h-5 w-24 rounded-full" />
          <Skeleton className="h-8 w-72" />
          <Skeleton className="h-4 w-96" />
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i}>
            <CardContent className="flex flex-col gap-3 p-5">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-8 w-16" />
              <Skeleton className="h-3 w-32" />
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[...Array(3)].map((_, i) => (
          <Card key={i}>
            <CardContent className="flex items-center gap-4 p-5">
              <Skeleton className="h-9 w-9 rounded-lg" />
              <div className="flex flex-1 flex-col gap-2">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-48" />
              </div>
              <Skeleton className="h-4 w-4" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

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
    if (status === "loading") {
      return <DashboardLoadingSkeleton />;
    }
    return null;
  }

  const displayName = user.full_name?.trim() || user.email.split("@")[0];

  const kpis: Kpi[] | null = overview
    ? [
        {
          label: "Total documents",
          value: overview.summary.total_documents,
          tone: "default",
          icon: <FileText className="h-4 w-4" />,
          hint: "Across every department",
        },
        {
          label: "Pending review",
          value: overview.summary.pending_review,
          tone: "warn",
          icon: <ClipboardCheck className="h-4 w-4" />,
          hint: "Waiting on action",
        },
        {
          label: "Critical",
          value: overview.summary.critical_escalations,
          tone: "destructive",
          icon: <AlertTriangle className="h-4 w-4" />,
          hint: "Escalations to triage",
        },
      ]
    : null;

  return (
    <div className="flex flex-col gap-6 py-6">
      <PageHeader
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <LayoutDashboard className="h-3.5 w-3.5" />
            Dashboard
          </span>
        }
        title={`Welcome back, ${displayName}`}
        subtitle="Pick up where you left off — review documents, manage your workflow, or start a new intake."
        actions={
          <Badge
            variant="outline"
            className="border-primary/30 bg-primary/10 px-3 py-1 text-xs text-primary"
          >
            {ROLE_LABELS[user.role]}
          </Badge>
        }
      />

      {/* Quick actions for all roles */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Quick actions
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <QuickActionCard
            icon={<Scale />}
            title="Find an Advocate"
            description="Find and connect with verified advocates."
            onClick={() => router.push("/advocates")}
          />
          <QuickActionCard
            icon={<MessageCircle />}
            tone="accent"
            title="Ask AI Assistant"
            description="Get answers about terminology and case help."
            onClick={() => window.dispatchEvent(new Event("orderflow:open-ai-chat"))}
          />
        </div>
      </section>

      {/* Citizen dashboard */}
      {user.role === "citizen" && (
        <div className="flex flex-col gap-8">
          <section>
            <Card className="card-interactive overflow-hidden">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <span className="icon-chip">
                    <Users className="h-4 w-4" />
                  </span>
                  Your cases
                </CardTitle>
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
          </section>
          <FeaturedAdvocates />
        </div>
      )}

      {/* Advocate dashboard */}
      {user.role === "advocate" && (
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Card className="card-interactive">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <span className="icon-chip">
                  <UserCog className="h-4 w-4" />
                </span>
                My profile
              </CardTitle>
              <CardDescription>View and edit your public advocate profile.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link href="/profile">Edit profile</Link>
              </Button>
            </CardContent>
          </Card>
          <Card className="card-interactive">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <span className="icon-chip icon-chip-accent">
                  <FileText className="h-4 w-4" />
                </span>
                Read documents <InfoHint glossaryKey="analyze" />
              </CardTitle>
              <CardDescription>Access document summaries and obligations.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link href="/document-summary">Analyze documents</Link>
              </Button>
            </CardContent>
          </Card>
          <Card className="card-interactive">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <span className="icon-chip icon-chip-good">
                  <Users className="h-4 w-4" />
                </span>
                Directory listing
              </CardTitle>
              <CardDescription>See how your profile appears publicly.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link href="/advocates">View directory</Link>
              </Button>
            </CardContent>
          </Card>
        </section>
      )}

      {/* Judge / Government dashboard */}
      {(user.role === "judge" || user.role === "government") && (
        <>
          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              At a glance
            </h2>
            {loadingOverview ? (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {[...Array(4)].map((_, i) => (
                  <Card key={i}>
                    <CardContent className="flex flex-col gap-3 p-5">
                      <Skeleton className="h-4 w-24" />
                      <Skeleton className="h-8 w-16" />
                      <Skeleton className="h-3 w-32" />
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : kpis ? (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {kpis.map((kpi) => (
                  <KpiTile
                    key={kpi.label}
                    label={kpi.label}
                    value={kpi.value}
                    tone={kpi.tone}
                    icon={kpi.icon}
                    hint={kpi.hint}
                  />
                ))}
              </div>
            ) : null}
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Workflow
            </h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Card className="card-interactive">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <span className="icon-chip">
                      <Gavel className="h-4 w-4" />
                    </span>
                    Case overview <InfoHint glossaryKey="workbench" />
                  </CardTitle>
                  <CardDescription>Full case overview and workflow management.</CardDescription>
                </CardHeader>
                <CardContent>
                  <Button asChild>
                    <Link href="/">Open case overview</Link>
                  </Button>
                </CardContent>
              </Card>
              <Card className="card-interactive">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <span className="icon-chip icon-chip-accent">
                      <Plus className="h-4 w-4" />
                    </span>
                    Add new case <InfoHint glossaryKey="intake" />
                  </CardTitle>
                  <CardDescription>Upload new judgments for processing.</CardDescription>
                </CardHeader>
                <CardContent>
                  <Button asChild variant="outline">
                    <Link href="/upload">Upload document</Link>
                  </Button>
                </CardContent>
              </Card>
              <Card className="card-interactive">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <span className="icon-chip icon-chip-good">
                      <ShieldCheck className="h-4 w-4" />
                    </span>
                    Advocate approvals <InfoHint glossaryKey="verifications" />
                  </CardTitle>
                  <CardDescription>Review pending advocate registrations.</CardDescription>
                </CardHeader>
                <CardContent>
                  <Button asChild variant="outline">
                    <Link href="/admin/verifications">Review queue</Link>
                  </Button>
                </CardContent>
              </Card>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
