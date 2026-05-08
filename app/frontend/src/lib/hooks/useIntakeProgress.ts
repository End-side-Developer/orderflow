import { useEffect, useRef, useState } from "react";
import {
  ExtractionJobStatusData,
  getCaseIntakeEventsUrl,
  getCaseIntakeStatus,
} from "../api/client";

export type UseIntakeProgressResult = {
  data: ExtractionJobStatusData | null;
  error: Error | null;
  isLoading: boolean;
  isPolling: boolean;
};

export function useIntakeProgress(documentId: string | null): UseIntakeProgressResult {
  const [data, setData] = useState<ExtractionJobStatusData | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isPolling, setIsPolling] = useState<boolean>(false);

  const eventSourceRef = useRef<EventSource | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    let cancelled = false;

    function cleanup() {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }

      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    }

    async function fetchStatus(options: { initial?: boolean } = {}) {
      if (!documentId || cancelled) return;

      try {
        const res = await getCaseIntakeStatus(documentId);

        if (cancelled) return;

        if (res.ok) {
          setData((previous) => {
            const previousSignature = previous ? JSON.stringify(previous) : "";
            const nextSignature = JSON.stringify(res.data);

            if (previousSignature === nextSignature) {
              return previous;
            }

            return res.data;
          });
          setError(null);
        } else {
          setError(new Error(res.error.message || "Failed to fetch intake status"));
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err : new Error("Unknown intake status error"));
        }
      } finally {
        if (options.initial && !cancelled) {
          setIsLoading(false);
        }
      }
    }

    if (!documentId) {
      cleanup();
      setData(null);
      setError(null);
      setIsLoading(false);
      setIsPolling(false);
      return cleanup;
    }

    cleanup();
    setIsLoading(true);
    setError(null);
    setIsPolling(true);

    void fetchStatus({ initial: true });

    // Reliable polling. This is the important fix.
    // SSE is useful, but polling guarantees UI updates even when SSE is silent.
    pollIntervalRef.current = setInterval(() => {
      void fetchStatus();
    }, 2000);

    // Optional SSE fast path.
    try {
      const url = getCaseIntakeEventsUrl(documentId);
      const eventSource = new EventSource(url, { withCredentials: true });
      eventSourceRef.current = eventSource;

      const handleStatusEvent = (event: MessageEvent<string>) => {
        try {
          const parsedData = parseStatusEventData(event.data);

          if (parsedData && !cancelled) {
            setData(parsedData);
            setError(null);
          }
        } catch (e) {
          console.error("Failed to parse SSE data", e);
        }
      };

      eventSource.onmessage = handleStatusEvent;
      eventSource.addEventListener("intake_status", handleStatusEvent);

      eventSource.onerror = (err) => {
        console.error("SSE error. Keeping polling active.", err);

        if (eventSourceRef.current) {
          eventSourceRef.current.close();
          eventSourceRef.current = null;
        }
      };
    } catch (e) {
      console.error("EventSource failed. Polling remains active.", e);
    }

    return () => {
      cancelled = true;
      cleanup();
      setIsPolling(false);
    };
  }, [documentId]);

  return { data, error, isLoading, isPolling };
}

function parseStatusEventData(rawData: string): ExtractionJobStatusData | null {
  const parsed: unknown = JSON.parse(rawData);

  if (isExtractionJobStatusData(parsed)) {
    return parsed;
  }

  if (isRecord(parsed) && isExtractionJobStatusData(parsed.data)) {
    return parsed.data;
  }

  return null;
}

function isExtractionJobStatusData(value: unknown): value is ExtractionJobStatusData {
  return (
    isRecord(value) &&
    typeof value.document_id === "string" &&
    typeof value.stage === "string"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}