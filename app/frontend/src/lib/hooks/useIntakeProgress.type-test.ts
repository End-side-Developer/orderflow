import { useIntakeProgress } from "./useIntakeProgress";
import { ExtractionJobStatusData } from "../api/client";

// This file serves as a typecheck proof for the useIntakeProgress hook.

function TypeCheckHook() {
  const { data, error, isLoading, isPolling } = useIntakeProgress("doc-123");

  // Validate the exposed properties on data
  if (data) {
    const stage: ExtractionJobStatusData["stage"] = data.stage;
    const percent: number = data.percent;
    const pagesTotal: number = data.pages_total;
    const pagesCompleted: number = data.pages_completed;
    const excerpt: Record<string, unknown> | null = data.current_page_excerpt;
    const jobError: ExtractionJobStatusData["error"] = data.error;
    const pausedUntil: string | null = data.paused_until;
    const retryAfter: number | null = data.retry_after_seconds;
    const concurrency: number = data.current_concurrency;

    // Log them to avoid unused variables (using console.log as a dummy for type-checking)
    console.log(
      stage,
      percent,
      pagesTotal,
      pagesCompleted,
      excerpt,
      jobError,
      pausedUntil,
      retryAfter,
      concurrency,
    );
  }

  console.log(error, isLoading, isPolling);
}
