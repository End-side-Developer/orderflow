"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import type { AdvocateDirectoryItem, AdvocateListParams } from "@/lib/api/client";
import { listAdvocatesDirectory } from "@/lib/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const SPECIALIZATIONS = [
  { value: "all", label: "All specializations" },
  { value: "criminal", label: "Criminal" },
  { value: "civil", label: "Civil" },
  { value: "family", label: "Family" },
  { value: "corporate", label: "Corporate" },
  { value: "tax", label: "Tax" },
  { value: "labour", label: "Labour" },
  { value: "ipr", label: "IPR" },
  { value: "consumer", label: "Consumer" },
  { value: "constitutional", label: "Constitutional" },
  { value: "other", label: "Other" },
];

const LANGUAGES = [
  { value: "all", label: "All languages" },
  { value: "en", label: "English" },
  { value: "hi", label: "Hindi" },
  { value: "kn", label: "Kannada" },
  { value: "ta", label: "Tamil" },
  { value: "te", label: "Telugu" },
  { value: "ml", label: "Malayalam" },
  { value: "mr", label: "Marathi" },
];

function AdvocateCard({ advocate }: { advocate: AdvocateDirectoryItem }) {
  const p = advocate.profile;
  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">
          {advocate.full_name ?? advocate.email}
        </CardTitle>
        <p className="text-xs text-muted-foreground font-mono">{p.bar_council_id}</p>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3">
        {p.bio && (
          <p className="text-sm text-muted-foreground line-clamp-2">{p.bio}</p>
        )}
        {p.specializations.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {p.specializations.slice(0, 4).map((s) => (
              <Badge key={s} variant="secondary" className="capitalize text-xs">
                {s}
              </Badge>
            ))}
            {p.specializations.length > 4 && (
              <Badge variant="outline" className="text-xs">+{p.specializations.length - 4}</Badge>
            )}
          </div>
        )}
        <div className="flex items-center justify-between text-xs text-muted-foreground mt-auto">
          {p.years_of_experience !== null && (
            <span>{p.years_of_experience}y exp</span>
          )}
          {p.consultation_fee_min_inr !== null && (
            <span>
              ₹{p.consultation_fee_min_inr.toLocaleString()}
              {p.consultation_fee_max_inr ? `–${p.consultation_fee_max_inr.toLocaleString()}` : "+"}
            </span>
          )}
          {p.ratings_count > 0 && (
            <span>★ {p.ratings_avg?.toFixed(1) ?? "—"} ({p.ratings_count})</span>
          )}
        </div>
        <Button asChild variant="outline" size="sm" className="mt-2 w-full">
          <Link href={`/advocates/${advocate.id}`}>View profile</Link>
        </Button>
      </CardContent>
    </Card>
  );
}

export default function AdvocatesPage() {
  const [advocates, setAdvocates] = useState<AdvocateDirectoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [q, setQ] = useState("");
  const [specialization, setSpecialization] = useState("all");
  const [language, setLanguage] = useState("all");
  const [offset, setOffset] = useState(0);
  const PAGE_SIZE = 20;

  async function load(params: AdvocateListParams) {
    setLoading(true);
    setError(null);
    try {
      const result = await listAdvocatesDirectory({ limit: PAGE_SIZE, ...params });
      if (result.ok) {
        setAdvocates(result.data.items);
        setTotal(result.data.total);
      } else {
        setError(result.error.message || "Failed to load advocates.");
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load({ 
      q: q || undefined, 
      specialization: specialization === "all" ? undefined : specialization, 
      language: language === "all" ? undefined : language, 
      offset 
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setOffset(0);
    void load({ 
      q: q || undefined, 
      specialization: specialization === "all" ? undefined : specialization, 
      language: language === "all" ? undefined : language, 
      offset: 0 
    });
  }

  function handlePage(dir: "prev" | "next") {
    const newOffset = dir === "next" ? offset + PAGE_SIZE : Math.max(0, offset - PAGE_SIZE);
    setOffset(newOffset);
    void load({ 
      q: q || undefined, 
      specialization: specialization === "all" ? undefined : specialization, 
      language: language === "all" ? undefined : language, 
      offset: newOffset 
    });
  }

  return (
    <div className="space-y-6 py-8">
      <div>
        <h1 className="text-2xl font-semibold">Advocate Directory</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Verified legal professionals available for consultation.
        </p>
      </div>

      {/* Filters */}
      <form onSubmit={handleSearch} className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <Label htmlFor="adv-q" className="text-xs">Search</Label>
          <Input
            id="adv-q"
            className="w-56"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Name or keyword…"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Specialization</Label>
          <Select value={specialization} onValueChange={setSpecialization}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SPECIALIZATIONS.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Language</Label>
          <Select value={language} onValueChange={setLanguage}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LANGUAGES.map((l) => (
                <SelectItem key={l.value} value={l.value}>
                  {l.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button type="submit" disabled={loading}>Search</Button>
      </form>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <p className="text-sm text-muted-foreground">
        {loading ? "Loading…" : `${total} verified advocate${total !== 1 ? "s" : ""} found`}
      </p>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {[...Array(8)].map((_, i) => (
            <Skeleton key={i} className="h-52 w-full" />
          ))}
        </div>
      ) : advocates.length === 0 ? (
        <p className="text-sm text-muted-foreground py-8 text-center">No advocates found.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {advocates.map((a) => (
            <AdvocateCard key={a.id} advocate={a} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => handlePage("prev")}>
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </span>
          <Button variant="outline" size="sm" disabled={offset + PAGE_SIZE >= total} onClick={() => handlePage("next")}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
