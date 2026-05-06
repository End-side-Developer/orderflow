"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import type { AuthUserRecord, AdvocateDirectoryItem } from "@/lib/api/client";
import { getMe, getAdvocate, updateUser } from "@/lib/api/client";
import { useAuthStore } from "@/lib/auth/store";
import { ROLE_LABELS } from "@/lib/auth/permissions";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

export default function ProfilePage() {
  const router = useRouter();
  const storeUser = useAuthStore((s) => s.user);
  const status = useAuthStore((s) => s.status);

  const [userRecord, setUserRecord] = useState<AuthUserRecord | null>(null);
  const [advocateProfile, setAdvocateProfile] = useState<AdvocateDirectoryItem | null>(null);
  const [loading, setLoading] = useState(true);

  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveOk, setSaveOk] = useState(false);

  useEffect(() => {
    if (status === "anon") {
      router.push("/login?redirect=/profile");
      return;
    }
    if (status !== "authed") return;

    async function load() {
      setLoading(true);
      try {
        const meResult = await getMe();
        if (meResult.ok) {
          setUserRecord(meResult.data);
          setFullName(meResult.data.full_name ?? "");
          setPhone(meResult.data.phone ?? "");

          if (meResult.data.role === "advocate") {
            const advResult = await getAdvocate(meResult.data.id);
            if (advResult.ok) setAdvocateProfile(advResult.data);
          }
        }
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [status, router]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!userRecord) return;
    setSaving(true);
    setSaveError(null);
    setSaveOk(false);
    try {
      const result = await updateUser(userRecord.id, {
        full_name: fullName,
        phone: phone || undefined,
      });
      if (!result.ok) {
        setSaveError(result.error.message || "Failed to save.");
      } else {
        setSaveOk(true);
        setUserRecord(result.data);
      }
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-xl space-y-4 py-8">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!userRecord) return null;

  const verificationStatus = advocateProfile?.profile?.verification_status;

  return (
    <div className="mx-auto max-w-xl space-y-6 py-8">
      <h1 className="text-2xl font-semibold">Profile</h1>

      {/* Advocate verification banner */}
      {userRecord.role === "advocate" && (
        <Alert
          variant={
            verificationStatus === "verified"
              ? "good"
              : verificationStatus === "rejected"
                ? "destructive"
                : "default"
          }
          className="text-sm"
        >
          {verificationStatus === "pending" && (
            <>
              <strong>Verification pending</strong> — your advocate profile is under review. You
              will appear in the directory once a judge or government officer approves your account.
            </>
          )}
          {verificationStatus === "verified" && (
            <>
              <strong>Verified advocate</strong> — your profile is visible in the public directory.
            </>
          )}
          {verificationStatus === "rejected" && (
            <>
              <strong>Verification rejected</strong>
              {advocateProfile?.profile?.rejection_reason
                ? ` — ${advocateProfile.profile.rejection_reason}`
                : ". Contact support for more information."}
            </>
          )}
          {!verificationStatus && <>Loading profile…</>}
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-3">
            Account details
            <Badge variant="outline">{ROLE_LABELS[userRecord.role]}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={(e) => void handleSave(e)} className="flex flex-col gap-4">
            {saveError && (
              <Alert variant="destructive" className="text-sm">
                {saveError}
              </Alert>
            )}
            {saveOk && (
              <Alert className="text-sm">Profile updated successfully.</Alert>
            )}

            <div className="flex flex-col gap-1.5">
              <Label>Email</Label>
              <Input value={userRecord.email} disabled />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="profile-name">Full name</Label>
              <Input
                id="profile-name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Your name"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="profile-phone">Phone</Label>
              <Input
                id="profile-phone"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+91 98765 43210"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Account status</Label>
              <Input value={userRecord.status} disabled />
            </div>

            <Button type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save changes"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Advocate profile summary */}
      {advocateProfile && (
        <Card>
          <CardHeader>
            <CardTitle>Advocate profile</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            <div className="grid grid-cols-2 gap-x-4 gap-y-2">
              <span className="text-muted-foreground">Bar Council ID</span>
              <span className="font-mono">{advocateProfile.profile.bar_council_id}</span>
              {advocateProfile.profile.years_of_experience !== null && (
                <>
                  <span className="text-muted-foreground">Experience</span>
                  <span>{advocateProfile.profile.years_of_experience} years</span>
                </>
              )}
              {advocateProfile.profile.specializations.length > 0 && (
                <>
                  <span className="text-muted-foreground">Specializations</span>
                  <span className="flex flex-wrap gap-1">
                    {advocateProfile.profile.specializations.map((s) => (
                      <Badge key={s} variant="secondary" className="capitalize">
                        {s}
                      </Badge>
                    ))}
                  </span>
                </>
              )}
              {advocateProfile.profile.languages.length > 0 && (
                <>
                  <span className="text-muted-foreground">Languages</span>
                  <span>{advocateProfile.profile.languages.join(", ")}</span>
                </>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}


