"""Unit tests for the core permission/role matrix."""

from __future__ import annotations

from orderflow_api.core.auth.permissions import (
    Permission,
    Role,
    has_permission,
    role_permissions,
)


# ──── Citizen ────────────────────────────────────────────────────────────────


def test_citizen_has_self_read() -> None:
    assert has_permission(Role.CITIZEN, Permission.SELF_READ)


def test_citizen_has_self_write() -> None:
    assert has_permission(Role.CITIZEN, Permission.SELF_WRITE)


def test_citizen_has_proof_submit() -> None:
    assert has_permission(Role.CITIZEN, Permission.PROOF_SUBMIT)


def test_citizen_has_advocate_directory_read() -> None:
    assert has_permission(Role.CITIZEN, Permission.ADVOCATE_DIRECTORY_READ)


def test_citizen_has_public_obligations_read() -> None:
    assert has_permission(Role.CITIZEN, Permission.PUBLIC_OBLIGATIONS_READ)


def test_citizen_cannot_read_cases() -> None:
    assert not has_permission(Role.CITIZEN, Permission.CASE_READ)


def test_citizen_cannot_upload_documents() -> None:
    assert not has_permission(Role.CITIZEN, Permission.DOCUMENT_UPLOAD)


def test_citizen_cannot_write_obligations() -> None:
    assert not has_permission(Role.CITIZEN, Permission.OBLIGATION_WRITE)


def test_citizen_cannot_run_extraction() -> None:
    assert not has_permission(Role.CITIZEN, Permission.EXTRACTION_RUN)


def test_citizen_cannot_manage_users() -> None:
    assert not has_permission(Role.CITIZEN, Permission.USER_MANAGE)


def test_citizen_cannot_verify_advocates() -> None:
    assert not has_permission(Role.CITIZEN, Permission.ADVOCATE_VERIFY)


# ──── Advocate ───────────────────────────────────────────────────────────────


def test_advocate_has_case_read() -> None:
    assert has_permission(Role.ADVOCATE, Permission.CASE_READ)


def test_advocate_has_inquiries_read() -> None:
    assert has_permission(Role.ADVOCATE, Permission.INQUIRIES_READ)


def test_advocate_has_self_profile_write() -> None:
    assert has_permission(Role.ADVOCATE, Permission.ADVOCATE_SELF_PROFILE_WRITE)


def test_advocate_inherits_all_citizen_permissions() -> None:
    citizen_perms = role_permissions(Role.CITIZEN)
    advocate_perms = role_permissions(Role.ADVOCATE)
    assert citizen_perms.issubset(advocate_perms)


def test_advocate_cannot_upload_documents() -> None:
    assert not has_permission(Role.ADVOCATE, Permission.DOCUMENT_UPLOAD)


def test_advocate_cannot_write_obligations() -> None:
    assert not has_permission(Role.ADVOCATE, Permission.OBLIGATION_WRITE)


def test_advocate_cannot_run_extraction() -> None:
    assert not has_permission(Role.ADVOCATE, Permission.EXTRACTION_RUN)


def test_advocate_cannot_verify_advocates() -> None:
    assert not has_permission(Role.ADVOCATE, Permission.ADVOCATE_VERIFY)


def test_advocate_cannot_manage_users() -> None:
    assert not has_permission(Role.ADVOCATE, Permission.USER_MANAGE)


# ──── Judge ──────────────────────────────────────────────────────────────────


def test_judge_has_obligation_write() -> None:
    assert has_permission(Role.JUDGE, Permission.OBLIGATION_WRITE)


def test_judge_has_document_upload() -> None:
    assert has_permission(Role.JUDGE, Permission.DOCUMENT_UPLOAD)


def test_judge_has_extraction_run() -> None:
    assert has_permission(Role.JUDGE, Permission.EXTRACTION_RUN)


def test_judge_has_audit_read() -> None:
    assert has_permission(Role.JUDGE, Permission.AUDIT_READ)


def test_judge_has_department_manage() -> None:
    assert has_permission(Role.JUDGE, Permission.DEPARTMENT_MANAGE)


def test_judge_can_verify_advocates() -> None:
    assert has_permission(Role.JUDGE, Permission.ADVOCATE_VERIFY)


def test_judge_inherits_all_advocate_permissions() -> None:
    advocate_perms = role_permissions(Role.ADVOCATE)
    judge_perms = role_permissions(Role.JUDGE)
    assert advocate_perms.issubset(judge_perms)


def test_judge_cannot_manage_users() -> None:
    assert not has_permission(Role.JUDGE, Permission.USER_MANAGE)


# ──── Government ─────────────────────────────────────────────────────────────


def test_government_has_user_manage() -> None:
    assert has_permission(Role.GOVERNMENT, Permission.USER_MANAGE)


def test_government_inherits_all_judge_permissions() -> None:
    judge_perms = role_permissions(Role.JUDGE)
    gov_perms = role_permissions(Role.GOVERNMENT)
    assert judge_perms.issubset(gov_perms)


def test_government_has_all_permissions() -> None:
    gov_perms = role_permissions(Role.GOVERNMENT)
    for perm in Permission:
        assert perm in gov_perms, f"Government should have {perm}"


# ──── Hierarchy monotonicity ──────────────────────────────────────────────────


def test_permission_count_increases_with_privilege_level() -> None:
    sizes = [
        len(role_permissions(Role.CITIZEN)),
        len(role_permissions(Role.ADVOCATE)),
        len(role_permissions(Role.JUDGE)),
        len(role_permissions(Role.GOVERNMENT)),
    ]
    for a, b in zip(sizes, sizes[1:]):
        assert a < b, "Each higher role must have strictly more permissions"


def test_has_permission_accepts_string_role() -> None:
    assert has_permission("judge", Permission.OBLIGATION_WRITE)
    assert not has_permission("citizen", Permission.OBLIGATION_WRITE)


def test_unknown_role_returns_false() -> None:
    assert not has_permission("superadmin", Permission.SELF_READ)
