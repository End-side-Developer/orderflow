"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  FileText,
  GitBranch,
  Loader2,
  RefreshCw,
  Scale,
  Users,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { CaseFlowGraph } from "@/components/case-flow-graph";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  CaseDocumentSummaryData,
  CaseFlowData,
  DocumentSummaryDirective,
  DocumentSummaryEntity,
  DocumentSummaryFlowGraph,
  DocumentSummaryFlowNodeType,
  DocumentSummaryImportantDate,
  DocumentSummaryResponsibleDepartment,
  DocumentSummarySourceEvidence,
  PageSummaryRecord,
  generateCaseActionPlan,
  generateCaseSummary,
  getCaseSummary,
  listPageSummaries,
} from "@/lib/api/client";

type SummaryPanelProps = {
  documentId: string;
};

const CaseIncidenceMap = dynamic(
  () => import("@/components/case-incidence-map").then((mod) => mod.CaseIncidenceMap),
  {
    ssr: false,
    loading: () => <div className="p-4 text-sm text-muted-foreground">Loading case map...</div>,
  },
);

export function SummaryPanel({ documentId }: SummaryPanelProps) {
  const [summary, setSummary] = useState<CaseDocumentSummaryData | null>(null);
  const [pageSummaries, setPageSummaries] = useState<PageSummaryRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isGeneratingActionPlan, setIsGeneratingActionPlan] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const confidencePercent = useMemo(
    () => clampPercent((summary?.confidence ?? 0) * 100),
    [summary?.confidence],
  );
  const summaryFlowData = useMemo(
    () => toCaseFlowData(summary?.flow_graph ?? null, documentId),
    [documentId, summary?.flow_graph],
  );
  const mapAvailable = Boolean(summary?.map_data?.places && summary.map_data.places.length > 0);
  const needsHumanReview = confidencePercent < 70;

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    setActionMessage(null);

    void Promise.all([getCaseSummary(documentId), listPageSummaries(documentId)])
      .then(([summaryResponse, pageResponse]) => {
        if (cancelled) return;
        if (summaryResponse.ok) {
          setSummary(summaryResponse.data);
        } else {
          setError(summaryResponse.error.message);
        }
        setPageSummaries(pageResponse.ok ? pageResponse.data.items : []);
      })
      .catch((requestError) => {
        if (cancelled) return;
        setError(requestError instanceof Error ? requestError.message : "Could not load summary.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [documentId]);

  async function handleRegenerateSummary() {
    setIsRegenerating(true);
    setError(null);
    setActionMessage(null);
    setSummary(null);
    try {
      const response = await generateCaseSummary(documentId, { bypassCache: true });
      if (response.ok) {
        setActionMessage("Summary regeneration requested. It will appear automatically when ready.");
      } else {
        setError(response.error.message);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not request regeneration.");
    } finally {
      setIsRegenerating(false);
    }
  }

  // Poll for the full summary every 4 s while it hasn't arrived yet.
  // Stops automatically once summary is set or the component unmounts.
  useEffect(() => {
    if (isLoading || summary) return;

    let cancelled = false;
    const interval = setInterval(() => {
      void Promise.all([getCaseSummary(documentId), listPageSummaries(documentId)]).then(
        ([summaryResponse, pageResponse]) => {
          if (cancelled) return;
          if (summaryResponse.ok) {
            setSummary(summaryResponse.data);
            setError(null);
          }
          if (pageResponse.ok) {
            setPageSummaries(pageResponse.data.items);
          }
        },
      );
    }, 4000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [documentId, isLoading, summary]);

  async function handleGenerateActionPlan() {
    setIsGeneratingActionPlan(true);
    setError(null);
    setActionMessage(null);
    try {
      const response = await generateCaseActionPlan(documentId);
      if (response.ok) {
        setActionMessage("Action plan generation requested.");
      } else {
        setError(response.error.message);
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Could not request action plan.",
      );
    } finally {
      setIsGeneratingActionPlan(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex min-h-[200px] items-center justify-center p-6">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading full summary
        </div>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Full summary generating…</AlertTitle>
          <AlertDescription>
            {error ?? "The full judgment summary is not ready yet. Checking automatically every few seconds."}
          </AlertDescription>
        </Alert>

        {/* Show already-extracted page summaries while the full summary is being generated */}
        {pageSummaries.length > 0 && (
          <CollapsibleSection
            icon={<FileText className="h-4 w-4 text-muted-foreground" />}
            title="Page-wise summary"
            badge={
              <Badge variant="secondary" className="ml-1">
                {pageSummaries.length}
              </Badge>
            }
            defaultOpen
          >
            <PageWiseSummaryList pages={pageSummaries} />
          </CollapsibleSection>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-0">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Full judgment summary</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {summary.case_basics.case_number ?? summary.case_basics.case_type ?? "Case summary"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="secondary">{summary.ai_model ?? "summary model"}</Badge>
          <Badge variant={confidencePercent >= 70 ? "good" : "warn"}>
            {confidencePercent}% confidence
          </Badge>
          {needsHumanReview ? <Badge variant="warn">Needs human review</Badge> : null}
        </div>
      </div>

      <div className="flex flex-col gap-4 p-6">
        {error ? (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Request failed</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        {actionMessage ? (
          <Alert>
            <CheckCircle2 className="h-4 w-4" />
            <AlertTitle>Action plan queued</AlertTitle>
            <AlertDescription>{actionMessage}</AlertDescription>
          </Alert>
        ) : null}

        {/* Page-wise summaries */}
        <CollapsibleSection
          icon={<FileText className="h-4 w-4 text-muted-foreground" />}
          title="Page-wise summary"
          badge={
            <Badge variant="secondary" className="ml-1">
              {pageSummaries.length}
            </Badge>
          }
          defaultOpen
        >
          <PageWiseSummaryList pages={pageSummaries} />
        </CollapsibleSection>

        {/* Case basics */}
        <CollapsibleSection
          icon={<Scale className="h-4 w-4 text-muted-foreground" />}
          title="Case basics"
          defaultOpen
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Fact label="Court" value={summary.case_basics.court_name} />
            <Fact label="Case type" value={summary.case_basics.case_type} />
            <Fact label="Order date" value={summary.case_basics.order_date} />
            <Fact label="Judge" value={summary.case_basics.judge_name} />
            <Fact label="Petitioner" value={summary.case_basics.petitioner} />
            <Fact label="Respondent" value={summary.case_basics.respondent} />
            <Fact label="Department" value={summary.case_basics.department_involved} />
            <Fact label="Subject" value={summary.case_basics.main_subject} />
          </div>
        </CollapsibleSection>

        {/* Overview */}
        <CollapsibleSection
          icon={<FileText className="h-4 w-4 text-muted-foreground" />}
          title="Overview"
          defaultOpen={false}
        >
          <p className="whitespace-pre-wrap break-words text-sm leading-7 text-muted-foreground">
            {summary.overview}
          </p>
          <div className="mt-4">
            <div className="mb-1.5 flex items-center justify-between text-xs text-muted-foreground">
              <span>Summary confidence</span>
              <span>{confidencePercent}%</span>
            </div>
            <Progress value={confidencePercent} className="h-2" />
          </div>
        </CollapsibleSection>

        {/* Tabs */}
        <Tabs defaultValue="directives" className="w-full">
          <TabsList className="h-auto flex-wrap border border-border bg-muted">
            <TabsTrigger value="directives">Directives</TabsTrigger>
            <TabsTrigger value="dates">Dates</TabsTrigger>
            <TabsTrigger value="entities">Entities</TabsTrigger>
            <TabsTrigger value="departments">Departments</TabsTrigger>
            <TabsTrigger value="flow">Flow</TabsTrigger>
            {mapAvailable ? <TabsTrigger value="map">Map</TabsTrigger> : null}
          </TabsList>

          <TabsContent value="directives" className="mt-4">
            <DirectiveList directives={summary.key_directives} />
          </TabsContent>

          <TabsContent value="dates" className="mt-4">
            <DateList dates={summary.important_dates} />
          </TabsContent>

          <TabsContent value="entities" className="mt-4">
            <EntityList entities={summary.entities_involved} />
          </TabsContent>

          <TabsContent value="departments" className="mt-4">
            <DepartmentList departments={summary.responsible_departments} />
          </TabsContent>

          <TabsContent value="flow" className="mt-4">
            <FlowGraph graph={summary.flow_graph} visualData={summaryFlowData} />
          </TabsContent>

          {mapAvailable ? (
            <TabsContent value="map" className="mt-4">
              <div className="flex flex-col gap-2">
                <div className="overflow-hidden rounded-md border border-border">
                  <CaseIncidenceMap places={summary.map_data?.places ?? []} mode="flow" />
                </div>
                {summary.map_data?.reason ? (
                  <p className="text-xs text-muted-foreground">{summary.map_data.reason}</p>
                ) : null}
              </div>
            </TabsContent>
          ) : null}
        </Tabs>

        {!mapAvailable && summary.map_data?.reason ? (
          <p className="text-xs text-muted-foreground">{summary.map_data.reason}</p>
        ) : null}

        {/* Footer */}
        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-5">
          <Button size="sm" type="button" variant="outline" onClick={() => window.location.reload()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh summary
          </Button>
          <Button
            size="sm"
            type="button"
            variant="outline"
            onClick={() => void handleRegenerateSummary()}
            disabled={isRegenerating}
            title="Re-run AI extraction from scratch, bypassing the cached result"
          >
            {isRegenerating ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            Re-generate summary
          </Button>
          <Button
            size="sm"
            type="button"
            variant="good"
            className="ml-auto"
            onClick={() => void handleGenerateActionPlan()}
            disabled={isGeneratingActionPlan}
          >
            {isGeneratingActionPlan ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <ArrowRight className="mr-2 h-4 w-4" />
            )}
            Generate Action Plan
          </Button>
        </div>
      </div>
    </div>
  );
}

function CollapsibleSection({
  icon,
  title,
  badge,
  defaultOpen = true,
  children,
}: {
  icon: ReactNode;
  title: string;
  badge?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="rounded-md border border-border overflow-hidden"
    >
      <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-muted/50">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-sm font-semibold text-foreground">{title}</span>
          {badge}
        </div>
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="border-t border-border p-4">{children}</div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function PageSummaryCard({ page }: { page: PageSummaryRecord }) {
  const [open, setOpen] = useState(false);
  const confidence = page.confidence != null ? clampPercent(page.confidence * 100) : null;

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="rounded-md border border-border overflow-hidden"
    >
      <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-muted/50">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">Page {page.page_number}</Badge>
          <Badge variant={page.extraction_mode === "ai" ? "accent" : "secondary"}>
            {page.extraction_mode}
          </Badge>
          {confidence != null ? (
            <Badge variant={confidence >= 70 ? "good" : "warn"}>{confidence}%</Badge>
          ) : null}
          <span className="hidden text-xs text-muted-foreground sm:block line-clamp-1 max-w-[280px]">
            {page.summary?.slice(0, 80)}…
          </span>
        </div>
        <ChevronDown
          className={`ml-3 h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="border-t border-border p-4 flex flex-col gap-4">
          <p className="whitespace-pre-wrap break-words text-sm leading-7 text-muted-foreground">
            {page.summary}
          </p>
          {page.key_points.length > 0 ? (
            <ul className="flex flex-col gap-1.5 pl-4">
              {page.key_points.slice(0, 4).map((point, index) => (
                <li
                  key={`${point}-${index}`}
                  className="list-disc text-sm leading-6 text-muted-foreground"
                >
                  {point}
                </li>
              ))}
            </ul>
          ) : null}
          {page.important_highlights.length > 0 ? (
            <div className="flex flex-col gap-2">
              {page.important_highlights.slice(0, 3).map((highlight, index) => (
                <div key={`${highlight.text}-${index}`} className="rounded-md bg-muted p-3">
                  <div className="mb-1.5 flex flex-wrap gap-2">
                    <Badge variant={highlight.significance === "critical" ? "warn" : "secondary"}>
                      {highlight.significance}
                    </Badge>
                  </div>
                  <p className="break-words text-xs leading-5 text-muted-foreground">
                    {highlight.text}
                  </p>
                </div>
              ))}
            </div>
          ) : null}
          {page.entities.length > 0 || page.dates.length > 0 || page.directions.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-3">
              <MiniList
                title="Entities"
                items={page.entities.map((e) => e.name)}
                empty="No entities cached."
              />
              <MiniList
                title="Dates"
                items={page.dates.map((d) => d.date_text)}
                empty="No dates cached."
              />
              <MiniList
                title="Directions"
                items={page.directions.map((d) => d.direction_text)}
                empty="No directions cached."
              />
            </div>
          ) : null}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function PageWiseSummaryList({ pages }: { pages: PageSummaryRecord[] }) {
  if (pages.length === 0) {
    return <EmptyPanel label="No cached page-wise summaries found yet." />;
  }

  return (
    <div className="flex flex-col gap-2">
      {[...pages]
        .sort((a, b) => a.page_number - b.page_number)
        .map((page) => (
          <PageSummaryCard key={page.id} page={page} />
        ))}
    </div>
  );
}

function MiniList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  const visibleItems = items.filter(Boolean).slice(0, 3);
  return (
    <div className="rounded-md bg-muted p-3">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      {visibleItems.length > 0 ? (
        <ul className="flex flex-col gap-1">
          {visibleItems.map((item, index) => (
            <li key={`${item}-${index}`} className="line-clamp-2 text-xs leading-5 text-foreground">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">{empty}</p>
      )}
    </div>
  );
}

function DirectiveList({ directives }: { directives: DocumentSummaryDirective[] }) {
  if (directives.length === 0) return <EmptyPanel label="No directives found." />;
  return (
    <div className="flex flex-col gap-3">
      {directives.map((directive, index) => (
        <div
          key={`${directive.direction_text}-${index}`}
          className="rounded-md border border-border p-4"
        >
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge variant={directive.directive_kind === "mandatory" ? "warn" : "secondary"}>
              {directive.directive_kind}
            </Badge>
            <Badge variant={directive.compliance_required === "yes" ? "good" : "muted"}>
              compliance {directive.compliance_required}
            </Badge>
            {directive.source_page_number ? (
              <Badge variant="outline">Page {directive.source_page_number}</Badge>
            ) : null}
          </div>
          <p className="break-words text-sm leading-6 text-foreground">
            {directive.direction_text}
          </p>
          <EvidenceList evidence={directive.source_evidence} />
        </div>
      ))}
    </div>
  );
}

function DateList({ dates }: { dates: DocumentSummaryImportantDate[] }) {
  if (dates.length === 0) return <EmptyPanel label="No dates found." />;
  return (
    <div className="flex flex-col gap-3">
      {dates.map((date, index) => (
        <div key={`${date.label}-${index}`} className="rounded-md border border-border p-4">
          <div className="flex items-start gap-3">
            <CalendarDays className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="break-words text-sm font-semibold text-foreground">{date.label}</p>
                {date.is_inferred ? <Badge variant="warn">inferred</Badge> : null}
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {date.date_text ?? date.source ?? "-"}
              </p>
              <EvidenceList evidence={date.source_evidence} />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function EntityList({ entities }: { entities: DocumentSummaryEntity[] }) {
  if (entities.length === 0) return <EmptyPanel label="No entities found." />;
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {entities.map((entity, index) => (
        <div key={`${entity.name}-${index}`} className="rounded-md border border-border p-4">
          <div className="mb-2 flex items-center gap-2">
            <Users className="h-4 w-4 shrink-0 text-muted-foreground" />
            <p className="break-words text-sm font-semibold text-foreground">{entity.name}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {entity.entity_type ? <Badge variant="secondary">{entity.entity_type}</Badge> : null}
            {entity.role ? <Badge variant="outline">{entity.role}</Badge> : null}
            {entity.source_page_number ? (
              <Badge variant="muted">Page {entity.source_page_number}</Badge>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}

function DepartmentList({ departments }: { departments: DocumentSummaryResponsibleDepartment[] }) {
  if (departments.length === 0) {
    return <EmptyPanel label="No departments found." />;
  }
  return (
    <div className="flex flex-col gap-3">
      {departments.map((department, index) => (
        <div
          key={`${department.primary_department ?? "department"}-${index}`}
          className="rounded-md border border-border p-4"
        >
          <div className="mb-2 flex items-center gap-2">
            <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" />
            <p className="break-words text-sm font-semibold text-foreground">
              {department.primary_department ?? "Unassigned"}
            </p>
          </div>
          {department.reason ? (
            <p className="mb-3 break-words text-sm leading-6 text-muted-foreground">
              {department.reason}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {department.legal_department_role ? (
              <Badge variant="secondary">{department.legal_department_role}</Badge>
            ) : null}
            {department.supporting_departments.map((item) => (
              <Badge key={item} variant="outline">
                {item}
              </Badge>
            ))}
          </div>
          <EvidenceList evidence={department.source_evidence} />
        </div>
      ))}
    </div>
  );
}

function FlowGraph({
  graph,
  visualData,
}: {
  graph: DocumentSummaryFlowGraph | null;
  visualData: CaseFlowData | null;
}) {
  if (!graph || graph.nodes.length === 0) {
    return <EmptyPanel label="No flow graph found." />;
  }
  return (
    <div className="flex flex-col gap-4">
      <CaseFlowGraph data={visualData} compact />
      {graph.narrative_steps.length > 0 ? (
        <div className="flex flex-col gap-2">
          {graph.narrative_steps.map((step, index) => (
            <div key={`${step}-${index}`} className="flex gap-3 rounded-md bg-muted p-3">
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
                {index + 1}
              </div>
              <p className="break-words text-sm leading-6 text-foreground">{step}</p>
            </div>
          ))}
        </div>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        {graph.nodes.map((node) => (
          <div key={node.id} className="rounded-md border border-border p-4">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <GitBranch className="h-4 w-4 text-muted-foreground" />
              <Badge variant="secondary">{node.node_type}</Badge>
              {node.page_ref ? <Badge variant="outline">Page {node.page_ref}</Badge> : null}
            </div>
            <p className="break-words text-sm font-semibold text-foreground">{node.label}</p>
            {node.detail ? (
              <p className="mt-2 break-words text-sm leading-6 text-muted-foreground">
                {node.detail}
              </p>
            ) : null}
          </div>
        ))}
      </div>
      {graph.edges.length > 0 ? (
        <div className="rounded-md border border-border p-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Flow links
          </p>
          <div className="flex flex-wrap gap-2">
            {graph.edges.map((edge) => (
              <Badge key={edge.id} variant="outline">
                {edge.source} → {edge.target}: {edge.relation}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-md bg-muted px-3 py-2.5">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 break-words text-sm font-semibold text-foreground">{value || "-"}</div>
    </div>
  );
}

function EvidenceList({ evidence }: { evidence: DocumentSummarySourceEvidence[] }) {
  const visibleEvidence = evidence.filter((item) => item.page_number || item.source_excerpt);
  if (visibleEvidence.length === 0) return null;
  return (
    <div className="mt-3 flex flex-col gap-2">
      {visibleEvidence.slice(0, 2).map((item, index) => (
        <div
          key={`${item.page_number ?? "source"}-${index}`}
          className="rounded-md bg-muted p-3"
        >
          <div className="mb-1.5 flex flex-wrap gap-2">
            {item.page_number ? <Badge variant="outline">Page {item.page_number}</Badge> : null}
            {item.confidence != null ? (
              <Badge variant="muted">{clampPercent(item.confidence * 100)}%</Badge>
            ) : null}
          </div>
          {item.source_excerpt ? (
            <p className="line-clamp-3 break-words text-xs leading-5 text-muted-foreground">
              {item.source_excerpt}
            </p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function EmptyPanel({ label }: { label: string }) {
  return (
    <div className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
      {label}
    </div>
  );
}

function toCaseFlowData(
  graph: DocumentSummaryFlowGraph | null,
  documentId: string,
): CaseFlowData | null {
  if (!graph || graph.nodes.length === 0) return null;
  return {
    document_id: graph.document_id || documentId,
    nodes: graph.nodes.map((node) => ({
      id: node.id,
      node_type: coerceFlowNodeType(node.node_type),
      label: node.label,
      detail: node.detail,
      page_ref: node.page_ref,
    })),
    edges: graph.edges,
  };
}

function coerceFlowNodeType(nodeType: string): DocumentSummaryFlowNodeType {
  if (
    nodeType === "party" ||
    nodeType === "event" ||
    nodeType === "order" ||
    nodeType === "obligation"
  ) {
    return nodeType;
  }
  return "obligation";
}

function clampPercent(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, Math.round(value)));
}
