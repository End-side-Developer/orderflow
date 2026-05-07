"use client";

import * as React from "react";
import {
  AlertTriangle,
  Clock,
  Globe,
  Inbox,
  KeyRound,
  Lock,
  RefreshCw,
  Server,
  ShieldAlert,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type AiErrorKind =
  | "no_provider_configured"
  | "missing_credentials"
  | "auth_failed"
  | "rate_limited"
  | "timeout"
  | "service_unavailable"
  | "request_too_large"
  | "model_unavailable"
  | "invalid_response"
  | "no_pages_extracted"
  | "extractor_unhealthy"
  | "unknown";

interface AiErrorRecipe {
  variant: "warn" | "destructive" | "info";
  title: string;
  description: string;
  icon: React.ReactNode;
}

const RECIPES: Record<AiErrorKind, AiErrorRecipe> = {
  no_provider_configured: {
    variant: "info",
    title: "AI provider not configured",
    description:
      "No AI provider is enabled on the backend. Configure a provider key, then retry the upload.",
    icon: <ShieldAlert />,
  },
  missing_credentials: {
    variant: "warn",
    title: "Missing API key",
    description:
      "The backend cannot reach the AI provider because the API key is missing or empty.",
    icon: <KeyRound />,
  },
  auth_failed: {
    variant: "destructive",
    title: "Authentication failed",
    description: "The configured AI key was rejected by the provider. Rotate the key and retry.",
    icon: <Lock />,
  },
  rate_limited: {
    variant: "warn",
    title: "Rate limited",
    description:
      "The AI provider is throttling requests. Wait a moment and retry, or lower batch size.",
    icon: <Clock />,
  },
  timeout: {
    variant: "warn",
    title: "Request timed out",
    description: "The AI provider did not respond in time. Retry the operation.",
    icon: <RefreshCw />,
  },
  service_unavailable: {
    variant: "warn",
    title: "Service unavailable",
    description: "The AI provider is currently unreachable. Retry shortly.",
    icon: <Globe />,
  },
  request_too_large: {
    variant: "warn",
    title: "Request too large",
    description: "The document or page is too large for a single AI call. Split it and retry.",
    icon: <Server />,
  },
  model_unavailable: {
    variant: "warn",
    title: "Model unavailable",
    description: "The configured model is not currently available on the provider.",
    icon: <ShieldAlert />,
  },
  invalid_response: {
    variant: "destructive",
    title: "Invalid AI response",
    description: "The AI returned an unexpected payload. The intake will retry on the next pass.",
    icon: <AlertTriangle />,
  },
  no_pages_extracted: {
    variant: "info",
    title: "No pages extracted",
    description: "The document had no extractable text pages. Check the source PDF.",
    icon: <Inbox />,
  },
  extractor_unhealthy: {
    variant: "destructive",
    title: "Extractor unhealthy",
    description: "The AI extractor service reported a degraded health check.",
    icon: <ShieldAlert />,
  },
  unknown: {
    variant: "warn",
    title: "AI extraction warning",
    description: "Something went wrong while talking to the AI provider.",
    icon: <AlertTriangle />,
  },
};

interface AiErrorAlertProps {
  kind?: AiErrorKind;
  message?: string | null;
  detail?: string | null;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}

export function AiErrorAlert({
  kind = "unknown",
  message,
  detail,
  onRetry,
  retryLabel = "Retry",
  className,
}: AiErrorAlertProps) {
  const recipe = RECIPES[kind] ?? RECIPES.unknown;

  return (
    <Alert variant={recipe.variant} className={cn(className)}>
      {recipe.icon}
      <AlertTitle>{recipe.title}</AlertTitle>
      <AlertDescription>
        <p>{message ?? recipe.description}</p>
        {detail ? <p className="mt-1 text-xs opacity-80">{detail}</p> : null}
        {onRetry ? (
          <div className="mt-3">
            <Button size="sm" variant="outline" onClick={onRetry}>
              <RefreshCw className="h-3.5 w-3.5" />
              {retryLabel}
            </Button>
          </div>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}


