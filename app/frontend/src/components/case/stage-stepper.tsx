import { CheckCircle2, Circle } from "lucide-react";
import { ExtractionJobStage } from "../../lib/api/client";

const STAGES = [
  { id: "extraction", label: "Page Extraction" },
  { id: "summary", label: "Full Summary" },
  { id: "action_plan", label: "Action Plan" },
  { id: "review", label: "Review" },
  { id: "dashboard", label: "Dashboard" },
];

export type WizardStage = "extraction" | "summary" | "action_plan" | "review" | "dashboard";

export function getWizardStageFromJobStage(jobStage: ExtractionJobStage | undefined): WizardStage {
  if (!jobStage) return "extraction";
  if (jobStage === "pending" || jobStage === "pages_extracting" || jobStage === "pages_done") return "extraction";
  if (jobStage === "summary_pending" || jobStage === "summary_done") return "summary";
  if (jobStage === "action_plan_pending" || jobStage === "action_plan_done") return "action_plan";
  if (jobStage === "review_in_progress") return "review";
  if (jobStage === "finalized") return "dashboard";
  return "extraction";
}

export function StageStepper({
  currentStage,
  activeStage,
  onStageClick,
}: {
  currentStage: WizardStage;
  activeStage: WizardStage;
  onStageClick: (stage: WizardStage) => void;
}) {
  const currentIndex = STAGES.findIndex((s) => s.id === currentStage);
  const activeIndex = STAGES.findIndex((s) => s.id === activeStage);

  return (
    <div className="flex items-center gap-2 p-4 bg-white border-b overflow-x-auto">
      {STAGES.map((stage, index) => {
        const isCompleted = index < currentIndex;
        const isCurrent = index === currentIndex;
        const isActive = index === activeIndex;
        const isLocked = index > currentIndex;

        return (
          <div key={stage.id} className="flex items-center gap-2 min-w-max">
            <button
              onClick={() => !isLocked && onStageClick(stage.id as WizardStage)}
              disabled={isLocked}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md transition-colors ${
                isActive
                  ? "bg-blue-50 text-blue-700 ring-1 ring-blue-200"
                  : isLocked
                  ? "text-muted-foreground cursor-not-allowed"
                  : "text-foreground hover:bg-slate-50"
              }`}
            >
              {isCompleted ? (
                <CheckCircle2 className="w-5 h-5 text-green-500" />
              ) : isCurrent ? (
                <Circle className="w-5 h-5 text-blue-500 fill-blue-50" />
              ) : (
                <Circle className="w-5 h-5 text-slate-300" />
              )}
              <span className={`text-sm font-medium ${isLocked ? "opacity-70" : ""}`}>
                {stage.label}
              </span>
            </button>
            {index < STAGES.length - 1 && (
              <div className={`w-8 h-px ${isLocked ? "bg-slate-200" : "bg-blue-200"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}


