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
  
  // Automatically calculate target time for countdown
  const targetDate = useMemo(() => {
    if (progress?.paused_until) {
      return new Date(progress.paused_until);
    }
    if (progress?.updated_at && progress?.retry_after_seconds) {
      return new Date(new Date(progress.updated_at).getTime() + progress.retry_after_seconds * 1000);
    }
    return null;
  }, [progress?.paused_until, progress?.updated_at, progress?.retry_after_seconds]);

  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(progress?.retry_after_seconds ?? null);

  useEffect(() => {
    if (!targetDate) {
      setRemainingSeconds(progress?.retry_after_seconds ?? null);
      return;
    }
    const updateTimer = () => {
      const diff = Math.floor((targetDate.getTime() - Date.now()) / 1000);
      setRemainingSeconds(diff > 0 ? diff : 0);
    };
    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [targetDate?.getTime(), progress?.retry_after_seconds]);

  const retryMessage = remainingSeconds !== null 
    ? `Retrying in ${remainingSeconds}s.` 
    : (progress?.paused_until ? `Paused until ${formatDate(progress?.paused_until)}.` : null);

  const failureReason = recordStringValue(
    progress?.current_page_excerpt,
    "error_message",
  );
  const failureCode = recordStringValue(progress?.current_page_excerpt, "error_code");
  const technicalError = recordStringValue(
    progress?.current_page_excerpt,
    "technical_error_type",
  );
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
      setActionError(
        error instanceof Error ? error.message : "Could not start intake.",
      );
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
      setActionError(
        error instanceof Error ? error.message : "Could not continue.",
      );
    } finally {
      setIsContinuing(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col gap-5 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-950">
            Page extraction
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            {statusMessage}
          </p>
          {progress?.next_action ? (
            <p className="mt-1 text-xs font-medium text-slate-500">
              Next: {progress.next_action}
            </p>
          ) : null}
        </div>
        <Badge variant={canContinue ? "good" : "secondary"}>
          {stage.replaceAll("_", " ")}
        </Badge>
        <Badge variant={isPolling ? "muted" : "good"}>
          {isPolling ? "Polling fallback" : "Live updates"}
        </Badge>
      </div>

      {actionError ? (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Request failed</AlertTitle>
          <AlertDescription>{actionError}</AlertDescription>
        </Alert>
      ) : null}

      {progress?.error?.message ? (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Extraction error</AlertTitle>
          <AlertDescription>{progress.error.message}</AlertDescription>
        </Alert>
      ) : null}

      {isPaused || retryMessage ? (
        <Alert>
          <Clock3 className="h-4 w-4" />
          <AlertTitle>Retry scheduled</AlertTitle>
          <AlertDescription>
            {retryMessage ?? `Paused until ${formatDate(progress?.paused_until)}`}
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="space-y-3 rounded-md border border-slate-200 p-4">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-medium text-slate-700">
            Pages completed
          </span>
          <span className="text-sm font-semibold tabular-nums text-slate-950">
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

      <div className="rounded-md border border-slate-200 p-4">
        <div className="mb-3 flex items-center gap-2">
          <FileText className="h-4 w-4 text-slate-500" />
          <h3 className="text-sm font-semibold text-slate-900">
            Current page excerpt
          </h3>
        </div>
        <p className="max-h-40 overflow-y-auto whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">
          {excerpt.text || "No excerpt available yet."}
        </p>
        {failureReason ? (
          <div className="mt-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">
            <div className="font-semibold">Why it failed</div>
            <div className="mt-1 leading-5">{failureReason}</div>
            <div className="mt-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => void handleStartIntake(true)}
                disabled={isStarting}
              >
                <RefreshCw className="mr-2 h-3 w-3" />
                Retry intake
              </Button>
            </div>

            {(failureCode || technicalError) ? (
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
        {cacheStatus ? (
          <Badge variant="muted" className="mt-3">
            {cacheStatus}
          </Badge>
        ) : null}
      </div>

      <div className="rounded-md border border-slate-200 p-4">
        <div className="mb-3 flex items-center gap-2">
          {ocrStatus.tone === "good" ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          ) : ocrStatus.tone === "bad" ? (
            <AlertTriangle className="h-4 w-4 text-rose-600" />
          ) : ocrStatus.tone === "running" ? (
            <Loader2 className="h-4 w-4 animate-spin text-slate-500" />
          ) : (
            <FileText className="h-4 w-4 text-slate-500" />
          )}
          <h3 className="text-sm font-semibold text-slate-900">Text source</h3>
        </div>
        <div className="space-y-2 text-sm">
          <div className="font-medium text-slate-900">{ocrStatus.label}</div>
          {ocrStatus.detail ? (
            <div className="leading-5 text-slate-600">{ocrStatus.detail}</div>
          ) : null}
          {ocrStatus.error ? (
            <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">
              {ocrStatus.error}
            </div>
          ) : null}
        </div>
      </div>

      <div className="mt-auto flex flex-wrap gap-3 border-t border-slate-200 pt-5">
        <Button
          type="button"
          variant="outline"
          onClick={() => void handleStartIntake()}
          disabled={canStart || isStarting}
        >
          <RefreshCw />
          Refresh intake
        </Button>
        <Button
          type="button"
          variant="good"
          onClick={() => void handleContinueToSummary()}
          disabled={!canContinue || isContinuing}
        >
          {isContinuing ? (
            <Loader2 className="animate-spin" />
          ) : (
            <ArrowRight />
          )}
          Continue to Summary
        </Button>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md bg-slate-50 px-3 py-2">
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className="mt-1 font-semibold tabular-nums text-slate-950">
        {value}
      </div>
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
      detail: [confidence ? `Confidence ${confidence}` : null, language ? `Language ${language}` : null]
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
