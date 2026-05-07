"use client";

import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { listClauses, type ClauseRecord, type ObligationRecord } from "@/lib/api/client";
import { cn } from "@/lib/utils";

type WhyPanelProps = {
  obligation: ObligationRecord;
  documentId: string;
  defaultOpen?: boolean;
};

function formatPercent(value: number | null | undefined): string {
  if (typeof value !== "number") return "n/a";
  return `${(value * 100).toFixed(0)}%`;
}

function formatComponentName(name: string): string {
  return name
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function WhyPanel({ obligation, documentId, defaultOpen = false }: WhyPanelProps) {
  const [open, setOpen] = useState(defaultOpen);
  const [clauseState, setClauseState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [clauseItems, setClauseItems] = useState<ClauseRecord[]>([]);
  const [clauseError, setClauseError] = useState<string | null>(null);

  const annotations = obligation.confidence_annotations;
  const citation = obligation.citation;

  useEffect(() => {
    if (!open) return;
    if (clauseState !== "idle") return;
    if (!citation?.clause_span) {
      setClauseState("ready");
      return;
    }
    let cancelled = false;
    setClauseState("loading");
    listClauses(documentId, { clauseSpan: citation.clause_span }).then((result) => {
      if (cancelled) return;
      if (!result.ok) {
        setClauseError(result.error.message);
        setClauseState("error");
        return;
      }
      setClauseItems(result.data.items);
      setClauseState("ready");
    });
    return () => {
      cancelled = true;
    };
  }, [open, clauseState, citation?.clause_span, documentId]);

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-md border border-border">
      <CollapsibleTrigger asChild>
        <Button
          variant="ghost"
          className="flex h-auto w-full items-center justify-between rounded-md px-3 py-2 text-sm font-semibold"
        >
          Why this obligation? Provenance & explainability
          <ChevronDown
            className={cn("h-4 w-4 transition-transform", open && "rotate-180")}
            aria-hidden
          />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="flex flex-col gap-4 border-t border-border px-3 py-3 text-sm">
        <section>
          <h5 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Extractor
          </h5>
          <p className="mt-1 text-foreground/90">
            <strong>Model version:</strong> {annotations?.extractor_version ?? "unknown"}
          </p>
          <p className="text-foreground/90">
            <strong>Overall confidence:</strong> {formatPercent(obligation.confidence ?? null)}
          </p>
        </section>

        {annotations?.components && Object.keys(annotations.components).length > 0 ? (
          <section>
            <h5 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Confidence components
            </h5>
            <Table className="mt-2 text-xs">
              <TableHeader>
                <TableRow>
                  <TableHead className="px-2">Signal</TableHead>
                  <TableHead className="px-2">Weight</TableHead>
                  <TableHead className="px-2">Score</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.entries(annotations.components).map(([name, value]) => {
                  const weight = annotations.weights?.[name];
                  return (
                    <TableRow key={name}>
                      <TableCell className="px-2 py-1.5">{formatComponentName(name)}</TableCell>
                      <TableCell className="px-2 py-1.5 text-muted-foreground">
                        {typeof weight === "number" ? formatPercent(weight) : "—"}
                      </TableCell>
                      <TableCell className="px-2 py-1.5">
                        {formatPercent(typeof value === "number" ? value : null)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            {annotations.rationale && annotations.rationale.length > 0 ? (
              <ul className="mt-2 ml-5 list-disc text-xs text-muted-foreground">
                {annotations.rationale.map((line, idx) => (
                  <li key={idx}>{line}</li>
                ))}
              </ul>
            ) : null}
          </section>
        ) : null}

        {citation ? (
          <section>
            <h5 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Source citation
            </h5>
            <p className="mt-1 text-foreground/90">
              <strong>Page:</strong> {citation.page_number ?? "n/a"} · <strong>Clause:</strong>{" "}
              {citation.clause_span ?? "n/a"}
              {typeof citation.span_start === "number" && typeof citation.span_end === "number"
                ? ` · chars ${citation.span_start}–${citation.span_end}`
                : null}
            </p>
            {clauseState === "loading" ? (
              <p className="text-xs text-muted-foreground">Loading clause snippet…</p>
            ) : null}
            {clauseState === "error" ? (
              <p className="text-xs text-destructive">
                Couldn&apos;t load clause snippet: {clauseError}
              </p>
            ) : null}
            {clauseState === "ready" && clauseItems.length > 0 ? (
              <blockquote className="mt-2 rounded-md border-l-2 border-accent bg-accent/10 px-3 py-2 text-xs italic text-accent">
                {clauseItems[0].text.length > 320
                  ? `${clauseItems[0].text.slice(0, 320)}…`
                  : clauseItems[0].text}
              </blockquote>
            ) : null}
          </section>
        ) : null}

        {obligation.risk_score !== null && obligation.risk_score !== undefined ? (
          <section>
            <h5 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Contempt-Risk reasoning
            </h5>
            <p className="mt-1 text-foreground/90">
              <strong>Score:</strong> {obligation.risk_score}/100 ({obligation.risk_band ?? "n/a"})
            </p>
            {obligation.risk_factors && obligation.risk_factors.length > 0 ? (
              <ul className="mt-2 ml-5 list-disc text-xs text-muted-foreground">
                {obligation.risk_factors.map((factor) => (
                  <li key={factor.name}>
                    <strong className="text-foreground">{formatComponentName(factor.name)}</strong>{" "}
                    +{factor.contribution.toFixed(1)} pts — {factor.detail}
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  );
}
