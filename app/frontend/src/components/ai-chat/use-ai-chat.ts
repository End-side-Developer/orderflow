import { useState, useCallback } from "react";
import { postAiChat } from "@/lib/api/client";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export function useAiChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([{
    id: "init",
    role: "assistant",
    content: "Hi! I am the OrderFlow assistant. I can help with navigation, definitions, and case guidance. How can I help you today?"
  }]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = useCallback(async (prompt: string, context?: "navigation" | "legal_term" | "case_help") => {
    if (!prompt.trim()) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: "user",
      content: prompt.trim()
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);
    setError(null);

    const res = await postAiChat({ message: userMessage.content, context });
    
    setIsLoading(false);

    if (res.ok) {
      const assistantMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: res.data.reply
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } else {
      setError(res.error.message || "Failed to connect to AI assistant.");
    }
  }, []);

  return {
    messages,
    isLoading,
    error,
    send
  };
}
