"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, BarChart3, CheckCircle2, FileText, Sparkles, X } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AiErrorBanner } from "@/components/ai-error-banner";
import { CaseFlowGraph } from "@/components/case-flow-graph";
import { TtsControls } from "@/components/tts-controls";
import { getPageInsight, type ApiFailure, type PageInsightData } from "@/lib/api/client";
import { cn } from "@/lib/utils";

type PageInsight = PageInsightData;

interface AiPageSummaryOverlayProps {
  currentPage: number;
  pageText: string;
  documentId: string;
  preferredLanguage?: string | null;
  onJumpToPage?: (page: number) => void;
}

const CATEGORY_VARIANT: Record<string, "accent" | "warn" | "good" | "destructive" | "muted"> = {
  Procedural: "accent",
  Factual: "muted",
  "Legal Analysis": "accent",
  "Order/Direction": "warn",
  Evidence: "good",
  Argument: "warn",
  Miscellaneous: "muted",
};

function complexityTone(score: number): { label: string; indicatorClass: string; textClass: string } {
  if (score <= 3) return { label: "Low", indicatorClass: "bg-good", textClass: "text-good" };
  if (score <= 6) return { label: "Moderate", indicatorClass: "bg-warn", textClass: "text-warn" };
  return { label: "High", indicatorClass: "bg-destructive", textClass: "text-destructive" };
}

export function AiPageSummaryOverlay({
  currentPage,
  pageText,
  documentId,
  preferredLanguage,
  onJumpToPage,
}: AiPageSummaryOverlayProps) {
  const [summary, setSummary] = useState<PageInsight | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiFailure | null>(null);
  const [isExpanded, setIsExpanded] = useState(true);
  const [activeTab, setActiveTab] = useState<"overview" | "entities" | "timeline" | "flow">(
    "overview",
  );

  useEffect(() => {
    async function fetchInsight() {
      if (!pageText || pageText.trim() === "") {
        setSummary(null);
        setError({
          ok: false,
          error: { code: "no_text", message: "No readable text found on this page." },
        });
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const result = await getPageInsight({
          document_id: documentId,
          page_number: currentPage,
          text: pageText,
        });
        if (result.ok) {
          setSummary(result.data);
          return;
        }
        setSummary(null);
        setError(result);
      } catch (err) {
        setSummary(null);
        setError({
          ok: false,
          error: {
            code: "network_error",
            message: err instanceof Error ? err.message : "Failed to fetch AI insight.",
          },
        });
      } finally {
        setLoading(false);
      }
    }
    void fetchInsight();
  }, [currentPage, pageText, documentId]);

  if (!isExpanded) {
    return (
      <Button variant="outline" className="w-full" onClick={() => setIsExpanded(true)}>
        <Sparkles />
        Open AI analysis
      </Button>
    );
  }

  return (
    <Card className="flex max-h-[calc(100vh-220px)] min-h-[420px] w-full flex-col">
      <CardHeader className="flex-row items-start justify-between gap-3 border-b border-border">
        <div className="flex flex-col gap-1">
          <CardTitle className="text-base">Page {currentPage} analysis</CardTitle>
          {summary?.page_category ? (
            <Badge variant={CATEGORY_VARIANT[summary.page_category] ?? "muted"}>
              {summary.page_category}
            </Badge>
          ) : (
            <CardDescription>AI-extracted insight for this page.</CardDescription>
          )}
          <TtsControls
            text={summary?.brief ?? ""}
            preferredLanguage={preferredLanguage}
            resetSignal={`${documentId}-${currentPage}`}
            className="mt-2"
          />
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Hide AI analysis"
          onClick={() => setIsExpanded(false)}
        >
          <X />
        </Button>
      </CardHeader>

      {!loading && summary ? (
        <Tabs
          value={activeTab}
          onValueChange={(v) => setActiveTab(v as typeof activeTab)}
          className="flex flex-1 flex-col"
        >
          <div className="border-b border-border px-4 pt-3">
            <TabsList className="w-full">
              <TabsTrigger value="overview" className="flex-1">
                Overview
              </TabsTrigger>
              <TabsTrigger value="entities" className="flex-1">
                Entities
              </TabsTrigger>
              <TabsTrigger value="timeline" className="flex-1">
                Dates
              </TabsTrigger>
              <TabsTrigger value="flow" className="flex-1">
                Flow
              </TabsTrigger>
            </TabsList>
          </div>

          <ScrollArea className="flex-1">
            <TabsContent value="overview" className="m-0 flex flex-col gap-5 p-4">
              <Section label="Summary">
                <p className="text-sm leading-relaxed text-foreground/90">{summary.brief}</p>
              </Section>

              {summary.complexity_score != null ? (
                <ComplexityRow score={summary.complexity_score} />
              ) : null}

              {summary.statistics.length > 0 ? (
                <Section label="Page statistics" icon={<BarChart3 />}>
                  <div className="overflow-hidden rounded-md border border-border">
                    {summary.statistics.map((stat, idx) => (
                      <div
                        key={idx}
                        className={cn(
                          "flex items-center justify-between px-3 py-2 text-sm",
                          idx % 2 === 0 ? "bg-muted/30" : "",
                          idx < summary.statistics.length - 1 ? "border-b border-border" : "",
                        )}
                      >
                        <span className="text-muted-foreground">{stat.label}</span>
                        <span className="font-semibold text-foreground tabular-nums">
                          {stat.value}
                        </span>
                      </div>
                    ))}
                  </div>
                </Section>
              ) : null}

              {summary.risks.length > 0 ? (
                <Section label="Identified risks" icon={<AlertTriangle />} tone="destructive">
                  <ul className="flex flex-col gap-1.5">
                    {summary.risks.map((r, idx) => (
                      <li
                        key={idx}
                        className="flex items-start gap-2 rounded-md border-l-2 border-destructive bg-destructive/10 px-3 py-2 text-sm text-destructive"
                      >
                        <span aria-hidden>•</span>
                        <span className="text-destructive/90">{r}</span>
                      </li>
                    ))}
                  </ul>
                </Section>
              ) : null}

              {summary.suggested_action ? (
                <Section label="Suggested action" icon={<CheckCircle2 />} tone="good">
                  <div className="rounded-md border border-good/30 bg-good/10 p-3 text-sm text-good">
                    {summary.suggested_action}
                  </div>
                </Section>
              ) : null}
            </TabsContent>

            <TabsContent value="entities" className="m-0 flex flex-col gap-3 p-4">
              <Section label="Key entities">
                {summary.key_entities.length > 0 ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    {summary.key_entities.map((entity, idx) => (
                      <div
                        key={idx}
                        className="rounded-md border border-border bg-muted/30 p-3 transition-colors hover:bg-muted/50"
                      >
                        <div className="text-sm font-semibold text-foreground">{entity.name}</div>
                        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                          {entity.role}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyMessage text="No entities identified on this page." />
                )}
              </Section>
            </TabsContent>

            <TabsContent value="timeline" className="m-0 flex flex-col gap-3 p-4">
              <Section label="Important dates">
                {summary.important_dates.length > 0 ? (
                  <ol className="relative ml-4 flex flex-col gap-3 border-l border-border pl-4">
                    {summary.important_dates.map((d, idx) => (
                      <li key={idx} className="relative">
                        <span
                          aria-hidden
                          className="absolute -left-[21px] top-2 h-2 w-2 rounded-full bg-primary"
                        />
                        <div className="rounded-md border border-border bg-muted/30 p-3">
                          <div className="text-sm font-semibold text-primary tabular-nums">
                            {d.date}
                          </div>
                          <div className="text-sm text-muted-foreground">{d.description}</div>
                        </div>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <EmptyMessage text="No specific dates identified on this page." />
                )}
              </Section>
            </TabsContent>

            <TabsContent value="flow" className="m-0 flex flex-col gap-3 p-4">
              <Section label="Procedural flow">
                <CaseFlowGraph
                  documentId={documentId}
                  currentPage={currentPage}
                  onNodePageJump={onJumpToPage}
                  compact
                />
              </Section>
            </TabsContent>
          </ScrollArea>
        </Tabs>
      ) : (
        <CardContent className="flex flex-1 flex-col gap-3 p-4">
          {loading ? (
            <>
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-20 w-full" />
            </>
          ) : error ? (
            <AiErrorBanner error={error} />
          ) : (
            <Alert>
              <FileText />
              <AlertTitle>No analysis yet</AlertTitle>
              <AlertDescription>
                Navigate pages to generate analysis. Ensure the PDF contains extractable text.
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      )}
    </Card>
  );
}

function ComplexityRow({ score }: { score: number }) {
  const tone = complexityTone(score);
  return (
    <Section label="Complexity score">
      <div className="flex items-center gap-3">
        <Progress
          value={(score / 10) * 100}
          indicatorClassName={tone.indicatorClass}
          className="flex-1"
        />
        <span className={cn("min-w-[44px] text-right text-sm font-semibold tabular-nums", tone.textClass)}>
          {score}/10
        </span>
      </div>
      <p className={cn("text-xs", tone.textClass)}>{tone.label} complexity</p>
    </Section>
  );
}

function Section({
  label,
  icon,
  tone,
  children,
}: {
  label: string;
  icon?: React.ReactNode;
  tone?: "good" | "destructive";
  children: React.ReactNode;
}) {
  const colour = tone === "good" ? "text-good" : tone === "destructive" ? "text-destructive" : "text-muted-foreground";
  return (
    <section className="flex flex-col gap-2">
      <h4 className={cn("flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide", colour)}>
        {icon}
        {label}
      </h4>
      {children}
    </section>
  );
}

function EmptyMessage({ text }: { text: string }) {
  return (
    <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
      {text}
    </p>
  );
}
