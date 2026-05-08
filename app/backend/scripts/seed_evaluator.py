"""Seed the dedicated hackathon evaluator account.

Creates one account with role=government so the evaluator can exercise the
full OrderFlow flow end-to-end (upload, intake, AI extraction, review,
finalize, dashboard) without needing any other privileged credential.

The account is intentionally a single-purpose login, separate from the
regular `gov.reviewer@orderflow.example` seed so it is easy to revoke or
rotate after the hackathon.

Configurable via env:
    ORDERFLOW_EVALUATOR_EMAIL     (default: evaluator@orderflow.example)
    ORDERFLOW_EVALUATOR_PASSWORD  (default: Evaluator@2026)
    ORDERFLOW_EVALUATOR_NAME      (default: Hackathon Evaluator)

Safe to re-run; existing accounts are left untouched. To rotate the
password, change it via the /auth/password endpoint after logging in.

Usage:
    python -m scripts.seed_evaluator
"""

from __future__ import annotations

import os
import sys

from orderflow_api.api import user_persistence
from orderflow_api.core.auth.passwords import hash_password


# Placeholders only — the real evaluator email/password MUST be supplied
# via the env vars below (set as GitHub Secrets in CI / Azure app settings
# locally). Never commit real credentials to git.
DEFAULT_EMAIL = "evaluator@example.invalid"
DEFAULT_PASSWORD = "change-me-in-env"
DEFAULT_NAME = "OrderFlow Hackathon Evaluator"


def main() -> int:
    email = os.environ.get("ORDERFLOW_EVALUATOR_EMAIL", DEFAULT_EMAIL).strip().lower()
    password = os.environ.get("ORDERFLOW_EVALUATOR_PASSWORD", DEFAULT_PASSWORD)
    full_name = os.environ.get("ORDERFLOW_EVALUATOR_NAME", DEFAULT_NAME)

    found = user_persistence.get_user_by_email(email)
    if found is not None:
        print(f"Evaluator account already exists: {email}. No changes.")
        return 0

    user_persistence.insert_user(
        email=email,
        password_hash=hash_password(password),
        role="government",
        status="active",
        full_name=full_name,
        phone=None,
        preferred_language="en",
        profile_metadata={
            "seed_source": "scripts.seed_evaluator",
            "purpose": "hackathon_evaluation",
        },
    )
    print(
        f"Evaluator account created: {email} "
        f"(role=government, password from env or default '{DEFAULT_PASSWORD}')."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
