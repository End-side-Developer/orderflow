import type { UserRole } from "@/lib/auth/permissions";

export type RouteKey =
  | "overview"
  | "intake"
  | "analyze"
  | "verify"
  | "escalate"
  | "departments"
  | "public"
  | "dashboard"
  | "advocates"
  | "admin";

export interface RouteDescriptor {
  key: RouteKey;
  href: string;
  label: string;
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
    description: "Workbench summary across all live cases.",
    inWorkflow: false,
    workflowIndex: null,
  },
  {
    key: "intake",
    href: "/upload",
    label: "Intake",
    description: "Upload a new judgment to start the workflow.",
    inWorkflow: true,
    workflowIndex: 1,
    requiredRoles: ["judge", "government"],
  },
  {
    key: "analyze",
    href: "/document-summary",
    label: "Analyze",
    description: "Page-level summaries, highlights, and AI extraction.",
    inWorkflow: true,
    workflowIndex: 2,
    requiredRoles: ["advocate", "judge", "government"],
  },
  {
    key: "verify",
    href: "/obligations",
    label: "Verify",
    description: "Approve, reject, and close obligations with proof.",
    inWorkflow: true,
    workflowIndex: 3,
    requiredRoles: ["advocate", "judge", "government"],
  },
  {
    key: "escalate",
    href: "/risk",
    label: "Escalate",
    description: "Triage risk-scored items and open escalations.",
    inWorkflow: true,
    workflowIndex: 4,
    requiredRoles: ["judge", "government"],
  },
  {
    key: "departments",
    href: "/departments",
    label: "Departments",
    description: "Department health, ownership, and load.",
    inWorkflow: false,
    workflowIndex: null,
    requiredRoles: ["judge", "government"],
  },
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
    description: "Advocate verification queue and user management.",
    inWorkflow: false,
    workflowIndex: null,
    requiredRoles: ["judge", "government"],
  },
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
