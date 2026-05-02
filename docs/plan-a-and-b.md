# Two Plans — UI Simplification + Home Page Quick Access

## Context

OrderFlow is a Next.js 16 + React 19 + TypeScript legal-tech web app (Tailwind + shadcn/Radix) for India's court case management. It uses domain-specific jargon (Obligations, Escalate, Triage, Workbench, CCMS, Audit trail, Proof) that confuses everyday users (citizens, junior advocates). After login users land on `/dashboard`, a role-aware page that already lists a couple of cards but doesn't make help (AI assistant) or advocate discovery prominent.

This document captures **two independent plans** the user requested:

- **Plan A** — rename complex UI labels to plain language and add reusable info-icon tooltips. Backend stays untouched (UI terminology only).
- **Plan B** — surface an AI chatbot and the existing advocate directory on the post-login home page in a standardized way, well-managed across roles.

The plans can be shipped in either order; Plan A gives quick UX wins with low risk, Plan B requires more new code (a new backend route + a global widget).

---

## PLAN A — Simplify UI Terminology + Add (i) Info Buttons

### Goal
Replace jargony UI labels with plain-language alternatives any user understands. Each renamed term gets a small `(i)` icon that reveals "what this is / what to do here" on hover or focus. Backend identifiers, routes, and API shapes stay unchanged.

### Files to create
- `src/lib/glossary.ts` — single source of truth for term entries:
  ```ts
  export interface GlossaryEntry {
    simpleLabel: string;     // shown to user
    originalLabel: string;   // for reference inside tooltip
    helpText: string;        // 1-sentence "what / why / what to do"
  }
  export const GLOSSARY: Record<string, GlossaryEntry> = {
    obligations:       { simpleLabel: "Court duties",     originalLabel: "Obligations",   helpText: "Required actions a court has ordered. Review them and mark them done with proof." },
    escalate:          { simpleLabel: "Urgent issues",    originalLabel: "Escalate",      helpText: "Items flagged as high-risk that need immediate review." },
    triage:            { simpleLabel: "Sort by urgency",  originalLabel: "Triage",        helpText: "Prioritize items so the most urgent ones get attention first." },
    intake:            { simpleLabel: "Add new case",     originalLabel: "Intake",        helpText: "Upload a new judgment to start the workflow." },
    workbench:         { simpleLabel: "Case overview",    originalLabel: "Workbench",     helpText: "Summary of all your active cases in one place." },
    ccms:              { simpleLabel: "Court system details", originalLabel: "CCMS / CIS metadata", helpText: "Information from the official Indian e-Courts system." },
    "extraction-mode": { simpleLabel: "AI reading method",originalLabel: "Extraction mode", helpText: "How the AI reads and extracts information from the document." },
    "audit-trail":     { simpleLabel: "Change history",   originalLabel: "Audit trail",   helpText: "Full record of every change made and who made it." },
    verifications:     { simpleLabel: "Advocate approvals", originalLabel: "Verifications", helpText: "Review and approve advocate registration requests." },
    proof:             { simpleLabel: "Evidence",         originalLabel: "Proof",         helpText: "Supporting document showing a duty was completed." },
    departments:       { simpleLabel: "Government offices", originalLabel: "Departments", helpText: "Performance and load across government departments." },
    analyze:           { simpleLabel: "Read documents",   originalLabel: "Analyze",       helpText: "View AI-generated page summaries and highlights." },
    verify:            { simpleLabel: "Approve duties",   originalLabel: "Verify",        helpText: "Approve, reject, or close court duties with evidence." },
  };
  ```

- `src/components/info-hint.tsx` — reusable `<InfoHint glossaryKey="obligations" />` (or `text="..."`) that renders a Lucide `Info` icon wrapped in shadcn `Tooltip`. Works for keyboard focus and touch (uses Radix Tooltip; existing `TooltipProvider` is already mounted in [layout.tsx:22](Application/orderflow/app/frontend/src/app/layout.tsx#L22)).
  ```tsx
  export function InfoHint({ glossaryKey, text, side = "top" }: Props) {
    const body = text ?? GLOSSARY[glossaryKey!]?.helpText;
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <button type="button" aria-label="More info"
            className="inline-flex h-4 w-4 items-center justify-center rounded-full text-muted-foreground hover:text-foreground">
            <Info className="h-3.5 w-3.5" />
          </button>
        </TooltipTrigger>
        <TooltipContent side={side} className="max-w-xs">{body}</TooltipContent>
      </Tooltip>
    );
  }
  ```

### Files to modify
- [src/lib/labels.ts](Application/orderflow/app/frontend/src/lib/labels.ts) — extend `RouteDescriptor` with optional `simpleLabel` and `helpText`. Populate per route (Intake → "Add new case", Analyze → "Read documents", Verify → "Approve duties", Escalate → "Urgent issues", Departments → "Government offices", Workbench/Overview → "Case overview"). Keep `label` so logs/breadcrumbs stay readable.
- [src/components/top-nav.tsx](Application/orderflow/app/frontend/src/components/top-nav.tsx) — render `route.simpleLabel ?? route.label`. In the workflow stepper, append `<InfoHint glossaryKey={route.key} />` after each label (visible only at `lg:` breakpoint to prevent crowding).
- [src/app/dashboard/page.tsx](Application/orderflow/app/frontend/src/app/dashboard/page.tsx) — every `<CardTitle>` ("Workbench", "Intake", "Verifications", "Case analysis", "Advocate directory") swaps to its simple label + adjacent `<InfoHint />`. Buttons reuse plainer verbs ("Open case overview", "Add new case", "Approve duties").
- Page sweep (H1 + section headings + table column headers — leave body prose for v2):
  - `src/app/obligations/page.tsx`
  - `src/app/risk/page.tsx`
  - `src/app/upload/page.tsx`
  - `src/app/document-summary/page.tsx`
  - `src/app/admin/verifications/page.tsx`
  - `src/app/departments/page.tsx`

### Implementation order
1. Add `glossary.ts` with all entries.
2. Build `InfoHint` and verify rendering inside the existing TooltipProvider.
3. Extend `labels.ts` types/ROUTES.
4. Update `top-nav.tsx` (lowest blast radius).
5. Update `dashboard/page.tsx`.
6. Sweep the six page files.
7. `Grep` for `Obligations|Escalate|Triage|Workbench|CCMS|Extraction|Audit` across `src/app/**/*.tsx` to catch stragglers.

### Verification
- `npm run dev`; sign in as each role (citizen, advocate, judge, government) and confirm new labels in nav + dashboard.
- Hover and keyboard-focus every `(i)` → tooltip shows correct `helpText`.
- Workflow stepper still highlights the active stage (label change shouldn't affect routing — matching is by `href`).
- `npm run lint` and `npm run typecheck` pass.
- Network tab: confirm no API payload field renames (proves backend untouched).

### Risks / notes
- Tooltip on the workflow stepper may overflow at `lg`; use `side="bottom"` if needed.
- Glossary keys overlap with `RouteKey` for some terms but not all (triage, ccms, extraction-mode, audit-trail, proof have no route) — keep `GLOSSARY` separate from `ROUTES` to avoid coupling.
- This work is the natural foundation for future i18n (Hindi, Tamil, etc.) — the glossary becomes the resource bundle.

---

## PLAN B — Show AI Chatbot + Advocate Directory on the Home Page

### Goal
Make help and advocate-discovery one click away from any authenticated screen. Add a global floating AI chat button (Gemini-backed) plus a prominent "Find an Advocate" card on the dashboard for **every** role, and a "Featured advocates" preview for citizens. Standardized using existing shadcn cards, Tailwind tokens, and Lucide icons.

### Files to create

**Frontend**
- `src/components/ai-chat/ai-chat-widget.tsx` — auth-gated FAB (`MessageCircle` icon, fixed bottom-right, `z-50`) that opens a shadcn `Sheet` containing a chat surface (input, message list, loading state, error pill). Returns `null` when not authenticated. Listens for a custom DOM event `orderflow:open-ai-chat` so other UI (dashboard card) can open it programmatically.
- `src/components/ai-chat/use-ai-chat.ts` — hook holding `messages`, `send(prompt)`, `isLoading`, `error`. Calls `postAiChat`.
- `src/components/dashboard/featured-advocates.tsx` — client component that calls `listAdvocatesDirectory({ sort: "rating", limit: 3 })` and renders three cards with name, specialization badge, rating, and a "View profile" link.
- `src/components/dashboard/quick-action-card.tsx` — small standardized card (`<Icon /> Title  →` button) reused for both quick actions (chat + advocates) so spacing/typography stay consistent.

**Backend**
- `app/backend/src/orderflow_api/schemas/ai_chat.py` — `AiChatRequest { message: str, context?: Literal["navigation","legal_term","case_help"] }` and `AiChatResponse { reply: str, model: str }`.
- `app/backend/src/orderflow_api/api/routes/ai_chat.py` — `POST /ai/chat` (auth required). Wraps the existing `core/gemini_client.py` with a constrained system prompt: "You are OrderFlow's help assistant. Answer concisely. Do not provide legal advice. Constrain responses to navigation, definitions of OrderFlow terms, and case-help guidance." Returns the reply text. No persistence in v1.

### Files to modify
- [src/app/layout.tsx](Application/orderflow/app/frontend/src/app/layout.tsx) — mount `<AiChatWidget />` once inside the auth provider so it appears on every authenticated page.
- [src/app/dashboard/page.tsx](Application/orderflow/app/frontend/src/app/dashboard/page.tsx) — restructure so a top "Quick actions" grid renders for **every** role with two always-present cards:
  1. **"Find an Advocate"** — icon `Users`/`Scale`, links to `/advocates`.
  2. **"Ask AI Assistant"** — icon `MessageCircle`, fires `window.dispatchEvent(new Event("orderflow:open-ai-chat"))`.

  Citizen branch additionally renders `<FeaturedAdvocates />` under the quick actions.
- [src/lib/api/client.ts](Application/orderflow/app/frontend/src/lib/api/client.ts) — add `postAiChat({ message, context })`. Confirm `listAdvocatesDirectory` accepts `sort` and `limit` (or extend it).
- [app/backend/src/orderflow_api/api/router.py](Application/orderflow/app/backend/src/orderflow_api/api/router.py) — `include_router(ai_chat_router)`.
- [app/backend/src/orderflow_api/api/routes/advocates.py](Application/orderflow/app/backend/src/orderflow_api/api/routes/advocates.py) — verify `GET /advocates?sort=rating&limit=3` works; fall back to `verified=true` ordered by `verified_at desc` if rating sort is missing.

### Implementation order
1. Backend: schemas → `ai_chat.py` route → register in `router.py` → manually `curl -X POST /api/ai/chat` with auth cookie to confirm.
2. Frontend client: add `postAiChat` in `lib/api/client.ts`.
3. Build `useAiChat` hook, then `AiChatWidget`; mount in `layout.tsx`.
4. Add `QuickActionCard`; refactor `dashboard/page.tsx` so both quick actions render for every role.
5. Build `FeaturedAdvocates`; render under the citizen branch.
6. Polish: dark-theme tokens (`bg-card`, `border-border`, `text-muted-foreground`), focus rings on the FAB, `aria-label="Open AI assistant"`, `z-50` so the FAB beats the sticky header (`z-40`).

### Verification
- Backend tests: happy-path POST `/ai/chat`; Gemini quota error maps to a friendly HTTP response.
- Manually `curl -X POST` with valid auth → reply returned.
- Frontend: log in as each role → dashboard shows both quick-action cards; citizen also sees three featured advocates.
- FAB visible bottom-right on `/dashboard`, `/advocates`, `/document-summary`, `/obligations`; **not** visible on `/login`, `/register`.
- Click FAB → Sheet opens → ask "What is an obligation?" → reply renders; loading spinner during request; friendly fallback for quota/error.
- Click "Ask AI Assistant" card on the dashboard → same Sheet opens.
- `npm run lint`, `npm run typecheck`, no new a11y warnings.

### Risks / open questions
- **Gemini quota**: surface `retry_after_seconds` from `GeminiQuotaError`; cap client-side prompt length (~1k chars).
- **No persistence in v1**: refresh wipes the conversation. If unacceptable, plan a `/ai/chat/sessions` table for v2.
- **Prompt safety**: constrain to informational help only ("not legal advice"). Reject obviously off-topic queries with a polite redirect.
- **Advocate sort**: confirm `advocates.py` exposes `sort=rating`; otherwise use `verified_at` fallback.
- **z-index**: FAB must use `z-50` (sticky header is `z-40`).

---

## Critical files

**Plan A**
- [src/lib/labels.ts](Application/orderflow/app/frontend/src/lib/labels.ts)
- [src/components/top-nav.tsx](Application/orderflow/app/frontend/src/components/top-nav.tsx)
- [src/app/dashboard/page.tsx](Application/orderflow/app/frontend/src/app/dashboard/page.tsx)
- (new) `src/lib/glossary.ts`, `src/components/info-hint.tsx`

**Plan B**
- [src/app/layout.tsx](Application/orderflow/app/frontend/src/app/layout.tsx)
- [src/app/dashboard/page.tsx](Application/orderflow/app/frontend/src/app/dashboard/page.tsx)
- [src/lib/api/client.ts](Application/orderflow/app/frontend/src/lib/api/client.ts)
- [app/backend/src/orderflow_api/api/router.py](Application/orderflow/app/backend/src/orderflow_api/api/router.py)
- (new) `src/components/ai-chat/*`, `src/components/dashboard/featured-advocates.tsx`, `app/backend/src/orderflow_api/api/routes/ai_chat.py`, `app/backend/src/orderflow_api/schemas/ai_chat.py`
