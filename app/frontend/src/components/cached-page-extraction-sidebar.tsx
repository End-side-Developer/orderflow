"use client";

import { type ReactNode, useEffect, useState } from "react";
import {
  AlertTriangle,
  Building2,
  CalendarDays,
  CheckCircle2,
  FileText,
  Hash,
  Landmark,
  ListChecks,
  RotateCcw,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { PageSummaryRecord } from "@/lib/api/client";

type CachedPageExtractionSidebarProps = {
  currentPage: number;
  pageSummary: PageSummaryRecord | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onJumpToPage?: (page: number) => void;
};

export function CachedPageExtractionSidebar({
  currentPage,
  pageSummary,
  loading,
  error,
  onRetry,
  onJumpToPage,
}: CachedPageExtractionSidebarProps) {
  const [activeTab, setActiveTab] = useState("overview");

  // Reset tab to overview when the page changes
  useEffect(() => {
    setActiveTab("overview");
  }, [currentPage]);

  if (loading) {
    return (
      <aside className="flex min-h-0 flex-col gap-3 border-l border-border bg-card p-4">
        <div className="h-4 w-32 animate-pulse rounded bg-muted" />
        <div className="h-24 animate-pulse rounded-md bg-muted" />
        <div className="h-32 animate-pulse rounded-md bg-muted" />
      </aside>
    );
  }

  if (error) {
    return (
      <aside className="flex min-h-0 flex-col gap-3 border-l border-border bg-card p-4">
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>Cached extraction unavailable</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
        <Button type="button" variant="outline" onClick={onRetry}>
          <RotateCcw data-icon="inline-start" />
          Retry
        </Button>
      </aside>
    );
  }

  if (!pageSummary) {
    return (
      <aside className="flex min-h-0 flex-col gap-3 border-l border-border bg-card p-4">
        <Alert>
          <FileText />
          <AlertTitle>Page {currentPage} has no cached extraction yet</AlertTitle>
          <AlertDescription>
            Start intake or wait for page extraction to complete. This viewer will not call a separate
            AI endpoint.
          </AlertDescription>
        </Alert>
      </aside>
    );
  }

  const confidence = clampPercent((pageSummary.confidence ?? 0) * 100);
  const sourceLabel = [
    pageSummary.ai_provider,
    pageSummary.ai_model,
    pageSummary.prompt_version,
  ]
    .filter(Boolean)
    .join(" / ");

  return (
    <aside className="flex min-h-0 flex-col border-l border-border bg-card">
      <div className="border-b border-border p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-card-foreground">
              Page {currentPage} cached extraction
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Same page-level data generated during intake.
            </p>
          </div>
          <Badge variant={pageSummary.extraction_mode === "ai" ? "accent" : "secondary"}>
            {pageSummary.extraction_mode}
          </Badge>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <Progress value={confidence} className="h-2 flex-1" />
          <span className="text-xs font-semibold tabular-nums text-muted-foreground">
            {confidence}%
          </span>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex min-h-0 flex-1 flex-col">
        <div className="border-b border-border px-4 pt-3">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="overview">Summary</TabsTrigger>
            <TabsTrigger value="entities">Entities</TabsTrigger>
            <TabsTrigger value="dates">Dates</TabsTrigger>
            <TabsTrigger value="directions">Directions</TabsTrigger>
          </TabsList>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <TabsContent value="overview" className="m-0 flex flex-col gap-6">
            <Section title="Page Summary">
              <p className="whitespace-pre-wrap break-words text-[15px] leading-relaxed text-foreground">
                {pageSummary.summary || "No summary captured for this page."}
              </p>
            </Section>

            <Section title="Important Paragraphs">
              <Highlights pageSummary={pageSummary} />
            </Section>

            <Section title="Key Points">
              {pageSummary.key_points.length > 0 ? (
                <ul className="flex flex-col gap-3">
                  {pageSummary.key_points.map((point, index) => (
                    <li key={`${point}-${index}`} className="flex gap-2 text-[15px] leading-relaxed">
                      <CheckCircle2 className="mt-[2px] h-5 w-5 shrink-0 text-emerald-600" />
                      <span className="break-words text-foreground">{point}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyText text="No key points cached for this page." />
              )}
            </Section>

            <RelatedPages pageSummary={pageSummary} onJumpToPage={onJumpToPage} />
            <CacheEvidence pageSummary={pageSummary} sourceLabel={sourceLabel} />
          </TabsContent>

          <TabsContent value="entities" className="m-0 flex flex-col gap-4">
            <Section title="Entities">
              {pageSummary.entities.length > 0 ? (
                <div className="grid gap-2">
                  {pageSummary.entities.map((entity, index) => (
                    <div key={`${entity.name}-${index}`} className="rounded-md border border-border p-3">
                      <div className="mb-2 flex items-start gap-2">
                        <Landmark className="mt-0.5 shrink-0 text-muted-foreground" />
                        <div className="min-w-0 flex-1">
                          <p className="break-words text-sm font-semibold text-card-foreground">
                            {entity.name}
                          </p>
                          <div className="mt-1 flex flex-wrap gap-2">
                            {entity.entity_type ? <Badge variant="secondary">{entity.entity_type}</Badge> : null}
                            {entity.role ? <Badge variant="outline">{entity.role}</Badge> : null}
                            <ConfidenceBadge value={entity.confidence} />
                          </div>
                        </div>
                      </div>
                      {entity.source_location ? (
                        <p className="text-xs text-muted-foreground">{entity.source_location}</p>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyText text="No entities cached for this page. Regenerate this page to fill rich extraction fields." />
              )}
            </Section>

            <Section title="Departments">
              {pageSummary.departments.length > 0 ? (
                <div className="flex flex-col gap-2">
                  {pageSummary.departments.map((department, index) => (
                    <div key={`${department.name}-${index}`} className="rounded-md bg-muted/40 p-3">
                      <div className="flex items-start gap-2">
                        <Building2 className="mt-0.5 shrink-0 text-muted-foreground" />
                        <div className="min-w-0 flex-1">
                          <p className="break-words text-sm font-semibold">{department.name}</p>
                          {department.role ? (
                            <p className="mt-1 break-words text-xs text-muted-foreground">
                              {department.role}
                            </p>
                          ) : null}
                        </div>
                        <ConfidenceBadge value={department.confidence} />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyText text="No departments cached for this page." />
              )}
            </Section>
          </TabsContent>

          <TabsContent value="dates" className="m-0 flex flex-col gap-3">
            {pageSummary.dates.length > 0 ? (
              pageSummary.dates.map((date, index) => (
                <div key={`${date.date_text}-${index}`} className="rounded-md border border-border p-3">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <CalendarDays className="text-muted-foreground" />
                    <p className="break-words text-sm font-semibold text-card-foreground">
                      {date.date_text}
                    </p>
                    {date.label ? <Badge variant="secondary">{date.label}</Badge> : null}
                    {date.is_inferred ? <Badge variant="warn">inferred</Badge> : null}
                    <ConfidenceBadge value={date.confidence} />
                  </div>
                  {date.source_location ? (
                    <p className="text-xs text-muted-foreground">{date.source_location}</p>
                  ) : null}
                </div>
              ))
            ) : (
              <EmptyText text="No dates cached for this page. Regenerate this page to fill rich extraction fields." />
            )}
          </TabsContent>

          <TabsContent value="directions" className="m-0 flex flex-col gap-3">
            {pageSummary.directions.length > 0 ? (
              pageSummary.directions.map((direction, index) => (
                <div key={`${direction.direction_text}-${index}`} className="rounded-md border border-border p-3">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <ListChecks className="text-muted-foreground" />
                    <Badge variant={direction.directive_kind === "mandatory" ? "warn" : "secondary"}>
                      {direction.directive_kind}
                    </Badge>
                    <Badge variant={direction.compliance_required === "yes" ? "good" : "muted"}>
                      compliance {direction.compliance_required}
                    </Badge>
                    <ConfidenceBadge value={direction.confidence} />
                  </div>
                  <p className="break-words text-sm leading-6 text-card-foreground/90">
                    {direction.direction_text}
                  </p>
                  {direction.source_location ? (
                    <p className="mt-2 text-xs text-muted-foreground">{direction.source_location}</p>
                  ) : null}
                </div>
              ))
            ) : (
              <EmptyText text="No directions cached for this page. Regenerate this page to fill rich extraction fields." />
            )}
          </TabsContent>
        </div>
      </Tabs>
    </aside>
  );
}

function Highlights({ pageSummary }: { pageSummary: PageSummaryRecord }) {
  if (pageSummary.important_highlights.length === 0) {
    return <EmptyText text="No important paragraphs cached for this page." />;
  }
  return (
    <div className="flex flex-col gap-3">
      {pageSummary.important_highlights.map((highlight, index) => (
        <div key={`${highlight.text}-${index}`} className="rounded-lg border border-border bg-muted p-4 shadow-sm">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge variant={highlight.significance === "critical" ? "destructive" : "secondary"} className="text-[10px] font-semibold uppercase tracking-wider">
              {highlight.significance}
            </Badge>
          </div>
          <p className="line-clamp-4 break-words text-[14px] leading-relaxed text-foreground italic border-l-2 border-border pl-3">
            "{highlight.text}"
          </p>
          {highlight.relevance ? (
            <p className="mt-3 break-words text-[13px] font-medium leading-relaxed text-foreground">
              <span className="font-semibold text-foreground">Relevance:</span> {highlight.relevance}
            </p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function RelatedPages({
  pageSummary,
  onJumpToPage,
}: {
  pageSummary: PageSummaryRecord;
  onJumpToPage?: (page: number) => void;
}) {
  if (pageSummary.context_links.length === 0) return null;
  return (
    <Section title="Related Pages">
      <div className="flex flex-col gap-2">
        {pageSummary.context_links.map((link) => (
          <Button
            key={`${link.page_number}-${link.reason}`}
            type="button"
            variant="outline"
            className="h-auto justify-start whitespace-normal text-left"
            onClick={() => onJumpToPage?.(link.page_number)}
          >
            Page {link.page_number}: {link.reason}
          </Button>
        ))}
      </div>
    </Section>
  );
}

function CacheEvidence({
  pageSummary,
  sourceLabel,
}: {
  pageSummary: PageSummaryRecord;
  sourceLabel: string;
}) {
  return (
    <Section title="Cache Evidence">
      <div className="flex flex-col gap-2 rounded-md bg-muted/40 p-3 text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <Hash />
          <span className="break-all">{pageSummary.content_hash ?? "No page hash stored"}</span>
        </div>
        <span>{sourceLabel || "Model metadata not captured"}</span>
        {pageSummary.source_excerpt ? (
          <p className="line-clamp-3 break-words leading-5">{pageSummary.source_excerpt}</p>
        ) : null}
      </div>
    </Section>
  );
}

function ConfidenceBadge({ value }: { value: number | null }) {
  if (value == null) return null;
  const percent = clampPercent(value * 100);
  return <Badge variant={percent >= 70 ? "good" : "warn"}>{percent}%</Badge>;
}

function Section({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2">
      <h4 className="text-xs font-semibold uppercase text-muted-foreground">{title}</h4>
      {children}
    </section>
  );
}

function EmptyText({ text }: { text: string }) {
  return (
    <p className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">
      {text}
    </p>
  );
}

function clampPercent(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, Math.round(value)));
}


