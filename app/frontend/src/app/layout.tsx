import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Inter } from "next/font/google";

import { TopNav } from "@/components/top-nav";
import { AuthProvider } from "@/lib/auth/provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AiChatWidget } from "@/components/ai-chat/ai-chat-widget";

import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "OrderFlow",
  description: "Judgment-to-action workflow for execution teams.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} dark`}>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <TooltipProvider delayDuration={150}>
          <AuthProvider>
            <div className="flex min-h-screen flex-col">
              <TopNav />
              <main className="mx-auto w-full max-w-[1380px] flex-1 px-6 py-8">{children}</main>
              <AiChatWidget />
            </div>
          </AuthProvider>
        </TooltipProvider>
      </body>
    </html>
  );
}
