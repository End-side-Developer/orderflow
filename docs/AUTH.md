# OrderFlow — Authentication & Authorization Setup

This document is the operator runbook for OrderFlow's auth system. It
explains who can do what, the seeded credentials, and how to flip auth
on in each deploy environment.

---

## 1. Roles and Permissions

Four roles are wired into the codebase. Higher roles inherit from lower.

| Role         | Can register? | Permissions                                                                                     |
| ------------ | ------------- | ----------------------------------------------------------------------------------------------- |
| `citizen`    | Yes (public)  | Read own profile, submit proofs, browse advocate directory, see Public-Trust dashboard.         |
| `advocate`   | Yes (public)  | Citizen perms + write own advocate profile, read assigned cases, view inquiries.                |
| `judge`      | No (admin)    | Advocate perms + obligation write, document upload, audit read, advocate verification, extraction run. |
| `government` | No (admin)    | Judge perms + user management. **Privileged role — bypasses any per-document owner checks.**     |

The "evaluator" credential for the hackathon is **a regular `government`
account** — there is no separate role enum. This keeps the role model
small and means the evaluator can exercise every flow end-to-end without
any special-case code.

`citizen` and `advocate` are the only roles available via the public
`/auth/register` endpoint. `judge` and `government` accounts must be
created via a seed script or directly in the database.

---

## 2. Seeded Demo / Evaluator Credentials

All seed scripts live in `app/backend/scripts/`. They are idempotent — safe
to re-run.

### 2.1 Evaluator (single hackathon credential)

```powershell
cd app/backend
python -m scripts.seed_evaluator
```

Creates one account:

| Field    | Value                                           |
| -------- | ----------------------------------------------- |
| Email    | `evaluator@orderflow.example`                   |
| Password | `Evaluator@2026`                                |
| Role     | `government` (full access, demo-friendly)       |
| Status   | `active`                                        |

Override via env vars before running:

```powershell
$env:ORDERFLOW_EVALUATOR_EMAIL = "judge1@hackathon.example"
$env:ORDERFLOW_EVALUATOR_PASSWORD = "<strong-password>"
$env:ORDERFLOW_EVALUATOR_NAME    = "Hackathon Judge 1"
python -m scripts.seed_evaluator
```

### 2.2 Demo accounts for full-stack testing

```powershell
python -m scripts.seed_demo_advocates
```

Creates three accounts:

| Role                            | Email                                | Password         |
| ------------------------------- | ------------------------------------ | ---------------- |
| Government reviewer (admin-ish) | `gov.reviewer@orderflow.example`     | `Orderflow@123`  |
| Advocate — already approved     | `adv.approved@orderflow.example`     | `Orderflow@123`  |
| Advocate — pending verification | `adv.pending@orderflow.example`      | `Orderflow@123`  |

Use **government reviewer** for almost every test. The two advocate
accounts exist to verify the verification flow.

### 2.3 Creating additional users

The only way to add a regular `citizen` or `advocate` account is the
public `/auth/register` endpoint (i.e. via the **/register** page in
the UI). Higher-role accounts (`judge`, `government`) require a seed
script or direct SQL — by design.

---

## 3. Turning Auth On

Auth is gated by a single backend env var:

```
ORDERFLOW_AUTH_REQUIRED=true
```

**Default in code:** `true` (secure by default).

**Effect when `true`:**
- All routes mounted under `/api/v1` enforce JWT authentication.
- The frontend `middleware.ts` redirects unauthenticated visitors to `/login`
  for every route except `/`, `/login`, `/register`, and `/public`.
- Expired tokens trigger a single refresh attempt; if that fails, the
  store dispatches `auth:logout` and the auth provider hard-redirects to
  `/login?redirect=...` so the user can resume after re-auth.

**When `false` (legacy / pre-Postgres mode):**
- Routes still apply permission checks but `get_current_user` returns a
  synthetic `government` user when no token is present. This is the
  historical demo behaviour and remains supported during migration.

### 3.1 Local development

The `.env` files copied from `.env.example` should include:

```
ORDERFLOW_AUTH_REQUIRED=true
ORDERFLOW_JWT_SECRET=<generate a 32+ char random string>
```

Generate a secret with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 3.2 Azure (production / staging)

The Azure App Service `orderflow-api-kr` currently runs in
**stub-repository mode** (`ORDERFLOW_API_USE_STUB_REPOSITORY=true`)
without an attached Postgres. Because user accounts live in Postgres,
flipping `ORDERFLOW_AUTH_REQUIRED=true` while still in stub mode would
prevent anyone from logging in.

The temporary Azure setting therefore is:

```
ORDERFLOW_AUTH_REQUIRED=false   # ← override on Azure until Postgres is provisioned
```

Once Postgres is attached (see §4), set it to `true` and seed users.

### 3.3 Hardening the JWT secret on Azure

```powershell
$secret = python -c "import secrets; print(secrets.token_urlsafe(48))"
az webapp config appsettings set `
  --name orderflow-api-kr --resource-group Orderflow `
  --settings ORDERFLOW_JWT_SECRET=$secret
az webapp restart --name orderflow-api-kr --resource-group Orderflow
```

**Rotating the JWT secret invalidates every active session.** All users
have to log in again, which is the desired behaviour after a rotation.

---

## 4. Going to Real Postgres on Azure (Future Step)

When you're ready to flip auth on for real:

1. **Provision a Postgres flexible server** in `koreacentral`:

   ```powershell
   $pgPassword = python -c "import secrets; print(secrets.token_urlsafe(24))"
   az postgres flexible-server create `
     --name orderflow-pg-kr --resource-group Orderflow `
     --location koreacentral --tier Burstable --sku-name Standard_B1ms `
     --admin-user orderflow --admin-password $pgPassword `
     --version 16 --storage-size 32 --public-access 0.0.0.0
   az postgres flexible-server db create `
     --resource-group Orderflow --server-name orderflow-pg-kr --database-name orderflow
   az postgres flexible-server parameter set `
     --resource-group Orderflow --server-name orderflow-pg-kr `
     --name azure.extensions --value vector,uuid-ossp,pg_trgm
   ```

2. **Wire the connection string into the Web App and disable stub mode:**

   ```powershell
   $connStr = "postgresql+psycopg://orderflow:$pgPassword@orderflow-pg-kr.postgres.database.azure.com:5432/orderflow?sslmode=require"
   az webapp config appsettings set --name orderflow-api-kr --resource-group Orderflow `
     --settings `
       ORDERFLOW_API_DATABASE_URL=$connStr `
       ORDERFLOW_API_USE_STUB_REPOSITORY=false `
       ORDERFLOW_AUTH_REQUIRED=true
   ```

3. **Run migrations and seed users on first boot.** The simplest path is
   a one-shot SSH session into the app:

   ```powershell
   az webapp ssh --name orderflow-api-kr --resource-group Orderflow
   # inside the SSH:
   cd /home/site/wwwroot
   python -m alembic -c alembic.ini upgrade head
   python -m scripts.seed_demo_advocates
   python -m scripts.seed_evaluator
   exit
   ```

4. **Verify:**

   ```powershell
   curl -X POST https://orderflow-api-kr.azurewebsites.net/api/v1/auth/login `
     -H "content-type: application/json" `
     -d '{"email":"evaluator@orderflow.example","password":"Evaluator@2026"}'
   # expect: {"ok": true, "data": {"access_token": "...", "user": { ... }}}
   ```

After step 4, calls without an `Authorization: Bearer ...` header will
get `401 Unauthorized`. Mission accomplished.

---

## 5. How API Protection Works

Every sensitive route uses one of three FastAPI dependencies (all live
in `api/dependencies/auth.py`):

| Dependency                | Purpose                                                                                  |
| ------------------------- | ---------------------------------------------------------------------------------------- |
| `get_current_user`        | Parses the bearer token. Returns the user or 401. In legacy mode returns a synthetic gov user. |
| `require_permission(p)`   | Calls `get_current_user`, then 403s if the user's role lacks permission `p`.             |
| `require_role(*roles)`    | Calls `get_current_user`, then 403s if the user's role isn't in the allow-list.          |
| `require_self_or_role(...)` | For `/users/{id}` style paths — caller must be the same user, or have one of the roles. |

The full permission matrix is in `core/auth/permissions.py`. Routes
already protected with `Depends(require_permission(...))` include —

- Documents: `/documents/*`, `/documents/intake/*`, `/documents/{id}/download`
- Cases: every endpoint under `/cases/{id}/*`
- Page summaries / annotations / clauses
- Obligations and escalations
- Routing, departments, advocates
- Workbench, workflows, exports
- Intelligence (`/judgment-decisions`, `/page-insight`, `/extract-obligations`, `/review-obligation`)

Open routes (no auth required, by design):

- `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/register`, `/auth/me`
- `/health`
- `/public/obligations` (Public-Trust read-only, PII redacted)
- `/webhooks/ccms` (gateway delivery; intentional public ingress for CCMS)

---

## 6. Frontend Behaviour

- `middleware.ts` checks for the `orderflow_refresh` cookie on every
  request. If absent and the path is not in `/`, `/login`, `/register`,
  `/public`, the user is redirected to `/login?redirect=<original path>`.
- After a successful login, the redirect param is honoured.
- On any 401 from the API client, the auth store attempts a single
  refresh. If the refresh also returns 401, the session is cleared and
  the `auth:logout` event fires, triggering a hard redirect to `/login`.
- The auth store persists only the user summary in `localStorage`. The
  access token stays in memory; the refresh token lives in an HttpOnly
  cookie and is unreadable from JS.

The role of the logged-in user is exposed via `useAuthStore` selectors
(`selectRole`, `selectUser`). UI elements that should be role-gated
should call these — but the **backend is the source of truth**; the
frontend gating is a UX nicety only.

---

## 7. Security Hardening Checklist (Pre-Launch)

- [ ] `ORDERFLOW_JWT_SECRET` is a 32+ char random value, **not** the dev default.
- [ ] `ORDERFLOW_AUTH_REQUIRED=true` in every non-local env.
- [ ] `ORDERFLOW_API_CORS_ORIGINS` contains only your real frontend domain(s).
- [ ] AI provider keys (`ORDERFLOW_AI_*_API_KEY`) live only in backend env, **never** in frontend code or `NEXT_PUBLIC_*` vars.
- [ ] Passwords for seeded users (`Orderflow@123`, `Evaluator@2026`) are rotated before any external evaluator gets access.
- [ ] Postgres firewall is closed to the public IP range; only Azure App Service can reach it.
- [ ] `/auth/login` is rate-limited (TODO — not yet implemented; tracked under Roadmap).
- [ ] AI endpoints are rate-limited (TODO — not yet implemented; tracked under Roadmap).

---

## 8. Roadmap (Not Yet Implemented)

- **Per-document `owner_user_id`** — current model lets any government-role
  user see all cases. To support multiple non-privileged government users
  isolating their own cases, add an `owner_user_id` column to the
  `documents` table and enforce it in `documents.py` + `cases.py`.
- **Rate limiting** — slowapi or upstash-style limiter on `/auth/login`
  (5 attempts / 5 min / IP) and AI endpoints (Gemini-tier matching).
- **Email verification** — `email_verified_at` column already exists;
  the verify-email flow is not yet wired.
- **Password reset** — same: schema is ready, flow is not.
