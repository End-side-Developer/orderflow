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
import { DocumentRecord, getDocument } from "../../../lib/api/client";

export default function CaseWizardPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const router = useRouter();
  const { id } = use(params);
  const documentId = decodeURIComponent(id);

  const [document, setDocument] = useState<DocumentRecord | null>(null);
  const [docLoading, setDocLoading] = useState(true);
  const [docError, setDocError] = useState<string | null>(null);
  const [pdfPage, setPdfPage] = useState(1);

  const {
    data: progress,
    error: progressError,
    isLoading: progressLoading,
  } = useIntakeProgress(documentId);

  // Derive the backend stage
  const jobStage = progress?.stage;
  const currentAllowedStage = getWizardStageFromJobStage(jobStage);

  // The stage the user is currently viewing (can look back, but not forward)
  const [activeStage, setActiveStage] = useState<WizardStage>("extraction");

  useEffect(() => {
    // Fetch document details for the PDF viewer
    setPdfPage(1);
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
    <div className="flex flex-col h-full w-full overflow-hidden gap-4">
      <StageStepper
        currentStage={currentAllowedStage}
        activeStage={activeStage}
        onStageClick={handleStageClick}
      />

      <div className="flex-1 flex gap-4 overflow-hidden">
        {/* Left Pane: Stage Content */}
        <div className="flex-1 flex flex-col bg-white rounded-lg border overflow-y-auto shadow-sm">
          {activeStage === "extraction" && (
            <PageExtractionPanel documentId={documentId} progress={progress} />
          )}
          {activeStage === "summary" && (
            <SummaryPanel documentId={documentId} />
          )}
          {activeStage === "action_plan" && (
            <ActionPlanPanel
              documentId={documentId}
              onContinueToReview={() => setActiveStage("review")}
            />
          )}
          {activeStage === "review" && (
            <ReviewPanel
              documentId={documentId}
              onNavigateToPage={setPdfPage}
            />
          )}
          {activeStage === "dashboard" && (
            <DashboardPanel documentId={documentId} />
          )}
        </div>

        {/* Right Pane: Persistent PDF Viewer */}
        <div className="flex-1 flex flex-col bg-white rounded-lg border overflow-hidden shadow-sm">
          {document ? (
            <PdfViewer
              documentId={documentId}
              initialPage={pdfPage}
              onPageChange={setPdfPage}
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
