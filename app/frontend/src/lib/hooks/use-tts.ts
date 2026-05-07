"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

export type SupportedTtsLanguage = "en" | "hi" | "kn" | "ta" | "te" | "ml" | "mr";

export type TtsLanguageOption = {
  code: SupportedTtsLanguage;
  label: string;
  available: boolean;
};

export type TtsSpeakOptions = {
  language?: string | null;
  rate?: number;
};

export type TtsSpeakResult = {
  started: boolean;
  resolvedLanguage: SupportedTtsLanguage;
  hasMatchingVoice: boolean;
};

const SUPPORTED_LANGUAGE_CODES: SupportedTtsLanguage[] = ["en", "hi", "kn", "ta", "te", "ml", "mr"];

const LANGUAGE_LABELS: Record<SupportedTtsLanguage, string> = {
  en: "English",
  hi: "Hindi",
  kn: "Kannada",
  ta: "Tamil",
  te: "Telugu",
  ml: "Malayalam",
  mr: "Marathi",
};

const LANGUAGE_TAGS: Record<SupportedTtsLanguage, string> = {
  en: "en-IN",
  hi: "hi-IN",
  kn: "kn-IN",
  ta: "ta-IN",
  te: "te-IN",
  ml: "ml-IN",
  mr: "mr-IN",
};

function clampRate(value: number | undefined): number {
  if (typeof value !== "number" || Number.isNaN(value)) return 1;
  return Math.min(2, Math.max(0.5, value));
}

function matchesLanguageCode(voiceLang: string, languageCode: SupportedTtsLanguage): boolean {
  const normalized = voiceLang.toLowerCase();
  return normalized.startsWith(`${languageCode}-`) || normalized === languageCode;
}

function findVoiceForLanguage(
  voices: SpeechSynthesisVoice[],
  languageCode: SupportedTtsLanguage,
): SpeechSynthesisVoice | null {
  const preferredTag = LANGUAGE_TAGS[languageCode].toLowerCase();
  const exactPreferred = voices.find((voice) => voice.lang.toLowerCase() === preferredTag);
  if (exactPreferred) return exactPreferred;

  const byCode = voices.find((voice) => matchesLanguageCode(voice.lang, languageCode));
  if (byCode) return byCode;

  if (languageCode === "en") {
    return voices.find((voice) => voice.lang.toLowerCase().startsWith("en-")) ?? null;
  }
  return null;
}

export function normalizeTtsLanguage(value: string | null | undefined): SupportedTtsLanguage {
  if (!value) return "en";
  const normalized = value.toLowerCase().replace("_", "-");
  const base = normalized.split("-")[0];
  if (SUPPORTED_LANGUAGE_CODES.includes(base as SupportedTtsLanguage)) {
    return base as SupportedTtsLanguage;
  }
  return "en";
}

export function useTts() {
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isPaused, setIsPaused] = useState(false);

  const isSupported =
    typeof window !== "undefined" &&
    "speechSynthesis" in window &&
    "SpeechSynthesisUtterance" in window;

  useEffect(() => {
    if (!isSupported) return;

    const synth = window.speechSynthesis;
    const updateVoices = () => {
      setVoices(synth.getVoices());
    };

    updateVoices();
    synth.addEventListener("voiceschanged", updateVoices);
    return () => {
      synth.removeEventListener("voiceschanged", updateVoices);
    };
  }, [isSupported]);

  const stop = useCallback(() => {
    if (!isSupported) return;
    window.speechSynthesis.cancel();
    utteranceRef.current = null;
    setIsSpeaking(false);
    setIsPaused(false);
  }, [isSupported]);

  useEffect(() => stop, [stop]);

  const pause = useCallback(() => {
    if (!isSupported) return;
    if (!window.speechSynthesis.speaking) return;
    window.speechSynthesis.pause();
    setIsPaused(true);
  }, [isSupported]);

  const resume = useCallback(() => {
    if (!isSupported) return;
    if (!window.speechSynthesis.paused) return;
    window.speechSynthesis.resume();
    setIsPaused(false);
  }, [isSupported]);

  const speak = useCallback(
    (text: string, options?: TtsSpeakOptions): TtsSpeakResult => {
      const resolvedLanguage = normalizeTtsLanguage(options?.language);
      if (!isSupported || !text.trim()) {
        return { started: false, resolvedLanguage, hasMatchingVoice: false };
      }

      stop();

      const utterance = new SpeechSynthesisUtterance(text.trim());
      utterance.lang = LANGUAGE_TAGS[resolvedLanguage];
      utterance.rate = clampRate(options?.rate);

      const matchedVoice = findVoiceForLanguage(voices, resolvedLanguage);
      if (matchedVoice) utterance.voice = matchedVoice;

      utterance.onstart = () => {
        setIsSpeaking(true);
        setIsPaused(false);
      };
      utterance.onend = () => {
        setIsSpeaking(false);
        setIsPaused(false);
        utteranceRef.current = null;
      };
      utterance.onpause = () => {
        setIsPaused(true);
      };
      utterance.onresume = () => {
        setIsPaused(false);
      };
      utterance.onerror = () => {
        setIsSpeaking(false);
        setIsPaused(false);
        utteranceRef.current = null;
      };

      utteranceRef.current = utterance;
      window.speechSynthesis.speak(utterance);
      return {
        started: true,
        resolvedLanguage,
        hasMatchingVoice: Boolean(matchedVoice),
      };
    },
    [isSupported, stop, voices],
  );

  const supportedLanguages = useMemo<TtsLanguageOption[]>(
    () =>
      SUPPORTED_LANGUAGE_CODES.map((code) => ({
        code,
        label: LANGUAGE_LABELS[code],
        available: voices.some((voice) => matchesLanguageCode(voice.lang, code)),
      })),
    [voices],
  );

  return {
    speak,
    pause,
    resume,
    stop,
    isSpeaking,
    isPaused,
    isSupported,
    voices,
    supportedLanguages,
  };
}
