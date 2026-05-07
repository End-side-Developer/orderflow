"use client";

import { useEffect, useState, useRef } from "react";
import { MessageCircle, X, Send, AlertCircle, Loader2 } from "lucide-react";

import { useAuthStore } from "@/lib/auth/store";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useAiChat, type ChatMessage } from "./use-ai-chat";

export function AiChatWidget() {
  const status = useAuthStore((s) => s.status);
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const { messages, isLoading, error, send } = useAiChat();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOpen = () => setOpen(true);
    window.addEventListener("orderflow:open-ai-chat", handleOpen);
    return () => window.removeEventListener("orderflow:open-ai-chat", handleOpen);
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  if (status !== "authed") return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    send(input);
    setInput("");
  };

  return (
    <>
      {/* Floating Action Button */}
      <Button
        size="icon"
        className="fixed bottom-6 right-6 h-14 w-14 rounded-full shadow-lg z-50 p-0 hover:scale-105 transition-transform"
        aria-label="Open AI assistant"
        onClick={() => setOpen(true)}
      >
        <MessageCircle className="h-6 w-6" />
      </Button>

      {/* Chat Sheet */}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="w-full sm:max-w-md flex flex-col p-6 z-50">
          <SheetHeader className="mb-4">
            <SheetTitle className="flex items-center gap-2">
              <MessageCircle className="h-5 w-5" /> AI Assistant
            </SheetTitle>
            <SheetDescription>
              I can help you navigate OrderFlow and define terminology.
            </SheetDescription>
          </SheetHeader>

          <div className="flex-1 flex flex-col overflow-hidden relative min-h-0 bg-muted/30 rounded-md border border-border">
            <div className="flex-1 overflow-y-auto p-4 space-y-4" ref={scrollRef}>
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] rounded-lg px-4 py-2 text-sm ${
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground"
                        : "bg-background border border-border text-foreground"
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              ))}

              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-background border border-border rounded-lg px-4 py-2 text-sm flex items-center text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin mr-2" /> Typing...
                  </div>
                </div>
              )}

              {error && (
                <Alert variant="destructive" className="mt-4">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
            </div>

            <form
              onSubmit={handleSubmit}
              className="p-3 bg-background border-t border-border flex items-center gap-2"
            >
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Type your message..."
                disabled={isLoading}
                className="flex-1"
                maxLength={500}
              />
              <Button type="submit" size="icon" disabled={!input.trim() || isLoading}>
                <Send className="h-4 w-4" />
              </Button>
            </form>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
