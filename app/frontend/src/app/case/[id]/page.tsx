"use client";

import { use, useEffect, useState } from "react";
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
import { CitationVisualRef, DocumentRecord, getDocument } from "../../../lib/api/client";

export default function CaseWizardPage({ params }: { params: Promise<{ id: string }> }) {
  const router = useRouter();
  const { id } = use(params);
  const documentId = decodeURIComponent(id);

  const [document, setDocument] = useState<DocumentRecord | null>(null);
  const [docLoading, setDocLoading] = useState(true);
  const [docError, setDocError] = useState<string | null>(null);
  const [pdfPage, setPdfPage] = useState(1);
  const [activeVisualRefs, setActiveVisualRefs] = useState<CitationVisualRef[]>([]);

  const {
    data: progress,
    error: progressError,
    isLoading: progressLoading,
    isPolling,
  } = useIntakeProgress(documentId);

  // Derive the backend stage
  const jobStage = progress?.stage;
  const currentAllowedStage = getWizardStageFromJobStage(jobStage);

  // The stage the user is currently viewing (can look back, but not forward)
  const [activeStage, setActiveStage] = useState<WizardStage>("extraction");

  useEffect(() => {
    // Fetch document details for the PDF viewer
    setPdfPage(1);
    setActiveVisualRefs([]);
    setDocLoading(true);
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
    // Auto-advance active stage when allowed stage moves forward, unless user is looking back
    if (jobStage) {
      setActiveStage(currentAllowedStage);
    }
  }, [currentAllowedStage, jobStage]);

  const handleStageClick = (stage: WizardStage) => {
    setActiveStage(stage);
  };

  if (docError || progressError) {
    return (
      <div className="flex flex-col h-full bg-slate-50">
        <div className="flex-1 flex items-center justify-center">
          <div className="bg-red-50 text-red-600 p-6 rounded-lg max-w-md">
            <h2 className="text-lg font-bold mb-2">Error Loading Case</h2>
            <p>{docError || progressError?.message}</p>
            <button
              onClick={() => router.push("/dashboard")}
              className="mt-4 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
            >
              Back to Dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (docLoading || progressLoading) {
    return (
      <div className="flex flex-col h-full bg-slate-50">
        <div className="flex-1 flex items-center justify-center">
          <div className="text-slate-500 animate-pulse">Loading case data...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-9rem)] w-full flex-col gap-4 overflow-hidden">
      <StageStepper
        currentStage={currentAllowedStage}
        activeStage={activeStage}
        onStageClick={handleStageClick}
      />

      <div className="grid min-h-0 flex-1 gap-4 overflow-hidden xl:grid-cols-[minmax(420px,0.92fr)_minmax(560px,1.08fr)]">
        <div className="flex min-h-0 flex-col overflow-y-auto rounded-lg border border-border bg-card shadow-sm">
          {activeStage === "extraction" && (
            <PageExtractionPanel
              documentId={documentId}
              progress={progress}
              isPolling={isPolling}
            />
          )}
          {activeStage === "summary" && <SummaryPanel documentId={documentId} />}
          {activeStage === "action_plan" && (
            <ActionPlanPanel
              documentId={documentId}
              onContinueToReview={() => setActiveStage("review")}
            />
          )}
          {activeStage === "review" && (
            <ReviewPanel
              documentId={documentId}
              onNavigateToPage={(pageNumber, visualRefs = []) => {
                setPdfPage(pageNumber);
                setActiveVisualRefs(visualRefs);
              }}
              onProceedToDashboard={() => setActiveStage("dashboard")}
            />
          )}
          {activeStage === "dashboard" && <DashboardPanel documentId={documentId} />}
        </div>

        <div className="flex min-h-[640px] flex-col overflow-hidden rounded-lg border border-border bg-card shadow-sm xl:min-h-0">
          {document ? (
            <PdfViewer
              documentId={documentId}
              initialPage={pdfPage}
              onPageChange={setPdfPage}
              activeVisualRefs={activeVisualRefs}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-400">
              PDF not available
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
