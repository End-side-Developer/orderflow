"""T11 auth & users (RBAC foundation)

Adds the four auth tables that power role-based login:

  - users                     core auth + role
  - refresh_tokens            rotation/revocation chain
  - user_credentials_audit    append-only login/logout/refresh history
  - advocate_profiles         deep profile fields for the Advocate Directory

Roles supported: citizen, advocate, judge, government.

Revision ID: 20260502_01
Revises: 20260430_01
Create Date: 2026-05-02 00:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260502_01"
down_revision = "20260430_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # citext gives us case-insensitive email uniqueness without LOWER() everywhere.
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column(
            "preferred_language",
            sa.String(length=8),
            nullable=False,
            server_default=sa.text("'en'"),
        ),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "profile_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "role IN ('citizen', 'advocate', 'judge', 'government')",
            name="ck_users_role",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'pending_verification', 'suspended', 'disabled')",
            name="ck_users_status",
        ),
    )
    # Switch the email column to citext after table creation — Alembic's column
    # reflection doesn't ship a citext type, so we override with raw SQL.
    op.execute("ALTER TABLE users ALTER COLUMN email TYPE citext")
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"], unique=False)
    op.create_index("ix_users_status", "users", ["status"], unique=False)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "replaced_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
    )
    op.create_index(
        "ix_refresh_tokens_user_active",
        "refresh_tokens",
        ["user_id"],
        unique=False,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_refresh_tokens_expires_at",
        "refresh_tokens",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "user_credentials_audit",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "event IN ("
            "'login_success', 'login_failed', 'token_refreshed', "
            "'logout', 'password_reset', 'password_changed', 'account_locked'"
            ")",
            name="ck_user_credentials_audit_event",
        ),
    )
    op.create_index(
        "ix_user_credentials_audit_user_created",
        "user_credentials_audit",
        ["user_id", "created_at"],
        unique=False,
    )

    # Advocate profile — typed columns + GIN indexes power the Directory.
    op.create_table(
        "advocate_profiles",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("bar_council_id", sa.String(length=64), nullable=False),
        sa.Column("registration_number", sa.String(length=64), nullable=True),
        sa.Column("photo_url", sa.Text(), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("years_of_experience", sa.SmallInteger(), nullable=True),
        sa.Column(
            "languages",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column(
            "specializations",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column(
            "jurisdictions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "education",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "notable_cases",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("consultation_fee_min_inr", sa.Integer(), nullable=True),
        sa.Column("consultation_fee_max_inr", sa.Integer(), nullable=True),
        sa.Column(
            "availability",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "contact_preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "verification_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "ratings_avg",
            sa.Numeric(3, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "ratings_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("bar_council_id", name="uq_advocate_bar_council_id"),
        sa.CheckConstraint(
            "verification_status IN ('pending', 'verified', 'rejected')",
            name="ck_advocate_verification_status",
        ),
        sa.CheckConstraint(
            "consultation_fee_min_inr IS NULL OR consultation_fee_min_inr >= 0",
            name="ck_advocate_fee_min_nonneg",
        ),
        sa.CheckConstraint(
            "consultation_fee_max_inr IS NULL OR "
            "consultation_fee_min_inr IS NULL OR "
            "consultation_fee_max_inr >= consultation_fee_min_inr",
            name="ck_advocate_fee_range",
        ),
    )

    # Generated tsvector — full-text on bio. Name comes from users.full_name
    # via a separate query/join so we don't denormalise here. For pure-bio
    # search the generated column is fine; richer searches use SQL `to_tsvector`
    # at query time.
    op.execute(
        """
        ALTER TABLE advocate_profiles
        ADD COLUMN search_tsv tsvector
        GENERATED ALWAYS AS (
            to_tsvector('simple', coalesce(bio, ''))
        ) STORED
        """
    )

    op.create_index(
        "ix_advocate_specializations",
        "advocate_profiles",
        ["specializations"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_advocate_languages",
        "advocate_profiles",
        ["languages"],
        unique=False,
        postgresql_using="gin",
    )
    op.execute(
        """
        CREATE INDEX ix_advocate_jurisdictions
        ON advocate_profiles
        USING gin (jurisdictions jsonb_path_ops)
        """
    )
    op.create_index(
        "ix_advocate_search_tsv",
        "advocate_profiles",
        ["search_tsv"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_advocate_verification_status",
        "advocate_profiles",
        ["verification_status"],
        unique=False,
    )
    # Hot-path partial index — directory queries always include this filter.
    op.create_index(
        "ix_advocate_directory_visible",
        "advocate_profiles",
        ["ratings_avg"],
        unique=False,
        postgresql_where=sa.text("verification_status = 'verified'"),
    )


def downgrade() -> None:
    op.drop_index("ix_advocate_directory_visible", table_name="advocate_profiles")
    op.drop_index("ix_advocate_verification_status", table_name="advocate_profiles")
    op.drop_index("ix_advocate_search_tsv", table_name="advocate_profiles")
    op.execute("DROP INDEX IF EXISTS ix_advocate_jurisdictions")
    op.drop_index("ix_advocate_languages", table_name="advocate_profiles")
    op.drop_index("ix_advocate_specializations", table_name="advocate_profiles")
    op.drop_table("advocate_profiles")

    op.drop_index(
        "ix_user_credentials_audit_user_created",
        table_name="user_credentials_audit",
    )
    op.drop_table("user_credentials_audit")

    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_active", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    # Intentionally do not drop citext — other tables/extensions may depend on it.
