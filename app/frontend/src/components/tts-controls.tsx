"use client";

import { useEffect, useMemo, useState } from "react";
import { Pause, Play, Square, Volume2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { normalizeTtsLanguage, useTts, type SupportedTtsLanguage } from "@/lib/hooks/use-tts";

interface TtsControlsProps {
  text: string;
  preferredLanguage?: string | null;
  resetSignal?: string | number;
  className?: string;
}

export function TtsControls({
  text,
  preferredLanguage,
  resetSignal,
  className,
}: TtsControlsProps) {
  const {
    speak,
    pause,
    resume,
    stop,
    isSpeaking,
    isPaused,
    isSupported,
    supportedLanguages,
  } = useTts();

  const [language, setLanguage] = useState<SupportedTtsLanguage>(
    normalizeTtsLanguage(preferredLanguage),
  );
  const [rate, setRate] = useState(1);
  const [voiceWarning, setVoiceWarning] = useState<string | null>(null);

  useEffect(() => {
    setLanguage(normalizeTtsLanguage(preferredLanguage));
  }, [preferredLanguage]);

  useEffect(() => {
    stop();
    setVoiceWarning(null);
  }, [resetSignal, stop]);

  const activeLanguage = useMemo(
    () => supportedLanguages.find((option) => option.code === language) ?? null,
    [supportedLanguages, language],
  );

  function handlePlay() {
    const result = speak(text, { language, rate });
    if (!result.started) return;
    if (!result.hasMatchingVoice) {
      setVoiceWarning(
        `A native ${activeLanguage?.label ?? language.toUpperCase()} voice is unavailable on this device. Using best available voice.`,
      );
      return;
    }
    setVoiceWarning(null);
  }

  function handlePauseResume() {
    if (isPaused) {
      resume();
      return;
    }
    pause();
  }

  return (
    <div className={cn("flex flex-col gap-2 rounded-md border border-border bg-muted/20 p-3", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" onClick={handlePlay} disabled={!isSupported || !text.trim()}>
          <Play className="h-3.5 w-3.5" />
          Listen
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={handlePauseResume}
          disabled={!isSupported || !isSpeaking}
        >
          <Pause className="h-3.5 w-3.5" />
          {isPaused ? "Resume" : "Pause"}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={stop}
          disabled={!isSupported || (!isSpeaking && !isPaused)}
        >
          <Square className="h-3.5 w-3.5" />
          Stop
        </Button>
        <span className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground">
          <Volume2 className="h-3.5 w-3.5" />
          {Math.round(rate * 100)}%
        </span>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <Select value={language} onValueChange={(value) => setLanguage(value as SupportedTtsLanguage)}>
          <SelectTrigger className="h-8">
            <SelectValue placeholder="Language" />
          </SelectTrigger>
          <SelectContent>
            {supportedLanguages.map((option) => (
              <SelectItem key={option.code} value={option.code}>
                {option.label}
                {option.available ? "" : " (fallback)"}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="flex items-center gap-2 rounded-md border border-border bg-background px-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Speed
          </span>
          <input
            type="range"
            min={0.75}
            max={1.5}
            step={0.05}
            value={rate}
            onChange={(event) => setRate(Number(event.target.value))}
            className="h-8 w-full"
            aria-label="Speech rate"
          />
        </div>
      </div>

      {!isSupported ? (
        <p className="text-xs text-muted-foreground">
          Text-to-speech is not supported in this browser.
        </p>
      ) : null}

      {isSupported && !text.trim() ? (
        <p className="text-xs text-muted-foreground">No summary text available for this page yet.</p>
      ) : null}

      {voiceWarning ? <p className="text-xs text-muted-foreground">{voiceWarning}</p> : null}
    </div>
  );
}

