"use client";

import { useEffect, useState } from "react";
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
  Target,
  Users,
  X,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AiErrorBanner } from "@/components/ai-error-banner";
import {
  getJudgmentDecisions,
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

const PRIORITY_VARIANT: Record<string, "destructive" | "warn" | "accent" | "muted"> = {
  critical: "destructive",
  high: "warn",
  medium: "accent",
  low: "muted",
};

export function JudgmentDecisionPanel({ documentId, fullText, pageCount }: JudgmentDecisionPanelProps) {
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
              {data.extraction_mode === "ai" ? `Gemini ${data.ai_model ?? ""}`.trim() : data.extraction_mode}
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
            <div className="grid gap-3 md:grid-cols-2">
              <ComplianceCard decision={data.compliance_decision} />
              <AppealCard analysis={data.appeal_analysis} />
              <AuthoritiesCard authorities={data.responsible_authorities} />
              <ActionsCard actions={data.critical_actions} />
            </div>
            {data.action_plan && data.action_plan.items.length > 0 ? (
              <ActionPlanCard plan={data.action_plan} />
            ) : null}
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
                  {data.case_summary.order_date ? <span>{data.case_summary.order_date}</span> : null}
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
                <Badge variant={d.urgency === "immediate" ? "destructive" : "warn"} className="ml-auto">
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

function ActionsCard({ actions }: { actions: CriticalAction[] }) {
  return (
    <HeroCard
      eyebrow="Q4: Critical actions"
      title={`${actions.length} action${actions.length !== 1 ? "s" : ""} required`}
      tone="warn"
      icon={<Target />}
    >
      {actions.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No critical actions extracted. Review document manually.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {actions.map((act, i) => {
            const variant = PRIORITY_VARIANT[act.priority] ?? "muted";
            return (
              <div
                key={i}
                className="flex flex-col gap-1.5 rounded-md border border-border bg-muted/30 p-2.5 text-xs"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="text-sm font-semibold text-foreground">{act.action}</span>
                  <Badge variant={variant} className="uppercase">
                    {act.priority}
                  </Badge>
                </div>
                <div className="flex flex-wrap gap-x-3 gap-y-1 text-muted-foreground">
                  {act.owner ? (
                    <span className="inline-flex items-center gap-1">
                      <Users className="h-3 w-3" /> {act.owner}
                    </span>
                  ) : null}
                  {act.deadline ? (
                    <span className="inline-flex items-center gap-1">
                      <Calendar className="h-3 w-3" /> {act.deadline}
                    </span>
                  ) : null}
                </div>
                {act.consequence_if_missed ? (
                  <span className="text-destructive">{act.consequence_if_missed}</span>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </HeroCard>
  );
}

function ActionPlanCard({ plan }: { plan: ActionPlanSummary }) {
  return (
    <Card className="border-good/20 bg-good/5">
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className="text-good">
            <Rocket />
          </span>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-good">
              Key differentiator
            </p>
            <CardTitle className="text-lg">Structured action plan</CardTitle>
          </div>
        </div>
        <div className="flex gap-4 text-sm">
          <div className="text-right">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Total
            </div>
            <div className="text-lg font-semibold text-good">{plan.total_actions}</div>
          </div>
          <div className="text-right">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Critical
            </div>
            <div className="text-lg font-semibold text-destructive">{plan.critical_count}</div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {plan.items.map((item, i) => {
          const riskVariant: "destructive" | "warn" | "accent" | "good" =
            item.risk_level === "critical"
              ? "destructive"
              : item.risk_level === "high"
                ? "warn"
                : item.risk_level === "medium"
                  ? "accent"
                  : "good";
          return (
            <div
              key={i}
              className="grid gap-4 rounded-lg border border-border bg-card p-4 lg:grid-cols-[minmax(0,1fr)_minmax(220px,300px)]"
            >
              <div className="flex flex-col gap-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant="muted">{item.action_id}</Badge>
                  <Badge variant="good">{item.nature_of_action}</Badge>
                  <Badge variant={riskVariant} className="uppercase">
                    {item.risk_level} risk
                  </Badge>
                </div>
                <div className="text-base font-semibold text-foreground">{item.title}</div>
                <p className="text-sm text-muted-foreground">{item.description}</p>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  {item.compliance_requirement ? (
                    <span>
                      <strong className="text-foreground">Compliance:</strong>{" "}
                      {item.compliance_requirement}
                    </span>
                  ) : null}
                  {item.appeal_consideration ? (
                    <span>
                      <strong className="text-foreground">Appeal:</strong> {item.appeal_consideration}
                    </span>
                  ) : null}
                  {item.verification_method ? (
                    <span>
                      <strong className="text-foreground">Verification:</strong>{" "}
                      {item.verification_method}
                    </span>
                  ) : null}
                </div>
              </div>
              <div className="flex flex-col gap-3 border-t border-border pt-3 text-sm lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0">
                {item.timeline ? (
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      Timeline ({item.timeline_type})
                    </div>
                    <div className="font-semibold text-foreground">{item.timeline}</div>
                  </div>
                ) : null}
                {item.responsible_department ? (
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      Owner
                    </div>
                    <div className="text-foreground">{item.responsible_department}</div>
                    {item.responsible_officer ? (
                      <div className="text-xs text-muted-foreground">
                        {item.responsible_officer}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {item.risk_if_delayed ? (
                  <Alert variant="destructive" className="mt-auto">
                    <AlertTriangle />
                    <AlertDescription className="text-xs">
                      <strong>Risk:</strong> {item.risk_if_delayed}
                    </AlertDescription>
                  </Alert>
                ) : null}
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
