export type UserRole = "citizen" | "advocate" | "judge" | "government";

export type Permission =
  | "self_read"
  | "self_write"
  | "proof_submit"
  | "advocate_directory_read"
  | "public_obligations_read"
  | "advocate_self_profile_write"
  | "case_read"
  | "inquiries_read"
  | "obligation_write"
  | "document_upload"
  | "audit_read"
  | "advocate_verify"
  | "department_manage"
  | "extraction_run"
  | "user_manage";

const CITIZEN_PERMS = new Set<Permission>([
  "self_read",
  "self_write",
  "proof_submit",
  "advocate_directory_read",
  "public_obligations_read",
]);

const ADVOCATE_PERMS = new Set<Permission>([
  ...CITIZEN_PERMS,
  "advocate_self_profile_write",
  "case_read",
  "inquiries_read",
]);

const JUDGE_PERMS = new Set<Permission>([
  ...ADVOCATE_PERMS,
  "obligation_write",
  "document_upload",
  "audit_read",
  "advocate_verify",
  "department_manage",
  "extraction_run",
]);

const GOVERNMENT_PERMS = new Set<Permission>([...JUDGE_PERMS, "user_manage"]);

export const ROLE_PERMISSIONS: Record<UserRole, Set<Permission>> = {
  citizen: CITIZEN_PERMS,
  advocate: ADVOCATE_PERMS,
  judge: JUDGE_PERMS,
  government: GOVERNMENT_PERMS,
};

export function hasPermission(role: UserRole, permission: Permission): boolean {
  return ROLE_PERMISSIONS[role]?.has(permission) ?? false;
}

export function hasRole(userRole: UserRole, ...allowedRoles: UserRole[]): boolean {
  return allowedRoles.includes(userRole);
}

export const ROLE_LABELS: Record<UserRole, string> = {
  citizen: "Citizen",
  advocate: "Advocate",
  judge: "Judge",
  government: "Government",
};

export const ROLE_BADGE_VARIANT: Record<
  UserRole,
  "default" | "secondary" | "destructive" | "outline"
> = {
  citizen: "secondary",
  advocate: "outline",
  judge: "default",
  government: "destructive",
};
