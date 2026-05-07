import type { UserRole } from "@/lib/auth/permissions";

export type RouteKey =
  | "overview"
  | "intake"
  | "analyze"
  | "verify"
  | "departments"
  | "public"
  | "dashboard"
  | "advocates"
  | "admin";

export interface RouteDescriptor {
  key: RouteKey;
  href: string;
  label: string;
  simpleLabel?: string;
  helpText?: string;
  description: string;
  inWorkflow: boolean;
  workflowIndex: number | null;
  /** Roles that can see this nav item. Undefined = visible to all (including anon/demo). */
  requiredRoles?: UserRole[];
}

export const ROUTES: RouteDescriptor[] = [
  {
    key: "overview",
    href: "/",
    label: "Overview",
    simpleLabel: "Case overview",
    helpText: "Summary of all your active cases in one place.",
    description: "Workbench summary across all live cases.",
    inWorkflow: false,
    workflowIndex: null,
  },
  {
    key: "intake",
    href: "/upload",
    label: "Intake",
    simpleLabel: "Add new case",
    helpText: "Upload a new judgment to start the workflow.",
    description: "Upload a new judgment to start the workflow.",
    inWorkflow: false,
    workflowIndex: null,
    requiredRoles: ["judge", "government"],
  },
  {
    key: "departments",
    href: "/departments",
    label: "Departments",
    simpleLabel: "Department Health",
    helpText: "Performance and load across government departments.",
    description: "Department health, ownership, and load.",
    inWorkflow: false,
    workflowIndex: null,
    requiredRoles: ["judge", "government"],
  },
  /* hide for not fully implemented
  {
    key: "advocates",
    href: "/advocates",
    label: "Advocates",
    description: "Public directory of verified advocates and advisers.",
    inWorkflow: false,
    workflowIndex: null,
  },
  {
    key: "public",
    href: "/public",
    label: "Public",
    description: "Citizen-facing surface for transparency.",
    inWorkflow: false,
    workflowIndex: null,
  },
  {
    key: "dashboard",
    href: "/dashboard",
    label: "Dashboard",
    description: "Role-aware personal dashboard.",
    inWorkflow: false,
    workflowIndex: null,
    requiredRoles: ["citizen", "advocate", "judge", "government"],
  },
  {
    key: "admin",
    href: "/admin/verifications",
    label: "Admin",
    simpleLabel: "Advocate approvals",
    helpText: "Review and approve advocate registration requests.",
    description: "Advocate verification queue and user management.",
    inWorkflow: false,
    workflowIndex: null,
    requiredRoles: ["judge", "government"],
  },
  */
];

export const ROUTE_BY_KEY: Record<RouteKey, RouteDescriptor> = ROUTES.reduce(
  (acc, route) => {
    acc[route.key] = route;
    return acc;
  },
  {} as Record<RouteKey, RouteDescriptor>,
);

export const WORKFLOW_STAGES: RouteDescriptor[] = ROUTES.filter((route) => route.inWorkflow);

/** Returns routes visible for the given role (or all non-restricted routes when role is null/demo). */
export function visibleRoutes(role: UserRole | null): RouteDescriptor[] {
  return ROUTES.filter((r) => !r.requiredRoles || (role && r.requiredRoles.includes(role)));
}
