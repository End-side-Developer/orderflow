"use client";

import Link from "next/link";
import type { FormEvent } from "react";
import { useCallback, useEffect, useMemo, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  Download,
  RefreshCw,
} from "lucide-react";

import { PageHeader } from "@/components/app/page-header";
import { KpiTile } from "@/components/app/kpi-tile";
import { StatusPill } from "@/components/app/status-pill";
import { ConfidenceMeter } from "@/components/app/confidence-meter";
import { EmptyState } from "@/components/app/empty-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { RiskScoreGauge } from "@/components/risk-score-gauge";
import { WhyPanel } from "@/components/why-panel";
import {
  downloadActionPlan,
  getDocumentWorkbench,
  getObligationAuditTrail,
  listAllObligations,
  listClauses,
  listDocuments,
  listObligations,
  updateObligation,
  type ExportLanguage,
  type ObligationAuditEvent,
  type ClauseRecord,
  type DocumentRecord,
  type ObligationRecord,
  type WorkbenchDocumentData,
} from "@/lib/api/client";
import { cn } from "@/lib/utils";

type LoadState = "idle" | "loading" | "success" | "error";
const OBLIGATION_POLL_MS = 15000;
const SIMILAR_CASE_LIMIT = 5;

const SIMILARITY_STOPWORDS = new Set([
  "the",
  "and",
  "for",
  "with",
  "this",
  "that",
  "from",
  "into",
  "shall",
  "must",
  "case",
  "court",
  "order",
  "document",
  "within",
  "under",
  "against",
  "between",
]);

type BoardColumns = {
  pending_review: ObligationRecord[];
  approved: ObligationRecord[];
  rejected: ObligationRecord[];
};

type RelatedCaseRecommendation = {
  documentId: string;
  similarityScore: number;
  overlapCount: number;
  rationaleTags: string[];
  sampleTitles: string[];
  totalObligations: number;
  openEscalations: number;
  approvedCount: number;
  completedCount: number;
};

const exportLanguageOptions: Array<{ value: ExportLanguage; label: string }> = [
  { value: "en", label: "English" },
  { value: "hi", label: "Hindi" },
  { value: "ta", label: "Tamil" },
  { value: "te", label: "Telugu" },
  { value: "kn", label: "Kannada" },
  { value: "ml", label: "Malayalam" },
  { value: "mr", label: "Marathi" },
];

function emptyBoardColumns(): BoardColumns {
  return { pending_review: [], approved: [], rejected: [] };
}

function formatDueDate(value: string | null): string {
  if (!value) return "No deadline";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString();
}

function formatDateTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function formatEscalationReason(reason: string): string {
  return reason.replaceAll("_", " ");
}

function rankEscalationLevel(level: "none" | "watch" | "escalated" | "critical"): number {
  return { none: 0, watch: 1, escalated: 2, critical: 3 }[level];
}

function formatAuditPayload(payload: Record<string, unknown> | null): string | null {
  if (!payload) return null;
  const fields = Object.entries(payload)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => `${key}: ${String(value)}`);
  return fields.length === 0 ? null : fields.join(" · ");
}

function formatAuditAction(action: string): string {
  return action.replaceAll(".", " ");
}

function tokenizeSimilarityText(value: string | null | undefined): string[] {
  if (!value) return [];
  const cleaned = value.toLowerCase().replace(/[^a-z0-9\s]/g, " ");
  return cleaned
    .split(/\s+/)
    .filter((token) => token.length >= 4 && !SIMILARITY_STOPWORDS.has(token));
}

function buildRelatedCaseRecommendations(
  activeDocumentId: string,
  activeItems: ObligationRecord[],
  allItems: ObligationRecord[],
): RelatedCaseRecommendation[] {
  if (!activeDocumentId || activeItems.length === 0 || allItems.length === 0) return [];
  const activeTokens = new Set<string>();
  const activeOwners = new Set<string>();
  const activePriorities = new Set<string>();
  for (const item of activeItems) {
    for (const token of tokenizeSimilarityText(`${item.title} ${item.description ?? ""}`)) {
      activeTokens.add(token);
    }
    if (item.owner_hint) activeOwners.add(item.owner_hint.trim().toLowerCase());
    activePriorities.add(item.priority);
  }
  if (activeTokens.size === 0) return [];

  const grouped = new Map<string, ObligationRecord[]>();
  for (const item of allItems) {
    if (!item.document_id || item.document_id === activeDocumentId) continue;
    const existing = grouped.get(item.document_id);
    if (existing) existing.push(item);
    else grouped.set(item.document_id, [item]);
  }

  const recommendations: RelatedCaseRecommendation[] = [];
  for (const [documentId, items] of grouped.entries()) {
    const candidateTokens = new Set<string>();
    const overlapTokens = new Set<string>();
    let ownerOverlap = false;
    let priorityOverlap = false;
    let openEscalations = 0;
    let approvedCount = 0;
    let completedCount = 0;
    for (const item of items) {
      const tokens = tokenizeSimilarityText(`${item.title} ${item.description ?? ""}`);
      for (const token of tokens) {
        candidateTokens.add(token);
        if (activeTokens.has(token)) overlapTokens.add(token);
      }
      if (item.escalation?.open) openEscalations += 1;
      if (item.review_state === "approved") approvedCount += 1;
      if (item.status === "completed") completedCount += 1;
      if (item.owner_hint && activeOwners.has(item.owner_hint.trim().toLowerCase())) {
        ownerOverlap = true;
      }
      if (activePriorities.has(item.priority)) priorityOverlap = true;
    }
    if (overlapTokens.size === 0) continue;
    const denominator = Math.sqrt(activeTokens.size * Math.max(candidateTokens.size, 1));
    const lexicalSimilarity = overlapTokens.size / (denominator || 1);
    const similarityScore =
      lexicalSimilarity + (ownerOverlap ? 0.2 : 0) + (priorityOverlap ? 0.1 : 0);
    const rationaleTags = [
      ...Array.from(overlapTokens)
        .slice(0, 3)
        .map((token) => `pattern:${token}`),
      ownerOverlap ? "owner-overlap" : null,
      priorityOverlap ? "priority-overlap" : null,
    ].filter((value): value is string => Boolean(value));
    recommendations.push({
      documentId,
      similarityScore,
      overlapCount: overlapTokens.size,
      rationaleTags,
      sampleTitles: items.slice(0, 2).map((item) => item.title),
      totalObligations: items.length,
      openEscalations,
      approvedCount,
      completedCount,
    });
  }
  recommendations.sort((left, right) => {
    const scoreDelta = right.similarityScore - left.similarityScore;
    return scoreDelta !== 0 ? scoreDelta : right.overlapCount - left.overlapCount;
  });
  return recommendations.slice(0, SIMILAR_CASE_LIMIT);
}

import { InfoHint } from "@/components/info-hint";

export default function ObligationsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4">
          <Skeleton className="h-12 w-full max-w-md" />
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      }
    >
      <ObligationsContent />
    </Suspense>
  );
}

function ObligationsContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const documentId = searchParams.get("document_id")?.trim() ?? "";
  const workflowRunId = searchParams.get("workflow_run_id")?.trim() ?? "";

  useEffect(() => {
    if (!documentId && typeof window !== "undefined") {
      const savedDocumentId = window.localStorage.getItem("orderflow:current_document_id");
      if (savedDocumentId) {
        router.replace(`/obligations?document_id=${encodeURIComponent(savedDocumentId)}`);
      }
    }
  }, [documentId, router]);

  const [state, setState] = useState<LoadState>("idle");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [warningText, setWarningText] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [exportLanguage, setExportLanguage] = useState<ExportLanguage>("en");
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [items, setItems] = useState<ObligationRecord[]>([]);
  const [allObligations, setAllObligations] = useState<ObligationRecord[]>([]);
  const [allDocuments, setAllDocuments] = useState<DocumentRecord[]>([]);
  const [relatedCasesState, setRelatedCasesState] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [relatedCasesError, setRelatedCasesError] = useState<string | null>(null);
  const [documentWorkbench, setDocumentWorkbench] = useState<WorkbenchDocumentData | null>(null);
  const [activeTab, setActiveTab] = useState<"pending_review" | "approved" | "rejected">(
    "pending_review",
  );
  const [openObligationId, setOpenObligationId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load(silent: boolean): Promise<void> {
      if (!documentId) {
        setItems([]);
        setErrorText(null);
        setWarningText(null);
        setLastRefreshedAt(null);
        setState("idle");
        return;
      }
      if (!silent) {
        setState("loading");
        setErrorText(null);
      }
      const result = await listObligations(documentId);
      if (cancelled) return;
      if (!result.ok) {
        if (silent) {
          setWarningText(`Auto-refresh warning: ${result.error.message}`);
          return;
        }
        setState("error");
        setWarningText(null);
        setErrorText(result.error.message);
        setItems([]);
        return;
      }
      setState("success");
      setWarningText(null);
      setItems(result.data.items);
      setLastRefreshedAt(new Date().toISOString());
    }
    void load(false);
    if (!documentId) {
      return () => {
        cancelled = true;
      };
    }
    const intervalId = window.setInterval(() => {
      void load(true);
    }, OBLIGATION_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [documentId, refreshTick]);

  useEffect(() => {
    let cancelled = false;
    async function loadAll(): Promise<void> {
      if (!documentId) {
        setAllObligations([]);
        setRelatedCasesState("idle");
        setRelatedCasesError(null);
        return;
      }
      setRelatedCasesState("loading");
      setRelatedCasesError(null);
      const result = await listAllObligations();
      if (cancelled) return;
      if (!result.ok) {
        setRelatedCasesState("error");
        setRelatedCasesError(result.error.message);
        setAllObligations([]);
        return;
      }
      setAllObligations(result.data.items);
      setRelatedCasesState("ready");
    }
    void loadAll();
    return () => {
      cancelled = true;
    };
  }, [documentId, refreshTick]);

  useEffect(() => {
    let cancelled = false;
    async function loadAllDocuments(): Promise<void> {
      const result = await listDocuments();
      if (cancelled) return;
      if (result.ok) setAllDocuments(result.data.items);
    }
    void loadAllDocuments();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadDocumentWorkbench(): Promise<void> {
      if (!documentId) {
        setDocumentWorkbench(null);
        return;
      }
      const result = await getDocumentWorkbench(documentId);
      if (cancelled || !result.ok) return;
      setDocumentWorkbench(result.data);
    }
    void loadDocumentWorkbench();
    return () => {
      cancelled = true;
    };
  }, [documentId, refreshTick]);

  const columns = useMemo(() => {
    const grouped = emptyBoardColumns();
    for (const item of items) grouped[item.review_state].push(item);
    return grouped;
  }, [items]);

  const openEscalations = useMemo(() => {
    return items
      .filter((item) => item.escalation?.open)
      .slice()
      .sort((left, right) => {
        const ll = left.escalation,
          rl = right.escalation;
        if (!ll || !rl) return 0;
        const levelDelta = rankEscalationLevel(rl.level) - rankEscalationLevel(ll.level);
        if (levelDelta !== 0) return levelDelta;
        const ld =
          typeof ll.days_until_due === "number" ? ll.days_until_due : Number.POSITIVE_INFINITY;
        const rd =
          typeof rl.days_until_due === "number" ? rl.days_until_due : Number.POSITIVE_INFINITY;
        return ld - rd;
      });
  }, [items]);

  const criticalEscalations = useMemo(
    () => openEscalations.filter((item) => item.escalation?.level === "critical").length,
    [openEscalations],
  );

  const relatedCases = useMemo(
    () => buildRelatedCaseRecommendations(documentId, items, allObligations),
    [allObligations, documentId, items],
  );

  const serverRelatedCases = documentWorkbench?.related_cases ?? [];

  const currentIndex = useMemo(() => {
    return allDocuments.findIndex((doc) => doc.id === documentId);
  }, [allDocuments, documentId]);

  const previousDocument = currentIndex > 0 ? allDocuments[currentIndex - 1] : null;
  const nextDocument =
    currentIndex >= 0 && currentIndex < allDocuments.length - 1
      ? allDocuments[currentIndex + 1]
      : null;

  useEffect(() => {
    if (documentId && typeof window !== "undefined") {
      window.localStorage.setItem("orderflow:current_document_id", documentId);
    }
  }, [documentId]);

  const handleObligationUpdated = useCallback((updated: ObligationRecord) => {
    setItems((previous) => previous.map((entry) => (entry.id === updated.id ? updated : entry)));
  }, []);

  const requestRefresh = useCallback(() => {
    setRefreshTick((previous) => previous + 1);
  }, []);

  async function handleExportActionPlan(): Promise<void> {
    if (!documentId) return;
    setIsExporting(true);
    setExportError(null);
    try {
      const result = await downloadActionPlan(documentId, exportLanguage, "markdown");
      const objectUrl = URL.createObjectURL(result.blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = result.fileName ?? `action-plan-${documentId}-${exportLanguage}.md`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "Action plan export failed");
    } finally {
      setIsExporting(false);
    }
  }

  const openObligation = items.find((item) => item.id === openObligationId) ?? null;

  if (!documentId) {
    return (
      <EmptyState
        title="No document selected"
        message="Open Verify with a document id, or upload a new judgment to begin."
        actionHref="/upload"
        actionLabel="Go to Intake"
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={
          <span className="flex items-center gap-1.5">
            Court duties <InfoHint glossaryKey="obligations" />
          </span>
        }
        title="Approve, reject, and close court duties with evidence"
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs">{documentId.slice(0, 8)}</span>
            {documentWorkbench ? (
              <Badge variant="muted">
                Stage: {documentWorkbench.document.stage.replaceAll("_", " ")}
              </Badge>
            ) : null}
            {documentWorkbench ? <span>Next: {documentWorkbench.document.next_action}</span> : null}
          </span>
        }
        actions={
          <>
            {previousDocument ? (
              <Button asChild variant="outline" size="sm">
                <Link href={`/obligations?document_id=${encodeURIComponent(previousDocument.id)}`}>
                  <ArrowLeft />
                  Previous
                </Link>
              </Button>
            ) : null}
            {nextDocument ? (
              <Button asChild variant="outline" size="sm">
                <Link href={`/obligations?document_id=${encodeURIComponent(nextDocument.id)}`}>
                  Next
                  <ArrowRight />
                </Link>
              </Button>
            ) : null}
          </>
        }
      />

      {/* Action plan export */}
      <Card>
        <CardContent className="flex flex-col items-end gap-3 p-4 sm:flex-row">
          <div className="flex-1">
            <Label htmlFor="export_language" className="mb-1 block">
              Action plan language
            </Label>
            <Select
              value={exportLanguage}
              onValueChange={(value) => setExportLanguage(value as ExportLanguage)}
            >
              <SelectTrigger id="export_language" className="w-full max-w-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {exportLanguageOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button onClick={() => void handleExportActionPlan()} disabled={isExporting}>
            <Download />
            {isExporting ? "Preparing…" : "Download action plan"}
          </Button>
          <Button variant="outline" size="icon" onClick={requestRefresh} aria-label="Refresh">
            <RefreshCw />
          </Button>
        </CardContent>
        {exportError ? (
          <CardContent className="pt-0">
            <p className="text-sm text-destructive">{exportError}</p>
          </CardContent>
        ) : null}
      </Card>

      {state === "loading" ? (
        <section className="grid gap-3 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </section>
      ) : null}

      {state === "error" ? (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>Could not load obligations</AlertTitle>
          <AlertDescription>{errorText}</AlertDescription>
        </Alert>
      ) : null}

      {state === "success" ? (
        <>
          {warningText ? (
            <Alert variant="warn">
              <AlertTriangle />
              <AlertTitle>Auto-refresh warning</AlertTitle>
              <AlertDescription>{warningText}</AlertDescription>
            </Alert>
          ) : null}

          <section className="grid gap-3 md:grid-cols-3">
            <KpiTile
              label="Total obligations"
              value={items.length}
              hint="Loaded for this document"
            />
            <KpiTile
              label="Open escalations"
              value={openEscalations.length}
              hint="Escalation signal is open"
              tone={openEscalations.length > 0 ? "warn" : "default"}
            />
            <KpiTile
              label="Critical escalations"
              value={criticalEscalations}
              hint={lastRefreshedAt ? `Refreshed ${formatDateTime(lastRefreshedAt)}` : "n/a"}
              tone={criticalEscalations > 0 ? "destructive" : "default"}
            />
          </section>

          {openEscalations.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Escalation queue</CardTitle>
                <CardDescription>Highest pressure items first.</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {openEscalations.map((item) => (
                  <div
                    key={`escalation-${item.id}`}
                    className="flex flex-col gap-2 rounded-md border border-border p-3 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="flex flex-col gap-1">
                      <span className="text-sm font-semibold text-foreground">{item.title}</span>
                      <span className="text-xs text-muted-foreground">
                        Due: {formatDueDate(item.due_date)} · Review:{" "}
                        {item.review_state.replace("_", " ")}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusPill kind="escalation" value={item.escalation?.level ?? "none"} />
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setOpenObligationId(item.id)}
                      >
                        Open
                      </Button>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {serverRelatedCases.length > 0 ||
          relatedCases.length > 0 ||
          relatedCasesState === "loading" ? (
            <Collapsible defaultOpen={false}>
              <Card>
                <CardHeader className="pb-3">
                  <CollapsibleTrigger asChild>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between text-left"
                    >
                      <div>
                        <CardTitle className="text-base">Related prior cases (advisory)</CardTitle>
                        <CardDescription>
                          Recommendations are advisory only. They do not auto-approve or auto-close.
                        </CardDescription>
                      </div>
                      <ChevronDown className="h-4 w-4 text-muted-foreground" />
                    </button>
                  </CollapsibleTrigger>
                </CardHeader>
                <CollapsibleContent>
                  <CardContent className="flex flex-col gap-2">
                    {relatedCasesState === "loading" && serverRelatedCases.length === 0 ? (
                      <Skeleton className="h-16 w-full" />
                    ) : null}
                    {relatedCasesState === "error" && serverRelatedCases.length === 0 ? (
                      <p className="text-sm text-destructive">
                        Related-case lookup warning: {relatedCasesError}
                      </p>
                    ) : null}
                    {serverRelatedCases.length > 0
                      ? serverRelatedCases.map((caseItem) => (
                          <RelatedCaseRow
                            key={caseItem.document_id}
                            href={`/obligations?document_id=${encodeURIComponent(caseItem.document_id)}`}
                            title={caseItem.source_file_name}
                            similarity={caseItem.similarity_score}
                            overlap={caseItem.overlap_count}
                            tags={caseItem.rationale_tags}
                            sample={caseItem.sample_titles}
                            footer={
                              caseItem.open_escalations > 0 ? (
                                <StatusPill kind="pressure" value={caseItem.pressure_level} />
                              ) : null
                            }
                            origin="server ranked"
                          />
                        ))
                      : relatedCases.map((caseItem) => (
                          <RelatedCaseRow
                            key={caseItem.documentId}
                            href={`/obligations?document_id=${encodeURIComponent(caseItem.documentId)}`}
                            title={`Document ${caseItem.documentId.slice(0, 8)}`}
                            similarity={caseItem.similarityScore}
                            overlap={caseItem.overlapCount}
                            tags={caseItem.rationaleTags}
                            sample={caseItem.sampleTitles}
                            footer={
                              caseItem.openEscalations > 0 ? (
                                <Badge variant="warn">
                                  {caseItem.openEscalations} open escalations
                                </Badge>
                              ) : null
                            }
                            origin="local fallback"
                          />
                        ))}
                  </CardContent>
                </CollapsibleContent>
              </Card>
            </Collapsible>
          ) : null}

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Obligations</CardTitle>
              <CardDescription>
                Click any row to open it. Approve and reject from inside the panel.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)}>
                <TabsList className="w-full justify-start">
                  <TabsTrigger value="pending_review" className="flex-1 sm:flex-none">
                    Pending review
                    <Badge variant="warn" className="ml-2">
                      {columns.pending_review.length}
                    </Badge>
                  </TabsTrigger>
                  <TabsTrigger value="approved" className="flex-1 sm:flex-none">
                    Approved
                    <Badge variant="good" className="ml-2">
                      {columns.approved.length}
                    </Badge>
                  </TabsTrigger>
                  <TabsTrigger value="rejected" className="flex-1 sm:flex-none">
                    Rejected
                    <Badge variant="destructive" className="ml-2">
                      {columns.rejected.length}
                    </Badge>
                  </TabsTrigger>
                </TabsList>
                {(["pending_review", "approved", "rejected"] as const).map((tab) => (
                  <TabsContent key={tab} value={tab} className="flex flex-col gap-2">
                    {columns[tab].length === 0 ? (
                      <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
                        Nothing in this state.
                      </p>
                    ) : (
                      columns[tab].map((item) => (
                        <ObligationListRow
                          key={item.id}
                          item={item}
                          onOpen={() => setOpenObligationId(item.id)}
                        />
                      ))
                    )}
                  </TabsContent>
                ))}
              </Tabs>
            </CardContent>
          </Card>
        </>
      ) : null}

      <ObligationDetailSheet
        obligation={openObligation}
        documentId={documentId}
        open={Boolean(openObligation)}
        onOpenChange={(next) => {
          if (!next) setOpenObligationId(null);
        }}
        onObligationUpdated={handleObligationUpdated}
        onRefreshRequested={requestRefresh}
      />
    </div>
  );
}

function ObligationListRow({ item, onOpen }: { item: ObligationRecord; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        "group flex w-full flex-col gap-1.5 rounded-md border border-border bg-card px-4 py-3 text-left transition-colors hover:border-primary/40 hover:bg-secondary/40",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-foreground">{item.title}</span>
        <StatusPill kind="priority" value={item.priority} />
        {item.escalation?.open ? (
          <StatusPill kind="escalation" value={item.escalation.level} />
        ) : null}
        <Badge variant="muted">{item.status}</Badge>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
        <span>
          Owner: <span className="text-foreground">{item.owner_hint ?? "Unresolved"}</span> · Due:{" "}
          <span className="text-foreground">{formatDueDate(item.due_date)}</span>
        </span>
        <ConfidenceMeter
          value={typeof item.confidence === "number" ? item.confidence : 0}
          compact
        />
      </div>
    </button>
  );
}

function ObligationDetailSheet({
  obligation,
  documentId,
  open,
  onOpenChange,
  onObligationUpdated,
  onRefreshRequested,
}: {
  obligation: ObligationRecord | null;
  documentId: string;
  open: boolean;
  onOpenChange: (next: boolean) => void;
  onObligationUpdated: (item: ObligationRecord) => void;
  onRefreshRequested: () => void;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent>
        {obligation ? (
          <ObligationDetail
            key={obligation.id}
            item={obligation}
            documentId={documentId}
            onObligationUpdated={onObligationUpdated}
            onRefreshRequested={onRefreshRequested}
          />
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function ObligationDetail({
  item,
  documentId,
  onObligationUpdated,
  onRefreshRequested,
}: {
  item: ObligationRecord;
  documentId: string;
  onObligationUpdated: (item: ObligationRecord) => void;
  onRefreshRequested: () => void;
}) {
  const [actionState, setActionState] = useState<"idle" | "saving" | "error">("idle");
  const [actionError, setActionError] = useState<string | null>(null);

  const [citationState, setCitationState] = useState<"idle" | "loading" | "ready" | "error">(
    "idle",
  );
  const [citationError, setCitationError] = useState<string | null>(null);
  const [citationItems, setCitationItems] = useState<ClauseRecord[]>([]);

  const [auditState, setAuditState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditItems, setAuditItems] = useState<ObligationAuditEvent[]>([]);

  const [evidenceSummary, setEvidenceSummary] = useState("");
  const [evidenceDate, setEvidenceDate] = useState("");
  const [evidenceSourceDocumentId, setEvidenceSourceDocumentId] = useState(documentId);
  const [completionState, setCompletionState] = useState<"idle" | "saving" | "error">("idle");
  const [completionError, setCompletionError] = useState<string | null>(null);

  async function runReviewerAction(reviewState: "approved" | "rejected"): Promise<void> {
    setActionState("saving");
    setActionError(null);
    const nextStatus = reviewState === "approved" ? "active" : item.status;
    const result = await updateObligation(item.id, {
      review_state: reviewState,
      status: nextStatus,
    });
    if (!result.ok) {
      setActionState("error");
      setActionError(result.error.message);
      return;
    }
    onObligationUpdated(result.data);
    onRefreshRequested();
    setActionState("idle");
  }

  async function reassignOwner(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const ownerHint = String(formData.get("owner_hint") ?? "").trim();
    if (!ownerHint) return;
    setActionState("saving");
    setActionError(null);
    const result = await updateObligation(item.id, { owner_hint: ownerHint });
    if (!result.ok) {
      setActionState("error");
      setActionError(result.error.message);
      return;
    }
    onObligationUpdated(result.data);
    onRefreshRequested();
    setActionState("idle");
  }

  async function loadCitationDetails(): Promise<void> {
    if (!documentId || !item.citation?.clause_span) return;
    setCitationState("loading");
    setCitationError(null);
    const result = await listClauses(documentId, { clauseSpan: item.citation.clause_span });
    if (!result.ok) {
      setCitationState("error");
      setCitationError(result.error.message);
      setCitationItems([]);
      return;
    }
    setCitationState("ready");
    setCitationItems(result.data.items);
  }

  async function loadAuditTrail(): Promise<void> {
    if (auditState === "ready" || auditState === "loading") return;
    setAuditState("loading");
    setAuditError(null);
    const result = await getObligationAuditTrail(item.id);
    if (!result.ok) {
      setAuditState("error");
      setAuditError(result.error.message);
      setAuditItems([]);
      return;
    }
    setAuditState("ready");
    setAuditItems(result.data.items);
  }

  const completionVerification = useMemo(() => {
    const summary = evidenceSummary.trim().toLowerCase();
    const evidenceTokens = tokenizeSimilarityText(summary);
    const obligationTokens = new Set(
      tokenizeSimilarityText(`${item.title} ${item.description ?? ""}`),
    );
    let overlapCount = 0;
    for (const token of evidenceTokens) {
      if (obligationTokens.has(token)) overlapCount += 1;
    }
    const minimumOverlap = obligationTokens.size >= 4 ? 2 : 1;
    const relevancePass =
      summary.length >= 20 && (obligationTokens.size === 0 || overlapCount >= minimumOverlap);
    const parsedDate = evidenceDate ? new Date(evidenceDate) : null;
    const now = new Date();
    const dateValidityPass =
      Boolean(parsedDate) &&
      parsedDate !== null &&
      !Number.isNaN(parsedDate.getTime()) &&
      parsedDate.getTime() <= now.getTime();
    const sourceConsistencyPass = evidenceSourceDocumentId.trim() === item.document_id;
    const allChecksPass = relevancePass && dateValidityPass && sourceConsistencyPass;
    return { relevancePass, dateValidityPass, sourceConsistencyPass, overlapCount, allChecksPass };
  }, [
    evidenceDate,
    evidenceSourceDocumentId,
    evidenceSummary,
    item.description,
    item.document_id,
    item.title,
  ]);

  const completionLockedByReview = item.review_state !== "approved";
  const completionLockedByStatus = item.status === "completed" || item.status === "cancelled";
  const canMarkCompleted =
    !completionLockedByReview &&
    !completionLockedByStatus &&
    completionVerification.allChecksPass &&
    completionState !== "saving";

  async function markCompletedWithVerification(): Promise<void> {
    if (!canMarkCompleted) return;
    setCompletionState("saving");
    setCompletionError(null);
    const proofTimestamp = evidenceDate
      ? new Date(`${evidenceDate}T12:00:00Z`).toISOString()
      : undefined;
    const result = await updateObligation(item.id, {
      status: "completed",
      proof: { proof_text: evidenceSummary.trim(), proof_timestamp: proofTimestamp },
    });
    if (!result.ok) {
      setCompletionState("error");
      setCompletionError(result.error.message);
      return;
    }
    onObligationUpdated(result.data);
    onRefreshRequested();
    setCompletionState("idle");
  }

  const escalation = item.escalation;
  const isPending = item.review_state === "pending_review";

  return (
    <>
      <SheetHeader>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill kind="priority" value={item.priority} />
          <StatusPill kind="review" value={item.review_state} />
          {escalation ? <StatusPill kind="escalation" value={escalation.level} /> : null}
          <Badge variant="muted">{item.status}</Badge>
        </div>
        <SheetTitle>{item.title}</SheetTitle>
        <SheetDescription>
          Owner: <span className="text-foreground">{item.owner_hint ?? "Unresolved"}</span> · Due:{" "}
          <span className="text-foreground">{formatDueDate(item.due_date)}</span> · Confidence:{" "}
          <span className="text-foreground">
            {typeof item.confidence === "number" ? `${(item.confidence * 100).toFixed(0)}%` : "n/a"}
          </span>
        </SheetDescription>
      </SheetHeader>

      <SheetBody className="flex flex-col gap-4">
        {item.description ? (
          <Card>
            <CardContent className="p-4 text-sm leading-relaxed">{item.description}</CardContent>
          </Card>
        ) : null}

        {escalation?.open ? (
          <Alert variant="warn">
            <AlertTriangle />
            <AlertTitle>Escalation open</AlertTitle>
            <AlertDescription>
              Reasons:{" "}
              {escalation.reasons.map((value) => formatEscalationReason(value)).join(", ") || "n/a"}
              {typeof escalation.days_until_due === "number"
                ? ` · ${escalation.days_until_due} days until due`
                : ""}
            </AlertDescription>
          </Alert>
        ) : null}

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Confidence</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <ConfidenceMeter value={typeof item.confidence === "number" ? item.confidence : 0} />
          </CardContent>
        </Card>

        {typeof item.risk_score === "number" ? (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Risk</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <RiskScoreGauge
                score={item.risk_score}
                band={item.risk_band}
                factors={item.risk_factors}
              />
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Reassign owner</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <form className="flex gap-2" onSubmit={reassignOwner}>
              <Input
                name="owner_hint"
                placeholder="Department / officer"
                defaultValue={item.owner_hint ?? ""}
                key={`${item.id}:${item.updated_at}`}
              />
              <Button type="submit" size="sm" disabled={actionState === "saving"}>
                Save
              </Button>
            </form>
            {actionError ? <p className="mt-2 text-sm text-destructive">{actionError}</p> : null}
          </CardContent>
        </Card>

        <WhyPanel obligation={item} documentId={item.document_id} />

        {item.citation?.clause_span ? (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Citation</CardTitle>
              <CardDescription className="text-xs">{item.citation.clause_span}</CardDescription>
            </CardHeader>
            <CardContent className="pt-0">
              <Button
                variant="outline"
                size="sm"
                onClick={loadCitationDetails}
                disabled={citationState === "loading"}
              >
                {citationState === "loading" ? "Loading…" : "Load citation details"}
              </Button>
              {citationState === "error" ? (
                <p className="mt-2 text-sm text-destructive">{citationError}</p>
              ) : null}
              {citationState === "ready" && citationItems.length > 0 ? (
                <div className="mt-3 flex flex-col gap-2">
                  {citationItems.map((clause) => (
                    <div
                      key={clause.id}
                      className="rounded-md border border-border bg-muted/30 p-3 text-sm"
                    >
                      <div className="text-xs text-muted-foreground">
                        Page {clause.page_number ?? "n/a"} · Clause {clause.clause_index} ·{" "}
                        {clause.citation_span}
                      </div>
                      <p className="mt-1 text-foreground/90">{clause.text}</p>
                    </div>
                  ))}
                </div>
              ) : null}
              {citationState === "ready" && citationItems.length === 0 ? (
                <p className="mt-2 text-sm text-muted-foreground">
                  No clause details for this citation.
                </p>
              ) : null}
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Completion verification</CardTitle>
            <CardDescription className="text-xs">
              Closure guardrails: relevance, date validity, and source must pass.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 pt-0">
            <div className="flex flex-wrap gap-2">
              <Badge variant={completionVerification.relevancePass ? "good" : "destructive"}>
                Relevance {completionVerification.relevancePass ? "pass" : "fail"}
              </Badge>
              <Badge variant={completionVerification.dateValidityPass ? "good" : "destructive"}>
                Date {completionVerification.dateValidityPass ? "pass" : "fail"}
              </Badge>
              <Badge
                variant={completionVerification.sourceConsistencyPass ? "good" : "destructive"}
              >
                Source {completionVerification.sourceConsistencyPass ? "pass" : "fail"}
              </Badge>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`proof_summary_${item.id}`}>Evidence summary</Label>
              <Textarea
                id={`proof_summary_${item.id}`}
                rows={3}
                value={evidenceSummary}
                onChange={(event) => setEvidenceSummary(event.target.value)}
                placeholder="Summarize supporting evidence using obligation-specific terms."
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`proof_date_${item.id}`}>Evidence date</Label>
                <Input
                  id={`proof_date_${item.id}`}
                  type="date"
                  value={evidenceDate}
                  onChange={(event) => setEvidenceDate(event.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`proof_source_${item.id}`}>Source document id</Label>
                <Input
                  id={`proof_source_${item.id}`}
                  value={evidenceSourceDocumentId}
                  onChange={(event) => setEvidenceSourceDocumentId(event.target.value)}
                  placeholder="Document UUID"
                />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Matched evidence keywords: {completionVerification.overlapCount}
            </p>
            {completionLockedByReview ? (
              <p className="text-xs text-muted-foreground">
                Completion is locked until reviewer state is approved.
              </p>
            ) : null}
            {item.status === "completed" ? (
              <p className="text-xs text-muted-foreground">Obligation is already completed.</p>
            ) : null}
            {completionError ? <p className="text-sm text-destructive">{completionError}</p> : null}
            <Button
              size="sm"
              variant="good"
              disabled={!canMarkCompleted}
              onClick={() => void markCompletedWithVerification()}
            >
              {completionState === "saving" ? "Closing…" : "Verify and mark completed"}
            </Button>
          </CardContent>
        </Card>

        <Collapsible
          onOpenChange={(open) => {
            if (open) void loadAuditTrail();
          }}
        >
          <Card>
            <CardHeader className="pb-3">
              <CollapsibleTrigger asChild>
                <button type="button" className="flex w-full items-center justify-between">
                  <CardTitle className="text-sm">Audit trail</CardTitle>
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                </button>
              </CollapsibleTrigger>
            </CardHeader>
            <CollapsibleContent>
              <CardContent className="pt-0">
                {auditState === "loading" ? <Skeleton className="h-12 w-full" /> : null}
                {auditState === "error" ? (
                  <p className="text-sm text-destructive">{auditError}</p>
                ) : null}
                {auditState === "ready" ? (
                  auditItems.length > 0 ? (
                    <ul className="flex flex-col gap-3 text-sm">
                      {auditItems.map((event) => (
                        <li
                          key={`${event.id}-${event.created_at}`}
                          className="rounded-md border border-border p-3"
                        >
                          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            {formatAuditAction(event.action)}
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">
                            Actor: {event.actor_type}
                            {event.actor_id ? ` (${event.actor_id})` : ""} ·{" "}
                            {formatDateTime(event.created_at)}
                          </p>
                          {formatAuditPayload(event.payload) ? (
                            <p className="mt-1 text-xs text-foreground/90">
                              {formatAuditPayload(event.payload)}
                            </p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      No reviewer audit events recorded yet.
                    </p>
                  )
                ) : null}
              </CardContent>
            </CollapsibleContent>
          </Card>
        </Collapsible>
      </SheetBody>

      <SheetFooter>
        {isPending ? (
          <>
            <Button
              variant="outline"
              onClick={() => void runReviewerAction("rejected")}
              disabled={actionState === "saving"}
            >
              Reject
            </Button>
            <Button
              variant="good"
              onClick={() => void runReviewerAction("approved")}
              disabled={actionState === "saving"}
            >
              Approve
            </Button>
          </>
        ) : (
          <p className="self-center text-sm text-muted-foreground">
            Already {item.review_state.replace("_", " ")}.
          </p>
        )}
      </SheetFooter>
    </>
  );
}

function RelatedCaseRow({
  href,
  title,
  similarity,
  overlap,
  tags,
  sample,
  footer,
  origin,
}: {
  href: string;
  title: string;
  similarity: number;
  overlap: number;
  tags: string[];
  sample: string[];
  footer?: React.ReactNode;
  origin: string;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-col gap-1">
        <span className="text-sm font-semibold text-foreground">{title}</span>
        <span className="text-xs text-muted-foreground">
          Similarity: {similarity.toFixed(2)} · Shared patterns: {overlap}
        </span>
        <span className="text-xs text-muted-foreground">
          Tags: {tags.join(", ") || "pattern-overlap"}
        </span>
        {sample.length > 0 ? (
          <span className="text-xs text-muted-foreground">Sample: {sample.join(" · ")}</span>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        <Badge variant="muted">{origin}</Badge>
        {footer}
        <Button asChild variant="outline" size="sm">
          <Link href={href}>Open</Link>
        </Button>
      </div>
    </div>
  );
}
