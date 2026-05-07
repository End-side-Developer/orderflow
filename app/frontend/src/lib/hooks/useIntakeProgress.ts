import { useState, useEffect, useRef } from "react";
import {
  getCaseIntakeEventsUrl,
  getCaseIntakeStatus,
  ExtractionJobStatusData,
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

  // Use refs to keep track of state within closures without triggering re-renders
  const fallbackPollingRef = useRef<boolean>(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (!documentId) {
      setData(null);
      setError(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);
    fallbackPollingRef.current = false;
    setIsPolling(false);

    // Initial fetch to get status immediately
    getCaseIntakeStatus(documentId)
      .then((res) => {
        if (res.ok) {
          setData(res.data);
          setError(null);
          // If already in a terminal state, we don't strictly need to open SSE, but we can rely on backend to close it or just not open it.
          // Let's open SSE anyway to get potential updates unless it's already finalized or failed permanently (but we don't have permanent fail state yet).
        } else {
          setError(new Error(res.error.message || "Failed to fetch initial status"));
        }
      })
      .catch((err) => {
        setError(err instanceof Error ? err : new Error("Unknown error"));
      })
      .finally(() => {
        setIsLoading(false);
      });

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

    function startPolling() {
      if (pollIntervalRef.current) return;

      fallbackPollingRef.current = true;
      setIsPolling(true);

      pollIntervalRef.current = setInterval(async () => {
        try {
          const res = await getCaseIntakeStatus(documentId!);
          if (res.ok) {
            setData(res.data);
            setError(null);
          } else {
            console.error("Polling error:", res.error);
          }
        } catch (e) {
          console.error("Polling exception:", e);
        }
      }, 2000);
    }

    // Attempt to connect via SSE
    try {
      const url = getCaseIntakeEventsUrl(documentId);
      const eventSource = new EventSource(url, { withCredentials: true });
      eventSourceRef.current = eventSource;

      const handleStatusEvent = (event: MessageEvent<string>) => {
        try {
          const parsedData = parseStatusEventData(event.data);
          if (parsedData) {
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
        console.error("SSE error, falling back to polling", err);
        // Close the failing SSE
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
          eventSourceRef.current = null;
        }
        // Start polling
        startPolling();
      };
    } catch (e) {
      console.error(
        "EventSource not supported or failed to initialize, falling back to polling",
        e,
      );
      startPolling();
    }

    return () => {
      cleanup();
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
    isRecord(value) && typeof value.document_id === "string" && typeof value.stage === "string"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
