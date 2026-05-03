"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  claimAdvocateCase,
  listDocumentAdvocates,
  type AdvocateCaseLink,
} from "@/lib/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface DocumentAdvocatesStripProps {
  documentId: string;
}

export function DocumentAdvocatesStrip({ documentId }: DocumentAdvocatesStripProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<AdvocateCaseLink[]>([]);
  const [claiming, setClaiming] = useState(false);
  const [claimNote, setClaimNote] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setItems([]);

    (async () => {
      const result = await listDocumentAdvocates(documentId);
      if (cancelled) return;
      if (result.ok) {
        setItems(result.data.items);
      } else {
        setError(result.error.message);
      }
      setLoading(false);
    })();

    return () => {
      cancelled = true;
    };
  }, [documentId]);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">Counsel on record</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading counsel links…</p>
        ) : null}
        {!loading && error ? (
          <p className="text-sm text-muted-foreground">Could not load counsel links: {error}</p>
        ) : null}
        {!loading && !error && items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No advocates linked to this case yet.</p>
        ) : null}
        {!loading && !error && items.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {items.map((item) => (
              <Link
                key={item.id}
                href={`/advocates/${item.advocate_user_id}`}
                className="inline-flex items-center gap-2 rounded-md border border-border bg-muted/20 px-2.5 py-1.5 text-xs transition-colors hover:bg-muted/40"
              >
                <span className="font-medium text-foreground">
                  {item.advocate_full_name ?? "Advocate"}
                </span>
                <Badge variant={item.status === "verified" ? "good" : "warn"} className="text-[10px]">
                  {item.status}
                </Badge>
              </Link>
            ))}
          </div>
        ) : null}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={claiming}
            onClick={async () => {
              setClaiming(true);
              setClaimNote(null);
              const result = await claimAdvocateCase({
                document_id: documentId,
                role: "counsel",
              });
              if (result.ok) {
                setClaimNote("Case claim submitted. Awaiting verification.");
                setItems((prev) => [result.data.item, ...prev]);
              } else {
                setClaimNote(result.error.message);
              }
              setClaiming(false);
            }}
          >
            {claiming ? "Claiming..." : "Claim this case"}
          </Button>
          {claimNote ? <span className="text-xs text-muted-foreground">{claimNote}</span> : null}
        </div>
      </CardContent>
    </Card>
  );
}
