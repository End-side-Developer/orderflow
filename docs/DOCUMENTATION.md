# OrderFlow — Technical Documentation

> Turn court judgments into verified, owner-assigned, deadline-safe actions.

OrderFlow is a Theme-11 reference platform that ingests court judgments from
the Indian eCourts ecosystem and converts every directive into an atomic,
owner-assigned, deadline-safe **obligation** with full source provenance,
human review gates, proof-gated closure, and a public-trust read-only view.

This document is the single deep-dive reference for engineers, reviewers,
and integrators. It is self-contained: no external links, no
cross-references that depend on the surrounding repository.

---

## Table of Contents

1. Why OrderFlow Exists
2. Product Pillars
3. System Architecture
4. Repository Layout
5. Domain Model
6. The Gated Case Flow (Five Stages)
7. Intelligence Layer
8. API Surface
9. Multi-Language Support
10. Security, Auth, and Permissions
11. Observability
12. Local Development
13. Database Migrations
14. Configuration Reference
15. Demo Mode
16. Roadmap
17. Glossary

---

## 1. Why OrderFlow Exists

Government departments do not fail to implement court judgments because the
documents are unavailable. They fail because:

- the next step is **buried** inside a 40-page PDF;
- **ownership** of each step is unclear;
- **deadlines** drift silently until contempt is filed;
- **compliance evidence** is accepted on trust, not verified;
- **conflicting directives** across cases are invisible until they collide.

Most existing tools stop at document tracking. OrderFlow is a
*judiciary-to-executive execution layer*: each judgment becomes a verified
obligation ledger with proof-gated closure and a risk engine that warns the
team before a deadline misses.

---

## 2. Product Pillars

| Pillar                        | What it means                                                                                                                                                          | Where it lives                                                                                          |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Verified Obligation Ledger    | Each directive is an atomic obligation with owner_hint, due_date, citation (page + span), priority, confidence, confidence_annotations, and an audit trail.            | schemas/obligations.py, api/extraction_persistence.py                                                   |
| Proof-Gated Completion        | Closure is blocked until evidence passes (a) date-validity, (b) semantic similarity, (c) PDF tamper checks (SHA-256 + metadata).                                       | core/proof_verifier.py, schemas/proofs.py, routes/proofs.py                                             |
| Risk & Escalation Engine      | Predictive 0–100 score with explainable factors (deadline pressure, blocked dependencies, proof quality, owner workload).                                              | core/risk_service.py, schemas/obligations.py (ObligationRiskFactor)                                     |
| Refuse-to-Guess Extraction    | When confidence is low, items go to pending_review with structured signals — never fabricated.                                                                          | intelligence/graph/intake_graph.py, api/ai_extraction.py                                                |
| Provenance & Explainability   | Every AI output stores model + prompt version, source span, deterministic↔LLM agreement, components/weights/signals.                                                    | schemas/obligations.py (ObligationConfidenceAnnotations), core/ai_versions.py                           |
| Department-Aware Routing      | Maps directive language to canonical departments and named officers; flags multi-department obligations.                                                                | core/routing_service.py, data/canonical_departments.json, data/officer_directory.json                   |
| Cross-Case Linking            | Obligation embeddings (pgvector) + clustering surface similar past cases on the workbench.                                                                              | core/embedding_service.py, core/clustering_service.py, alembic/versions/20260430_01_t11_obligation_embeddings.py |
| Public-Trust Read-Only View   | Plain-language directives, ownership, deadlines, status — with regex-based PII redaction.                                                                               | routes/public.py, core/redaction_service.py                                                             |
| CCMS Event Ingestion          | Webhook + poll endpoints accept new judgments from the eCourts gateway and run the same intake pipeline.                                                                | core/ccms_client.py, routes/webhooks.py                                                                 |
| Department Health Scoring     | Compliance rate, missed deadlines, and case outcomes roll up into a per-department score.                                                                               | core/department_health.py, routes/departments.py                                                        |

---

## 3. System Architecture

```
                   ┌─────────────────────────────────────────────────────┐
                   │                      Reviewer                       │
                   └───────────┬─────────────────────────────┬───────────┘
                               │  HTTPS                      │  HTTPS
                               ▼                             ▼
                    ┌──────────────────┐           ┌──────────────────┐
                    │  Next.js (App    │           │   Public-Trust   │
                    │  Router) + TS    │           │    /public       │
                    │  /upload, /case  │           │    page          │
                    │  /dashboard …    │           └────────┬─────────┘
                    └────────┬─────────┘                    │
                             │  /api/v1/* (typed envelopes) │
                             ▼                              │
                    ┌──────────────────────────────────────────────┐
                    │             FastAPI + Pydantic v2            │
                    │  routes/{cases, documents, obligations,      │
                    │           proofs, public, webhooks, …}       │
                    │  intake_orchestrator + intake_adapter        │
                    └──────────┬─────────────────────┬─────────────┘
                               │ Temporal SDK        │ SQLAlchemy + asyncpg
                               ▼                     ▼
                    ┌──────────────────┐   ┌──────────────────────┐
                    │  Temporal worker │   │  PostgreSQL 16 +     │
                    │  workflows/      │   │  pgvector            │
                    │  intake.py       │   │  (case + obligation  │
                    │  activities/     │   │   embeddings, audit) │
                    │  intake.py       │   └──────────────────────┘
                    └────┬─────────────┘
                         │ LangGraph
                         ▼
                ┌──────────────────────┐
                │   Intelligence       │
                │   graph/intake_graph │
                │   gemini/groq client │
                │   refuse-to-guess    │
                └──────────┬───────────┘
                           │ LibreTranslate / OCR / Geocoder
                           ▼
                ┌──────────────────────────────────┐
                │  External services (local)       │
                │  • LibreTranslate (translation)  │
                │  • PaddleOCR / Tesseract (OCR)   │
                │  • Nominatim (geocoding)         │
                │  • MinIO (S3) — document store   │
                │  • Redis — short-lived state     │
                │  • Jaeger + OTel collector       │
                └──────────────────────────────────┘
```

The contract between layers is always a **Pydantic envelope**:

```jsonc
{ "ok": true, "message": "ok", "request_id": "…", "data": { … } }
```

This shape is enforced by `api/response.py:success(...)` on the backend and
`lib/api/client.ts:parseResponse(...)` on the frontend, so a route can never
leak un-versioned payloads to the UI.

---

## 4. Repository Layout

```
Application/orderflow/
├── README.md                  # Pitch + flow diagrams
├── DEVELOPMENT.md             # Day-to-day developer handoff
├── docs/                      # All long-form docs
│   ├── DOCUMENTATION.md           # ← this file
│   ├── engineering-standards.md
│   ├── environment-variable-policy.md
│   ├── language-support.md
│   ├── new-flow-plan.md / plan-a-and-b.md / plan-c.md
│   ├── samples/                   # Real Delhi-HC PDFs + CCMS envelopes
│   └── simple-flow-diagram.md
├── run_orchestration.py       # Top-level launcher (infra + backend + worker + frontend)
├── scripts/                   # Quality gate + start scripts
├── vercel.json                # Frontend deploy config
├── package.json               # Top-level workspace root
└── app/
    ├── README.md
    ├── infra/                 # docker-compose: Postgres, Redis, MinIO, OTel, LibreTranslate, Jaeger
    ├── shared/                # Cross-service contracts and schemas
    ├── backend/               # FastAPI service
    │   ├── alembic/           # DB migrations (versions/)
    │   ├── src/orderflow_api/
    │   │   ├── api/                  # HTTP layer
    │   │   │   ├── routes/           # Per-domain routers
    │   │   │   ├── stub_repository.py    # In-memory mode for demo / tests
    │   │   │   ├── intake_orchestrator.py
    │   │   │   ├── extraction_engine.py
    │   │   │   ├── ai_extraction.py
    │   │   │   ├── document_persistence.py
    │   │   │   ├── extraction_persistence.py
    │   │   │   ├── page_summary_persistence.py
    │   │   │   ├── document_summary_persistence.py
    │   │   │   ├── geocoding_service.py
    │   │   │   ├── ocr_service.py
    │   │   │   └── …
    │   │   ├── core/                 # Stateless business services
    │   │   │   ├── auth/
    │   │   │   ├── ccms_client.py
    │   │   │   ├── clustering_service.py
    │   │   │   ├── embedding_service.py
    │   │   │   ├── department_health.py
    │   │   │   ├── proof_verifier.py
    │   │   │   ├── redaction_service.py
    │   │   │   ├── risk_service.py
    │   │   │   ├── routing_service.py
    │   │   │   ├── translation_service.py
    │   │   │   ├── language_service.py
    │   │   │   ├── ai_versions.py
    │   │   │   ├── gemini_client.py / groq_client.py
    │   │   │   └── temporal.py
    │   │   ├── data/
    │   │   │   ├── canonical_departments.json
    │   │   │   └── officer_directory.json
    │   │   ├── schemas/              # Pydantic v2 contracts
    │   │   └── templates/            # Export templates (action plan PDFs/MD)
    │   └── tests/
    ├── worker/                 # Temporal worker (Python SDK)
    │   └── src/orderflow_worker/
    │       ├── workflows/intake.py       # Five-stage durable state machine
    │       ├── activities/intake.py      # Page extraction, summary, action-plan activities
    │       └── core/                     # Worker config, retries, timeouts
    ├── intelligence/           # LangGraph + LLM clients (independent package)
    │   └── src/orderflow_intelligence/
    │       ├── graph/intake_graph.py
    │       └── core/{config,gemini_client,groq_client}.py
    ├── data-pipelines/         # Batch jobs (backfill embeddings, places, advocates)
    └── frontend/               # Next.js 15 App Router
        └── src/
            ├── app/              # Routes
            │   ├── upload/          # Source picker + intake wizard
            │   ├── case/[id]/       # Five-stage reviewer workspace
            │   ├── dashboard/       # Trusted dashboard (post-finalize)
            │   ├── obligations/     # Cross-case obligation board
            │   ├── document-summary/
            │   ├── departments/     # Health + directory
            │   ├── advocates/       # Recommended advocates
            │   ├── public/          # Public-Trust read-only
            │   ├── login/, register/, profile/, admin/
            │   └── page.tsx         # Landing
            ├── components/
            │   ├── case/{stage-stepper, page-extraction-panel, summary-panel,
            │   │         action-plan-panel, review-panel, dashboard-panel}.tsx
            │   ├── case-flow-graph.tsx, case-incidence-map.tsx
            │   ├── pdf-viewer.tsx, pdf-overlay-layer.tsx
            │   ├── why-panel.tsx, risk-score-gauge.tsx
            │   └── ui/                  # shadcn-style primitives
            └── lib/
                ├── api/client.ts        # Single typed API client
                ├── demo/case-01-mock.{ts,json}    # Frontend-only demo mode
                └── hooks/
```

---

## 5. Domain Model

The five core entities — and their relationships — are:

```
DocumentRecord (1) ── ▶ (N) ClauseRecord
       │                          │
       │                          ▼
       │                  PageSummaryRecord (1 per page)
       │                          │
       ▼                          ▼
DocumentSummaryData ──────▶ ObligationRecord (N)
       │                          │
       │                          ▼
       │                  ObligationAuditEvent (N, append-only)
       │                          │
       ▼                          ▼
case_flow_graph        ObligationProofSubmission (on close)
(nodes + edges)               + Verifier verdict
```

### 5.1 DocumentRecord

Every uploaded judgment. Tracks `status` (`uploaded → processing → ready →
failed`), `checksum_sha256` (for duplicate-upload reuse), language metadata,
and a denormalized `case_flow_graph` snapshot for fast UI rendering.

### 5.2 ClauseRecord

Atomic legal clauses extracted with page + span fidelity
(`page_number`, `span_start`, `span_end`, `citation_span="p7:c4:50-410"`).
Used as the primary citation surface — every obligation references a clause
plus an explicit `ObligationCitation` with `visual_refs[]` (bounding boxes
on the PDF).

### 5.3 PageSummaryRecord

Per-page narrative + structured extraction:

- 2–3 sentence `summary`
- 3–5 `key_points`
- `important_highlights[]` with `significance ∈ {critical, important, contextual}`
- `entities[]`, `dates[]`, `directions[]`, `departments[]`, `extracted_places[]`
- `context_links[]` (other pages worth jumping to)
- OCR metadata when `text_source = ocr`

### 5.4 DocumentSummaryData

Full-judgment synthesis, generated only after all page summaries are cached:

- `case_basics` — number, court, parties, judge, disposal status
- `key_directives[]` — every operative directive with `directive_kind` and `compliance_required`
- `important_dates[]` — both stated and **inferred** (with `is_inferred=true` and reasoning)
- `entities_involved[]`, `responsible_departments[]`
- `flow_graph` — typed nodes (`party | event | order | obligation`) + edges + narrative steps
- `map_data` — geocoded places + flow lines (rendered by case-incidence-map.tsx)

### 5.5 ObligationRecord

The unit of execution. Carries:

| Field                           | Purpose                                                                       |
| ------------------------------- | ----------------------------------------------------------------------------- |
| `obligation_code`               | Stable code (e.g. `OBL-001`) for reviewer references                          |
| `title`, `description`          | Human-facing labels                                                           |
| `owner_hint`                    | Department / officer mapped via routing_service                               |
| `due_date`                      | ISO date computed from the order or inferred ("within 4 weeks from today")    |
| `status`                        | `draft | active | completed | cancelled`                                      |
| `priority`                      | `low | medium | high | critical`                                              |
| `review_state`                  | `pending_review | approved | rejected`                                        |
| `action_plan_stage`             | `extracted | in_action_plan | review_pending | approved | rejected | edited`  |
| `nature_of_action`              | One of 17 typed values (`compliance_report`, `appointment`, `policy`, …)      |
| `confidence` + `_annotations`   | Components, weights, rationale, signals — drives the **Why?** panel           |
| `escalation`                    | `level ∈ {none, watch, escalated, critical}`, `reasons[]`, `days_until_due`   |
| `risk_score` + `risk_band`      | 0–100 contempt-risk score with explainable `risk_factors[]`                   |
| `regen_count` + `regen_history` | Per-item LLM regenerations driven by reviewer feedback                        |
| `citation`                      | Page + clause span + `visual_refs[]`                                          |
| `metadata`                      | Sequence, dependencies (`depends_on`, `blocks`), source (`reviewer_added`)    |

### 5.6 Audit Trail

Every mutation appends an `ObligationAuditEvent` with `actor_type`,
`actor_id`, `request_id`, and a structured `payload`. The trail is
queryable per obligation and is immutable.

---

## 6. The Gated Case Flow (Five Stages)

The case wizard at `/case/[id]` enforces a strict left-to-right gate. Each
stage has an explicit acceptance criterion and a typed status field on the
`ExtractionJobStatusData` envelope:

```
upload  ──▶  pages_extracting  ──▶  pages_done
                                       │
                                       ▼
                                  summary_pending  ──▶  summary_done
                                                            │
                                                            ▼
                                                  action_plan_pending  ──▶  action_plan_done
                                                                                  │
                                                                                  ▼
                                                                         review_in_progress
                                                                                  │
                                                                                  ▼
                                                                              finalized
```

| Stage              | Trigger                                                      | Backend route                                                        | Acceptance criterion                                                                |
| ------------------ | ------------------------------------------------------------ | -------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Upload             | `POST /documents/upload` or `POST /documents/intake/indian-ecourts` | document persisted, checksum recorded                                | `status = "uploaded"`                                                               |
| Pages extracting   | `POST /cases/{id}/intake/start`                              | Temporal `IntakeWorkflow` starts, fans out per-page activities        | every page has a cached `PageSummaryRecord`                                         |
| Summary            | `POST /cases/{id}/summary/generate`                          | LangGraph synthesises `DocumentSummaryData` from cached pages         | `flow_graph` and `map_data` populated, summary persisted                            |
| Action plan        | `POST /cases/{id}/action-plan/generate`                      | One-shot extractor reads cited pages and writes `ObligationRecord[]`  | every obligation in `review_pending` with citation + confidence                     |
| Review (per item)  | `POST /cases/{id}/action-plan/items/{obligation_id}/review`  | Reviewer approves / edits / rejects each item                         | `action_plan_stage ∈ {approved, edited, rejected}` for **all** items                 |
| Finalize           | `POST /cases/{id}/finalize`                                  | Backend asserts every item has a decision and snapshots counts        | `case.stage = "finalized"`; trusted dashboard becomes available                     |

Polling is provided by:

- **SSE**  `GET /cases/{id}/intake/events` — primary real-time channel
- **Fallback** `GET /cases/{id}/intake/status` — frontend uses this when SSE is blocked

The frontend hook `useIntakeProgress` keeps SSE preferred and silently
falls back to 2-second polling on transport errors.

---

## 7. Intelligence Layer

OrderFlow runs a **dual-track** extraction pipeline:

```
                            ┌───────────────────────┐
PDF page text  ──────────▶ │ Deterministic parser  │ ─┐
                            │ (Docling + regex)     │  │
                            └───────────────────────┘  │
                                                       ├──▶  reconcile()  ──▶  ObligationRecord
                            ┌───────────────────────┐  │
PDF page text  ──────────▶ │ LangGraph agent       │ ─┘
                            │ (Gemini / Groq)       │
                            │ refuse-to-guess gate  │
                            └───────────────────────┘
```

### 7.1 LangGraph

`intelligence/graph/intake_graph.py` is the agentic state machine. The graph
moves through nodes for: ingest → cite → propose → score → reconcile → emit.
At every step the agent must produce structured output; if a step would
require fabrication, it emits `confidence < threshold` and the router pushes
the obligation to `review_state = pending_review` with a structured signal
in `confidence_annotations.signals`.

### 7.2 Provider abstraction

Provider clients live in `core/{gemini_client,groq_client}.py` and expose
a uniform `generate(...)` surface. Defaults are set via env:

- `ORDERFLOW_AI_DEFAULT_PROVIDER=gemini`
- `ORDERFLOW_AI_DEFAULT_MODEL=gemini-2.0-flash`

Reviewers can override per-intake from the UI (mode picker on `/upload`).
Rate limiting (RPM / TPM / RPD) is built-in for Gemini's free tier; see the
configuration section.

### 7.3 Caching

Page extraction is **content-addressable**: each page hashes its normalized
text + prompt version + OCR engine version into `content_hash`, and the
worker reuses cached `PageSummaryRecord` rows on re-runs. This is verified
by tests in `app/backend/tests/test_page_summary_engine_cache.py`.

### 7.4 Confidence components

`ObligationConfidenceAnnotations` stores the explainable breakdown:

```jsonc
{
  "extractor_version": "demo-v1",
  "components": { "directive_clarity": 0.98, "deadline_explicitness": 0.99, "owner_specificity": 0.92 },
  "weights":    { "directive_clarity": 0.4,  "deadline_explicitness": 0.4,  "owner_specificity": 0.2 },
  "rationale":  ["Operative paragraph is unambiguous", "Deadline computed from explicit '4 weeks from today'"],
  "signals":    { "concession_on_record": true }
}
```

The `why-panel.tsx` component renders this verbatim.

---

## 8. API Surface

All HTTP routes are mounted under `/api/v1` and use the
`{ ok, message, request_id, data }` envelope.

### 8.1 Documents and intake

| Method | Path                                              | Purpose                                                        |
| ------ | ------------------------------------------------- | -------------------------------------------------------------- |
| POST   | `/documents/upload`                               | Multipart upload of a judgment PDF                             |
| POST   | `/documents/intake/indian-ecourts/lookup`         | Resolve a case-id / token / URL into a prefilled CCMS envelope |
| POST   | `/documents/intake/indian-ecourts`                | Create a document from the prefilled envelope                  |
| GET    | `/documents`                                      | List all documents (workbench)                                 |
| GET    | `/documents/{id}`                                 | Fetch a single document                                        |
| GET    | `/documents/{id}/download`                        | Stream the original PDF                                        |
| DELETE | `/documents`                                      | Bulk-clear (admin)                                             |

### 8.2 Case wizard

| Method | Path                                                            | Purpose                                  |
| ------ | --------------------------------------------------------------- | ---------------------------------------- |
| POST   | `/cases/{id}/intake/start`                                      | Kick off page extraction                 |
| GET    | `/cases/{id}/intake/status`                                     | Poll progress                            |
| GET    | `/cases/{id}/intake/events`                                     | SSE stream                               |
| POST   | `/cases/{id}/summary/generate`                                  | Generate document summary                |
| GET    | `/cases/{id}/summary`                                           | Fetch the summary                        |
| POST   | `/cases/{id}/action-plan/generate`                              | Generate the action plan                 |
| GET    | `/cases/{id}/action-plan`                                       | List action-plan items                   |
| POST   | `/cases/{id}/action-plan/items/{obligation_id}/review`          | Approve / edit / reject one item         |
| POST   | `/cases/{id}/action-plan/items/{obligation_id}/regenerate`      | Surgically re-extract one item          |
| POST   | `/cases/{id}/finalize`                                          | Lock the case (gated on all-decided)     |
| GET    | `/cases/{id}/dashboard`                                         | Trusted dashboard (post-finalize only)   |

### 8.3 Page summaries, clauses, annotations

| Method | Path                                            | Purpose                                                                   |
| ------ | ----------------------------------------------- | ------------------------------------------------------------------------- |
| GET    | `/summaries/{document_id}`                      | List per-page summaries                                                   |
| POST   | `/summaries/{document_id}/generate`             | Force-regenerate                                                          |
| POST   | `/summaries/{document_id}/places/refresh`       | Re-run geocoder on extracted places                                       |
| GET    | `/clauses?document_id=…&page_number=…`          | Citation drill-down                                                       |
| GET    | `/annotations/{document_id}`                    | Visual-evidence overlay metadata                                          |
| POST   | `/annotations/{document_id}/generate`           | Create annotations from cached summaries                                  |
| POST   | `/annotations/{document_id}/coordinates`        | Reviewer-corrected bounding boxes                                         |

### 8.4 Obligations, escalations, audit

| Method | Path                                             | Purpose                                |
| ------ | ------------------------------------------------ | -------------------------------------- |
| GET    | `/obligations?document_id=…`                     | Per-document list                      |
| GET    | `/obligations`                                   | Global cross-case list                 |
| POST   | `/obligations/{id}` (PATCH-style)                | Update review state, owner, status     |
| GET    | `/escalations?document_id=…`                     | Open escalations                       |
| GET    | `/obligations/{id}/audit`                        | Append-only audit trail                |

### 8.5 Proofs and closure

| Method | Path                       | Purpose                                                                               |
| ------ | -------------------------- | ------------------------------------------------------------------------------------- |
| POST   | `/proofs/verify`           | Three-layer verifier: date, semantic similarity, tamper (`proof_bytes_sha256`)        |

### 8.6 Routing, departments, advocates

| Method | Path                                            | Purpose                                                |
| ------ | ----------------------------------------------- | ------------------------------------------------------ |
| POST   | `/routing/route`                                | Map free-text directive → canonical department/officer |
| GET    | `/routing/departments`                          | Canonical department directory                         |
| GET    | `/departments/health`                           | Health score + benchmarking                            |
| GET    | `/advocates`                                    | Advocate directory                                     |
| GET    | `/advocates/{id}/cases`                         | Cases linked to an advocate                            |
| POST   | `/advocates/me/cases`                           | Self-claim a case                                      |
| POST   | `/advocates/{id}/verify` / `/reject`            | Admin verification                                     |

### 8.7 Public-Trust view

| Method | Path                                | Purpose                                                                  |
| ------ | ----------------------------------- | ------------------------------------------------------------------------ |
| GET    | `/public/obligations`               | Citizen-facing list — PII redacted, plain language, deadlines + status   |

### 8.8 Webhooks and exports

| Method | Path                                  | Purpose                                                       |
| ------ | ------------------------------------- | ------------------------------------------------------------- |
| POST   | `/webhooks/ccms`                      | CCMS event ingestion (events → intake pipeline)               |
| POST   | `/webhooks/ccms/poll`                 | Operator-triggered backfill                                   |
| GET    | `/exports/action-plan?language=…`     | Markdown / JSON export in any of 7 languages                  |
| POST   | `/exports/case-bundle/pdf`            | Full case PDF bundle (summary + map + obligations)            |

### 8.9 AI helpers (review-side)

| Method | Path                          | Purpose                                            |
| ------ | ----------------------------- | -------------------------------------------------- |
| POST   | `/ai-chat/chat`               | Reviewer chat over the cached judgment context     |
| POST   | `/judgment-decisions`         | Verify a stated outcome against the judgment text  |
| POST   | `/page-insight`               | One-shot page-level Q&A                            |
| POST   | `/extract-obligations`        | Direct extraction (bypasses workflow gates)        |
| POST   | `/review-obligation`          | Reviewer micro-agent for a single obligation       |

### 8.10 Auth and users

`/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me`, `/auth/password`,
`/users/{id}`. JWT bearer tokens, refresh-on-401 retry baked into the
frontend client.

---

## 9. Multi-Language Support

Supported languages: **English, Hindi, Tamil, Telugu, Kannada, Malayalam, Marathi.**

| Step              | Behaviour                                                                          |
| ----------------- | ---------------------------------------------------------------------------------- |
| Detect            | `core/language_service.py` — fastText-style detection with user override           |
| Translate         | `core/translation_service.py` → LibreTranslate at `ORDERFLOW_TRANSLATION_SERVICE_URL` |
| Extract           | All AI extraction runs on the English working copy                                  |
| Preserve          | Original PDF + translation metadata retained for audit                             |
| Export            | `GET /exports/action-plan?language=hi&format=markdown`                              |
| Render            | Frontend labels translate via `lib/labels.ts`                                       |

---

## 10. Security, Auth, and Permissions

### 10.1 Auth model

- Users live in the `auth_users` table (alembic 20260502_01).
- JWT access tokens with refresh; refresh handler is wired through
  `client.ts:registerAuthHandlers(...)`.
- Permissions are enumerated in `core/auth/permissions.py:Permission`:
  `DOCUMENT_UPLOAD`, `EXTRACTION_RUN`, `CASE_READ`, `CASE_REVIEW`,
  `PROOF_VERIFY`, `ADMIN_*`, etc.
- Routes guard themselves with `Depends(require_permission(...))`.

### 10.2 PII redaction (Public-Trust)

`core/redaction_service.py` is regex + heuristic only (no spaCy dependency).
Patterns covered:

- Honorifics + names (Shri/Smt./Dr./Justice/Hon'ble + capitalized words)
- Phone numbers (Indian formats)
- Email addresses
- 12-digit Aadhaar-like numbers
- 10-character PAN-like alphanumerics
- Case numbers (`W.P. 1234/2024`)
- Specific addresses (door / plot / flat numbers)

Redaction is deterministic: identical names map to identical placeholders,
preserving readability while severing identity.

### 10.3 Tamper resistance

Proof bytes are SHA-256 hashed at submit; the verifier checks that
`proof_bytes_sha256 == expected_sha256` before any further validation.
PDF metadata (creation/mod times, producer) is captured to detect
re-saves and post-processing.

---

## 11. Observability

- **Tracing.** OpenTelemetry SDK in FastAPI, the worker, and the LangGraph
  package. Spans flow to the OTel Collector and Jaeger UI on port 16686.
- **Logging.** Structured JSON lines with `request_id` propagated through
  `x-request-id` header on every boundary.
- **Workflow audit.** Temporal's history is the source of truth for
  five-stage progress, retries, and cache hits.
- **Per-obligation audit.** Append-only `ObligationAuditEvent` rows with
  actor + request id; surfaced at `/obligations/{id}/audit`.

---

## 12. Local Development

### 12.1 Prerequisites

- Python 3.11+, uv for backend / worker / intelligence
- Node 20+, pnpm or npm for the frontend
- Docker Desktop for the infra stack (Postgres + Redis + MinIO + Jaeger + LibreTranslate)

### 12.2 Bring up infrastructure

```powershell
cd Application/orderflow/app/infra
docker compose up -d
```

Services exposed locally:

| Service        | Port  | Notes                                                |
| -------------- | ----- | ---------------------------------------------------- |
| Postgres       | 5432  | `pgvector/pgvector:pg16`, user/pass `orderflow`      |
| Redis          | 6379  | Workflow scratchpad                                  |
| MinIO          | 9000  | Console at `:9001`, bucket `orderflow-documents`     |
| Jaeger         | 16686 | UI                                                   |
| OTel Collector | 4318  | OTLP/HTTP                                            |
| LibreTranslate | 5000  | `/translate` endpoint                                |

### 12.3 Backend + worker + frontend (one command)

```powershell
cd Application/orderflow
python run_orchestration.py
```

This spawns four processes (infra check, FastAPI, Temporal worker, Next.js)
and tails their logs. To run them individually:

```powershell
# FastAPI (auto-reload)
cd app/backend && uv run uvicorn orderflow_api.main:app --reload

# Temporal worker
cd app/worker  && uv run python -m orderflow_worker.main

# Frontend (Next.js)
cd app/frontend && npm run dev
```

### 12.4 Quality gate

```powershell
cd Application/orderflow
python scripts/quality_check.py
```

Runs Prettier, ESLint, TypeScript, Black, flake8, and pytest in sequence.

---

## 13. Database Migrations

Alembic is configured at `app/backend/alembic.ini` with versions in
`app/backend/alembic/versions/`. Recent timeline:

| Date        | Migration                                | What it adds                                   |
| ----------- | ---------------------------------------- | ---------------------------------------------- |
| 2026-04-23  | `t11_a006_core_schema_v1`                | Documents, clauses, obligations, audit events  |
| 2026-04-23  | `t11_a009_workflow_runs`                 | Temporal workflow run tracking                 |
| 2026-04-24  | `t11_phase1_multilingual_support`        | Language fields on documents                   |
| 2026-04-24  | `t11_page_summaries`                     | Per-page summary table                         |
| 2026-04-24  | `t11_page_annotations`                   | Annotation overlays                            |
| 2026-04-30  | `t11_obligation_embeddings`              | pgvector column + ANN index                    |
| 2026-05-02  | `t11_auth_users`                         | Auth users + RBAC                              |
| 2026-05-02  | `case_advocates`                         | Advocate ↔ case links                          |
| 2026-05-02  | `case_flow`                              | `case_flow_graph` JSONB on documents           |
| 2026-05-03  | `case_incidence_places`                  | Geocoded places                                |
| 2026-05-04  | `t12_intake_flow`                        | Five-stage gate state on cases                 |
| 2026-05-05  | `page_summary_rich_extraction`           | Highlights, entities, dates, directions        |
| 2026-05-06  | `ocr_metadata`                           | OCR engine, confidence, language               |
| 2026-05-07  | `document_text_boxes` + `invalidate_summary_v1_0` | PDF text-box positions; cache bust       |

Apply with `uv run alembic upgrade head` from `app/backend`.

---

## 14. Configuration Reference

All settings are in `core/config.py`, env-var driven, prefixed `ORDERFLOW_*`.

**Core**

| Variable                            | Default                                                              |
| ----------------------------------- | -------------------------------------------------------------------- |
| `ORDERFLOW_ENV`                     | `local`  (one of `local | staging | production`)                     |
| `ORDERFLOW_LOG_LEVEL`               | `info`                                                               |
| `ORDERFLOW_API_HOST`                | `0.0.0.0`                                                            |
| `ORDERFLOW_API_PORT`                | `8000`                                                               |
| `ORDERFLOW_API_DATABASE_URL`        | `postgresql+psycopg://orderflow:orderflow@localhost:5432/orderflow`  |
| `ORDERFLOW_API_USE_STUB_REPOSITORY` | `false` (in-memory mode for demos and tests)                         |
| `ORDERFLOW_API_CORS_ORIGINS`        | `http://localhost:3000` (comma-separated)                            |

**Object storage (MinIO / S3)**

| Variable                              | Default                  |
| ------------------------------------- | ------------------------ |
| `ORDERFLOW_API_S3_ENDPOINT`           | `http://localhost:9000`  |
| `ORDERFLOW_API_S3_ACCESS_KEY`         | `minioadmin`             |
| `ORDERFLOW_API_S3_SECRET_KEY`         | `minioadmin`             |
| `ORDERFLOW_API_S3_BUCKET`             | `orderflow-documents`    |

**Temporal**

| Variable                                       | Default              |
| ---------------------------------------------- | -------------------- |
| `ORDERFLOW_API_TEMPORAL_HOST`                  | `localhost:7233`     |
| `ORDERFLOW_API_TEMPORAL_NAMESPACE`             | `default`            |
| `ORDERFLOW_API_TEMPORAL_TASK_QUEUE`            | `orderflow-default`  |
| `ORDERFLOW_API_TEMPORAL_WORKFLOW_ID_PREFIX`    | `orderflow-intake`   |

**AI**

| Variable                                  | Default              |
| ----------------------------------------- | -------------------- |
| `ORDERFLOW_AI_ENABLED_DEFAULT`            | `false`              |
| `ORDERFLOW_AI_DEFAULT_PROVIDER`           | `gemini`             |
| `ORDERFLOW_AI_DEFAULT_MODEL`              | `gemini-2.0-flash`   |
| `ORDERFLOW_AI_TIMEOUT_SECONDS`            | `45`                 |
| `ORDERFLOW_AI_GEMINI_REQUESTS_PER_MINUTE` | `15`                 |
| `ORDERFLOW_AI_GEMINI_TOKENS_PER_MINUTE`   | `1000000`            |
| `ORDERFLOW_AI_GEMINI_REQUESTS_PER_DAY`    | `1500`               |
| `ORDERFLOW_AI_GEMINI_MAX_OUTPUT_TOKENS`   | `2048`               |
| `ORDERFLOW_AI_GEMINI_MAX_CLAUSES`         | `24`                 |
| `ORDERFLOW_AI_OPENAI_API_KEY`             | unset                |
| `ORDERFLOW_AI_ANTHROPIC_API_KEY`          | unset                |
| `ORDERFLOW_AI_GEMINI_API_KEY`             | unset                |
| `ORDERFLOW_AI_GROQ_API_KEY`               | unset                |

**OCR**

| Variable                          | Default        | Notes                                       |
| --------------------------------- | -------------- | ------------------------------------------- |
| `ORDERFLOW_OCR_ENABLED`           | `true`         |                                             |
| `ORDERFLOW_OCR_PRIMARY_ENGINE`    | `paddleocr`    | Fallback engine via `…_FALLBACK_ENGINE`     |
| `ORDERFLOW_OCR_DPI`               | `300`          |                                             |
| `ORDERFLOW_OCR_MIN_CHARS`         | `120`          | Below this → trigger OCR even on native PDF |

**Translation**

| Variable                                 | Default                  |
| ---------------------------------------- | ------------------------ |
| `ORDERFLOW_TRANSLATION_SERVICE_URL`      | `http://localhost:5000`  |
| `ORDERFLOW_TRANSLATION_TIMEOUT_SECONDS`  | `30`                     |
| `ORDERFLOW_TRANSLATION_API_KEY`          | unset                    |

**Geocoder (Nominatim)**

| Variable                                       | Default                                            |
| ---------------------------------------------- | -------------------------------------------------- |
| `ORDERFLOW_API_GEOCODER_USER_AGENT`            | `OrderFlow local development contact@example.invalid` |
| `ORDERFLOW_API_GEOCODER_TIMEOUT_SECONDS`       | `10`                                               |
| `ORDERFLOW_API_GEOCODER_PACE_SECONDS`          | `1.05`                                             |

**Observability**

| Variable                  | Default | Notes                  |
| ------------------------- | ------- | ---------------------- |
| `ORDERFLOW_OTEL_ENDPOINT` | unset   | OTLP/HTTP collector    |

---

## 15. Demo Mode

For deterministic demos (and Vercel previews without a backend), the
frontend ships a self-contained mock for the Delhi HC W.P.(C) 8524/2025
judgment.

- Files: `app/frontend/src/lib/demo/case-01-mock.ts` and `case-01-mock.json`
- PDF: `app/frontend/public/demo/delhi-hc-wpc-8524-2025-judgment-05-02-2026.pdf`
- Trigger: paste any of these into the eCourts lookup field on `/upload`:
  - `https://delhihighcourt.nic.in/app/showFileJudgment/75005022026CW85242025_154137.pdf`
  - the bare token `75005022026CW85242025_154137`
  - the case id `W.P.(C) 8524/2025`

Once activated, every case API call is intercepted at the typed client
layer and resolved against the local mock with realistic delays
(lookup ~1.5 s; pages extraction ~6 s; summary ~3 s; action plan ~2 s;
review ~250 ms; regenerate ~1.2 s). **No AI calls and no backend
reachability are required for the demo.** A reference fixture lives at
`docs/samples/court-cases/case-01-demo-mock-data.json`.

---

## 16. Roadmap

Tracked alongside the planning notes in `docs/`. Headline items not yet
shipped:

- **WhatsApp & Voice field loop** — IVR / WhatsApp check-in for field
  officers, deadline reminders, and one-tap proof upload.
- **Cross-case knowledge graph** — explicit graph-DB linking by statute
  citation and conflicting orders (currently approximated by pgvector +
  clustering).
- **Quality gate close-out** — backend Black + flake8 cleanup is the last
  open red item.

---

## 17. Glossary

| Term                | Meaning                                                                                  |
| ------------------- | ---------------------------------------------------------------------------------------- |
| Obligation          | A single atomic, owner-assigned, deadline-safe unit of action derived from a directive   |
| Directive           | A line of operative text in the judgment that imposes one or more obligations            |
| Citation            | `(page, span_start, span_end, visual_refs)` — the exact location backing an obligation   |
| Action plan         | The full list of obligations for a case after generation, before review                  |
| Review state        | `pending_review | approved | rejected` on each obligation                                |
| Action-plan stage   | `extracted | in_action_plan | review_pending | approved | rejected | edited`             |
| Escalation level    | `none | watch | escalated | critical` driven by the risk service                         |
| Refuse-to-Guess     | When confidence is low, the system marks `pending_review` instead of fabricating         |
| Why? panel          | Reviewer-facing explanation of a confidence score (components + weights + signals)        |
| CCMS                | Court Case Management System — gateway delivering judgments to OrderFlow                  |
| CIS                 | Case Information System — structured case metadata accompanying CCMS deliveries          |
| Public-Trust mode   | Read-only citizen view with PII redaction and plain-language directives                   |
| Trusted dashboard   | Post-finalize view that only shows approved or edited obligations                         |

---

*Last updated: 2026-05-07. Maintainer: OrderFlow team.*
