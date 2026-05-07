from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import RowMapping

from orderflow_api.core.db import get_engine
from orderflow_api.schemas.advocates import (
    AdvocateCaseLinkRecord,
    AdvocateDirectoryItem,
    AdvocateProfileRecord,
    Availability,
    ContactPreferences,
)
from orderflow_api.schemas.users import UserRecord


_METADATA = sa.MetaData()


USERS_TABLE = sa.Table(
    "users",
    _METADATA,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
    sa.Column("email", sa.Text(), nullable=False),
    sa.Column("password_hash", sa.Text(), nullable=False),
    sa.Column("role", sa.String(length=32), nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column("full_name", sa.String(length=200), nullable=False),
    sa.Column("phone", sa.String(length=32), nullable=True),
    sa.Column("preferred_language", sa.String(length=8), nullable=False),
    sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "profile_metadata",
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    ),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)


REFRESH_TOKENS_TABLE = sa.Table(
    "refresh_tokens",
    _METADATA,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
    sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("replaced_by", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("user_agent", sa.Text(), nullable=True),
    sa.Column("ip_address", postgresql.INET(), nullable=True),
)


CREDENTIALS_AUDIT_TABLE = sa.Table(
    "user_credentials_audit",
    _METADATA,
    sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
    sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("event", sa.String(length=64), nullable=False),
    sa.Column("ip_address", postgresql.INET(), nullable=True),
    sa.Column("user_agent", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)


ADVOCATE_PROFILES_TABLE = sa.Table(
    "advocate_profiles",
    _METADATA,
    sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
    sa.Column("bar_council_id", sa.String(length=64), nullable=False),
    sa.Column("registration_number", sa.String(length=64), nullable=True),
    sa.Column("photo_url", sa.Text(), nullable=True),
    sa.Column("bio", sa.Text(), nullable=True),
    sa.Column("years_of_experience", sa.SmallInteger(), nullable=True),
    sa.Column("languages", postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column("specializations", postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column("jurisdictions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("education", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("notable_cases", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("consultation_fee_min_inr", sa.Integer(), nullable=True),
    sa.Column("consultation_fee_max_inr", sa.Integer(), nullable=True),
    sa.Column("availability", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("contact_preferences", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("verification_status", sa.String(length=32), nullable=False),
    sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("verified_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("rejection_reason", sa.Text(), nullable=True),
    sa.Column("ratings_avg", sa.Numeric(3, 2), nullable=False),
    sa.Column("ratings_count", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    # Generated tsvector — declared on the model so we can reference it in
    # filters via ADVOCATE_PROFILES_TABLE.c.search_tsv. Reads only; writes
    # are handled by the GENERATED ALWAYS clause in the migration.
    sa.Column("search_tsv", postgresql.TSVECTOR(), nullable=True),
)

DOCUMENTS_TABLE = sa.Table(
    "documents",
    _METADATA,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
    sa.Column("source_file_name", sa.String(length=255), nullable=False),
    sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
)

CASE_ADVOCATES_TABLE = sa.Table(
    "case_advocates",
    _METADATA,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
    sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("advocate_user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("role", sa.String(length=32), nullable=False),
    sa.Column("status", sa.String(length=16), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("verified_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
)


class EmailAlreadyRegistered(Exception):
    pass


class BarCouncilIdAlreadyRegistered(Exception):
    pass


class UserNotFound(Exception):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


# ------------- users -------------------------------------------------------


def insert_user(
    *,
    email: str,
    password_hash: str,
    role: str,
    status: str,
    full_name: str,
    phone: str | None,
    preferred_language: str,
    profile_metadata: dict[str, Any] | None = None,
) -> UserRecord:
    user_id = uuid4()
    now = _now()
    row = {
        "id": user_id,
        "email": email,
        "password_hash": password_hash,
        "role": role,
        "status": status,
        "full_name": full_name,
        "phone": phone,
        "preferred_language": preferred_language,
        "email_verified_at": None,
        "last_login_at": None,
        "profile_metadata": profile_metadata or {},
        "created_at": now,
        "updated_at": now,
    }
    try:
        with get_engine().begin() as connection:
            connection.execute(sa.insert(USERS_TABLE).values(row))
    except sa.exc.IntegrityError as exc:
        raise EmailAlreadyRegistered(email) from exc
    return _to_user_record(row)


def get_user_by_email(email: str) -> tuple[UserRecord, str] | None:
    """Return (user, password_hash) tuple, or None if no such user."""
    statement = sa.select(USERS_TABLE).where(USERS_TABLE.c.email == email)
    with get_engine().connect() as connection:
        row = connection.execute(statement).mappings().first()
    if row is None:
        return None
    return _to_user_record(row), row["password_hash"]


def get_user_by_id(user_id: UUID) -> UserRecord | None:
    statement = sa.select(USERS_TABLE).where(USERS_TABLE.c.id == user_id)
    with get_engine().connect() as connection:
        row = connection.execute(statement).mappings().first()
    return _to_user_record(row) if row is not None else None


def get_user_with_password_hash(user_id: UUID) -> tuple[UserRecord, str] | None:
    statement = sa.select(USERS_TABLE).where(USERS_TABLE.c.id == user_id)
    with get_engine().connect() as connection:
        row = connection.execute(statement).mappings().first()
    if row is None:
        return None
    return _to_user_record(row), row["password_hash"]


def update_user_last_login(user_id: UUID) -> None:
    now = _now()
    with get_engine().begin() as connection:
        connection.execute(
            sa.update(USERS_TABLE)
            .where(USERS_TABLE.c.id == user_id)
            .values(last_login_at=now, updated_at=now)
        )


def update_user_password(user_id: UUID, password_hash: str) -> None:
    now = _now()
    with get_engine().begin() as connection:
        connection.execute(
            sa.update(USERS_TABLE)
            .where(USERS_TABLE.c.id == user_id)
            .values(password_hash=password_hash, updated_at=now)
        )


def update_user_fields(
    user_id: UUID,
    *,
    full_name: str | None = None,
    phone: str | None = None,
    preferred_language: str | None = None,
    profile_metadata: dict[str, Any] | None = None,
    role: str | None = None,
    status: str | None = None,
) -> UserRecord | None:
    values: dict[str, Any] = {}
    if full_name is not None:
        values["full_name"] = full_name
    if phone is not None:
        values["phone"] = phone
    if preferred_language is not None:
        values["preferred_language"] = preferred_language
    if profile_metadata is not None:
        values["profile_metadata"] = profile_metadata
    if role is not None:
        values["role"] = role
    if status is not None:
        values["status"] = status

    if not values:
        return get_user_by_id(user_id)

    values["updated_at"] = _now()

    with get_engine().begin() as connection:
        connection.execute(
            sa.update(USERS_TABLE).where(USERS_TABLE.c.id == user_id).values(**values)
        )

    return get_user_by_id(user_id)


# ------------- refresh tokens ----------------------------------------------


def insert_refresh_token(
    *,
    token_id: UUID,
    user_id: UUID,
    expires_at: datetime,
    issued_at: datetime,
    user_agent: str | None,
    ip_address: str | None,
) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            sa.insert(REFRESH_TOKENS_TABLE).values(
                id=token_id,
                user_id=user_id,
                issued_at=issued_at,
                expires_at=expires_at,
                revoked_at=None,
                replaced_by=None,
                user_agent=user_agent,
                ip_address=ip_address,
            )
        )


def get_active_refresh_token(token_id: UUID) -> RowMapping | None:
    statement = sa.select(REFRESH_TOKENS_TABLE).where(REFRESH_TOKENS_TABLE.c.id == token_id)
    with get_engine().connect() as connection:
        return connection.execute(statement).mappings().first()


def revoke_refresh_token(token_id: UUID, *, replaced_by: UUID | None = None) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            sa.update(REFRESH_TOKENS_TABLE)
            .where(REFRESH_TOKENS_TABLE.c.id == token_id)
            .where(REFRESH_TOKENS_TABLE.c.revoked_at.is_(None))
            .values(revoked_at=_now(), replaced_by=replaced_by)
        )


def revoke_refresh_chain(token_id: UUID) -> None:
    """
    Revoke this token and any descendants — used when token reuse is detected.
    Walks `replaced_by` forward.
    """
    visited: set[UUID] = set()
    cursor: UUID | None = token_id
    with get_engine().begin() as connection:
        while cursor is not None and cursor not in visited:
            visited.add(cursor)
            row = connection.execute(
                sa.select(REFRESH_TOKENS_TABLE.c.replaced_by).where(
                    REFRESH_TOKENS_TABLE.c.id == cursor
                )
            ).first()
            connection.execute(
                sa.update(REFRESH_TOKENS_TABLE)
                .where(REFRESH_TOKENS_TABLE.c.id == cursor)
                .where(REFRESH_TOKENS_TABLE.c.revoked_at.is_(None))
                .values(revoked_at=_now())
            )
            cursor = row[0] if row else None


def revoke_all_user_tokens(user_id: UUID) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            sa.update(REFRESH_TOKENS_TABLE)
            .where(REFRESH_TOKENS_TABLE.c.user_id == user_id)
            .where(REFRESH_TOKENS_TABLE.c.revoked_at.is_(None))
            .values(revoked_at=_now())
        )


# ------------- credentials audit -------------------------------------------


def record_credentials_event(
    *,
    user_id: UUID | None,
    event: str,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            sa.insert(CREDENTIALS_AUDIT_TABLE).values(
                user_id=user_id,
                event=event,
                ip_address=ip_address,
                user_agent=user_agent,
                created_at=_now(),
            )
        )


# ------------- advocate profiles -------------------------------------------


def insert_advocate_profile(
    *,
    user_id: UUID,
    bar_council_id: str,
    registration_number: str | None,
    photo_url: str | None,
    bio: str | None,
    years_of_experience: int | None,
    languages: list[str],
    specializations: list[str],
    jurisdictions: list[dict[str, Any]],
    education: list[dict[str, Any]],
    notable_cases: list[dict[str, Any]] | None,
    consultation_fee_min_inr: int | None,
    consultation_fee_max_inr: int | None,
    availability: dict[str, Any],
    contact_preferences: dict[str, Any],
) -> None:
    now = _now()
    row = {
        "user_id": user_id,
        "bar_council_id": bar_council_id,
        "registration_number": registration_number,
        "photo_url": photo_url,
        "bio": bio,
        "years_of_experience": years_of_experience,
        "languages": languages,
        "specializations": specializations,
        "jurisdictions": jurisdictions,
        "education": education,
        "notable_cases": notable_cases,
        "consultation_fee_min_inr": consultation_fee_min_inr,
        "consultation_fee_max_inr": consultation_fee_max_inr,
        "availability": availability,
        "contact_preferences": contact_preferences,
        "verification_status": "pending",
        "verified_at": None,
        "verified_by_user_id": None,
        "rejection_reason": None,
        "ratings_avg": 0,
        "ratings_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    try:
        with get_engine().begin() as connection:
            connection.execute(sa.insert(ADVOCATE_PROFILES_TABLE).values(row))
    except sa.exc.IntegrityError as exc:
        raise BarCouncilIdAlreadyRegistered(bar_council_id) from exc


def update_advocate_profile(
    user_id: UUID,
    *,
    photo_url: str | None = None,
    bio: str | None = None,
    years_of_experience: int | None = None,
    languages: list[str] | None = None,
    specializations: list[str] | None = None,
    jurisdictions: list[dict[str, Any]] | None = None,
    education: list[dict[str, Any]] | None = None,
    notable_cases: list[dict[str, Any]] | None = None,
    consultation_fee_min_inr: int | None = None,
    consultation_fee_max_inr: int | None = None,
    availability: dict[str, Any] | None = None,
    contact_preferences: dict[str, Any] | None = None,
    registration_number: str | None = None,
) -> AdvocateProfileRecord | None:
    values: dict[str, Any] = {}
    for key, val in {
        "photo_url": photo_url,
        "bio": bio,
        "years_of_experience": years_of_experience,
        "languages": languages,
        "specializations": specializations,
        "jurisdictions": jurisdictions,
        "education": education,
        "notable_cases": notable_cases,
        "consultation_fee_min_inr": consultation_fee_min_inr,
        "consultation_fee_max_inr": consultation_fee_max_inr,
        "availability": availability,
        "contact_preferences": contact_preferences,
        "registration_number": registration_number,
    }.items():
        if val is not None:
            values[key] = val

    if not values:
        return get_advocate_profile(user_id)

    values["updated_at"] = _now()
    with get_engine().begin() as connection:
        connection.execute(
            sa.update(ADVOCATE_PROFILES_TABLE)
            .where(ADVOCATE_PROFILES_TABLE.c.user_id == user_id)
            .values(**values)
        )

    return get_advocate_profile(user_id)


def set_advocate_verification(
    user_id: UUID,
    *,
    status: str,
    verified_by_user_id: UUID | None,
    rejection_reason: str | None,
) -> AdvocateProfileRecord | None:
    now = _now()
    values: dict[str, Any] = {
        "verification_status": status,
        "updated_at": now,
        "rejection_reason": rejection_reason,
    }
    if status == "verified":
        values["verified_at"] = now
        values["verified_by_user_id"] = verified_by_user_id
    elif status == "rejected":
        values["verified_at"] = None

    with get_engine().begin() as connection:
        connection.execute(
            sa.update(ADVOCATE_PROFILES_TABLE)
            .where(ADVOCATE_PROFILES_TABLE.c.user_id == user_id)
            .values(**values)
        )
        # When an advocate is verified, the user account moves from
        # pending_verification → active. Rejection moves them to suspended.
        if status == "verified":
            connection.execute(
                sa.update(USERS_TABLE)
                .where(USERS_TABLE.c.id == user_id)
                .values(status="active", updated_at=now)
            )
        elif status == "rejected":
            connection.execute(
                sa.update(USERS_TABLE)
                .where(USERS_TABLE.c.id == user_id)
                .values(status="suspended", updated_at=now)
            )

    return get_advocate_profile(user_id)


def get_advocate_profile(user_id: UUID) -> AdvocateProfileRecord | None:
    join = ADVOCATE_PROFILES_TABLE.join(
        USERS_TABLE, USERS_TABLE.c.id == ADVOCATE_PROFILES_TABLE.c.user_id
    )
    statement = (
        sa.select(
            ADVOCATE_PROFILES_TABLE,
            USERS_TABLE.c.full_name.label("full_name"),
        )
        .select_from(join)
        .where(ADVOCATE_PROFILES_TABLE.c.user_id == user_id)
    )
    with get_engine().connect() as connection:
        row = connection.execute(statement).mappings().first()
    return _to_advocate_record(row) if row is not None else None


def list_advocates(
    *,
    q: str | None = None,
    specialization: str | None = None,
    jurisdiction_level: str | None = None,
    jurisdiction_state: str | None = None,
    language: str | None = None,
    min_experience: int | None = None,
    max_fee: int | None = None,
    sort: str = "rating",
    only_verified: bool = True,
    pending_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[AdvocateDirectoryItem]]:
    join = ADVOCATE_PROFILES_TABLE.join(
        USERS_TABLE, USERS_TABLE.c.id == ADVOCATE_PROFILES_TABLE.c.user_id
    )

    where_clauses: list[sa.sql.ColumnElement[bool]] = []
    if pending_only:
        where_clauses.append(ADVOCATE_PROFILES_TABLE.c.verification_status == "pending")
    elif only_verified:
        where_clauses.append(ADVOCATE_PROFILES_TABLE.c.verification_status == "verified")
    if specialization:
        where_clauses.append(
            ADVOCATE_PROFILES_TABLE.c.specializations.op("&&")(
                sa.cast([specialization], postgresql.ARRAY(sa.Text()))
            )
        )
    if language:
        where_clauses.append(
            ADVOCATE_PROFILES_TABLE.c.languages.op("&&")(
                sa.cast([language], postgresql.ARRAY(sa.Text()))
            )
        )
    if jurisdiction_level:
        where_clauses.append(
            ADVOCATE_PROFILES_TABLE.c.jurisdictions.op("@>")(
                sa.cast([{"level": jurisdiction_level}], postgresql.JSONB)
            )
        )
    if jurisdiction_state:
        where_clauses.append(
            ADVOCATE_PROFILES_TABLE.c.jurisdictions.op("@>")(
                sa.cast([{"state": jurisdiction_state}], postgresql.JSONB)
            )
        )
    if min_experience is not None:
        where_clauses.append(ADVOCATE_PROFILES_TABLE.c.years_of_experience >= min_experience)
    if max_fee is not None:
        where_clauses.append(
            sa.or_(
                ADVOCATE_PROFILES_TABLE.c.consultation_fee_min_inr.is_(None),
                ADVOCATE_PROFILES_TABLE.c.consultation_fee_min_inr <= max_fee,
            )
        )
    if q:
        # tsvector match on bio + ILIKE on full_name so callers get both
        # bio-text and name-prefix hits without two endpoints.
        ts = sa.func.plainto_tsquery("simple", q)
        where_clauses.append(
            sa.or_(
                ADVOCATE_PROFILES_TABLE.c.search_tsv.op("@@")(ts),
                USERS_TABLE.c.full_name.ilike(f"%{q}%"),
            )
        )

    case_count_subquery = (
        sa.select(sa.func.count())
        .select_from(CASE_ADVOCATES_TABLE)
        .where(CASE_ADVOCATES_TABLE.c.advocate_user_id == ADVOCATE_PROFILES_TABLE.c.user_id)
        .correlate(ADVOCATE_PROFILES_TABLE)
        .scalar_subquery()
    )

    base = sa.select(
        ADVOCATE_PROFILES_TABLE.c.user_id,
        USERS_TABLE.c.full_name.label("full_name"),
        ADVOCATE_PROFILES_TABLE.c.photo_url,
        ADVOCATE_PROFILES_TABLE.c.years_of_experience,
        ADVOCATE_PROFILES_TABLE.c.languages,
        ADVOCATE_PROFILES_TABLE.c.specializations,
        ADVOCATE_PROFILES_TABLE.c.jurisdictions,
        ADVOCATE_PROFILES_TABLE.c.consultation_fee_min_inr,
        ADVOCATE_PROFILES_TABLE.c.consultation_fee_max_inr,
        ADVOCATE_PROFILES_TABLE.c.ratings_avg,
        ADVOCATE_PROFILES_TABLE.c.ratings_count,
        ADVOCATE_PROFILES_TABLE.c.verified_at,
        case_count_subquery.label("case_count"),
    ).select_from(join)

    if where_clauses:
        base = base.where(sa.and_(*where_clauses))

    if sort == "experience":
        base = base.order_by(
            sa.desc(sa.func.coalesce(ADVOCATE_PROFILES_TABLE.c.years_of_experience, 0))
        )
    elif sort == "recent":
        base = base.order_by(sa.desc(ADVOCATE_PROFILES_TABLE.c.created_at))
    else:  # default → rating
        base = base.order_by(
            sa.desc(ADVOCATE_PROFILES_TABLE.c.ratings_avg),
            sa.desc(ADVOCATE_PROFILES_TABLE.c.ratings_count),
        )

    count_stmt = sa.select(sa.func.count()).select_from(base.subquery())
    page_stmt = base.limit(limit).offset(offset)

    with get_engine().connect() as connection:
        total = int(connection.execute(count_stmt).scalar_one())
        rows = connection.execute(page_stmt).mappings().all()

    items = [
        AdvocateDirectoryItem(
            user_id=row["user_id"],
            full_name=row["full_name"],
            photo_url=row["photo_url"],
            years_of_experience=row["years_of_experience"],
            languages=list(row["languages"] or []),
            specializations=list(row["specializations"] or []),
            jurisdictions=row["jurisdictions"] or [],
            consultation_fee_min_inr=row["consultation_fee_min_inr"],
            consultation_fee_max_inr=row["consultation_fee_max_inr"],
            ratings_avg=float(row["ratings_avg"] or 0),
            ratings_count=row["ratings_count"] or 0,
            verified_at=row["verified_at"],
            case_count=int(row["case_count"] or 0),
        )
        for row in rows
    ]
    return total, items


def list_advocate_cases(
    advocate_user_id: UUID,
    *,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[AdvocateCaseLinkRecord]]:
    join = (
        CASE_ADVOCATES_TABLE.join(
            DOCUMENTS_TABLE,
            DOCUMENTS_TABLE.c.id == CASE_ADVOCATES_TABLE.c.document_id,
        )
        .outerjoin(
            USERS_TABLE,
            USERS_TABLE.c.id == CASE_ADVOCATES_TABLE.c.advocate_user_id,
        )
        .outerjoin(
            ADVOCATE_PROFILES_TABLE,
            ADVOCATE_PROFILES_TABLE.c.user_id == CASE_ADVOCATES_TABLE.c.advocate_user_id,
        )
    )

    statement = (
        sa.select(
            CASE_ADVOCATES_TABLE,
            DOCUMENTS_TABLE.c.source_file_name.label("document_title"),
            DOCUMENTS_TABLE.c.metadata.label("document_metadata"),
            USERS_TABLE.c.full_name.label("advocate_full_name"),
            ADVOCATE_PROFILES_TABLE.c.photo_url.label("advocate_photo_url"),
        )
        .select_from(join)
        .where(CASE_ADVOCATES_TABLE.c.advocate_user_id == advocate_user_id)
    )
    if status is not None:
        statement = statement.where(CASE_ADVOCATES_TABLE.c.status == status)

    statement = statement.order_by(
        sa.desc(CASE_ADVOCATES_TABLE.c.verified_at.nulls_last()),
        sa.desc(CASE_ADVOCATES_TABLE.c.created_at),
    )

    count_stmt = sa.select(sa.func.count()).select_from(statement.subquery())
    page_stmt = statement.limit(limit).offset(offset)

    with get_engine().connect() as connection:
        total = int(connection.execute(count_stmt).scalar_one())
        rows = connection.execute(page_stmt).mappings().all()

    return total, [_to_case_link_record(row) for row in rows]


def list_document_advocates(
    document_id: UUID,
    *,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[AdvocateCaseLinkRecord]]:
    join = (
        CASE_ADVOCATES_TABLE.join(
            DOCUMENTS_TABLE,
            DOCUMENTS_TABLE.c.id == CASE_ADVOCATES_TABLE.c.document_id,
        )
        .outerjoin(
            USERS_TABLE,
            USERS_TABLE.c.id == CASE_ADVOCATES_TABLE.c.advocate_user_id,
        )
        .outerjoin(
            ADVOCATE_PROFILES_TABLE,
            ADVOCATE_PROFILES_TABLE.c.user_id == CASE_ADVOCATES_TABLE.c.advocate_user_id,
        )
    )

    statement = (
        sa.select(
            CASE_ADVOCATES_TABLE,
            DOCUMENTS_TABLE.c.source_file_name.label("document_title"),
            DOCUMENTS_TABLE.c.metadata.label("document_metadata"),
            USERS_TABLE.c.full_name.label("advocate_full_name"),
            ADVOCATE_PROFILES_TABLE.c.photo_url.label("advocate_photo_url"),
        )
        .select_from(join)
        .where(CASE_ADVOCATES_TABLE.c.document_id == document_id)
    )
    if status is not None:
        statement = statement.where(CASE_ADVOCATES_TABLE.c.status == status)

    statement = statement.order_by(
        sa.desc(CASE_ADVOCATES_TABLE.c.status),
        sa.desc(CASE_ADVOCATES_TABLE.c.verified_at.nulls_last()),
        sa.desc(CASE_ADVOCATES_TABLE.c.created_at),
    )

    count_stmt = sa.select(sa.func.count()).select_from(statement.subquery())
    page_stmt = statement.limit(limit).offset(offset)
    with get_engine().connect() as connection:
        total = int(connection.execute(count_stmt).scalar_one())
        rows = connection.execute(page_stmt).mappings().all()

    return total, [_to_case_link_record(row) for row in rows]


def claim_advocate_case(
    *,
    advocate_user_id: UUID,
    document_id: UUID,
    role: str,
) -> AdvocateCaseLinkRecord:
    now = _now()
    link_id = uuid4()
    with get_engine().begin() as connection:
        insert_stmt = postgresql.insert(CASE_ADVOCATES_TABLE).values(
            id=link_id,
            document_id=document_id,
            advocate_user_id=advocate_user_id,
            role=role,
            status="claimed",
            created_at=now,
            verified_at=None,
            verified_by_user_id=None,
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["document_id", "advocate_user_id"],
            set_={
                "role": role,
                "status": "claimed",
                "verified_at": None,
                "verified_by_user_id": None,
            },
        )
        connection.execute(upsert_stmt)

    record = get_advocate_case_link(advocate_user_id=advocate_user_id, document_id=document_id)
    if record is None:
        raise UserNotFound()
    return record


def unclaim_advocate_case(*, advocate_user_id: UUID, document_id: UUID) -> bool:
    with get_engine().begin() as connection:
        result = connection.execute(
            sa.delete(CASE_ADVOCATES_TABLE)
            .where(CASE_ADVOCATES_TABLE.c.advocate_user_id == advocate_user_id)
            .where(CASE_ADVOCATES_TABLE.c.document_id == document_id)
            .where(CASE_ADVOCATES_TABLE.c.status == "claimed")
        )
    return bool(result.rowcount and result.rowcount > 0)


def verify_advocate_case(
    *,
    advocate_user_id: UUID,
    document_id: UUID,
    verified_by_user_id: UUID,
) -> AdvocateCaseLinkRecord | None:
    now = _now()
    with get_engine().begin() as connection:
        result = connection.execute(
            sa.update(CASE_ADVOCATES_TABLE)
            .where(CASE_ADVOCATES_TABLE.c.advocate_user_id == advocate_user_id)
            .where(CASE_ADVOCATES_TABLE.c.document_id == document_id)
            .values(
                status="verified",
                verified_at=now,
                verified_by_user_id=verified_by_user_id,
            )
        )
    if not result.rowcount:
        return None
    return get_advocate_case_link(advocate_user_id=advocate_user_id, document_id=document_id)


def get_advocate_case_link(
    *,
    advocate_user_id: UUID,
    document_id: UUID,
) -> AdvocateCaseLinkRecord | None:
    join = (
        CASE_ADVOCATES_TABLE.join(
            DOCUMENTS_TABLE,
            DOCUMENTS_TABLE.c.id == CASE_ADVOCATES_TABLE.c.document_id,
        )
        .outerjoin(
            USERS_TABLE,
            USERS_TABLE.c.id == CASE_ADVOCATES_TABLE.c.advocate_user_id,
        )
        .outerjoin(
            ADVOCATE_PROFILES_TABLE,
            ADVOCATE_PROFILES_TABLE.c.user_id == CASE_ADVOCATES_TABLE.c.advocate_user_id,
        )
    )
    statement = (
        sa.select(
            CASE_ADVOCATES_TABLE,
            DOCUMENTS_TABLE.c.source_file_name.label("document_title"),
            DOCUMENTS_TABLE.c.metadata.label("document_metadata"),
            USERS_TABLE.c.full_name.label("advocate_full_name"),
            ADVOCATE_PROFILES_TABLE.c.photo_url.label("advocate_photo_url"),
        )
        .select_from(join)
        .where(
            CASE_ADVOCATES_TABLE.c.advocate_user_id == advocate_user_id,
            CASE_ADVOCATES_TABLE.c.document_id == document_id,
        )
    )
    with get_engine().connect() as connection:
        row = connection.execute(statement).mappings().first()
    return _to_case_link_record(row) if row is not None else None


# ------------- mappers -----------------------------------------------------


def _to_user_record(row: RowMapping | dict[str, Any]) -> UserRecord:
    return UserRecord(
        id=row["id"],
        email=row["email"],
        role=row["role"],
        status=row["status"],
        full_name=row["full_name"],
        phone=row.get("phone") if isinstance(row, dict) else row["phone"],
        preferred_language=row["preferred_language"],
        email_verified_at=(
            row.get("email_verified_at") if isinstance(row, dict) else row["email_verified_at"]
        ),
        last_login_at=row.get("last_login_at") if isinstance(row, dict) else row["last_login_at"],
        profile_metadata=(
            dict(row.get("profile_metadata") or {})
            if isinstance(row, dict)
            else dict(row["profile_metadata"] or {})
        ),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_advocate_record(row: RowMapping) -> AdvocateProfileRecord:
    return AdvocateProfileRecord(
        user_id=row["user_id"],
        full_name=row["full_name"],
        bar_council_id=row["bar_council_id"],
        registration_number=row["registration_number"],
        photo_url=row["photo_url"],
        bio=row["bio"],
        years_of_experience=row["years_of_experience"],
        languages=list(row["languages"] or []),
        specializations=list(row["specializations"] or []),
        jurisdictions=row["jurisdictions"] or [],
        education=row["education"] or [],
        notable_cases=row["notable_cases"],
        consultation_fee_min_inr=row["consultation_fee_min_inr"],
        consultation_fee_max_inr=row["consultation_fee_max_inr"],
        availability=Availability(**(row["availability"] or {})),
        contact_preferences=ContactPreferences(**(row["contact_preferences"] or {})),
        verification_status=row["verification_status"],
        verified_at=row["verified_at"],
        verified_by_user_id=row["verified_by_user_id"],
        rejection_reason=row["rejection_reason"],
        ratings_avg=float(row["ratings_avg"] or 0),
        ratings_count=row["ratings_count"] or 0,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_case_link_record(row: RowMapping) -> AdvocateCaseLinkRecord:
    metadata = row.get("document_metadata")
    court_name = _extract_metadata_text(metadata, ("cis", "court_name"))
    order_date = _extract_metadata_text(metadata, ("cis", "order_date"))
    return AdvocateCaseLinkRecord(
        id=row["id"],
        document_id=row["document_id"],
        advocate_user_id=row["advocate_user_id"],
        role=row["role"],
        status=row["status"],
        created_at=row["created_at"],
        verified_at=row["verified_at"],
        verified_by_user_id=row["verified_by_user_id"],
        document_title=row.get("document_title"),
        court_name=court_name,
        order_date=order_date,
        advocate_full_name=row.get("advocate_full_name"),
        advocate_photo_url=row.get("advocate_photo_url"),
    )


def _extract_metadata_text(metadata: object, path: tuple[str, ...]) -> str | None:
    cursor: object = metadata if isinstance(metadata, dict) else {}
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    if isinstance(cursor, str):
        cleaned = cursor.strip()
        return cleaned or None
    return None
