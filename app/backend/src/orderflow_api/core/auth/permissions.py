from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    CITIZEN = "citizen"
    ADVOCATE = "advocate"
    JUDGE = "judge"
    GOVERNMENT = "government"


class Permission(StrEnum):
    SELF_READ = "self_read"
    SELF_WRITE = "self_write"
    PROOF_SUBMIT = "proof_submit"
    ADVOCATE_DIRECTORY_READ = "advocate_directory_read"
    PUBLIC_OBLIGATIONS_READ = "public_obligations_read"

    ADVOCATE_SELF_PROFILE_WRITE = "advocate_self_profile_write"
    CASE_READ = "case_read"
    INQUIRIES_READ = "inquiries_read"

    OBLIGATION_WRITE = "obligation_write"
    DOCUMENT_UPLOAD = "document_upload"
    AUDIT_READ = "audit_read"
    ADVOCATE_VERIFY = "advocate_verify"
    DEPARTMENT_MANAGE = "department_manage"
    EXTRACTION_RUN = "extraction_run"

    USER_MANAGE = "user_manage"


_CITIZEN_PERMS: frozenset[Permission] = frozenset(
    {
        Permission.SELF_READ,
        Permission.SELF_WRITE,
        Permission.PROOF_SUBMIT,
        Permission.ADVOCATE_DIRECTORY_READ,
        Permission.PUBLIC_OBLIGATIONS_READ,
    }
)

_ADVOCATE_PERMS: frozenset[Permission] = _CITIZEN_PERMS | frozenset(
    {
        Permission.ADVOCATE_SELF_PROFILE_WRITE,
        Permission.CASE_READ,
        Permission.INQUIRIES_READ,
    }
)

_JUDGE_PERMS: frozenset[Permission] = _ADVOCATE_PERMS | frozenset(
    {
        Permission.OBLIGATION_WRITE,
        Permission.DOCUMENT_UPLOAD,
        Permission.AUDIT_READ,
        Permission.ADVOCATE_VERIFY,
        Permission.DEPARTMENT_MANAGE,
        Permission.EXTRACTION_RUN,
    }
)

_GOVERNMENT_PERMS: frozenset[Permission] = _JUDGE_PERMS | frozenset({Permission.USER_MANAGE})


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.CITIZEN: _CITIZEN_PERMS,
    Role.ADVOCATE: _ADVOCATE_PERMS,
    Role.JUDGE: _JUDGE_PERMS,
    Role.GOVERNMENT: _GOVERNMENT_PERMS,
}


# Roles that bypass per-document owner_user_id checks (can see every case).
# Hackathon evaluators log in as a dedicated government-role account, so
# `government` is the only privileged role here.
PRIVILEGED_ROLES: frozenset[Role] = frozenset({Role.GOVERNMENT})


def is_privileged(role: Role | str) -> bool:
    if isinstance(role, str):
        try:
            role = Role(role)
        except ValueError:
            return False
    return role in PRIVILEGED_ROLES


def role_permissions(role: Role | str) -> frozenset[Permission]:
    if isinstance(role, str):
        try:
            role = Role(role)
        except ValueError:
            return frozenset()
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: Role | str, permission: Permission) -> bool:
    return permission in role_permissions(role)
