# Theme 11 - OrderFlow

Tagline: Turn court judgments into verified, owner-assigned, deadline-safe actions.

## What OrderFlow Does

Government teams do not fail because judgments are unavailable. They fail because the next step is buried in a PDF, the owner is unclear, the deadline is missed, and no one sees the risk until it is too late.

OrderFlow turns each judgment into a verified obligation ledger. Every directive becomes a trackable task with a source citation, owner, deadline, proof requirement, and escalation path.

## Why OrderFlow Beats the Crowd

Most Theme 11 submissions focus on document extraction, dashboards, or generic compliance summaries. That is useful, but it is not enough.

OrderFlow is built around the threats those ideas leave behind:
- If the AI reads the judgment but misses the legal edge, OrderFlow sends the case into human review instead of guessing.
- If the action is extracted but not owned, OrderFlow assigns the obligation to a real department and a real deadline.
- If the team claims compliance without proof, OrderFlow blocks closure until evidence passes verification.
- If a judgment creates conflicting duties, OrderFlow exposes the conflict and escalates it.

This makes the product feel like a workflow system for government action, not another PDF parser.

## Core Moat

### 1. Verified Obligation Ledger
Convert each judgment directive into a single atomic obligation with owner, due date, dependency, and exact source citation.

### 2. Proof-Gated Completion
Completion only happens when evidence is attached and verified for relevance, date validity, and document match.

### 3. Risk and Escalation Engine
Track deadline pressure, blocked dependencies, and weak evidence so the system can warn before a miss happens.

## Flow 1: Cached Judgment to Verified Action Plan

```mermaid
flowchart TD
    A[Upload judgment PDF] --> B{Duplicate checksum?}
    B -->|Yes| C[Open existing cached case]
    B -->|No| D[Create document record]
    C --> E[Reviewer clicks Intake]
    D --> E
    E --> F[Temporal extracts cached page summaries]
    F --> G{Pages done?}
    G -->|No| H[Show progress, retry, or pause state]
    H --> F
    G -->|Yes| I[Reviewer generates full summary]
    I --> J[Reviewer generates action plan]
    J --> K[Human reviews each item]
    K --> L{All items decided?}
    L -->|No| K
    L -->|Yes| M[Finalize case]
    M --> N[Trusted dashboard shows approved records only]
```

## Flow 2: Risk and Escalation Loop

```mermaid
flowchart TD
    A[Open obligations] --> B[Check deadline pressure]
    B --> C[Check dependency blockers]
    C --> D[Check proof quality]
    D --> E{Risk threshold crossed?}
    E -->|No| F[Keep monitoring]
    E -->|Yes| G[Raise alert]
    G --> H[Recommend escalation or correction]
    H --> I[Update audit trail]
```

## Tech Stack

| Layer | Stack | Purpose |
| --- | --- | --- |
| Frontend | Next.js App Router + TypeScript | Reviewer flow, obligation board, and risk dashboard |
| API | FastAPI + Pydantic v2 | Typed workflow and verification APIs |
| Orchestration | Temporal | Durable task routing and escalation |
| Intelligence | LangGraph | Human-in-the-loop extraction and review control |
| Document parsing | Docling with OCR fallback | Structured parsing for digital and scanned PDFs |
| Storage | PostgreSQL + JSONB + pgvector | Audit-friendly case and evidence storage |
| Queue and cache | Redis | Short-lived workflow state |
| Files | MinIO in dev, S3-compatible storage | Judgment and evidence storage |
| Observability | OpenTelemetry | End-to-end traceability |
| Translation | LibreTranslate | Multi-language judgment support |

## Multi-Language Support

OrderFlow processes court judgments in regional Indian languages (Hindi, Tamil, Telugu, Kannada, Malayalam, Marathi) and English.

**How it works:**
1. **Upload**: Submit a case file in any supported language or English
2. **Auto-Detect**: System automatically detects the document language (with user override option)
3. **Translate**: Case file is translated to English for AI extraction
4. **Extract**: Obligations are extracted from the translated text
5. **Export**: Download the action plan in your original language or English

**Export API:**
- `GET /api/v1/exports/action-plan?document_id=<uuid>&language=<code>&format=markdown|json`
- `language` supports `en`, `hi`, `ta`, `te`, `kn`, `ml`, `mr`

**Supported Languages:**
- English (en)
- हिन्दी (Hindi, hi)
- தமிழ் (Tamil, ta)
- తెలుగు (Telugu, te)
- ಕನ್ನಡ (Kannada, kn)
- മലയാളം (Malayalam, ml)
- मराठी (Marathi, mr)

**Key Benefits:**
- Original court files are preserved for audit trail
- Translation metadata stored for compliance tracking
- Accurate extraction in AI's native language (English)
- User-friendly action plans in their preferred language
- Legal citations and technical terms remain intact for accuracy

For detailed setup and configuration, see [docs/language-support.md](docs/language-support.md).

## What Makes It Strong

- It does not stop at extraction.
- It does not trust the model blindly.
- It does not allow closure without proof.
- It does not hide risk inside a dashboard.

## Demo Storyline

1. Upload a judgment.
2. Click Intake to start durable page extraction.
3. Watch page progress, cache hits, retry pauses, and recovery state.
4. Generate the full judgment summary only after pages are done.
5. Generate the action plan from cached cited pages.
6. Approve, edit, reject, or surgically regenerate individual action items.
7. Finalize only after every action-plan item has a human decision.
8. Open the trusted dashboard, which shows approved or edited records only.

## Current Build Status

- The new gated case flow is implemented across FastAPI, Temporal worker, and the Next.js `/case/[id]` reviewer workspace.
- Manual API-driven E2E passed on 2026-05-04: duplicate upload reuse, intake, page extraction, summary generation, action-plan generation, 18 human approvals, finalize, and trusted dashboard.
- Cache behavior is covered by worker tests for page cache hits, prompt-version invalidation, resumability, full-summary cache hits, and action-plan one-shot behavior.
- Same-PDF re-upload is blocked by checksum with `409 duplicate_document`, returning the existing document id instead of starting another extraction.
- The trusted dashboard API rejects non-finalized cases and filters records server-side to human-approved or edited action-plan items.
- Current caveat: the root `python scripts/quality_check.py` gate is not green yet. Frontend lint/typecheck pass, but Prettier, backend flake8, and backend Black cleanup are still required before final cutover.

## Key Case Routes

- `POST /api/v1/documents/upload`
- `POST /api/v1/cases/{document_id}/intake/start`
- `GET /api/v1/cases/{document_id}/intake/status`
- `POST /api/v1/cases/{document_id}/summary/generate`
- `GET /api/v1/cases/{document_id}/summary`
- `POST /api/v1/cases/{document_id}/action-plan/generate`
- `GET /api/v1/cases/{document_id}/action-plan`
- `POST /api/v1/cases/{document_id}/action-plan/items/{obligation_id}/review`
- `POST /api/v1/cases/{document_id}/action-plan/items/{obligation_id}/regenerate`
- `POST /api/v1/cases/{document_id}/finalize`
- `GET /api/v1/cases/{document_id}/dashboard`

## Where To Continue

- Root development guide: DEVELOPMENT.md
- Service boundaries: app/README.md
