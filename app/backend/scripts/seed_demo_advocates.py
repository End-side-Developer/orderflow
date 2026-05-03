"""Seed idempotent demo advocate accounts for local OrderFlow startup.

Creates a small, repeatable set of demo profiles:
- Government reviewer account
- Advocate already approved by government
- Advocate pending (not approved yet)

Safe to re-run. Existing users/profiles are not overwritten.

Usage:
    python -m scripts.seed_demo_advocates
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from orderflow_api.api import user_persistence
from orderflow_api.core.auth.passwords import hash_password
from orderflow_api.schemas.users import UserRecord


DEMO_PASSWORD = "Orderflow@123"


@dataclass(frozen=True)
class DemoUserSpec:
    email: str
    full_name: str
    role: str
    status: str
    preferred_language: str = "en"
    phone: str | None = None


@dataclass(frozen=True)
class DemoAdvocateSpec:
    user: DemoUserSpec
    bar_council_id: str
    registration_number: str
    bio: str
    years_of_experience: int
    languages: list[str]
    specializations: list[str]
    jurisdictions: list[dict[str, Any]]
    education: list[dict[str, Any]]
    consultation_fee_min_inr: int
    consultation_fee_max_inr: int
    verification_status: str  # pending | verified


GOVERNMENT_REVIEWER = DemoUserSpec(
    email="gov.reviewer@orderflow.example",
    full_name="Demo Government Reviewer",
    role="government",
    status="active",
)


DEMO_ADVOCATES: tuple[DemoAdvocateSpec, ...] = (
    DemoAdvocateSpec(
        user=DemoUserSpec(
            email="adv.approved@orderflow.example",
            full_name="Adv. Ananya Menon",
            role="advocate",
            status="pending_verification",
        ),
        bar_council_id="BAR/DL/2026/00101",
        registration_number="DEL-ADV-2026-00101",
        bio=(
            "Constitutional and civil litigator with a focus on compliance-driven "
            "implementation of court directives."
        ),
        years_of_experience=11,
        languages=["en", "hi"],
        specializations=["constitutional", "civil"],
        jurisdictions=[
            {"level": "high_court", "name": "Delhi High Court", "state": "Delhi"}
        ],
        education=[
            {"institution": "Faculty of Law, Delhi University", "degree": "LL.B.", "year": 2012}
        ],
        consultation_fee_min_inr=2500,
        consultation_fee_max_inr=6000,
        verification_status="verified",
    ),
    DemoAdvocateSpec(
        user=DemoUserSpec(
            email="adv.pending@orderflow.example",
            full_name="Adv. Raghav Kulkarni",
            role="advocate",
            status="pending_verification",
        ),
        bar_council_id="BAR/KA/2026/00127",
        registration_number="KAR-ADV-2026-00127",
        bio=(
            "Labour and consumer law practitioner handling state-level litigation "
            "for service and compliance matters."
        ),
        years_of_experience=6,
        languages=["en", "kn", "hi"],
        specializations=["labour", "consumer"],
        jurisdictions=[
            {"level": "high_court", "name": "Karnataka High Court", "state": "Karnataka"}
        ],
        education=[
            {"institution": "NLSIU Bengaluru", "degree": "B.A. LL.B.", "year": 2018}
        ],
        consultation_fee_min_inr=1800,
        consultation_fee_max_inr=4200,
        verification_status="pending",
    ),
)


def _ensure_user(spec: DemoUserSpec) -> tuple[UserRecord, bool]:
    found = user_persistence.get_user_by_email(spec.email)
    if found is not None:
        return found[0], False

    user = user_persistence.insert_user(
        email=spec.email,
        password_hash=hash_password(DEMO_PASSWORD),
        role=spec.role,
        status=spec.status,
        full_name=spec.full_name,
        phone=spec.phone,
        preferred_language=spec.preferred_language,
        profile_metadata={"seed_source": "scripts.seed_demo_advocates", "demo": True},
    )
    return user, True


def _ensure_advocate_profile(
    spec: DemoAdvocateSpec,
    *,
    reviewer_user_id: UUID,
) -> tuple[bool, bool]:
    user, created_user = _ensure_user(spec.user)
    profile = user_persistence.get_advocate_profile(user.id)
    created_profile = False
    status_applied = False

    if profile is None:
        user_persistence.insert_advocate_profile(
            user_id=user.id,
            bar_council_id=spec.bar_council_id,
            registration_number=spec.registration_number,
            photo_url=None,
            bio=spec.bio,
            years_of_experience=spec.years_of_experience,
            languages=spec.languages,
            specializations=spec.specializations,
            jurisdictions=spec.jurisdictions,
            education=spec.education,
            notable_cases=None,
            consultation_fee_min_inr=spec.consultation_fee_min_inr,
            consultation_fee_max_inr=spec.consultation_fee_max_inr,
            availability={"days_of_week": ["Mon", "Wed", "Fri"], "time_slots": ["10:00-13:00"]},
            contact_preferences={"email": True, "phone": False, "in_app": True},
        )
        created_profile = True

    # Apply initial verification state only at first seed creation so reruns
    # never overwrite manual moderation done by reviewers.
    if created_profile and spec.verification_status == "verified":
        user_persistence.set_advocate_verification(
            user.id,
            status="verified",
            verified_by_user_id=reviewer_user_id,
            rejection_reason=None,
        )
        status_applied = True

    return created_user or created_profile, status_applied


def main() -> int:
    created_any = False
    created_users = 0
    created_profiles = 0
    applied_verification = 0

    reviewer, reviewer_created = _ensure_user(GOVERNMENT_REVIEWER)
    if reviewer_created:
        created_any = True
        created_users += 1

    for spec in DEMO_ADVOCATES:
        before_user = user_persistence.get_user_by_email(spec.user.email)
        had_user = before_user is not None
        had_profile = False
        if before_user is not None:
            had_profile = user_persistence.get_advocate_profile(before_user[0].id) is not None

        created, status_applied = _ensure_advocate_profile(spec, reviewer_user_id=reviewer.id)
        created_any = created_any or created
        if status_applied:
            applied_verification += 1

        after_user = user_persistence.get_user_by_email(spec.user.email)
        if not had_user and after_user is not None:
            created_users += 1
        if after_user is not None:
            now_has_profile = user_persistence.get_advocate_profile(after_user[0].id) is not None
            if not had_profile and now_has_profile:
                created_profiles += 1

    if created_any:
        print(
            "Demo advocate seeding complete: "
            f"{created_users} user(s) created, "
            f"{created_profiles} advocate profile(s) created, "
            f"{applied_verification} approval(s) applied."
        )
    else:
        print("Demo advocate profiles already seeded; no changes made.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
