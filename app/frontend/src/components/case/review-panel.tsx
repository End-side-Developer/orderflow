"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Edit3,
  FileText,
  Loader2,
  RefreshCw,
  RotateCcw,
  UserRound,
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import {
  CaseActionPlanData,
  CaseActionPlanReviewDecision,
  ObligationRecord,
  getCaseActionPlan,
  regenerateCaseActionPlanItem,
  reviewCaseActionPlanItem,
} from "@/lib/api/client";

type ReviewPanelProps = {
  documentId: string;
  onNavigateToPage?: (pageNumber: number) => void;
};

type ActiveReviewForm =
  | { itemId: string; kind: "edit" }
  | { itemId: string; kind: "reject" }
  | null;

const EMPTY_ACTION_ITEMS: ObligationRecord[] = [];

export function ReviewPanel({ documentId, onNavigateToPage }: ReviewPanelProps) {
  const [actionPlan, setActionPlan] = useState<CaseActionPlanData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pendingItemId, setPendingItemId] = useState<string | null>(null);
  const [activeForm, setActiveForm] = useState<ActiveReviewForm>(null);
  const [regenerationItem, setRegenerationItem] = useState<ObligationRecord | null>(null);
  const [reviewerName, setReviewerName] = useState("");
  const [comments, setComments] = useState("");
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editOwner, setEditOwner] = useState("");
  const [rejectionReason, setRejectionReason] = useState("");
  const [regenFeedback, setRegenFeedback] = useState("");

  const loadActionPlan = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await getCaseActionPlan(documentId);
      if (response.ok) {
        setActionPlan(response.data);
      } else {
        setActionPlan(null);
        setError(response.error.message);
      }
    } catch (requestError) {
      setActionPlan(null);
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not load review items.",
      );
    } finally {
      setIsLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    let cancelled = false;

    setIsLoading(true);
    setError(null);

    void getCaseActionPlan(documentId)
      .then((response) => {
        if (cancelled) return;
        if (response.ok) {
          setActionPlan(response.data);
        } else {
          setActionPlan(null);
          setError(response.error.message);
        }
      })
      .catch((requestError) => {
        if (cancelled) return;
        setActionPlan(null);
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Could not load review items.",
        );
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [documentId]);

  const items = actionPlan?.items ?? EMPTY_ACTION_ITEMS;
  const stats = useMemo(() => buildReviewStats(items), [items]);

  function startForm(item: ObligationRecord, kind: Exclude<ActiveReviewForm, null>["kind"]) {
    setActiveForm({ itemId: item.id, kind });
    setError(null);
    setMessage(null);
    setComments("");
    setRejectionReason("");
    setRegenFeedback("");
    setEditTitle(item.title);
    setEditDescription(item.description ?? "");
    setEditOwner(item.owner_hint ?? "");
  }

  function openRegenerationModal(item: ObligationRecord) {
    setActiveForm(null);
    setRegenerationItem(item);
    setError(null);
    setMessage(null);
    setRegenFeedback("");
  }

  function closeRegenerationModal() {
    setRegenerationItem(null);
    setRegenFeedback("");
  }

  async function handleApprove(item: ObligationRecord) {
    await submitReviewDecision(item, "approve");
  }

  async function submitReviewDecision(
    item: ObligationRecord,
    decision: CaseActionPlanReviewDecision,
  ) {
    setPendingItemId(item.id);
    setError(null);
    setMessage(null);

    const trimmedReviewer = reviewerName.trim();
    const trimmedComments = comments.trim();

    try {
      const response = await reviewCaseActionPlanItem(documentId, item.id, {
        decision,
        reviewer_name: trimmedReviewer || undefined,
        comments: trimmedComments || undefined,
        ...(decision === "edit"
          ? {
              edited_fields: {
                title: editTitle.trim() || item.title,
                description: editDescription.trim() || null,
                owner_hint: editOwner.trim() || null,
              },
            }
          : {}),
        ...(decision === "reject"
          ? { rejection_reason: rejectionReason.trim() }
          : {}),
      });

      if (response.ok) {
        upsertReviewedItem(item.id, response.data.obligation);
        setMessage(`${formatMachineLabel(decision)} saved.`);
        clearForm();
      } else {
        setError(response.error.message);
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not submit review decision.",
      );
    } finally {
      setPendingItemId(null);
    }
  }

  async function submitRegeneration(item: ObligationRecord) {
    const feedback = regenFeedback.trim();
    if (!feedback) {
      setError("Regeneration feedback is required.");
      return;
    }

    setPendingItemId(item.id);
    setError(null);
    setMessage(null);

    try {
      const response = await regenerateCaseActionPlanItem(documentId, item.id, {
        feedback,
        reviewer_name: reviewerName.trim() || undefined,
      });

      if (response.ok) {
        upsertReviewedItem(item.id, response.data.obligation);
        setMessage("Item regenerated from cited page summaries.");
        closeRegenerationModal();
      } else {
        setError(response.error.message);
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not regenerate this item.",
      );
    } finally {
      setPendingItemId(null);
    }
  }

  function upsertReviewedItem(itemId: string, updatedItem: ObligationRecord | null) {
    if (!updatedItem) {
      void loadActionPlan();
      return;
    }

    setActionPlan((current) => {
      if (!current) return current;
      return {
        ...current,
        items: current.items.map((item) => (item.id === itemId ? updatedItem : item)),
      };
    });
  }

  function clearForm() {
    setActiveForm(null);
    setComments("");
    setEditTitle("");
    setEditDescription("");
    setEditOwner("");
    setRejectionReason("");
    setRegenFeedback("");
  }

  if (isLoading) {
    return (
      <div className="flex min-h-full items-center justify-center p-6">
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading review queue
        </div>
      </div>
    );
  }

  if (!actionPlan) {
    return (
      <div className="flex min-h-full flex-col gap-4 p-6">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Review queue unavailable</AlertTitle>
          <AlertDescription>
            {error ?? "The generated action plan is not ready for review."}
          </AlertDescription>
        </Alert>
        <div>
          <Button type="button" variant="outline" onClick={() => void loadActionPlan()}>
            <RefreshCw data-icon="inline-start" />
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-full flex-col gap-5 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-950">Human review</h2>
          <p className="mt-1 text-sm text-slate-600">
            Check each AI-generated item against its cited page before approval.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="warn">{stats.pending} pending</Badge>
          <Badge variant="good">{stats.approvedOrEdited} approved</Badge>
          <Badge variant={stats.rejected > 0 ? "destructive" : "muted"}>
            {stats.rejected} rejected
          </Badge>
        </div>
      </div>

      <Alert variant="warn">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>AI-generated result. Human verification required.</AlertTitle>
        <AlertDescription>
          Use the cited page button on each item to verify the source before approving.
        </AlertDescription>
      </Alert>

      {error ? (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Review action failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {message ? (
        <Alert>
          <CheckCircle2 className="h-4 w-4" />
          <AlertTitle>Review saved</AlertTitle>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      ) : null}

      <section className="rounded-md border border-slate-200 p-4">
        <div className="mb-3 flex items-center gap-2">
          <UserRound className="h-4 w-4 text-slate-500" />
          <h3 className="text-sm font-semibold text-slate-900">Reviewer</h3>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Input
            value={reviewerName}
            onChange={(event) => setReviewerName(event.target.value)}
            placeholder="Reviewer name"
          />
          <Input
            value={comments}
            onChange={(event) => setComments(event.target.value)}
            placeholder="Optional comment for the next decision"
          />
        </div>
      </section>

      {items.length === 0 ? (
        <Alert>
          <CheckCircle2 className="h-4 w-4" />
          <AlertTitle>No items need review</AlertTitle>
          <AlertDescription>
            Refresh after action-plan generation completes.
          </AlertDescription>
        </Alert>
      ) : (
        <div className="flex flex-col gap-3">
          {items.map((item, index) => (
            <ReviewItemCard
              key={item.id}
              item={item}
              index={index}
              activeForm={activeForm}
              pending={pendingItemId === item.id}
              editTitle={editTitle}
              editDescription={editDescription}
              editOwner={editOwner}
              rejectionReason={rejectionReason}
              onEditTitleChange={setEditTitle}
              onEditDescriptionChange={setEditDescription}
              onEditOwnerChange={setEditOwner}
              onRejectionReasonChange={setRejectionReason}
              onNavigateToPage={onNavigateToPage}
              onApprove={() => void handleApprove(item)}
              onStartForm={(kind) => startForm(item, kind)}
              onCancelForm={clearForm}
              onSubmitEdit={() => void submitReviewDecision(item, "edit")}
              onSubmitReject={() => void submitReviewDecision(item, "reject")}
              onOpenRegeneration={() => openRegenerationModal(item)}
            />
          ))}
        </div>
      )}

      <RegenerationFeedbackDialog
        item={regenerationItem}
        feedback={regenFeedback}
        pending={Boolean(regenerationItem && pendingItemId === regenerationItem.id)}
        onFeedbackChange={setRegenFeedback}
        onOpenChange={(open) => {
          if (!open && !pendingItemId) closeRegenerationModal();
        }}
        onSubmit={() => {
          if (regenerationItem) void submitRegeneration(regenerationItem);
        }}
      />

      <div className="mt-auto flex flex-wrap gap-3 border-t border-slate-200 pt-5">
        <Button type="button" variant="outline" onClick={() => void loadActionPlan()}>
          <RefreshCw data-icon="inline-start" />
          Refresh review queue
        </Button>
      </div>
    </div>
  );
}

function ReviewItemCard({
  item,
  index,
  activeForm,
  pending,
  editTitle,
  editDescription,
  editOwner,
  rejectionReason,
  onEditTitleChange,
  onEditDescriptionChange,
  onEditOwnerChange,
  onRejectionReasonChange,
  onNavigateToPage,
  onApprove,
  onStartForm,
  onCancelForm,
  onSubmitEdit,
  onSubmitReject,
  onOpenRegeneration,
}: {
  item: ObligationRecord;
  index: number;
  activeForm: ActiveReviewForm;
  pending: boolean;
  editTitle: string;
  editDescription: string;
  editOwner: string;
  rejectionReason: string;
  onEditTitleChange: (value: string) => void;
  onEditDescriptionChange: (value: string) => void;
  onEditOwnerChange: (value: string) => void;
  onRejectionReasonChange: (value: string) => void;
  onNavigateToPage?: (pageNumber: number) => void;
  onApprove: () => void;
  onStartForm: (kind: Exclude<ActiveReviewForm, null>["kind"]) => void;
  onCancelForm: () => void;
  onSubmitEdit: () => void;
  onSubmitReject: () => void;
  onOpenRegeneration: () => void;
}) {
  const activeKind = activeForm?.itemId === item.id ? activeForm.kind : null;
  const citedPage = item.citation?.page_number ?? null;
  const confidencePercent =
    item.confidence == null ? null : clampPercent(item.confidence * 100);
  const needsHumanReview =
    confidencePercent != null && confidencePercent < 70;

  return (
    <Card className="shadow-none">
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <CardTitle className="break-words text-sm">
              {index + 1}. {item.title}
            </CardTitle>
            <CardDescription className="mt-1 break-words">
              {item.owner_hint || "Unassigned owner"} - {formatMachineLabel(item.nature_of_action ?? "other")}
            </CardDescription>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <Badge variant={reviewVariant(item.action_plan_stage)}>
              {formatMachineLabel(item.action_plan_stage)}
            </Badge>
            <Badge variant={priorityVariant(item.priority)}>
              {formatMachineLabel(item.priority)}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">
          {item.description || "No description captured."}
        </p>

        <div className="flex flex-wrap gap-2">
          <Badge variant="secondary">Due {item.due_date || "not dated"}</Badge>
          <Badge variant="outline">Status {formatMachineLabel(item.status)}</Badge>
          {item.risk_band ? (
            <Badge variant={riskVariant(item.risk_band)}>
              Risk {formatMachineLabel(item.risk_band)}
            </Badge>
          ) : null}
          {item.regen_count > 0 ? (
            <Badge variant="accent">Regenerated {item.regen_count}</Badge>
          ) : null}
        </div>

        {confidencePercent != null ? (
          <div className="rounded-md bg-slate-50 p-3">
            <div className="mb-2 flex items-center justify-between gap-3 text-xs font-medium text-slate-600">
              <span>Extraction confidence</span>
              <span className="flex flex-wrap items-center justify-end gap-2">
                {needsHumanReview ? (
                  <Badge variant="warn">Needs human review.</Badge>
                ) : null}
                {confidencePercent}%
              </span>
            </div>
            <Progress value={confidencePercent} className="h-2" />
          </div>
        ) : null}

        <div className="rounded-md border border-slate-200 p-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-slate-500" />
              <p className="text-xs font-semibold uppercase text-slate-500">
                Cited source
              </p>
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={!citedPage || !onNavigateToPage}
              onClick={() => citedPage && onNavigateToPage?.(citedPage)}
            >
              Open page {citedPage ?? "-"}
            </Button>
          </div>
          {item.citation?.clause_span ? (
            <p className="line-clamp-4 break-words text-xs leading-5 text-slate-600">
              {item.citation.clause_span}
            </p>
          ) : (
            <p className="text-xs text-slate-500">Citation text was not captured.</p>
          )}
        </div>

        {activeKind === "edit" ? (
          <InlineForm
            title="Edit and approve"
            submitLabel="Save edit"
            pending={pending}
            onCancel={onCancelForm}
            onSubmit={onSubmitEdit}
          >
            <Input
              value={editTitle}
              onChange={(event) => onEditTitleChange(event.target.value)}
              placeholder="Action title"
            />
            <Textarea
              value={editDescription}
              onChange={(event) => onEditDescriptionChange(event.target.value)}
              placeholder="Action description"
              rows={4}
            />
            <Input
              value={editOwner}
              onChange={(event) => onEditOwnerChange(event.target.value)}
              placeholder="Responsible owner or department"
            />
          </InlineForm>
        ) : null}

        {activeKind === "reject" ? (
          <InlineForm
            title="Reject item"
            submitLabel="Reject"
            pending={pending}
            destructive
            onCancel={onCancelForm}
            onSubmit={onSubmitReject}
          >
            <Textarea
              value={rejectionReason}
              onChange={(event) => onRejectionReasonChange(event.target.value)}
              placeholder="Why should this item be rejected?"
              rows={3}
            />
          </InlineForm>
        ) : null}

        {!activeKind ? (
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant="good"
              disabled={pending}
              onClick={onApprove}
            >
              {pending ? <Loader2 className="animate-spin" /> : <Check data-icon="inline-start" />}
              Approve
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={pending}
              onClick={() => onStartForm("edit")}
            >
              <Edit3 data-icon="inline-start" />
              Edit
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={pending}
              onClick={onOpenRegeneration}
            >
              <RotateCcw data-icon="inline-start" />
              Regenerate
            </Button>
            <Button
              type="button"
              size="sm"
              variant="destructive"
              disabled={pending}
              onClick={() => onStartForm("reject")}
            >
              <X data-icon="inline-start" />
              Reject
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function RegenerationFeedbackDialog({
  item,
  feedback,
  pending,
  onFeedbackChange,
  onOpenChange,
  onSubmit,
}: {
  item: ObligationRecord | null;
  feedback: string;
  pending: boolean;
  onFeedbackChange: (value: string) => void;
  onOpenChange: (open: boolean) => void;
  onSubmit: () => void;
}) {
  if (!item) return null;

  const citedPage = item.citation?.page_number ?? null;
  const canSubmit = feedback.trim().length > 0 && !pending;

  return (
    <Dialog open={Boolean(item)} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Regenerate one action item</DialogTitle>
          <DialogDescription>
            Feedback is sent only for the selected item and its cited page summaries.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="rounded-md border border-slate-200 p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge variant="secondary">
                {item.obligation_code ?? item.id}
              </Badge>
              <Badge variant="outline">Page {citedPage ?? "-"}</Badge>
              <Badge variant="muted">
                Regenerated {item.regen_count} time{item.regen_count === 1 ? "" : "s"}
              </Badge>
            </div>
            <p className="break-words text-sm font-semibold text-slate-950">
              {item.title}
            </p>
            {item.description ? (
              <p className="mt-2 line-clamp-3 break-words text-sm leading-6 text-slate-600">
                {item.description}
              </p>
            ) : null}
          </div>

          {item.citation?.clause_span ? (
            <div className="rounded-md bg-slate-50 p-3">
              <p className="mb-1 text-xs font-semibold uppercase text-slate-500">
                Current cited source
              </p>
              <p className="line-clamp-4 break-words text-xs leading-5 text-slate-600">
                {item.citation.clause_span}
              </p>
            </div>
          ) : null}

          <Textarea
            value={feedback}
            onChange={(event) => onFeedbackChange(event.target.value)}
            placeholder="Example: make the owner more specific, preserve the cited page, and clarify the exact deadline."
            rows={5}
          />
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            type="button"
            variant="outline"
            disabled={pending}
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button type="button" disabled={!canSubmit} onClick={onSubmit}>
            {pending ? <Loader2 className="animate-spin" /> : <RotateCcw data-icon="inline-start" />}
            Regenerate item
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function InlineForm({
  title,
  submitLabel,
  pending,
  destructive = false,
  children,
  onCancel,
  onSubmit,
}: {
  title: string;
  submitLabel: string;
  pending: boolean;
  destructive?: boolean;
  children: ReactNode;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
      <p className="mb-3 text-sm font-semibold text-slate-950">{title}</p>
      <div className="flex flex-col gap-3">{children}</div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant={destructive ? "destructive" : "default"}
          disabled={pending}
          onClick={onSubmit}
        >
          {pending ? <Loader2 className="animate-spin" /> : null}
          {submitLabel}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={pending}
          onClick={onCancel}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}

function buildReviewStats(items: ObligationRecord[]) {
  return items.reduce(
    (stats, item) => {
      if (item.action_plan_stage === "approved" || item.action_plan_stage === "edited") {
        stats.approvedOrEdited += 1;
      } else if (item.action_plan_stage === "rejected") {
        stats.rejected += 1;
      } else {
        stats.pending += 1;
      }
      return stats;
    },
    { pending: 0, approvedOrEdited: 0, rejected: 0 },
  );
}

function reviewVariant(stage: ObligationRecord["action_plan_stage"]) {
  if (stage === "approved" || stage === "edited") return "good" as const;
  if (stage === "rejected") return "destructive" as const;
  if (stage === "review_pending") return "warn" as const;
  return "muted" as const;
}

function priorityVariant(priority: ObligationRecord["priority"]) {
  if (priority === "critical") return "destructive" as const;
  if (priority === "high") return "warn" as const;
  if (priority === "medium") return "secondary" as const;
  return "good" as const;
}

function riskVariant(riskBand: ObligationRecord["risk_band"]) {
  if (riskBand === "critical" || riskBand === "high") return "destructive" as const;
  if (riskBand === "moderate") return "warn" as const;
  if (riskBand === "low") return "good" as const;
  return "muted" as const;
}

function formatMachineLabel(value: string) {
  return value.replaceAll("_", " ");
}

function clampPercent(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, Math.round(value)));
}
