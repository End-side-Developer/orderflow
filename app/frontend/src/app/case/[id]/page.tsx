"use client";

import { Loader2, Trash2 } from "lucide-react";
import { use, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useIntakeProgress } from "../../../lib/hooks/useIntakeProgress";
import {
  StageStepper,
  WizardStage,
  getWizardStageFromJobStage,
} from "../../../components/case/stage-stepper";
import { PageExtractionPanel } from "../../../components/case/page-extraction-panel";
import { SummaryPanel } from "../../../components/case/summary-panel";
import { ActionPlanPanel } from "../../../components/case/action-plan-panel";
import { ReviewPanel } from "../../../components/case/review-panel";
import { DashboardPanel } from "../../../components/case/dashboard-panel";
import { PdfViewer } from "../../../components/pdf-viewer";
import { Button } from "../../../components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../../components/ui/dialog";
import {
  CitationVisualRef,
  DocumentRecord,
  deleteDocument,
  getDocument,
} from "../../../lib/api/client";

export default function CaseWizardPage({ params }: { params: Promise<{ id: string }> }) {
  const router = useRouter();
  const { id } = use(params);
  const documentId = decodeURIComponent(id);

  const [document, setDocument] = useState<DocumentRecord | null>(null);
  const [docLoading, setDocLoading] = useState(true);
  const [docError, setDocError] = useState<string | null>(null);
  const [pdfPage, setPdfPage] = useState(1);
  const [activeVisualRefs, setActiveVisualRefs] = useState<CitationVisualRef[]>([]);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [activeStage, setActiveStage] = useState<WizardStage>("extraction");
  const [refreshNonce, setRefreshNonce] = useState(0);

  const {
    data: progress,
    error: progressError,
    isLoading: progressLoading,
    isPolling,
  } = useIntakeProgress(documentId);

  const jobStage = progress?.stage;
  const currentAllowedStage = getWizardStageFromJobStage(jobStage);

  const progressSignature = useMemo(() => {
    return JSON.stringify({
      stage: progress?.stage ?? null,
      pages_completed: progress?.pages_completed ?? 0,
      pages_total: progress?.pages_total ?? 0,
      current_page: progress?.current_page ?? 0,
      percent: progress?.percent ?? 0,
      updated_at: progress?.updated_at ?? null,
    });
  }, [progress]);

  const progressRefreshKey = `${documentId}:${refreshNonce}`;

  async function handleDelete() {
    setDeleting(true);
    setDeleteError(null);

    try {
      const result = await deleteDocument(documentId);

      if (!result.ok) {
        setDeleteError(result.error.message || "Failed to delete case.");
        return;
      }

      setDeleteOpen(false);
      router.replace("/dashboard");
    } finally {
      setDeleting(false);
    }
  }

  useEffect(() => {
    setPdfPage(1);
    setActiveVisualRefs([]);
    setDocLoading(true);
    setDocError(null);

    getDocument(documentId)
      .then((res) => {
        if (res.ok) {
          setDocument(res.data);
        } else {
          setDocError(res.error.message || "Failed to load document");
        }
      })
      .catch((err) => {
        setDocError(err.message || "Failed to load document");
      })
      .finally(() => {
        setDocLoading(false);
      });
  }, [documentId]);

  useEffect(() => {
    if (jobStage) {
      setActiveStage(currentAllowedStage);
    }
  }, [currentAllowedStage, jobStage]);

  useEffect(() => {
  if (!progress?.stage) return;

  const shouldHardReload =
    progress.stage === "summary_pending" ||
    progress.stage === "action_plan_pending" ||
    progress.stage === "review_in_progress" ||
    progress.stage === "finalized";

  if (!shouldHardReload) return;

  const reloadKey = `orderflow:auto-reloaded:${documentId}:${progress.stage}`;

  if (window.sessionStorage.getItem(reloadKey) === "true") return;

  window.sessionStorage.setItem(reloadKey, "true");

  window.setTimeout(() => {
    window.location.reload();
  }, 800);
}, [documentId, progress?.stage]);

  const handleStageClick = (stage: WizardStage) => {
    setActiveStage(stage);
  };

  if (docError || progressError) {
    return (
      <div className="flex h-full flex-col bg-muted">
        <div className="flex flex-1 items-center justify-center">
          <div className="max-w-md rounded-lg bg-destructive/10 p-6 text-destructive">
            <h2 className="mb-2 text-lg font-bold">Error Loading Case</h2>
            <p>{docError || progressError?.message}</p>
            <button
              onClick={() => router.push("/dashboard")}
              className="mt-4 rounded bg-destructive px-4 py-2 text-destructive-foreground hover:opacity-90"
            >
              Back to Dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (docLoading) {
    return (
      <div className="flex h-full flex-col bg-muted">
        <div className="flex flex-1 items-center justify-center">
          <div className="animate-pulse text-muted-foreground">Loading case data...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-9rem)] w-full flex-col gap-4 overflow-hidden">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <StageStepper
            currentStage={currentAllowedStage}
            activeStage={activeStage}
            onStageClick={handleStageClick}
          />
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setDeleteError(null);
            setDeleteOpen(true);
          }}
          className="shrink-0 text-destructive hover:bg-destructive/10 hover:text-destructive"
        >
          <Trash2 className="mr-1 h-4 w-4" />
          Delete case
        </Button>
      </div>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this case?</DialogTitle>
            <DialogDescription>
              This permanently removes the document and every cached extraction
              (clauses, page summaries, obligations, audit log, action plan,
              annotations, and the stored PDF). This cannot be undone.
            </DialogDescription>
          </DialogHeader>

          {deleteError && <div className="text-sm text-destructive">{deleteError}</div>}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={deleting}
              onClick={() => setDeleteOpen(false)}
            >
              Cancel
            </Button>

            <Button
              type="button"
              variant="destructive"
              disabled={deleting}
              onClick={() => void handleDelete()}
            >
              {deleting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="mr-2 h-4 w-4" />
              )}
              Yes, delete permanently
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
        <div className="flex shrink-0 flex-col overflow-y-auto rounded-lg border border-border bg-card shadow-sm">
          {activeStage === "extraction" && (
            <PageExtractionPanel
              key={`extraction:${progressRefreshKey}`}
              documentId={documentId}
              progress={progress}
              isPolling={isPolling}
              isLoading={progressLoading}
            />
          )}

          {activeStage === "summary" && (
            <SummaryPanel
              key={`summary:${progressRefreshKey}`}
              documentId={documentId}
            />
          )}

          {activeStage === "action_plan" && (
            <ActionPlanPanel
              key={`action:${progressRefreshKey}`}
              documentId={documentId}
              onContinueToReview={() => setActiveStage("review")}
            />
          )}

          {activeStage === "review" && (
            <ReviewPanel
              key={`review:${progressRefreshKey}`}
              documentId={documentId}
              onNavigateToPage={(pageNumber, visualRefs = []) => {
                setPdfPage(pageNumber);
                setActiveVisualRefs(visualRefs);
              }}
              onProceedToDashboard={() => setActiveStage("dashboard")}
            />
          )}

          {activeStage === "dashboard" && (
            <DashboardPanel
              key={`dashboard:${progressRefreshKey}`}
              documentId={documentId}
            />
          )}
        </div>

        <div className="flex min-h-[500px] flex-1 flex-col overflow-hidden rounded-lg border border-border bg-card shadow-sm">
          {document ? (
            <PdfViewer
  key={`pdf:${documentId}`}
  documentId={documentId}
  initialPage={pdfPage}
  onPageChange={setPdfPage}
  activeVisualRefs={activeVisualRefs}
  refreshToken={progressRefreshKey}
  expectedSummaryCount={progress?.pages_completed ?? 0}
/>
          ) : (
            <div className="flex flex-1 items-center justify-center text-muted-foreground">
              PDF not available
            </div>
          )}
        </div>
      </div>
    </div>
  );
}