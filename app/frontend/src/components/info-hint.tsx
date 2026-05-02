"use client";

import { Info } from "lucide-react";
import { GLOSSARY } from "@/lib/glossary";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface InfoHintProps {
  glossaryKey?: string;
  text?: string;
  side?: "top" | "right" | "bottom" | "left";
}

export function InfoHint({ glossaryKey, text, side = "top" }: InfoHintProps) {
  const body = text ?? (glossaryKey ? GLOSSARY[glossaryKey]?.helpText : "");
  
  if (!body) return null;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label="More info"
          className="inline-flex h-4 w-4 items-center justify-center rounded-full text-muted-foreground hover:text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          <Info className="h-3.5 w-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent side={side} className="max-w-xs">
        <p className="text-sm">{body}</p>
      </TooltipContent>
    </Tooltip>
  );
}
