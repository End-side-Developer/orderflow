"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Calendar,
  CheckCircle2,
  Clock,
  Gavel,
  Landmark,
  Rocket,
  Scale,
  Search,
  Users,
  X,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AiErrorBanner } from "@/components/ai-error-banner";
import {
  getJudgmentDecisions,
  type ActionPlanItem,
  type ActionPlanSummary,
  type AppealAnalysis,
  type ApiFailure,
  type ComplianceDecision,
  type CriticalAction,
  type JudgmentDecisionData,
  type ResponsibleAuthority,
} from "@/lib/api/client";
import { cn } from "@/lib/utils";

interface JudgmentDecisionPanelProps {
  documentId: string;
  fullText: string;
  pageCount: number;
}

type RecKey = "comply" | "appeal" | "partial_comply" | "legal_review_required";

const REC_CONFIG: Record<
  string,
  { tone: "good" | "warn" | "destructive" | "accent"; label: string; icon: React.ReactNode }
> = {
  comply: { tone: "good", label: "Comply with order", icon: <CheckCircle2 /> },
  appeal: { tone: "warn", label: "File appeal", icon: <Scale /> },
  partial_comply: { tone: "warn", label: "Partial compliance", icon: <AlertTriangle /> },
  legal_review_required: { tone: "accent", label: "Legal review required", icon: <Search /> },
};

const ACTION_DEDUPE_STOPWORDS = new Set([
  "the",
  "and",
  "for",
  "with",
  "from",
  "into",
  "shall",
  "must",
  "will",
  "within",
  "action",
  "order",
  "court",
  "report",
]);

type UnifiedActionItem = {
  key: string;
  actionId: string | null;
  title: string;
  description: string | null;
  natureOfAction: string | null;
  riskLevel: string | null;
  priority: CriticalAction["priority"] | null;
  owner: string | null;
  officer: string | null;
  deadline: string | null;
  timelineType: string | null;
  complianceRequirement: string | null;
  appealConsideration: string | null;
  verificationMethod: string | null;
  riskIfDelayed: string | null;
  sourcePage: number | null;
  sourceQuote: string | null;
  fromCriticalAction: boolean;
};

export function JudgmentDecisionPanel({
  documentId,
  fullText,
  pageCount,
}: JudgmentDecisionPanelProps) {
  const [data, setData] = useState<JudgmentDecisionData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiFailure | null>(null);
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    if (!fullText?.trim() || !documentId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      const result = await getJudgmentDecisions({
        document_id: documentId,
        full_text: fullText,
        page_count: pageCount,
      });
      if (cancelled) return;
      if (result.ok) setData(result.data);
      else setError(result);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [documentId, fullText, pageCount]);

  const unifiedActions = useMemo(
    () => (data ? buildUnifiedActionItems(data.action_plan, data.critical_actions) : []),
    [data],
  );

  if (!expanded) {
    return (
      <Button variant="outline" className="w-full" onClick={() => setExpanded(true)}>
        <Gavel />
        Show decision intelligence
      </Button>
    );
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="text-lg">Judgment decision intelligence</CardTitle>
          <CardDescription>
            AI answers to the four questions officials ask after a High Court judgment.
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          {data && data.extraction_mode !== "mock_fallback" ? (
            <Badge variant="muted">
              {data.extraction_mode === "ai"
                ? `Gemini ${data.ai_model ?? ""}`.trim()
                : data.extraction_mode}
            </Badge>
          ) : null}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setExpanded(false)}
            aria-label="Hide decision intelligence"
          >
            <X />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {loading ? (
          <div className="grid gap-3 md:grid-cols-2">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-40" />
            ))}
          </div>
        ) : null}

        {error ? <AiErrorBanner error={error} /> : null}

        {data && !loading ? (
          <>
            <div className="grid gap-3 lg:grid-cols-3">
              <ComplianceCard decision={data.compliance_decision} />
              <AppealCard analysis={data.appeal_analysis} />
              <AuthoritiesCard authorities={data.responsible_authorities} />
            </div>
            <UnifiedActionPlanCard actions={unifiedActions} plan={data.action_plan} />
            {data.case_summary &&
            (data.case_summary.case_type ||
              data.case_summary.parties ||
              data.case_summary.court ||
              data.case_summary.order_date ||
              data.case_summary.disposition) ? (
              <Card className="bg-muted/30">
                <CardContent className="flex flex-wrap gap-x-4 gap-y-2 p-4 text-xs text-muted-foreground">
                  {data.case_summary.case_type ? (
                    <span>
                      <strong className="text-foreground">{data.case_summary.case_type}</strong>
                    </span>
                  ) : null}
                  {data.case_summary.court ? <span>{data.case_summary.court}</span> : null}
                  {data.case_summary.parties ? <span>{data.case_summary.parties}</span> : null}
                  {data.case_summary.order_date ? (
                    <span>{data.case_summary.order_date}</span>
                  ) : null}
                  {data.case_summary.disposition ? (
                    <span>{data.case_summary.disposition}</span>
                  ) : null}
                </CardContent>
              </Card>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

function HeroCard({
  eyebrow,
  title,
  tone,
  icon,
  children,
}: {
  eyebrow: string;
  title: string;
  tone: "good" | "warn" | "destructive" | "accent" | "muted";
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  const toneClasses: Record<typeof tone, string> = {
    good: "border-good/30 bg-good/5",
    warn: "border-warn/30 bg-warn/5",
    destructive: "border-destructive/30 bg-destructive/5",
    accent: "border-accent/30 bg-accent/5",
    muted: "border-border bg-muted/20",
  };
  const toneText: Record<typeof tone, string> = {
    good: "text-good",
    warn: "text-warn",
    destructive: "text-destructive",
    accent: "text-accent",
    muted: "text-foreground",
  };
  return (
    <Card className={cn(toneClasses[tone])}>
      <CardContent className="flex flex-col gap-3 p-4">
        <div className="flex items-start gap-3">
          <span className={cn("mt-0.5", toneText[tone])}>{icon}</span>
          <div className="flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              {eyebrow}
            </p>
            <p className={cn("text-base font-semibold", toneText[tone])}>{title}</p>
          </div>
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

function ComplianceCard({ decision }: { decision: ComplianceDecision }) {
  const cfg = REC_CONFIG[decision.recommendation as RecKey] ?? REC_CONFIG.legal_review_required;
  return (
    <HeroCard eyebrow="Q1: Comply or appeal?" title={cfg.label} tone={cfg.tone} icon={cfg.icon}>
      <p className="text-sm text-muted-foreground">{decision.rationale}</p>
      {decision.directives.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Key directives
          </span>
          {decision.directives.slice(0, 3).map((d, i) => (
            <div
              key={i}
              className="flex items-start gap-2 rounded-md border border-border bg-muted/30 px-2.5 py-1.5 text-xs"
            >
              <span className="text-foreground/90">{d.text}</span>
              {d.urgency !== "standard" ? (
                <Badge
                  variant={d.urgency === "immediate" ? "destructive" : "warn"}
                  className="ml-auto"
                >
                  {d.urgency === "immediate" ? "URGENT" : "DEADLINE"}
                </Badge>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </HeroCard>
  );
}

function AppealCard({ analysis }: { analysis: AppealAnalysis }) {
  const tone = analysis.should_appeal ? "warn" : "good";
  return (
    <HeroCard
      eyebrow="Q2: Appeal & limitation"
      title={analysis.should_appeal ? "Appeal recommended" : "No appeal needed"}
      tone={tone}
      icon={<Clock />}
    >
      {analysis.limitation_period ? (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>Limitation period</AlertTitle>
          <AlertDescription>{analysis.limitation_period}</AlertDescription>
        </Alert>
      ) : null}
      {analysis.limitation_basis ? (
        <p className="text-xs italic text-muted-foreground">Basis: {analysis.limitation_basis}</p>
      ) : null}
      {analysis.appeal_grounds.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {analysis.appeal_grounds.map((g, i) => (
            <Badge key={i} variant="warn">
              {g}
            </Badge>
          ))}
        </div>
      ) : null}
      {analysis.risk_if_not_appealed ? (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertDescription>{analysis.risk_if_not_appealed}</AlertDescription>
        </Alert>
      ) : null}
    </HeroCard>
  );
}

function AuthoritiesCard({ authorities }: { authorities: ResponsibleAuthority[] }) {
  return (
    <HeroCard
      eyebrow="Q3: Responsible authority"
      title={`${authorities.length} ${authorities.length === 1 ? "authority" : "authorities"} identified`}
      tone="accent"
      icon={<Landmark />}
    >
      {authorities.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No specific authorities identified. Manual review required.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {authorities.map((auth, i) => (
            <div
              key={i}
              className="flex flex-col gap-1 rounded-md border border-border bg-muted/30 p-3 text-xs"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="text-sm font-semibold text-foreground">{auth.authority}</span>
                <Badge variant="accent">{auth.department}</Badge>
              </div>
              <span className="text-muted-foreground">{auth.role}</span>
              <span className="text-foreground/90">→ {auth.action_required}</span>
            </div>
          ))}
        </div>
      )}
    </HeroCard>
  );
}

function UnifiedActionPlanCard({
  actions,
  plan,
}: {
  actions: UnifiedActionItem[];
  plan: ActionPlanSummary;
}) {
  const criticalCount = actions.filter(
    (item) =>
      item.fromCriticalAction ||
      item.priority === "critical" ||
      item.riskLevel?.toLowerCase() === "critical",
  ).length;

  return (
    <Card className="border-good/20 bg-good/5">
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className="text-good">
            <Rocket />
          </span>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-good">
              Q4: Critical actions + structured plan
            </p>
            <CardTitle className="text-lg">Structured action plan</CardTitle>
            <CardDescription>
              Unique action list merged from critical findings and structured planning.
            </CardDescription>
          </div>
        </div>
        <div className="flex flex-wrap justify-end gap-4 text-sm">
          <div className="text-right">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Total
            </div>
            <div className="text-lg font-semibold text-good">{actions.length}</div>
          </div>
          <div className="text-right">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Critical
            </div>
            <div className="text-lg font-semibold text-destructive">{criticalCount}</div>
          </div>
          {plan.earliest_deadline ? (
            <div className="text-right">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Earliest
              </div>
              <div className="text-sm font-semibold text-foreground">{plan.earliest_deadline}</div>
            </div>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {actions.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No action plan extracted. Review document manually.
          </p>
        ) : (
          actions.map((item) => {
            const riskVariant: "destructive" | "warn" | "accent" | "good" =
              item.riskLevel === "critical" || item.priority === "critical"
                ? "destructive"
                : item.riskLevel === "high" || item.priority === "high"
                  ? "warn"
                  : item.riskLevel === "medium" || item.priority === "medium"
                    ? "accent"
                    : "good";
            return (
              <div
                key={item.key}
                className="grid gap-4 rounded-lg border border-border bg-card p-4 lg:grid-cols-[minmax(0,1fr)_minmax(220px,300px)]"
              >
                <div className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {item.actionId ? <Badge variant="muted">{item.actionId}</Badge> : null}
                    {item.natureOfAction ? (
                      <Badge variant="good">{item.natureOfAction}</Badge>
                    ) : null}
                    {item.fromCriticalAction ? <Badge variant="warn">Critical signal</Badge> : null}
                    <Badge variant={riskVariant} className="uppercase">
                      {item.riskLevel ?? item.priority ?? "low"} risk
                    </Badge>
                  </div>
                  <div className="text-base font-semibold text-foreground">{item.title}</div>
                  {item.description ? (
                    <p className="text-sm text-muted-foreground">{item.description}</p>
                  ) : null}
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    {item.complianceRequirement ? (
                      <span>
                        <strong className="text-foreground">Compliance:</strong>{" "}
                        {item.complianceRequirement}
                      </span>
                    ) : null}
                    {item.appealConsideration ? (
                      <span>
                        <strong className="text-foreground">Appeal:</strong>{" "}
                        {item.appealConsideration}
                      </span>
                    ) : null}
                    {item.verificationMethod ? (
                      <span>
                        <strong className="text-foreground">Verification:</strong>{" "}
                        {item.verificationMethod}
                      </span>
                    ) : null}
                    {item.sourcePage ? (
                      <span>
                        <strong className="text-foreground">Source:</strong> Page {item.sourcePage}
                      </span>
                    ) : null}
                  </div>
                  {item.sourceQuote ? (
                    <div className="rounded-md border-l-2 border-primary bg-primary/5 px-3 py-2 text-xs italic text-primary">
                      &ldquo;{item.sourceQuote}&rdquo;
                    </div>
                  ) : null}
                </div>
                <div className="flex flex-col gap-3 border-t border-border pt-3 text-sm lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0">
                  {item.deadline ? (
                    <div>
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                        Timeline{item.timelineType ? ` (${item.timelineType})` : ""}
                      </div>
                      <div className="inline-flex items-center gap-1 font-semibold text-foreground">
                        <Calendar className="h-3.5 w-3.5" />
                        {item.deadline}
                      </div>
                    </div>
                  ) : null}
                  {item.owner ? (
                    <div>
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                        Owner
                      </div>
                      <div className="inline-flex items-center gap-1 text-foreground">
                        <Users className="h-3.5 w-3.5" />
                        {item.owner}
                      </div>
                      {item.officer ? (
                        <div className="text-xs text-muted-foreground">{item.officer}</div>
                      ) : null}
                    </div>
                  ) : null}
                  {item.riskIfDelayed ? (
                    <Alert variant="destructive" className="mt-auto">
                      <AlertTriangle />
                      <AlertDescription className="text-xs">
                        <strong>Risk:</strong> {item.riskIfDelayed}
                      </AlertDescription>
                    </Alert>
                  ) : null}
                </div>
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}

function buildUnifiedActionItems(
  plan: ActionPlanSummary,
  criticalActions: CriticalAction[],
): UnifiedActionItem[] {
  const criticalPool = criticalActions.map((action, index) => ({
    action,
    index,
    matched: false,
  }));
  const seen = new Set<string>();
  const items: UnifiedActionItem[] = [];

  for (const [index, planItem] of plan.items.entries()) {
    const matchedCritical = criticalPool.find(
      (entry) => !entry.matched && isSameAction(planItem, entry.action),
    );
    if (matchedCritical) matchedCritical.matched = true;
    addUniqueAction(items, seen, mapPlanAction(planItem, index, matchedCritical?.action ?? null));
  }

  for (const entry of criticalPool) {
    if (!entry.matched) {
      addUniqueAction(items, seen, mapCriticalAction(entry.action, entry.index));
    }
  }

  return items;
}

function addUniqueAction(
  items: UnifiedActionItem[],
  seen: Set<string>,
  item: UnifiedActionItem,
): void {
  const key = getActionIdentity(item.title, item.owner, item.deadline);
  if (seen.has(key)) return;
  seen.add(key);
  items.push(item);
}

function mapPlanAction(
  item: ActionPlanItem,
  index: number,
  criticalAction: CriticalAction | null,
): UnifiedActionItem {
  return {
    key: item.action_id || `structured-${index}`,
    actionId: item.action_id || null,
    title: item.title,
    description: item.description,
    natureOfAction: item.nature_of_action,
    riskLevel: normalizeRiskLevel(item.risk_level),
    priority: criticalAction?.priority ?? null,
    owner: item.responsible_department || criticalAction?.owner || null,
    officer: item.responsible_officer,
    deadline: item.timeline || criticalAction?.deadline || null,
    timelineType: item.timeline_type,
    complianceRequirement: item.compliance_requirement,
    appealConsideration: item.appeal_consideration,
    verificationMethod: item.verification_method,
    riskIfDelayed: item.risk_if_delayed || criticalAction?.consequence_if_missed || null,
    sourcePage: item.source_page,
    sourceQuote: item.source_quote,
    fromCriticalAction: Boolean(criticalAction),
  };
}

function mapCriticalAction(action: CriticalAction, index: number): UnifiedActionItem {
  return {
    key: `critical-${index}-${getActionIdentity(action.action, action.owner, action.deadline)}`,
    actionId: null,
    title: action.action,
    description: null,
    natureOfAction: "critical",
    riskLevel: action.priority,
    priority: action.priority,
    owner: action.owner || null,
    officer: null,
    deadline: action.deadline,
    timelineType: action.deadline ? "deadline" : null,
    complianceRequirement: null,
    appealConsideration: null,
    verificationMethod: null,
    riskIfDelayed: action.consequence_if_missed,
    sourcePage: null,
    sourceQuote: null,
    fromCriticalAction: true,
  };
}

function isSameAction(planItem: ActionPlanItem, criticalAction: CriticalAction): boolean {
  const planText = `${planItem.title} ${planItem.description} ${planItem.responsible_department ?? ""} ${planItem.timeline ?? ""}`;
  const criticalText = `${criticalAction.action} ${criticalAction.owner ?? ""} ${criticalAction.deadline ?? ""}`;
  const planNormalized = normalizeActionTokens(planText).join(" ");
  const criticalNormalized = normalizeActionTokens(criticalText).join(" ");
  const titleNormalized = normalizeActionTokens(planItem.title).join(" ");
  const criticalActionNormalized = normalizeActionTokens(criticalAction.action).join(" ");

  if (!planNormalized || !criticalNormalized || !criticalActionNormalized) return false;
  if (planNormalized.includes(criticalActionNormalized)) return true;
  if (criticalNormalized.includes(titleNormalized) && titleNormalized.length > 0) return true;

  return (
    tokenOverlapScore(planItem.title, criticalAction.action) >= 0.7 ||
    tokenOverlapScore(`${planItem.title} ${planItem.description}`, criticalAction.action) >= 0.75
  );
}

function getActionIdentity(
  title: string,
  owner: string | null | undefined,
  deadline: string | null | undefined,
): string {
  return normalizeActionTokens(`${title} ${owner ?? ""} ${deadline ?? ""}`).join("|");
}

function normalizeActionTokens(value: string | null | undefined): string[] {
  if (!value) return [];
  return value
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((token) => token.length >= 3 && !ACTION_DEDUPE_STOPWORDS.has(token));
}

function tokenOverlapScore(left: string, right: string): number {
  const leftTokens = new Set(normalizeActionTokens(left));
  const rightTokens = new Set(normalizeActionTokens(right));
  if (leftTokens.size === 0 || rightTokens.size === 0) return 0;
  let overlap = 0;
  for (const token of leftTokens) {
    if (rightTokens.has(token)) overlap += 1;
  }
  return overlap / Math.min(leftTokens.size, rightTokens.size);
}

function normalizeRiskLevel(value: string | null | undefined): string | null {
  if (!value) return null;
  const normalized = value.toLowerCase().trim();
  if (normalized.includes("critical")) return "critical";
  if (normalized.includes("high")) return "high";
  if (normalized.includes("medium")) return "medium";
  if (normalized.includes("low")) return "low";
  return normalized;
}


