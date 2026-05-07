# OrderFlow — Run Instructions for the Testing Team

A single-file runbook so a tester can take the repository, bring it up,
and exercise every flow without reading any other document.

There are **two ways to run** the app:

- **Path A — Demo Mode (no backend, no AI, ~2 minutes).** Recommended for a
  first pass; runs entirely in the browser with the Delhi HC W.P.(C) 8524/2025
  judgment as fixture.
- **Path B — Full Stack (Docker + backend + worker + frontend).** Required
  for end-to-end validation, multi-language, CCMS webhooks, real AI.

Pick A or B based on what you need to test.

---

## 0. Prerequisites

Install **once** before either path. All platforms supported, Windows is the
default reference environment.

| Tool                 | Minimum version | Used for                                            |
| -------------------- | --------------- | --------------------------------------------------- |
| Node.js              | 20.x            | Frontend (Next.js)                                  |
| npm (or pnpm)        | 10.x            | Frontend dependency install                         |
| Python               | 3.11 or 3.12    | Backend, worker, intelligence                       |
| uv (or pip)          | latest          | Python package manager                              |
| Docker Desktop       | 24.x            | Postgres, Redis, MinIO, Jaeger, LibreTranslate, Temporal |
| Git                  | any             | Clone the repo                                      |
| Tesseract (optional) | 5.x             | OCR fallback if PaddleOCR misses                    |

**Path A only needs Node + npm.** Path B needs everything.

Ports the app uses (must be free): `3000` (frontend), `8000` (backend),
`5432` (Postgres), `6379` (Redis), `9000`/`9001` (MinIO), `7233` (Temporal),
`16686` (Jaeger UI), `4317`/`4318` (OTel collector), `5000` (LibreTranslate).

---

## 1. Get the Code

```powershell
# Pick a folder you have write-access to, then:
git clone <repository-url>
cd <repo>/Application/orderflow

# IMPORTANT: switch to the demo branch for the bundled demo fixture
git checkout demo
```

If you already have the repo, just:

```powershell
cd Application/orderflow
git fetch
git checkout demo
git pull
```

---

# PATH A — Demo Mode (fastest)

Use this for the very first acceptance test. No Docker, no Python, no AI keys.

### A.1 Install frontend dependencies

```powershell
cd app/frontend
npm install
```

First install takes 2–3 minutes.

### A.2 Start the frontend

```powershell
npm run dev
```

Wait for the line `▲ Next.js 15.x   Local: http://localhost:3000`.

### A.3 Open the app

Open `http://localhost:3000` in Chrome / Edge / Firefox.

### A.4 Trigger the demo

1. Click **Upload a judgment** (or navigate to `http://localhost:3000/upload`).
2. Scroll down to the **eCourts lookup** card.
3. Paste **any one** of these into the lookup field:
   - `https://delhihighcourt.nic.in/app/showFileJudgment/75005022026CW85242025_154137.pdf`
   - the bare token `75005022026CW85242025_154137`
   - the case id `W.P.(C) 8524/2025`
4. Click **Fetch and prefill form**.
5. Wait ~1.5 s — the form auto-fills with the case metadata.
6. Click **Confirm intake**. You will be routed to `/case/<id>`.

### A.5 Walk the five-stage flow

The wizard moves left-to-right. Each stage has a green check when done.

| Stage           | What you should see                                                                 | Approx duration |
| --------------- | ----------------------------------------------------------------------------------- | --------------- |
| Page extraction | Live progress, current page excerpt, 8/8 pages cached                                | ~6 s            |
| Summary         | Case basics, key directives, important dates, entities, **flow graph**, **map**      | ~3 s            |
| Action plan     | 5 obligations OBL-001 … OBL-005, each in `pending_review`                            | ~2 s            |
| Review          | For each item: **Approve** / **Edit** / **Reject** / **Regenerate** buttons          | per click       |
| Finalize        | Locks the case; trusted dashboard becomes available                                  | < 1 s           |

After finalize, the dashboard groups the approved/edited items by responsible
department (SSC vs DoPT).

### A.6 Demo Mode acceptance checklist

Tick each before signing off Path A:

- [ ] Lookup auto-fills the case form within ~2 s of clicking **Fetch**.
- [ ] PDF viewer renders all 8 pages with text-layer highlighting.
- [ ] Page extraction shows live `current_page` updates, not a single jump.
- [ ] Summary panel shows the **flow graph** with 12 nodes and 11 edges.
- [ ] Map shows 3 places (HC Delhi, SSC HQ, DoPT North Block).
- [ ] Action plan lists 5 obligations, each with citation page + risk score.
- [ ] **Regenerate** OBL-003 with feedback `Add DoPT as co-owner` — `regen_count` becomes 1.
- [ ] Approve at least 3 items, edit 1 item (change `owner_hint`), reject 1 item.
- [ ] **Finalize** is blocked while any item is still pending; passes once all decided.
- [ ] Dashboard shows correct totals: approved + edited + rejected = 5.
- [ ] Public-Trust view at `/public` lists the same case with PII redacted.

---

# PATH B — Full Stack

For backend / worker / AI / multi-language / CCMS validation.

### B.1 One-shot startup (Windows, recommended)

A PowerShell script bootstraps everything: infra → migrations → backend
→ worker → frontend, with health checks.

```powershell
cd Application/orderflow
powershell -ExecutionPolicy Bypass -File .\scripts\start-orderflow.ps1
```

You will see an interactive menu:

```
1. Start app or initialize all installs
2. Configure AI, model, and API keys (.env for all folders)
3. Run CLI orchestration
4. Run tests
```

For a **fresh laptop** choose `1` then `1` (initialize installs + start).
For a **subsequent run** choose `1` then `2` (start only).
For a **stuck environment** choose `1` then `3` (force restart).

Successful boot prints:

```
OrderFlow stack is ready.
Frontend:    http://localhost:3000
Backend:     http://localhost:8000/health
Temporal:    localhost:7233
```

…plus three demo seed accounts (see B.6 below).

### B.2 Manual startup (any OS)

If the script is unavailable or you want fine control:

#### B.2.1 Bring up infrastructure

```powershell
cd Application/orderflow/app/infra
docker compose up -d
```

Wait until all six containers are **healthy**:

```powershell
docker compose ps
```

You should see: `orderflow-postgres`, `orderflow-redis`, `orderflow-minio`,
`orderflow-libretranslate`, `orderflow-jaeger`, `orderflow-otel-collector`.

#### B.2.2 Start Temporal

```powershell
# easiest — run via Docker
docker run -d --name orderflow-temporal --network orderflow-local_default `
  -p 7233:7233 `
  -e DB=postgres12 -e DB_PORT=5432 -e DBNAME=orderflow `
  -e POSTGRES_SEEDS=orderflow-postgres `
  -e POSTGRES_USER=orderflow -e POSTGRES_PWD=orderflow `
  temporalio/auto-setup:1.25
```

Wait ~30 s for Temporal to finish its self-bootstrap.

#### B.2.3 Install Python dependencies

```powershell
cd Application/orderflow
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -e ".\app\backend[dev,pdf,ocr]"
pip install -e ".\app\worker[dev,ocr]"
pip install -e ".\app\intelligence[dev]"
pip install httpx
```

#### B.2.4 Run database migrations

```powershell
cd app/backend
python -m alembic -c alembic.ini upgrade head
```

You should see ~14 migrations applied.

#### B.2.5 Seed demo accounts

```powershell
python -m scripts.seed_demo_advocates
```

#### B.2.6 Start the backend

```powershell
python -m uvicorn orderflow_api.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify in another terminal:

```powershell
curl http://localhost:8000/api/v1/health
# expect: {"ok":true,...}
```

#### B.2.7 Start the worker

```powershell
cd app/worker
python -m orderflow_worker.main
```

The log should say `Worker started, polling task queue: orderflow-default`.

#### B.2.8 Start the frontend

```powershell
cd app/frontend
npm install            # first time only
npm run dev
```

### B.3 Configure AI keys

The backend runs in **deterministic mode** by default — every flow works
without AI keys, just with lower-confidence extraction. Set keys only if
you are explicitly testing AI behaviour.

Easiest path:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-orderflow.ps1
# Choose option 2 — Configure AI, model, and API keys
# Choose target 2 — all AI services (backend, worker, intelligence)
# Choose setting 4 — ORDERFLOW_AI_GEMINI_API_KEY (free tier, recommended)
# Paste the key when prompted
```

Manual path: edit `app/backend/.env`, `app/worker/.env`,
`app/intelligence/.env` and set:

```
ORDERFLOW_AI_ENABLED_DEFAULT=true
ORDERFLOW_AI_DEFAULT_PROVIDER=gemini
ORDERFLOW_AI_DEFAULT_MODEL=gemini-2.0-flash
ORDERFLOW_AI_GEMINI_API_KEY=<paste-here>
```

Restart the backend and worker after changing keys.

### B.4 Verify everything is up

| Check                          | Expected                                           |
| ------------------------------ | -------------------------------------------------- |
| `http://localhost:3000`        | Landing page renders                               |
| `http://localhost:8000/api/v1/health` | `{"ok": true, "data": { "status": "ok", … }}` |
| `http://localhost:8000/docs`   | Swagger UI lists all routes                        |
| `http://localhost:9001`        | MinIO console (login `minioadmin / minioadmin`)    |
| `http://localhost:16686`       | Jaeger UI                                          |
| `http://localhost:5000`        | LibreTranslate landing page                        |

### B.5 Quick smoke test

1. Login at `http://localhost:3000/login` with
   `gov.reviewer@orderflow.example` / `Orderflow@123`.
2. Click **Upload a judgment** and drop the file
   `docs/samples/court-cases/delhi-hc-wpc-8524-2025-judgment-05-02-2026.pdf`.
3. The intake wizard should run end-to-end. Pages extraction will take longer
   than in demo mode (real OCR / parsing) — typically 30–90 s for an 8-page
   PDF, depending on whether AI is enabled.
4. Continue through summary → action plan → review → finalize.
5. Open the trusted dashboard.

### B.6 Demo seed accounts

The startup script automatically seeds three accounts:

| Role                               | Email                                | Password         |
| ---------------------------------- | ------------------------------------ | ---------------- |
| Government reviewer (admin-ish)    | `gov.reviewer@orderflow.example`     | `Orderflow@123`  |
| Advocate — already approved        | `adv.approved@orderflow.example`     | `Orderflow@123`  |
| Advocate — pending verification    | `adv.pending@orderflow.example`      | `Orderflow@123`  |

Use the **government reviewer** for almost every test. The two advocate
accounts exist to verify the verification flow on the admin page.

---

## 2. Test Scenarios

The matrix below maps tester intents to the recommended path and the
single concrete URL or action.

### 2.1 Smoke / acceptance (Path A or B)

1. Demo lookup with W.P.(C) 8524/2025.
2. Upload a fresh PDF (Path B only).
3. Open `/dashboard` and confirm the workbench shows the case.
4. Open `/obligations` and confirm cross-case obligation board shows items.

### 2.2 Multi-language (Path B)

1. Upload a Hindi judgment PDF (any sample with Devanagari text).
2. On the upload form, leave **Source language** as `Auto-detect` —
   the form should populate `auto_detected_language=hi`.
3. Run intake. Translation metadata is stored on the document.
4. After finalize, open `/exports/action-plan?document_id=<id>&language=hi&format=markdown`
   and verify the action plan is exported in Hindi.
5. Repeat with `language=ta` (Tamil) on the same document.

### 2.3 CCMS event ingestion (Path B)

```powershell
cd app/backend
python -m scripts.simulate_ccms_event
```

This POSTs a sample event to `/api/v1/webhooks/ccms`. Confirm a new
document appears on `/dashboard` within ~5 s.

### 2.4 Proof-gated closure (Path B)

1. Pick any obligation in `active` state.
2. Try to mark it `completed` without proof — request is **rejected**.
3. Submit proof via `POST /api/v1/proofs/verify` with a matching SHA-256.
4. Confirm the verifier returns one of `verified`, `weak_match`, `rejected`
   with explainable reasons.

### 2.5 Risk and escalation engine (Path B)

1. On any open obligation, set `due_date` to 2 days in the future via the
   review-edit dialog.
2. Reload `/obligations`.
3. Confirm the row shows `escalation.level = escalated` and the reason
   `due_within_3_days`.
4. Set `due_date` to a past date — escalation should flip to `critical`
   with reason `overdue`.

### 2.6 Public-Trust view (Path A or B)

1. Open `http://localhost:3000/public`.
2. Confirm:
   - case numbers are masked,
   - personal names are masked to deterministic placeholders,
   - obligation text is plain-language,
   - emails / phones / Aadhaar / PAN are absent.

### 2.7 Department health (Path B)

1. Open `/departments`.
2. Confirm each department card shows compliance rate, missed deadlines,
   and case count.
3. Hit `GET /api/v1/departments/health` directly to inspect the JSON.

### 2.8 Visual regressions

While walking the wizard, eyeball:

- Stage stepper highlights the right stage after each transition.
- Right-pane PDF viewer scrolls to the cited page when an obligation citation is clicked.
- The "**Why?**" panel opens for each obligation and lists components, weights, rationale.
- The case-flow graph and map render without console errors.

---

## 3. Bug Reporting

When opening a defect, attach all of the following:

1. **Path**: A or B.
2. **Stage** at which it broke (e.g. `summary_pending`).
3. **HTTP request id** from the response header `x-request-id` (visible in
   browser devtools / Network).
4. **Browser console** screenshot (errors + warnings).
5. For Path B: the matching log files —
   `Application/orderflow/tmp/startup-logs/{backend,worker,frontend}.{out,err}.log`.
6. The PDF or eCourts URL used.
7. Reproduction steps from a clean state.

If you have access to Jaeger, drop the trace id from the same request id —
that traces the call across backend, worker, and intelligence.

---

## 4. Resetting / Clean Slate

### Path A

Just refresh the browser tab. Demo state is in-memory per session.

### Path B

```powershell
# Stop everything
cd Application/orderflow/app/infra
docker compose down

# Remove Postgres volume (DESTROYS DATA — only for clean reset)
docker volume ls | findstr orderflow
docker volume rm orderflow-local_postgres-data

# Remove Temporal container
docker rm -f orderflow-temporal

# Bring stack back up (the start script handles migrations + seeding)
cd ..\..
powershell -ExecutionPolicy Bypass -File .\scripts\start-orderflow.ps1
# Choose option 1 → 3 (force start)
```

---

## 5. Common Issues

| Symptom                                                       | Fix                                                                                                                                       |
| ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `npm install` fails on Windows with EPERM                     | Close VS Code / any explorer window inside the repo, then retry. Prefer running terminals as a normal user, not Administrator.            |
| Frontend page is blank, console says `Failed to fetch`        | Backend not running on `:8000`. Start it (Path B step B.2.6) or fall back to demo mode.                                                   |
| `docker compose up` errors with port 5432 in use              | Stop any local Postgres service, or change `POSTGRES_PORT` in `app/infra/.env`.                                                           |
| Migration error `permission denied for schema public`         | Reset the volume (section 4) and rerun migrations.                                                                                        |
| Temporal worker prints `connection refused`                   | Temporal container hasn't finished bootstrapping yet — wait 30 s, retry. If still failing, `docker logs orderflow-temporal`.              |
| AI extraction returns `429`                                   | Gemini free-tier rate limit. Wait a minute, or set `ORDERFLOW_AI_ENABLED_DEFAULT=false` to fall back to deterministic extraction.         |
| PDF viewer shows blank pages                                  | The PDF was scanned and OCR is disabled. Set `ORDERFLOW_OCR_ENABLED=true` and restart backend + worker.                                   |
| Demo lookup says `unknown identifier`                         | You are not on the **demo** branch. `git checkout demo` and rebuild the frontend (`npm run dev`).                                         |
| Login fails with `invalid credentials`                        | Demo seed didn't run. From `app/backend`: `python -m scripts.seed_demo_advocates`, then re-login.                                         |
| Frontend hot-reload stuck                                     | Ctrl+C the dev server, delete `.next/`, run `npm run dev` again.                                                                          |

---

## 6. Test Suite (Optional)

If you also want to run the automated tests:

```powershell
# Full quality gate
cd Application/orderflow
python scripts/quality_check.py

# Or per-component
cd app/backend  && python -m pytest -q
cd app/worker   && python -m pytest -q
cd app/intelligence && python -m pytest -q
cd app/frontend && npm run lint && npm run typecheck && npm run test
```

The full quality gate covers Prettier, ESLint, TypeScript, Black, flake8,
and pytest in sequence and exits non-zero on the first failure.

---

## 7. Stopping the App

### Path A
Ctrl+C in the terminal running `npm run dev`.

### Path B (script-managed)
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-orderflow.ps1
# Choose option 1 → 3 (force start) — this stops everything before restarting
# Or just stop the script-launched processes manually:
```

### Path B (manual)
- Ctrl+C the frontend, backend, and worker terminals.
- `docker compose down` in `app/infra`.
- `docker rm -f orderflow-temporal`.

---

## 8. Quick Reference

```
Demo URL                  http://localhost:3000/upload
Demo lookup string        https://delhihighcourt.nic.in/app/showFileJudgment/75005022026CW85242025_154137.pdf
Reviewer login            gov.reviewer@orderflow.example / Orderflow@123
Backend health            http://localhost:8000/api/v1/health
Backend Swagger           http://localhost:8000/docs
Public-Trust              http://localhost:3000/public
MinIO console             http://localhost:9001  (minioadmin/minioadmin)
Jaeger UI                 http://localhost:16686
LibreTranslate            http://localhost:5000
Logs (Path B script)      Application/orderflow/tmp/startup-logs/
Sample judgment           Application/orderflow/docs/samples/court-cases/delhi-hc-wpc-8524-2025-judgment-05-02-2026.pdf
```

---

*Tested on Windows 11 + Docker Desktop 24 + Node 20 + Python 3.12.*
*If something is broken on macOS / Linux, open a bug with the platform tag — the steps are the same except for the PowerShell wrapper.*
