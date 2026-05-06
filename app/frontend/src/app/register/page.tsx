"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { AdvocateProfileCreatePayload } from "@/lib/api/client";
import { registerUser } from "@/lib/api/client";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

const SPECIALIZATIONS = [
  "criminal",
  "civil",
  "family",
  "corporate",
  "tax",
  "labour",
  "ipr",
  "consumer",
  "constitutional",
  "other",
] as const;

export default function RegisterPage() {
  const router = useRouter();
  const [role, setRole] = useState<"citizen" | "advocate">("citizen");

  // Common fields
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");

  // Advocate-only fields
  const [barId, setBarId] = useState("");
  const [regNumber, setRegNumber] = useState("");
  const [bio, setBio] = useState("");
  const [experience, setExperience] = useState("");
  const [languages, setLanguages] = useState("");
  const [selectedSpecs, setSelectedSpecs] = useState<Set<string>>(new Set());
  const [feeMin, setFeeMin] = useState("");
  const [feeMax, setFeeMax] = useState("");

  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  function toggleSpec(s: string) {
    setSelectedSpecs((prev) => {
      const next = new Set(prev);
      next.has(s) ? next.delete(s) : next.add(s);
      return next;
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      let advocate_profile: AdvocateProfileCreatePayload | undefined;
      if (role === "advocate") {
        if (!barId.trim()) {
          setError("Bar Council ID is required for advocate registration.");
          return;
        }
        advocate_profile = {
          bar_council_id: barId.trim(),
          registration_number: regNumber.trim() || undefined,
          bio: bio.trim() || undefined,
          years_of_experience: experience ? Number(experience) : undefined,
          languages: languages
            .split(",")
            .map((l) => l.trim())
            .filter(Boolean),
          specializations: Array.from(selectedSpecs),
          consultation_fee_min_inr: feeMin ? Number(feeMin) : undefined,
          consultation_fee_max_inr: feeMax ? Number(feeMax) : undefined,
        };
      }

      const result = await registerUser({
        email: email.trim(),
        password,
        full_name: name.trim(),
        role,
        phone: phone.trim() || undefined,
        advocate_profile,
      });

      if (!result.ok) {
        setError(result.error.message || "Registration failed. Please try again.");
        return;
      }

      setDone(true);
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center">
        <Card className="w-full max-w-md text-center">
          <CardHeader>
            <CardTitle>Registration complete</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {role === "advocate" ? (
              <Alert className="text-sm">
                Your advocate profile is <strong>pending verification</strong>. A judge or
                government officer will review and approve your profile before it appears in the
                directory.
              </Alert>
            ) : (
              <p className="text-sm text-muted-foreground">Your account is ready.</p>
            )}
            <Button onClick={() => router.push("/login")}>Continue to sign in</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-[70vh] items-center justify-center py-8">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>Create account</CardTitle>
          <CardDescription>Choose your role and fill in your details.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-5">
            {error && (
              <Alert variant="destructive" className="text-sm">
                {error}
              </Alert>
            )}

            <Tabs
              value={role}
              onValueChange={(v) => setRole(v as "citizen" | "advocate")}
              className="w-full"
            >
              <TabsList className="w-full">
                <TabsTrigger value="citizen" className="flex-1">
                  Citizen / Case Party
                </TabsTrigger>
                <TabsTrigger value="advocate" className="flex-1">
                  Advocate / Adviser
                </TabsTrigger>
              </TabsList>

              {/* Common fields shown in both tabs */}
              <div className="mt-4 flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="name">Full name</Label>
                  <Input
                    id="name"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Priya Sharma"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="reg-email">Email</Label>
                  <Input
                    id="reg-email"
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="reg-password">Password</Label>
                  <Input
                    id="reg-password"
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={8}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Minimum 8 characters"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="phone">Phone (optional)</Label>
                  <Input
                    id="phone"
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+91 98765 43210"
                  />
                </div>
              </div>

              <TabsContent value="advocate" className="mt-4 flex flex-col gap-4">
                <div className="rounded-md border border-border p-3 text-xs text-muted-foreground">
                  Advocate accounts are <strong>pending verification</strong> until a judge or
                  government officer approves your profile.
                </div>

                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="bar-id">
                    Bar Council ID <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="bar-id"
                    value={barId}
                    onChange={(e) => setBarId(e.target.value)}
                    placeholder="BAR/KA/2024/12345"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="reg-num">Registration number</Label>
                  <Input
                    id="reg-num"
                    value={regNumber}
                    onChange={(e) => setRegNumber(e.target.value)}
                    placeholder="REG-2024-0001"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="experience">Years of experience</Label>
                  <Input
                    id="experience"
                    type="number"
                    min={0}
                    max={60}
                    value={experience}
                    onChange={(e) => setExperience(e.target.value)}
                    placeholder="5"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Specializations</Label>
                  <div className="flex flex-wrap gap-2">
                    {SPECIALIZATIONS.map((s) => (
                      <Badge
                        key={s}
                        variant={selectedSpecs.has(s) ? "default" : "outline"}
                        className="cursor-pointer select-none capitalize"
                        onClick={() => toggleSpec(s)}
                      >
                        {s}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="languages">Languages (comma-separated)</Label>
                  <Input
                    id="languages"
                    value={languages}
                    onChange={(e) => setLanguages(e.target.value)}
                    placeholder="en, hi, kn"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="fee-min">Min fee (₹)</Label>
                    <Input
                      id="fee-min"
                      type="number"
                      min={0}
                      value={feeMin}
                      onChange={(e) => setFeeMin(e.target.value)}
                      placeholder="500"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="fee-max">Max fee (₹)</Label>
                    <Input
                      id="fee-max"
                      type="number"
                      min={0}
                      value={feeMax}
                      onChange={(e) => setFeeMax(e.target.value)}
                      placeholder="5000"
                    />
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="bio">Bio</Label>
                  <Textarea
                    id="bio"
                    rows={3}
                    value={bio}
                    onChange={(e) => setBio(e.target.value)}
                    placeholder="Brief professional summary…"
                  />
                </div>
              </TabsContent>
            </Tabs>

            <Button type="submit" disabled={loading} className="w-full">
              {loading ? "Creating account…" : "Create account"}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              Already have an account?{" "}
              <Link href="/login" className="text-foreground underline-offset-2 hover:underline">
                Sign in
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}


