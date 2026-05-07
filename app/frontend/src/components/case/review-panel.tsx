"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
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
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
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
  CitationVisualRef,
  finalizeCase,
  ObligationRecord,
  getCaseActionPlan,
  regenerateCaseActionPlanItem,
  reviewCaseActionPlanItem,
} from "@/lib/api/client";

type ReviewPanelProps = {
  documentId: string;
  onNavigateToPage?: (pageNumber: number, visualRefs?: CitationVisualRef[]) => void;
  onProceedToDashboard?: () => void;
};

type ActiveReviewForm =
  | { itemId: string; kind: "edit" }
  | { itemId: string; kind: "reject" }
  | null;

const EMPTY_ACTION_ITEMS: ObligationRecord[] = [];

export function ReviewPanel({
  documentId,
  onNavigateToPage,
  onProceedToDashboard,
}: ReviewPanelProps) {
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
  const [isFinalizing, setIsFinalizing] = useState(false);

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
        requestError instanceof Error ? requestError.message : "Could not load review items.",
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
          requestError instanceof Error ? requestError.message : "Could not load review items.",
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
  const canProceedToDashboard =
    Boolean(onProceedToDashboard) && stats.pending === 0 && stats.approvedOrEdited > 0;

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
        ...(decision === "reject" ? { rejection_reason: rejectionReason.trim() } : {}),
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
        requestError instanceof Error ? requestError.message : "Could not submit review decision.",
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
        requestError instanceof Error ? requestError.message : "Could not regenerate this item.",
      );
    } finally {
      setPendingItemId(null);
    }
  }

  async function handleFinalizeAndProceed() {
    if (!canProceedToDashboard || isFinalizing) return;

    setIsFinalizing(true);
    setError(null);

    try {
      const response = await finalizeCase(documentId, {
        reviewer_name: reviewerName.trim() || undefined,
        comments: comments.trim() || undefined,
      });

      if (response.ok) {
        setMessage("Case finalized.");
        onProceedToDashboard?.();
      } else {
        setError(response.error.message);
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Could not finalize the case.",
      );
    } finally {
      setIsFinalizing(false);
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
      <div className="flex min-h-[200px] items-center justify-center p-6">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading review queue
        </div>
      </div>
    );
  }

  if (!actionPlan) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Review queue unavailable</AlertTitle>
          <AlertDescription>
            {error ?? "The generated action plan is not ready for review."}
          </AlertDescription>
        </Alert>
        <div>
          <Button size="sm" type="button" variant="outline" onClick={() => void loadActionPlan()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-0">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Human review</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Verify each AI-generated item against its cited page before approving.
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

      <div className="flex flex-col gap-4 p-6">
        <Alert variant="warn">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>AI-generated result — human verification required</AlertTitle>
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

        {/* Reviewer inputs */}
        <div className="rounded-md border border-border p-4">
          <div className="mb-3 flex items-center gap-2">
            <UserRound className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold text-foreground">Reviewer</h3>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              value={reviewerName}
              onChange={(e) => setReviewerName(e.target.value)}
              placeholder="Reviewer name"
            />
            <Input
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="Optional comment for the next decision"
            />
          </div>
        </div>

        {/* Review items */}
        {items.length === 0 ? (
          <Alert>
            <CheckCircle2 className="h-4 w-4" />
            <AlertTitle>No items need review</AlertTitle>
            <AlertDescription>Refresh after action-plan generation completes.</AlertDescription>
          </Alert>
        ) : (
          <div className="flex flex-col gap-2">
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

        {/* Footer */}
        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-5">
          <Button size="sm" type="button" variant="outline" onClick={() => void loadActionPlan()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh review queue
          </Button>
          <Button
            size="sm"
            type="button"
            variant={canProceedToDashboard ? "good" : "outline"}
            className="ml-auto"
            onClick={() => void handleFinalizeAndProceed()}
            disabled={!canProceedToDashboard || isFinalizing}
          >
            {isFinalizing ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <ArrowRight className="mr-2 h-4 w-4" />
            )}
            {isFinalizing ? "Finalizing..." : "Finalize case and open dashboard"}
          </Button>
        </div>
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
  onNavigateToPage?: (pageNumber: number, visualRefs?: CitationVisualRef[]) => void;
  onApprove: () => void;
  onStartForm: (kind: Exclude<ActiveReviewForm, null>["kind"]) => void;
  onCancelForm: () => void;
  onSubmitEdit: () => void;
  onSubmitReject: () => void;
  onOpenRegeneration: () => void;
}) {
  const [localOpen, setLocalOpen] = useState(false);
  const activeKind = activeForm?.itemId === item.id ? activeForm.kind : null;
  const isOpen = localOpen || activeKind !== null;
  const citedPage = item.citation?.page_number ?? null;
  const confidencePercent = item.confidence == null ? null : clampPercent(item.confidence * 100);
  const needsHumanReview = confidencePercent != null && confidencePercent < 70;

  const isApproved =
    item.action_plan_stage === "approved" || item.action_plan_stage === "edited";
  const isRejected = item.action_plan_stage === "rejected";

  return (
    <Collapsible
      open={isOpen}
      onOpenChange={setLocalOpen}
      className="rounded-md border border-border overflow-hidden"
    >
      {/* Header row: trigger on left, action buttons on right */}
      <div className="flex items-center gap-2 px-4 py-3">
        <CollapsibleTrigger className="flex min-w-0 flex-1 items-center gap-3 text-left transition-colors hover:opacity-80">
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="text-sm font-semibold text-foreground leading-snug">
              {index + 1}. {item.title}
            </span>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={reviewVariant(item.action_plan_stage)}>
                {formatMachineLabel(item.action_plan_stage)}
              </Badge>
              <Badge variant={priorityVariant(item.priority)}>
                {formatMachineLabel(item.priority)}
              </Badge>
              {confidencePercent != null ? (
                <Badge variant={needsHumanReview ? "warn" : "muted"}>
                  {confidencePercent}% confidence
                </Badge>
              ) : null}
              {item.regen_count > 0 ? (
                <Badge variant="accent">Regen ×{item.regen_count}</Badge>
              ) : null}
            </div>
          </div>
          <ChevronDown
            className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
          />
        </CollapsibleTrigger>

        {/* Action buttons — always visible, stop propagation so they don't toggle collapsible */}
        <div
          className="flex shrink-0 flex-wrap gap-1.5 pl-2 border-l border-border"
          onClick={(e) => e.stopPropagation()}
        >
          {!isApproved && !isRejected ? (
            <>
              <Button
                type="button"
                size="sm"
                variant="good"
                disabled={pending}
                onClick={onApprove}
                className="h-7 px-2.5 text-xs"
              >
                {pending && activeKind === null ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Check className="h-3 w-3" />
                )}
                <span className="ml-1 hidden sm:inline">Approve</span>
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={pending}
                onClick={() => onStartForm("edit")}
                className="h-7 px-2.5 text-xs"
              >
                <Edit3 className="h-3 w-3" />
                <span className="ml-1 hidden sm:inline">Edit</span>
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={pending}
                onClick={onOpenRegeneration}
                className="h-7 px-2.5 text-xs"
              >
                <RotateCcw className="h-3 w-3" />
                <span className="ml-1 hidden sm:inline">Regen</span>
              </Button>
              <Button
                type="button"
                size="sm"
                variant="destructive"
                disabled={pending}
                onClick={() => onStartForm("reject")}
                className="h-7 px-2.5 text-xs"
              >
                <X className="h-3 w-3" />
                <span className="ml-1 hidden sm:inline">Reject</span>
              </Button>
            </>
          ) : (
            <Badge variant={isApproved ? "good" : "destructive"} className="py-1">
              {isApproved ? (
                <CheckCircle2 className="mr-1 h-3 w-3" />
              ) : (
                <X className="mr-1 h-3 w-3" />
              )}
              {formatMachineLabel(item.action_plan_stage)}
            </Badge>
          )}
        </div>
      </div>

      {/* Expandable content */}
      <CollapsibleContent>
        <div className="border-t border-border flex flex-col gap-4 p-4">
          <p className="whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">
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
          </div>

          {confidencePercent != null ? (
            <ConfidenceBlock
              percent={confidencePercent}
              needsReview={needsHumanReview}
              annotations={item.confidence_annotations}
            />
          ) : null}

          {/* Cited source */}
          <div className="rounded-md border border-border p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Cited source
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={!citedPage || !onNavigateToPage}
                onClick={() =>
                  citedPage && onNavigateToPage?.(citedPage, item.citation?.visual_refs)
                }
              >
                Open page {citedPage ?? "—"}
              </Button>
            </div>
            {item.citation?.clause_span ? (
              <p className="line-clamp-4 break-words text-xs leading-5 text-muted-foreground">
                {item.citation.clause_span}
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">Citation text was not captured.</p>
            )}
          </div>

          {/* Inline forms */}
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
                onChange={(e) => onEditTitleChange(e.target.value)}
                placeholder="Action title"
              />
              <Textarea
                value={editDescription}
                onChange={(e) => onEditDescriptionChange(e.target.value)}
                placeholder="Action description"
                rows={4}
              />
              <Input
                value={editOwner}
                onChange={(e) => onEditOwnerChange(e.target.value)}
                placeholder="Responsible owner or department"
              />
            </InlineForm>
          ) : null}

          {activeKind === "reject" ? (
            <InlineForm
              title="Reject item"
              submitLabel="Confirm rejection"
              pending={pending}
              destructive
              onCancel={onCancelForm}
              onSubmit={onSubmitReject}
            >
              <Textarea
                value={rejectionReason}
                onChange={(e) => onRejectionReasonChange(e.target.value)}
                placeholder="Why should this item be rejected?"
                rows={3}
              />
            </InlineForm>
          ) : null}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function ConfidenceBlock({
  percent,
  needsReview,
  annotations,
}: {
  percent: number;
  needsReview: boolean;
  annotations: ObligationRecord["confidence_annotations"];
}) {
  return (
    <div className="rounded-md bg-muted p-3">
      <div className="mb-2 flex items-center justify-between gap-3 text-xs font-medium text-muted-foreground">
        <span>Extraction confidence</span>
        <span className="flex flex-wrap items-center justify-end gap-2">
          {needsReview ? <Badge variant="warn">Needs human review</Badge> : null}
          {percent}%
        </span>
      </div>
      <Progress value={percent} className="h-2" />
      {annotations?.components && Object.keys(annotations.components).length > 0 ? (
        <div className="mt-3 space-y-1.5">
          {Object.entries(annotations.components).map(([key, val]) => (
            <div key={key} className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="w-28 shrink-0 capitalize">{key.replace(/_/g, " ")}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-border">
                <div
                  className={`h-full rounded-full ${val < 0.5 ? "bg-warn" : "bg-good"}`}
                  style={{ width: `${Math.round(val * 100)}%` }}
                />
              </div>
              <span className="w-8 text-right tabular-nums">{Math.round(val * 100)}%</span>
            </div>
          ))}
        </div>
      ) : null}
      {needsReview && annotations?.rationale?.length ? (
        <ul className="mt-2 space-y-0.5 text-xs">
          {annotations.rationale.map((r, i) => (
            <li key={i} className="flex gap-1 text-muted-foreground">
              <span className="shrink-0 text-warn">•</span>
              <span>{r}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
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
    <div className="rounded-md border border-border bg-muted/50 p-4">
      <p className="mb-3 text-sm font-semibold text-foreground">{title}</p>
      <div className="flex flex-col gap-3">{children}</div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant={destructive ? "destructive" : "default"}
          disabled={pending}
          onClick={onSubmit}
        >
          {pending ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : null}
          {submitLabel}
        </Button>
        <Button type="button" size="sm" variant="outline" disabled={pending} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
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
          <div className="rounded-md border border-border p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge variant="secondary">{item.obligation_code ?? item.id}</Badge>
              <Badge variant="outline">Page {citedPage ?? "—"}</Badge>
              <Badge variant="muted">
                Regenerated {item.regen_count} time{item.regen_count === 1 ? "" : "s"}
              </Badge>
            </div>
            <p className="break-words text-sm font-semibold text-foreground">{item.title}</p>
            {item.description ? (
              <p className="mt-2 line-clamp-3 break-words text-sm leading-6 text-muted-foreground">
                {item.description}
              </p>
            ) : null}
          </div>

          {item.citation?.clause_span ? (
            <div className="rounded-md bg-muted p-3">
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Current cited source
              </p>
              <p className="line-clamp-4 break-words text-xs leading-5 text-muted-foreground">
                {item.citation.clause_span}
              </p>
            </div>
          ) : null}

          <Textarea
            value={feedback}
            onChange={(e) => onFeedbackChange(e.target.value)}
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
            {pending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RotateCcw className="mr-2 h-4 w-4" />
            )}
            Regenerate item
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
