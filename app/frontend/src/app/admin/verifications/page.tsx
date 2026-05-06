"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import type { AdvocateDirectoryItem } from "@/lib/api/client";
import { listPendingAdvocates, verifyAdvocate, rejectAdvocate } from "@/lib/api/client";
import { useAuthStore } from "@/lib/auth/store";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/app/page-header";
import { InfoHint } from "@/components/info-hint";

export default function VerificationsPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const status = useAuthStore((s) => s.status);

  const [advocates, setAdvocates] = useState<AdvocateDirectoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [rejectTarget, setRejectTarget] = useState<AdvocateDirectoryItem | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [actionLoading, setActionLoading] = useState(false);

  const loadPending = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await listPendingAdvocates();
      if (result.ok) {
        setAdvocates(result.data.items);
      } else {
        setError(result.error.message || "Failed to load pending advocates.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (status === "anon") {
      router.push("/login?redirect=/admin/verifications");
      return;
    }
    if (status !== "authed") return;
    if (user && user.role !== "judge" && user.role !== "government") {
      router.push("/dashboard");
      return;
    }
    void loadPending();
  }, [loadPending, router, status, user]);

  async function handleVerify(id: string) {
    setActionLoading(true);
    try {
      const result = await verifyAdvocate(id);
      if (result.ok) {
        setAdvocates((prev) => prev.filter((a) => a.id !== id));
      }
    } finally {
      setActionLoading(false);
    }
  }

  async function handleRejectConfirm() {
    if (!rejectTarget) return;
    setActionLoading(true);
    try {
      const result = await rejectAdvocate(rejectTarget.id, rejectReason);
      if (result.ok) {
        setAdvocates((prev) => prev.filter((a) => a.id !== rejectTarget.id));
        setRejectTarget(null);
        setRejectReason("");
      }
    } finally {
      setActionLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4 py-8">
        <Skeleton className="h-8 w-64" />
        {[...Array(3)].map((_, i) => (
          <Skeleton key={i} className="h-32 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6 py-8">
      <PageHeader
        eyebrow={
          <span className="flex items-center gap-1.5">
            Advocate approvals <InfoHint glossaryKey="verifications" />
          </span>
        }
        title="Review pending registrations"
        subtitle="Review and approve or reject pending advocate registrations."
      />

      {error && <p className="text-sm text-destructive">{error}</p>}

      {advocates.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            No pending verifications.
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-col gap-4">
          {advocates.map((advocate) => {
            const p = advocate.profile;
            return (
              <Card key={advocate.id}>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center justify-between gap-3 text-base">
                    <span>{advocate.full_name ?? advocate.email}</span>
                    <Badge variant="outline">Pending</Badge>
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">{advocate.email}</p>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                    <span className="text-muted-foreground">Bar Council ID</span>
                    <span className="font-mono">{p.bar_council_id}</span>
                    {p.registration_number && (
                      <>
                        <span className="text-muted-foreground">Registration</span>
                        <span className="font-mono">{p.registration_number}</span>
                      </>
                    )}
                    {p.years_of_experience !== null && (
                      <>
                        <span className="text-muted-foreground">Experience</span>
                        <span>{p.years_of_experience} years</span>
                      </>
                    )}
                    {p.specializations.length > 0 && (
                      <>
                        <span className="text-muted-foreground">Specializations</span>
                        <span className="flex flex-wrap gap-1">
                          {p.specializations.map((s) => (
                            <Badge key={s} variant="secondary" className="capitalize text-xs">
                              {s}
                            </Badge>
                          ))}
                        </span>
                      </>
                    )}
                  </div>
                  {p.bio && (
                    <p className="text-sm text-muted-foreground line-clamp-2">{p.bio}</p>
                  )}
                  <div className="flex gap-2 pt-2">
                    <Button
                      size="sm"
                      disabled={actionLoading}
                      onClick={() => void handleVerify(advocate.id)}
                    >
                      Verify
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={actionLoading}
                      onClick={() => {
                        setRejectTarget(advocate);
                        setRejectReason("");
                      }}
                    >
                      Reject
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Reject dialog */}
      <Dialog open={!!rejectTarget} onOpenChange={(open) => !open && setRejectTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject advocate registration</DialogTitle>
            <DialogDescription>
              Provide a reason for rejecting{" "}
              <strong>{rejectTarget?.full_name ?? rejectTarget?.email}</strong>. This will be
              visible to the applicant.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="reject-reason">Reason</Label>
            <Input
              id="reject-reason"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Invalid bar council ID, insufficient documentation…"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={actionLoading || !rejectReason.trim()}
              onClick={() => void handleRejectConfirm()}
            >
              {actionLoading ? "Rejecting…" : "Reject"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}


