# Environment Variable Policy

Purpose: keep configuration predictable, secure, and service-scoped.

## Global Rules

- All project variables start with ORDERFLOW_.
- Secrets are never committed to git.
- `.env.example` contains non-secret placeholders only.
- Runtime values are loaded from environment, not hardcoded in code.

## Service Prefixes

- Backend: ORDERFLOW_API_
- Frontend: ORDERFLOW_WEB_
- Worker: ORDERFLOW_WORKER_
- Intelligence: ORDERFLOW_AI_
- Data pipelines: ORDERFLOW_PIPELINE_
- Infra: ORDERFLOW_INFRA_

AI extraction settings used by backend also use the ORDERFLOW_AI_ prefix.

## Required Shared Variables

- ORDERFLOW_ENV (local, dev, staging, prod)
- ORDERFLOW_LOG_LEVEL (debug, info, warning, error)
- ORDERFLOW_OTEL_ENDPOINT

## Secret Management Rules

- Database credentials are injected at runtime.
- API keys and tokens are injected at runtime.
- Local development can use `.env.local` files that are gitignored.

## Validation Rules

- Each service must fail fast if required variables are missing.
- Config loaders should validate type and allowed values on startup.

## Backend AI Variables

- ORDERFLOW_AI_ENABLED_DEFAULT
- ORDERFLOW_AI_ALLOW_USER_OVERRIDE
- ORDERFLOW_AI_DEFAULT_PROVIDER
- ORDERFLOW_AI_DEFAULT_MODEL
- ORDERFLOW_AI_OPENAI_API_KEY
- ORDERFLOW_AI_ANTHROPIC_API_KEY
- ORDERFLOW_AI_TIMEOUT_SECONDS
- ORDERFLOW_AI_MAX_CLAUSES

If request-level key overrides are enabled for live testing, they must be treated as runtime-only values and must never be written to git-tracked files.
