"use client";

import { useMemo, useState, useEffect } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileText,
  Loader2,
  RefreshCw,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  ExtractionJobCurrentPageExcerpt,
  ExtractionJobStatusData,
  generateCaseSummary,
  startCaseIntake,
} from "@/lib/api/client";

type PageExtractionPanelProps = {
  documentId: string;
  progress: ExtractionJobStatusData | null;
  isPolling?: boolean;
};

export function PageExtractionPanel({
  documentId,
  progress,
  isPolling = false,
}: PageExtractionPanelProps) {
  const [isStarting, setIsStarting] = useState(false);
  const [isContinuing, setIsContinuing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const excerpt = useMemo(
    () => normalizeExcerpt(progress?.current_page_excerpt ?? null),
    [progress?.current_page_excerpt],
  );
  const percent = clampPercent(progress?.percent ?? 0);
  const pagesTotal = progress?.pages_total ?? 0;
  const pagesCompleted = progress?.pages_completed ?? 0;
  const currentPage = progress?.current_page ?? excerpt.pageNumber;
  const stage = progress?.stage ?? "pending";
  const statusMessage = progress?.status_message ?? stageLabel(stage);
  const cacheStatus = progress?.current_page_cache_status ?? excerpt.cacheStatus;
  const ocrStatus = buildOcrStatus(progress?.current_page_excerpt ?? null);
  const isPaused = Boolean(progress?.is_paused ?? progress?.paused_until);

  const pausedUntil = progress?.paused_until ?? null;
  const updatedAt = progress?.updated_at ?? null;
  const retryAfterSeconds = progress?.retry_after_seconds ?? null;

  const targetDate = useMemo(() => {
    if (pausedUntil) {
      return new Date(pausedUntil);
    }
    if (updatedAt && retryAfterSeconds) {
      return new Date(new Date(updatedAt).getTime() + retryAfterSeconds * 1000);
    }
    return null;
  }, [pausedUntil, updatedAt, retryAfterSeconds]);

  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(retryAfterSeconds);

  useEffect(() => {
    if (!targetDate) {
      setRemainingSeconds(retryAfterSeconds);
      return;
    }
    const updateTimer = () => {
      const diff = Math.floor((targetDate.getTime() - Date.now()) / 1000);
      setRemainingSeconds(diff > 0 ? diff : 0);
    };
    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [targetDate, retryAfterSeconds]);

  const retryMessage =
    remainingSeconds !== null
      ? `Retrying in ${remainingSeconds}s.`
      : progress?.paused_until
        ? `Paused until ${formatDate(progress?.paused_until)}.`
        : null;

  const failureReason = recordStringValue(progress?.current_page_excerpt, "error_message");
  const failureCode = recordStringValue(progress?.current_page_excerpt, "error_code");
  const technicalError = recordStringValue(progress?.current_page_excerpt, "technical_error_type");
  const aiProvider = recordStringValue(progress?.current_page_excerpt, "ai_provider");
  const aiModel = recordStringValue(progress?.current_page_excerpt, "ai_model");
  const canStart = !progress || stage === "pending";
  const canContinue = stage === "pages_done";

  async function handleStartIntake(bypassCache = false) {
    setIsStarting(true);
    setActionError(null);
    try {
      const response = await startCaseIntake(documentId, {
        bypass_cache: Boolean(bypassCache),
      });
      if (!response.ok) {
        setActionError(response.error.message);
      }
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not start intake.");
    } finally {
      setIsStarting(false);
    }
  }

  async function handleContinueToSummary() {
    setIsContinuing(true);
    setActionError(null);
    try {
      const response = await generateCaseSummary(documentId);
      if (!response.ok) {
        setActionError(response.error.message);
      }
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not continue.");
    } finally {
      setIsContinuing(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 p-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Page extraction</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {statusMessage}
            {progress?.next_action && ` — Next: ${progress.next_action}`}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant={canContinue ? "good" : "secondary"}>{stage.replaceAll("_", " ")}</Badge>
          <Badge variant={isPolling ? "muted" : "good"}>
            {isPolling ? "Polling fallback" : "Live updates"}
          </Badge>
        </div>
      </div>

      {/* Main content: left = progress + OCR + alerts, right = excerpt */}
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-5 lg:grid-cols-3">
        {/* Left column */}
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 rounded-md border border-border p-4 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium text-foreground">Pages completed</span>
              <span className="text-sm font-semibold tabular-nums text-foreground">
                {pagesCompleted} / {pagesTotal || "-"}
              </span>
            </div>
            <Progress value={percent} className="h-2.5" />
            <div className="grid grid-cols-3 gap-3 text-sm">
              <Metric label="Current" value={currentPage ?? "-"} />
              <Metric label="Percent" value={`${percent}%`} />
              <Metric label="Concurrency" value={progress?.current_concurrency ?? "-"} />
            </div>
          </div>

          <div className="rounded-md border border-border p-4 shadow-sm">
            <div className="mb-3 flex items-center gap-2">
              {ocrStatus.tone === "good" ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              ) : ocrStatus.tone === "bad" ? (
                <AlertTriangle className="h-4 w-4 text-rose-600" />
              ) : ocrStatus.tone === "running" ? (
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              ) : (
                <FileText className="h-4 w-4 text-muted-foreground" />
              )}
              <h3 className="text-sm font-semibold text-foreground">Text source</h3>
            </div>
            <div className="space-y-2 text-sm">
              <div className="font-medium text-foreground">{ocrStatus.label}</div>
              {ocrStatus.detail ? (
                <div className="leading-5 text-muted-foreground">{ocrStatus.detail}</div>
              ) : null}
              {ocrStatus.error ? (
                <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">
                  {ocrStatus.error}
                </div>
              ) : null}
            </div>
          </div>

          {actionError || progress?.error?.message || isPaused || retryMessage ? (
            <div className="flex flex-col gap-2">
              {actionError ? (
                <Alert variant="destructive" className="py-2">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertTitle className="text-sm">Request failed</AlertTitle>
                  <AlertDescription className="text-xs">{actionError}</AlertDescription>
                </Alert>
              ) : null}
              {progress?.error?.message ? (
                <Alert variant="destructive" className="py-2">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertTitle className="text-sm">Extraction error</AlertTitle>
                  <AlertDescription className="text-xs">
                    {progress.error.message}
                  </AlertDescription>
                </Alert>
              ) : null}
              {isPaused || retryMessage ? (
                <Alert className="py-2">
                  <Clock3 className="h-4 w-4" />
                  <AlertTitle className="text-sm">Retry scheduled</AlertTitle>
                  <AlertDescription className="text-xs">
                    {retryMessage ?? `Paused until ${formatDate(progress?.paused_until)}`}
                  </AlertDescription>
                </Alert>
              ) : null}
            </div>
          ) : null}
        </div>

        {/* Right column: excerpt */}
        <div className="flex min-h-[200px] flex-col rounded-md border border-border p-4 shadow-sm lg:col-span-2">
          <div className="mb-3 flex shrink-0 items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">Current page excerpt</h3>
            </div>
            {cacheStatus ? (
              <Badge variant="muted" className="text-[10px]">
                {cacheStatus}
              </Badge>
            ) : null}
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-2">
            <p className="whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">
              {excerpt.text || "No excerpt available yet."}
            </p>
            {failureReason ? (
              <div className="mt-auto shrink-0 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">
                <div className="font-semibold">Why it failed</div>
                <div className="mt-1 leading-5">{failureReason}</div>
                {failureCode || technicalError ? (
                  <div className="mt-2 text-rose-700">
                    {failureCode ? <div>Code: {failureCode}</div> : null}
                    {technicalError ? <div>Type: {technicalError}</div> : null}
                    {aiProvider ? (
                      <div>
                        Provider: {aiProvider}
                        {aiModel ? ` / ${aiModel}` : ""}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {/* Footer actions */}
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-t border-border pt-4">
        <Button
          size="sm"
          type="button"
          variant="outline"
          onClick={() => void handleStartIntake(true)}
          disabled={isStarting || (canContinue && !failureReason)}
        >
          <RefreshCw className={`mr-2 h-4 w-4 ${isStarting ? "animate-spin" : ""}`} />
          {failureReason ? "Retry intake" : "Refresh intake"}
        </Button>
        <Button
          size="sm"
          type="button"
          variant="good"
          className="ml-auto"
          onClick={() => void handleContinueToSummary()}
          disabled={!canContinue || isContinuing}
        >
          {isContinuing ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <ArrowRight className="mr-2 h-4 w-4" />
          )}
          Continue to Summary
        </Button>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md bg-muted px-3 py-2">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 font-semibold tabular-nums text-foreground">{value}</div>
    </div>
  );
}

function normalizeExcerpt(excerpt: ExtractionJobCurrentPageExcerpt | null) {
  const pageNumber = numberValue(excerpt?.page_number);
  const cacheStatus = stringValue(excerpt?.cache_status);
  const text =
    stringValue(excerpt?.source_excerpt) ??
    stringValue(excerpt?.text) ??
    stringValue(excerpt?.error_message) ??
    skippedPagesText(excerpt?.skipped_page_numbers) ??
    "";

  return { pageNumber, cacheStatus, text };
}

function buildOcrStatus(excerpt: ExtractionJobCurrentPageExcerpt | null) {
  const textSource = stringValue(excerpt?.text_source);
  const ocrStatus = stringValue(excerpt?.ocr_status);
  const engine = stringValue(excerpt?.ocr_engine);
  const language = stringValue(excerpt?.ocr_language);
  const error = stringValue(excerpt?.ocr_error);
  const confidence = confidenceText(excerpt?.ocr_confidence);

  if (ocrStatus === "running") {
    return {
      label: "OCR running",
      detail: engine ? `Trying ${engine}.` : "Rendering this PDF page for OCR.",
      error: null,
      tone: "running" as const,
    };
  }

  if (textSource === "ocr" || ocrStatus === "done") {
    return {
      label: `OCR complete${engine ? `: ${engine}` : ""}`,
      detail: [
        confidence ? `Confidence ${confidence}` : null,
        language ? `Language ${language}` : null,
      ]
        .filter(Boolean)
        .join(" · "),
      error: null,
      tone: "good" as const,
    };
  }

  if (textSource === "low_text_fallback" || ocrStatus === "failed" || error) {
    return {
      label: "OCR failed: retry page",
      detail: engine ? `Attempted ${engine}.` : "OCR could not produce enough reliable text.",
      error,
      tone: "bad" as const,
    };
  }

  return {
    label: "Native text found",
    detail: "Using the PDF text layer for extraction.",
    error: null,
    tone: "neutral" as const,
  };
}

function confidenceText(value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return `${Math.round(value * 100)}%`;
}

function stageLabel(stage: string) {
  if (stage === "pending") return "Ready to begin intake.";
  if (stage === "pages_extracting") return "Extracting page summaries.";
  if (stage === "pages_done") return "Pages are ready for summary.";
  if (stage === "summary_pending") return "Summary generation requested.";
  return "Extraction stage complete.";
}

function skippedPagesText(value: unknown) {
  if (!Array.isArray(value) || value.length === 0) return null;
  return `Skipped cached page(s): ${value.join(", ")}`;
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function recordStringValue(record: Record<string, unknown> | null | undefined, key: string) {
  if (!record) return null;
  return stringValue(record[key]);
}

function numberValue(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && /^\d+$/.test(value)) return Number(value);
  return null;
}

function clampPercent(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, Math.round(value)));
}

function formatDate(value: string | null | undefined) {
  if (!value) return "scheduled retry time";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}
