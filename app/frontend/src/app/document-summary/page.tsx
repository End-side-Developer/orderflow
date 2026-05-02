"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ClipboardList,
  FileText,
  KeyRound,
  Link2,
  ListChecks,
  Lock,
  Pencil,
  Settings2,
  ShieldCheck,
  Sparkles,
  XCircle,
  Zap,
} from "lucide-react";

import { PageHeader } from "@/components/app/page-header";
import { ConfidenceMeter, getConfidenceTone } from "@/components/app/confidence-meter";
import { EmptyState } from "@/components/app/empty-state";
import { StatusPill } from "@/components/app/status-pill";
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
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { JudgmentDecisionPanel } from "@/components/judgment-decision-panel";
import {
  apiGet,
  extractPageObligations,
  getDocument,
  getIntakeWorkflowStatus,
  listAnnotations,
  reviewObligation,
  updateAnnotationCoordinates,
  type AnnotationBboxUpdate,
  type ExtractedObligation,
  type PageAnnotation,
} from "@/lib/api/client";
import type { Annotation as PdfAnnotation, PdfTextPosition } from "@/components/pdf-viewer";
import { cn } from "@/lib/utils";

const PdfViewer = dynamic(
  () => import("@/components/pdf-viewer").then((mod) => mod.PdfViewer),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-96 items-center justify-center text-sm text-muted-foreground">
        Loading PDF viewer…
      </div>
    ),
  },
);

interface HighlightItem {
  text: string;
  significance: "critical" | "important" | "contextual";
  relevance?: string;
}
interface ContextLink {
  page_number: number;
  reason: string;
}
interface PageSummary {
  id: string;
  document_id: string;
  page_number: number;
  page_text: string;
  summary: string;
  key_points: string[];
  important_highlights: HighlightItem[];
  context_links: ContextLink[];
  obligation_ids: string[];
  confidence: number | null;
  extraction_mode: string;
  ai_model?: string;
  ai_provider?: string;
  generated_at: string;
  created_at: string;
  updated_at: string;
}
interface ApiResponse {
  ok: boolean;
  message: string;
  data: {
    document_id: string;
    total_pages: number;
    summary_count: number;
    items: PageSummary[];
  };
}

type LoadState = "idle" | "loading" | "success" | "error";
const LAST_DOC_KEY = "orderflow:last_uploaded_document_id";
const LAST_LABEL_KEY = "orderflow:last_uploaded_document_label";
const LAST_AI_REASON_KEY = "orderflow:last_uploaded_ai_reason";
const LAST_WORKFLOW_WARNING_KEY = "orderflow:last_uploaded_workflow_warning";

type PageLoadError = {
  message: string;
  cause?: string;
  requestId?: string;
};

const SIG_VARIANT: Record<HighlightItem["significance"], "destructive" | "warn" | "muted"> = {
  critical: "destructive",
  important: "warn",
  contextual: "muted",
};

const SIG_BORDER: Record<HighlightItem["significance"], string> = {
  critical: "border-l-destructive bg-destructive/5",
  important: "border-l-warn bg-warn/5",
  contextual: "border-l-border bg-muted/30",
};

const PRIORITY_VARIANT: Record<string, "destructive" | "warn" | "accent" | "muted"> = {
  critical: "destructive",
  high: "warn",
  medium: "accent",
  low: "muted",
};

export default function DocumentSummaryPage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4">
          <Skeleton className="h-12 w-full max-w-md" />
          <Skeleton className="h-64 w-full" />
        </div>
      }
    >
      <DocumentSummaryContent />
    </Suspense>
  );
}

function DocumentSummaryContent() {
  const router = useRouter();
  const sp = useSearchParams();
  const qid = sp.get("document_id");
  const workflowWarning = sp.get("workflow_warning");
  const extractionReason = sp.get("extraction_reason");

  const [summaries, setSummaries] = useState<PageSummary[]>([]);
  const [loading, setLoading] = useState<LoadState>("idle");
  const [error, setError] = useState<PageLoadError | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [docId, setDocId] = useState<string | null>(qid);
  const [docLabel, setDocLabel] = useState<string | null>(null);
  const [uploadReason, setUploadReason] = useState<string | null>(extractionReason);
  const [viewMode, setViewMode] = useState<"summary" | "pdf">("summary");
  const [annotations, setAnnotations] = useState<PageAnnotation[]>([]);
  const [importantOnly, setImportantOnly] = useState(false);

  const [pageObligations, setPageObligations] = useState<Map<number, ExtractedObligation[]>>(
    new Map(),
  );
  const [pageGateMeta, setPageGateMeta] = useState<Map<number, { gate: string; avgConf: number }>>(
    new Map(),
  );
  const [oblLoading, setOblLoading] = useState(false);
  const [oblFetched, setOblFetched] = useState<Set<number>>(new Set());
  const [reviewingCode, setReviewingCode] = useState<string | null>(null);
  const [editingCode, setEditingCode] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [obligationError, setObligationError] = useState<string | null>(null);

  useEffect(() => {
    if (qid) {
      setDocId(qid);
      if (typeof window !== "undefined") {
        setDocLabel(localStorage.getItem(LAST_LABEL_KEY));
        setUploadReason(extractionReason ?? localStorage.getItem(LAST_AI_REASON_KEY) ?? null);
        localStorage.setItem(LAST_DOC_KEY, qid);
        localStorage.setItem("orderflow:current_document_id", qid);
      }
      setError(null);
      setLoading("idle");
      return;
    }
    if (typeof window === "undefined") return;
    const lid = localStorage.getItem(LAST_DOC_KEY);
    if (lid) {
      setDocId(lid);
      setDocLabel(localStorage.getItem(LAST_LABEL_KEY));
      setUploadReason(localStorage.getItem(LAST_AI_REASON_KEY));
      router.replace(`/document-summary?document_id=${encodeURIComponent(lid)}`);
      return;
    }
    setError({
      message: "No uploaded document found. Upload a judgment first.",
      cause: "The summary page could not find a stored document id in local storage or the URL.",
    });
    setLoading("error");
  }, [qid, router, extractionReason]);

  const fetchSummaries = useCallback(
    async (id: string) => {
      if (!id) return;
      setLoading("loading");
      setError(null);
      try {
        const res = await apiGet<ApiResponse["data"]>(`/summaries/${encodeURIComponent(id)}`);
        if (!res.ok) {
          const causeParts = [
            res.error.details?.message,
            res.error.details?.detail,
            res.error.details?.error,
          ].filter((part): part is string => typeof part === "string" && part.trim().length > 0);
          setError({
            message: res.error.message,
            cause: causeParts.length > 0 ? causeParts.join(" · ") : undefined,
            requestId: res.request_id,
          });
          setLoading("error");
          return;
        }
        if (res.data.items.length === 0) {
          const [documentResult, workflowResult] = await Promise.all([
            getDocument(id),
            getIntakeWorkflowStatus(id),
          ]);
          const causeParts: string[] = [];
          const storedWorkflowWarning =
            typeof window !== "undefined"
              ? localStorage.getItem(LAST_WORKFLOW_WARNING_KEY)
              : null;
          const storedAiReason =
            typeof window !== "undefined" ? localStorage.getItem(LAST_AI_REASON_KEY) : null;
          const uploadNote = workflowWarning ?? storedWorkflowWarning ?? null;
          const aiNote = extractionReason ?? uploadReason ?? storedAiReason ?? null;
          if (uploadNote) causeParts.push(`Upload note: ${uploadNote}`);
          if (aiNote) causeParts.push(`Extraction note: ${aiNote}`);
          if (documentResult.ok) {
            causeParts.push(`Document status: ${documentResult.data.status}`);
            if (documentResult.data.workflow_run_id) {
              causeParts.push(`Workflow run id: ${documentResult.data.workflow_run_id}`);
            }
          } else {
            causeParts.push(`Document lookup failed: ${documentResult.error.message}`);
          }
          if (workflowResult.ok) {
            const workflowData = workflowResult.data;
            causeParts.push(`Workflow status: ${workflowData.status}`);
            const failureReason = getStringMetadataValue(workflowData.metadata, [
              "failure_reason",
              "error_reason",
              "last_error",
              "error",
              "cause",
              "detail",
            ]);
            if (failureReason) causeParts.push(`Workflow cause: ${failureReason}`);
            else if (workflowData.status === "started")
              causeParts.push("Workflow is still running, so summaries may not be ready yet.");
            else if (workflowData.status === "completed")
              causeParts.push("Workflow finished, but no page summaries were persisted.");
          } else {
            causeParts.push(`Workflow lookup failed: ${workflowResult.error.message}`);
          }
          setError({
            message: "No page summaries available for this document.",
            cause:
              causeParts.length > 0
                ? causeParts.join(" · ")
                : "The backend returned an empty summary list.",
          });
          setLoading("error");
          return;
        }
        setSummaries(res.data.items);
        setCurrentPage(1);
        setLoading("success");
      } catch (e) {
        setError({
          message: e instanceof Error ? e.message : "Unknown error",
          cause: "The summary request failed before the backend could return a structured response.",
        });
        setLoading("error");
      }
    },
    [extractionReason, uploadReason, workflowWarning],
  );

  useEffect(() => {
    if (docId) void fetchSummaries(docId);
  }, [docId, fetchSummaries]);

  useEffect(() => {
    if (!docId || viewMode !== "pdf") return;
    (async () => {
      const r = await listAnnotations(docId);
      if (r.ok) setAnnotations(r.data.items);
    })();
  }, [docId, viewMode]);

  useEffect(() => {
    if (!docId || loading !== "success" || oblFetched.has(currentPage)) return;
    const cur = summaries[currentPage - 1];
    if (!cur || !cur.page_text?.trim()) return;
    let cancelled = false;
    setOblLoading(true);
    setObligationError(null);
    (async () => {
      const result = await extractPageObligations({
        document_id: docId,
        page_number: currentPage,
        text: cur.page_text,
      });
      if (cancelled) return;
      if (result.ok) {
        setPageObligations((prev) => {
          const next = new Map(prev);
          next.set(currentPage, result.data.obligations);
          return next;
        });
        setPageGateMeta((prev) => {
          const next = new Map(prev);
          next.set(currentPage, {
            gate: result.data.gate_decision,
            avgConf: result.data.average_confidence,
          });
          return next;
        });
      } else {
        setObligationError(result.error.message);
      }
      setOblFetched((prev) => new Set(prev).add(currentPage));
      setOblLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [docId, currentPage, loading, summaries, oblFetched]);

  async function handleTextExtracted(positions: PdfTextPosition[]) {
    if (!docId || annotations.length === 0) return;
    const updates: AnnotationBboxUpdate[] = [];
    for (const a of annotations) {
      if (!a.text_content || a.bbox) continue;
      const st = a.text_content.toLowerCase().trim();
      const matches = positions.filter(
        (p) =>
          p.page === a.page_number &&
          p.text.toLowerCase().includes(st.substring(0, Math.min(st.length, 30))),
      );
      if (matches.length > 0) {
        let [x1, y1, x2, y2] = [
          matches[0].bbox.x,
          matches[0].bbox.y,
          matches[0].bbox.x + matches[0].bbox.width,
          matches[0].bbox.y + matches[0].bbox.height,
        ];
        matches.forEach((m) => {
          x1 = Math.min(x1, m.bbox.x);
          y1 = Math.min(y1, m.bbox.y);
          x2 = Math.max(x2, m.bbox.x + m.bbox.width);
          y2 = Math.max(y2, m.bbox.y + m.bbox.height);
        });
        updates.push({
          annotation_id: a.id,
          bbox: { x: x1, y: y1, width: x2 - x1, height: y2 - y1 },
        });
      }
    }
    if (updates.length > 0) {
      const r = await updateAnnotationCoordinates(docId, updates);
      if (r.ok) {
        const rl = await listAnnotations(docId);
        if (rl.ok) setAnnotations(rl.data.items);
      }
    }
  }

  const toggle = (id: string) => {
    const n = new Set(expanded);
    if (n.has(id)) n.delete(id);
    else n.add(id);
    setExpanded(n);
  };

  async function handleReview(obl: ExtractedObligation, decision: "approved" | "rejected") {
    setReviewingCode(obl.obligation_code);
    const result = await reviewObligation({
      obligation_code: obl.obligation_code,
      review_decision: decision,
      edited_title: editingCode === obl.obligation_code ? editTitle : undefined,
      edited_description: editingCode === obl.obligation_code ? editDesc : undefined,
      review_note: decision === "rejected" ? "Rejected by reviewer" : undefined,
    });
    if (result.ok) {
      setPageObligations((prev) => {
        const next = new Map(prev);
        const pageObls = next.get(obl.page_number) ?? [];
        next.set(
          obl.page_number,
          pageObls.map((o) =>
            o.obligation_code === obl.obligation_code
              ? {
                  ...o,
                  review_state: decision,
                  title: editingCode === obl.obligation_code && editTitle ? editTitle : o.title,
                  description:
                    editingCode === obl.obligation_code && editDesc ? editDesc : o.description,
                }
              : o,
          ),
        );
        return next;
      });
      setEditingCode(null);
      setEditTitle("");
      setEditDesc("");
      setObligationError(null);
    } else {
      setObligationError(result.error.message);
    }
    setReviewingCode(null);
  }

  if (!docId) {
    return (
      <EmptyState
        icon={<XCircle />}
        title="No document"
        message="Upload a PDF first, then return here to analyze."
        actionHref="/upload"
        actionLabel="Go to Intake"
      />
    );
  }
  if (loading === "loading") {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-12 w-full max-w-md" />
        <div className="grid gap-4 md:grid-cols-[240px_1fr]">
          <Skeleton className="h-96" />
          <div className="flex flex-col gap-3">
            <Skeleton className="h-32" />
            <Skeleton className="h-48" />
          </div>
        </div>
      </div>
    );
  }
  if (loading === "error") {
    return (
      <EmptyState
        icon={<AlertTriangle />}
        title="Could not load summaries"
        message={error?.message ?? "Something went wrong."}
        detail={error?.cause}
        requestId={error?.requestId}
        actionHref="/upload"
        actionLabel="Upload new document"
      />
    );
  }
  if (summaries.length === 0) {
    return (
      <EmptyState
        icon={<FileText />}
        title="No summaries"
        message="Page summaries haven't been generated yet."
        detail={
          [workflowWarning, uploadReason]
            .filter((item): item is string => Boolean(item && item.trim().length > 0))
            .join(" · ") || undefined
        }
        actionHref={`/upload?document_id=${docId}`}
        actionLabel="Generate summaries"
      />
    );
  }

  const cur = summaries[currentPage - 1];
  const highlights = importantOnly
    ? cur?.important_highlights.filter((h) => h.significance !== "contextual") ?? []
    : cur?.important_highlights ?? [];
  const currentPageObligations = pageObligations.get(currentPage) ?? [];
  const currentGateMeta = pageGateMeta.get(currentPage);
  const pendingObligations = currentPageObligations.filter(
    (o) => o.review_state === "pending_review",
  );

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Analyze"
        title={docLabel ? docLabel : "Page-level analysis"}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span>{summaries.length} pages analyzed</span>
            <Badge variant="muted">AI: {cur?.ai_model ?? "unknown"}</Badge>
          </span>
        }
        actions={
          <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as "summary" | "pdf")}>
            <TabsList>
              <TabsTrigger value="summary">Analysis</TabsTrigger>
              <TabsTrigger value="pdf">PDF view</TabsTrigger>
            </TabsList>
          </Tabs>
        }
      />

      {workflowWarning ? (
        <Alert variant="warn">
          <AlertTriangle />
          <AlertTitle>Upload note</AlertTitle>
          <AlertDescription>{workflowWarning}</AlertDescription>
        </Alert>
      ) : null}

      {viewMode === "pdf" ? (
        <PdfViewer
          documentId={docId}
          onPageChange={setCurrentPage}
          initialPage={currentPage}
          annotations={annotations}
          onTextExtracted={handleTextExtracted}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-[240px_minmax(0,1fr)]">
          <PageSidebar
            summaries={summaries}
            pageObligations={pageObligations}
            currentPage={currentPage}
            onSelect={setCurrentPage}
          />
          <div className="flex flex-col gap-4">
            {docId ? (
              <JudgmentDecisionPanel
                documentId={docId}
                fullText={summaries.map((s) => s.page_text).join(" ")}
                pageCount={summaries.length}
              />
            ) : null}
            {cur ? (
              <PageDetail
                page={cur}
                highlights={highlights}
                importantOnly={importantOnly}
                onToggleImportantOnly={() => setImportantOnly((v) => !v)}
                expanded={expanded}
                onToggleExpanded={toggle}
                pageObligations={currentPageObligations}
                pendingObligations={pendingObligations}
                gateMeta={currentGateMeta}
                obligationError={obligationError}
                oblLoading={oblLoading}
                reviewingCode={reviewingCode}
                editingCode={editingCode}
                editTitle={editTitle}
                editDesc={editDesc}
                onEditOpen={(o) => {
                  setEditingCode(o.obligation_code);
                  setEditTitle(o.title);
                  setEditDesc(o.description ?? "");
                }}
                onEditClose={() => {
                  setEditingCode(null);
                  setEditTitle("");
                  setEditDesc("");
                }}
                onEditTitleChange={setEditTitle}
                onEditDescChange={setEditDesc}
                onReview={handleReview}
                summaries={summaries}
                onJumpToPage={(pageNumber) => {
                  const ti = summaries.findIndex((s) => s.page_number === pageNumber);
                  if (ti >= 0) setCurrentPage(ti + 1);
                }}
              />
            ) : null}

            <Card>
              <CardContent className="flex items-center justify-between gap-4 p-4">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={currentPage === 1}
                  onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                >
                  <ArrowLeft />
                  Previous
                </Button>
                <span className="text-sm font-semibold text-muted-foreground">
                  Page {currentPage} of {summaries.length}
                </span>
                <Button
                  size="sm"
                  disabled={currentPage === summaries.length}
                  onClick={() => setCurrentPage(Math.min(summaries.length, currentPage + 1))}
                >
                  Next
                  <ArrowRight />
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

function PageSidebar({
  summaries,
  pageObligations,
  currentPage,
  onSelect,
}: {
  summaries: PageSummary[];
  pageObligations: Map<number, ExtractedObligation[]>;
  currentPage: number;
  onSelect: (pageNumber: number) => void;
}) {
  return (
    <Card className="sticky top-20 self-start">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Pages</CardTitle>
      </CardHeader>
      <CardContent className="p-2">
        <ScrollArea className="max-h-[calc(100vh-200px)]">
          <div className="flex flex-col gap-1 pr-2">
            {summaries.map((s, i) => {
              const obls = pageObligations.get(s.page_number);
              const oblCount = obls ? obls.length : s.obligation_ids?.length ?? 0;
              const active = currentPage === i + 1;
              return (
                <Button
                  key={s.id}
                  variant={active ? "secondary" : "ghost"}
                  size="sm"
                  className="justify-between"
                  onClick={() => onSelect(i + 1)}
                >
                  <span>Page {s.page_number}</span>
                  {oblCount > 0 ? (
                    <Badge variant={active ? "outline" : "warn"} className="ml-2">
                      {oblCount}
                    </Badge>
                  ) : null}
                </Button>
              );
            })}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

function PageDetail(props: {
  page: PageSummary;
  highlights: HighlightItem[];
  importantOnly: boolean;
  onToggleImportantOnly: () => void;
  expanded: Set<string>;
  onToggleExpanded: (id: string) => void;
  pageObligations: ExtractedObligation[];
  pendingObligations: ExtractedObligation[];
  gateMeta?: { gate: string; avgConf: number };
  obligationError: string | null;
  oblLoading: boolean;
  reviewingCode: string | null;
  editingCode: string | null;
  editTitle: string;
  editDesc: string;
  onEditOpen: (o: ExtractedObligation) => void;
  onEditClose: () => void;
  onEditTitleChange: (v: string) => void;
  onEditDescChange: (v: string) => void;
  onReview: (o: ExtractedObligation, decision: "approved" | "rejected") => Promise<void>;
  summaries: PageSummary[];
  onJumpToPage: (pageNumber: number) => void;
}) {
  const {
    page,
    highlights,
    importantOnly,
    onToggleImportantOnly,
    expanded,
    onToggleExpanded,
    pageObligations,
    pendingObligations,
    gateMeta,
    obligationError,
    oblLoading,
    reviewingCode,
    editingCode,
    editTitle,
    editDesc,
    onEditOpen,
    onEditClose,
    onEditTitleChange,
    onEditDescChange,
    onReview,
    onJumpToPage,
  } = props;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Page
            </span>
            <h2 className="text-2xl font-semibold tracking-tight text-foreground">
              Page {page.page_number}
            </h2>
          </div>
          {page.confidence != null ? (
            <div className="min-w-[180px]">
              <ConfidenceMeter value={page.confidence} />
            </div>
          ) : null}
          <Button
            variant={importantOnly ? "default" : "outline"}
            size="sm"
            onClick={onToggleImportantOnly}
          >
            <Settings2 />
            {importantOnly ? "Show all highlights" : "Important only"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <FileText className="h-4 w-4 text-muted-foreground" /> Page summary
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          <p className="text-sm leading-relaxed text-foreground/90">{page.summary}</p>
        </CardContent>
      </Card>

      {page.key_points.length > 0 ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <KeyRound className="h-4 w-4 text-muted-foreground" /> Key points
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 pt-0">
            {page.key_points.map((p, i) => (
              <div
                key={i}
                className="flex items-start gap-2 rounded-md border-l-2 border-primary bg-muted/30 px-3 py-2 text-sm"
              >
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-hidden />
                <span className="text-foreground/90">{p}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      {highlights.length > 0 ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Zap className="h-4 w-4 text-muted-foreground" />
              {importantOnly ? "Critical & important highlights" : "Important extracts"}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 pt-0">
            {highlights.map((h, i) => {
              const hid = `h-${i}`;
              const isOpen = expanded.has(hid);
              return (
                <div
                  key={i}
                  className={cn(
                    "rounded-md border-l-2 px-3 py-2",
                    SIG_BORDER[h.significance] ?? SIG_BORDER.contextual,
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="flex-1 text-sm italic leading-relaxed text-foreground/90">
                      &ldquo;{h.text}&rdquo;
                    </p>
                    <Badge variant={SIG_VARIANT[h.significance]} className="uppercase">
                      {h.significance}
                    </Badge>
                  </div>
                  {h.relevance ? (
                    <div className="mt-2">
                      <Button
                        variant="link"
                        size="sm"
                        className="h-auto p-0 text-xs"
                        onClick={() => onToggleExpanded(hid)}
                      >
                        {isOpen ? "Hide note" : "Show note"}
                      </Button>
                      {isOpen ? (
                        <p className="mt-1 text-xs text-muted-foreground">
                          <strong>Why it matters:</strong> {h.relevance}
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </CardContent>
        </Card>
      ) : null}

      {page.context_links.length > 0 ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Link2 className="h-4 w-4 text-muted-foreground" /> Related pages
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 pt-0">
            {page.context_links.map((lk, i) => (
              <Button
                key={i}
                variant="outline"
                className="h-auto justify-start gap-2 px-3 py-2 text-left"
                onClick={() => onJumpToPage(lk.page_number)}
              >
                <Badge variant="accent">Page {lk.page_number}</Badge>
                <span className="text-xs text-muted-foreground">{lk.reason}</span>
              </Button>
            ))}
          </CardContent>
        </Card>
      ) : null}

      {obligationError ? (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>Obligation extraction warning</AlertTitle>
          <AlertDescription>{obligationError}</AlertDescription>
        </Alert>
      ) : null}

      {oblLoading ? (
        <Alert variant="warn">
          <Sparkles />
          <AlertTitle>Extracting obligations…</AlertTitle>
          <AlertDescription>
            Running graph pipeline · confidence scoring · HITL gate check.
          </AlertDescription>
        </Alert>
      ) : null}

      {!oblLoading && pageObligations.length > 0 ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <ClipboardList className="h-4 w-4 text-muted-foreground" /> Obligations on this page
              ({pageObligations.length})
            </CardTitle>
            <CardDescription>
              Verify each item before it moves forward in the workflow.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 pt-0">
            <Alert variant="warn">
              <Lock />
              <AlertTitle>Verify — human-in-the-loop (mandatory)</AlertTitle>
              <AlertDescription>
                AI-extracted obligations are shown with source highlights and confidence levels. You
                must approve, edit, or reject each item. Only verified records move forward.
                {pendingObligations.length > 0 ? (
                  <span className="mt-2 block font-semibold">
                    {pendingObligations.length} obligation
                    {pendingObligations.length > 1 ? "s" : ""} awaiting your review on this page
                    {gateMeta ? ` · gate: ${gateMeta.gate}` : ""}
                  </span>
                ) : null}
              </AlertDescription>
            </Alert>

            {pageObligations.map((obl) => {
              const isReviewing = reviewingCode === obl.obligation_code;
              const reviewVariant: "good" | "destructive" | "warn" =
                obl.review_state === "approved"
                  ? "good"
                  : obl.review_state === "rejected"
                    ? "destructive"
                    : "warn";
              const reviewLabel =
                obl.review_state === "approved"
                  ? "Approved"
                  : obl.review_state === "rejected"
                    ? "Rejected"
                    : "Pending review";
              return (
                <div
                  key={obl.obligation_code}
                  className={cn(
                    "flex flex-col gap-3 rounded-md border p-4",
                    obl.review_state === "rejected"
                      ? "border-destructive/20 bg-destructive/5"
                      : obl.review_state === "approved"
                        ? "border-good/20 bg-good/5"
                        : "border-border bg-card",
                  )}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex-1">
                      <div className="mb-1 flex flex-wrap items-center gap-1.5">
                        <Badge variant={PRIORITY_VARIANT[obl.priority] ?? "muted"} className="uppercase">
                          {obl.priority}
                        </Badge>
                        <Badge variant={reviewVariant}>{reviewLabel}</Badge>
                        <span className="text-[10px] text-muted-foreground">
                          {obl.obligation_code}
                        </span>
                      </div>
                      <h5 className="text-sm font-semibold text-foreground">{obl.title}</h5>
                    </div>
                    <div className="min-w-[140px]">
                      <ConfidenceMeter value={obl.confidence} compact />
                    </div>
                  </div>

                  {obl.description ? (
                    <p className="text-sm text-muted-foreground">{obl.description}</p>
                  ) : null}

                  {obl.source_highlights.length > 0 ? (
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                        Source
                      </span>
                      {obl.source_highlights.map((sh, si) => (
                        <div
                          key={si}
                          className="rounded-md border-l-2 border-primary bg-primary/5 px-3 py-2 text-xs italic text-primary"
                        >
                          &ldquo;{sh.text}&rdquo;
                        </div>
                      ))}
                    </div>
                  ) : null}

                  <div className="grid grid-cols-3 gap-2">
                    <ConfidenceCell label="Directive" value={obl.confidence_components.directive_signal} />
                    <ConfidenceCell label="Entity" value={obl.confidence_components.entity_presence} />
                    <ConfidenceCell label="Temporal" value={obl.confidence_components.temporal_signal} />
                  </div>

                  {(obl.owner_hint || obl.due_date) ? (
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                      {obl.owner_hint ? (
                        <span>
                          Owner:{" "}
                          <strong className="text-foreground">{obl.owner_hint}</strong>
                        </span>
                      ) : null}
                      {obl.due_date ? (
                        <span>
                          Due: <strong className="text-foreground">{obl.due_date}</strong>
                        </span>
                      ) : null}
                    </div>
                  ) : null}

                  {obl.review_state === "pending_review" ? (
                    <div className="flex flex-wrap gap-2 border-t border-border pt-3">
                      <Button
                        variant="good"
                        size="sm"
                        disabled={isReviewing}
                        onClick={() => void onReview(obl, "approved")}
                      >
                        <CheckCircle2 />
                        {isReviewing ? "…" : "Approve"}
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => onEditOpen(obl)}>
                        <Pencil />
                        Edit
                      </Button>
                      <Button
                        variant="destructive"
                        size="sm"
                        disabled={isReviewing}
                        onClick={() => void onReview(obl, "rejected")}
                      >
                        <XCircle />
                        Reject
                      </Button>
                    </div>
                  ) : null}

                  {obl.review_state === "approved" ? (
                    <div className="flex items-center gap-2 border-t border-good/20 pt-2 text-xs text-good">
                      <ShieldCheck className="h-3.5 w-3.5" />
                      Verified — will move forward in workflow.
                    </div>
                  ) : null}
                  {obl.review_state === "rejected" ? (
                    <div className="flex items-center gap-2 border-t border-destructive/20 pt-2 text-xs text-destructive">
                      <XCircle className="h-3.5 w-3.5" />
                      Rejected — will not be persisted.
                    </div>
                  ) : null}
                </div>
              );
            })}
          </CardContent>
        </Card>
      ) : null}

      <EditObligationDialog
        editingCode={editingCode}
        title={editTitle}
        description={editDesc}
        onTitleChange={onEditTitleChange}
        onDescriptionChange={onEditDescChange}
        onClose={onEditClose}
        onSave={async () => {
          const target = pageObligations.find((o) => o.obligation_code === editingCode);
          if (!target) return;
          await onReview(target, "approved");
        }}
        saving={Boolean(reviewingCode)}
      />
    </div>
  );
}

function ConfidenceCell({ label, value }: { label: string; value: number }) {
  const tone = getConfidenceTone(value);
  return (
    <div className="flex flex-col gap-1 rounded-md border border-border bg-muted/20 px-2 py-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <ConfidenceMeter value={value} compact />
      <span className="sr-only">{tone.label}</span>
    </div>
  );
}

function EditObligationDialog({
  editingCode,
  title,
  description,
  onTitleChange,
  onDescriptionChange,
  onClose,
  onSave,
  saving,
}: {
  editingCode: string | null;
  title: string;
  description: string;
  onTitleChange: (v: string) => void;
  onDescriptionChange: (v: string) => void;
  onClose: () => void;
  onSave: () => void | Promise<void>;
  saving: boolean;
}) {
  const open = Boolean(editingCode);
  return (
    <Dialog open={open} onOpenChange={(next) => (!next ? onClose() : undefined)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit obligation</DialogTitle>
          <DialogDescription>
            Refine the AI-extracted text before approving. Saved edits go forward as the verified record.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="edit-obl-title">Title</Label>
            <Input
              id="edit-obl-title"
              value={title}
              onChange={(e) => onTitleChange(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="edit-obl-desc">Description</Label>
            <Textarea
              id="edit-obl-desc"
              rows={4}
              value={description}
              onChange={(e) => onDescriptionChange(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="good" disabled={saving} onClick={() => void onSave()}>
            <ListChecks />
            Save edits & approve
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function getStringMetadataValue(
  metadata: Record<string, unknown> | null,
  keys: string[],
): string | null {
  if (!metadata) return null;
  for (const key of keys) {
    const value = metadata[key];
    if (typeof value === "string" && value.trim().length > 0) return value.trim();
  }
  return null;
}
