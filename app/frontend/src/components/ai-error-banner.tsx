"use client";

import {
  AlertTriangle,
  Clock,
  Globe,
  Inbox,
  KeyRound,
  Lock,
  Network,
  Puzzle,
  RefreshCw,
  ShieldAlert,
  ShieldX,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { ApiFailure } from "@/lib/api/client";
import { cn } from "@/lib/utils";

type GeminiErrorCode =
  | "gemini_quota_exhausted"
  | "gemini_missing_key"
  | "gemini_auth_error"
  | "gemini_bad_request"
  | "gemini_server_error"
  | "gemini_timeout"
  | "gemini_network_error"
  | "gemini_invalid_json"
  | "gemini_empty_response"
  | "gemini_safety_blocked"
  | "gemini_unexpected_error"
  | "gemini_error";

type Tone = "warn" | "destructive" | "info";

type ErrorRecipe = {
  icon: React.ReactNode;
  title: string;
  guidance: string;
  tone: Tone;
  retryHint?: (retryAfter: number | null) => string | null;
};

function formatRetry(seconds: number): string {
  if (seconds >= 3600) return `${Math.round(seconds / 3600)}h`;
  if (seconds >= 60) return `${Math.round(seconds / 60)}m`;
  return `${seconds}s`;
}

const RECIPES: Record<GeminiErrorCode | "default", ErrorRecipe> = {
  gemini_quota_exhausted: {
    icon: <Clock />,
    title: "Gemini quota exhausted",
    guidance:
      "Hit Google's per-minute or per-day rate limit. The next call works once the window refreshes.",
    tone: "warn",
    retryHint: (s) => (s ? `Retry in about ${formatRetry(s)}.` : "Retry in about a minute."),
  },
  gemini_missing_key: {
    icon: <KeyRound />,
    title: "Gemini API key missing",
    guidance:
      "The backend has no Gemini key configured. Add ORDERFLOW_AI_GEMINI_API_KEY to the .env files and restart the API.",
    tone: "destructive",
  },
  gemini_auth_error: {
    icon: <Lock />,
    title: "Gemini rejected the API key",
    guidance:
      "The API key is invalid, expired, or lacks model access. Generate a new key at aistudio.google.com.",
    tone: "destructive",
  },
  gemini_bad_request: {
    icon: <ShieldAlert />,
    title: "Gemini didn't accept the request",
    guidance:
      "The model name or prompt structure was rejected. Check ORDERFLOW_AI_DEFAULT_MODEL has access.",
    tone: "destructive",
  },
  gemini_server_error: {
    icon: <Globe />,
    title: "Gemini service hiccup",
    guidance: "Google returned a 5xx — usually transient. Retry in a few seconds.",
    tone: "warn",
    retryHint: (s) => (s ? `Retry in ${formatRetry(s)}.` : "Retry in a few seconds."),
  },
  gemini_timeout: {
    icon: <RefreshCw />,
    title: "Gemini timed out",
    guidance:
      "Model took longer than the configured timeout. Retry, shrink the prompt, or raise ORDERFLOW_AI_TIMEOUT_SECONDS.",
    tone: "warn",
    retryHint: () => "Retry now.",
  },
  gemini_network_error: {
    icon: <Network />,
    title: "Network couldn't reach Gemini",
    guidance:
      "DNS / firewall / TLS error talking to generativelanguage.googleapis.com. Check the API container's network.",
    tone: "destructive",
    retryHint: () => "Retry once your connection is back.",
  },
  gemini_invalid_json: {
    icon: <Puzzle />,
    title: "Gemini returned malformed JSON",
    guidance: "Model wrapped its answer in extra text or broke its schema. Usually transient.",
    tone: "warn",
    retryHint: () => "Retry now.",
  },
  gemini_empty_response: {
    icon: <Inbox />,
    title: "Gemini returned no text",
    guidance:
      "Often hits the max_output_tokens cap. Try a shorter input or raise ORDERFLOW_AI_GEMINI_MAX_OUTPUT_TOKENS.",
    tone: "warn",
    retryHint: () => "Retry now.",
  },
  gemini_safety_blocked: {
    icon: <ShieldX />,
    title: "Gemini safety filter blocked the response",
    guidance: "Send this judgment to manual review — the AI extractor cannot process it.",
    tone: "destructive",
  },
  gemini_unexpected_error: {
    icon: <AlertTriangle />,
    title: "Unexpected AI error",
    guidance: "Something unanticipated failed inside the AI provider call.",
    tone: "warn",
    retryHint: () => "Retry once.",
  },
  gemini_error: {
    icon: <AlertTriangle />,
    title: "Gemini provider error",
    guidance: "The Gemini provider returned an error.",
    tone: "warn",
    retryHint: () => "Retry.",
  },
  default: {
    icon: <AlertTriangle />,
    title: "AI request failed",
    guidance: "The AI request did not complete.",
    tone: "warn",
    retryHint: () => "Retry.",
  },
};

interface AiErrorBannerProps {
  error: ApiFailure;
  onRetry?: () => void;
  compact?: boolean;
  className?: string;
}

export function AiErrorBanner({ error, onRetry, compact = false, className }: AiErrorBannerProps) {
  const code = (error.error.code ?? "") as GeminiErrorCode;
  const recipe = RECIPES[code] ?? RECIPES.default;
  const details = error.error.details ?? {};

  const retryAfterRaw = details.retry_after_seconds;
  const retryAfter = typeof retryAfterRaw === "number" ? retryAfterRaw : null;
  const retryable = details.retryable === true || (recipe.retryHint && retryAfter !== null);
  const providerDetail =
    typeof details.provider_detail === "string" && details.provider_detail.length > 0
      ? details.provider_detail
      : null;
  const retryHint = recipe.retryHint?.(retryAfter) ?? null;

  return (
    <Alert variant={recipe.tone} className={cn(className)}>
      {recipe.icon}
      <AlertTitle>{recipe.title}</AlertTitle>
      <AlertDescription>
        {!compact ? <p>{recipe.guidance}</p> : null}
        <p className="mt-1 font-mono text-[11px] opacity-70">
          {error.error.code ?? "unknown_error"}
          {error.request_id ? ` · ${error.request_id.slice(0, 8)}` : ""}
        </p>
        {retryHint ? (
          <p className="mt-1 text-xs font-semibold">{retryHint}</p>
        ) : null}
        {error.error.message && error.error.message !== recipe.title ? (
          <p className="mt-2 break-words rounded-md bg-black/30 px-2 py-1 font-mono text-[11px] opacity-90">
            {error.error.message}
          </p>
        ) : null}
        {providerDetail && !compact ? (
          <details className="mt-2 text-xs">
            <summary className="cursor-pointer font-semibold opacity-80">Provider response</summary>
            <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md bg-black/40 p-2 text-[10px]">
              {providerDetail}
            </pre>
          </details>
        ) : null}
        {onRetry && retryable ? (
          <div className="mt-3">
            <Button size="sm" variant="outline" onClick={onRetry}>
              <RefreshCw />
              Retry
            </Button>
          </div>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}


