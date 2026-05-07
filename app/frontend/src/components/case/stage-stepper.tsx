import { CheckCircle2, ChevronRight } from "lucide-react";
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
  if (jobStage === "pending" || jobStage === "pages_extracting" || jobStage === "pages_done")
    return "extraction";
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
    <div className="flex items-center gap-2 p-3 bg-surface border-b border-border overflow-x-auto scrollbar-hide">
      <div className="flex items-center gap-1 mx-auto max-w-7xl w-full px-4">
        {STAGES.map((stage, index) => {
          const isCompleted = index < currentIndex;
          const isActive = index === activeIndex;
          const isLocked = index > currentIndex;

          return (
            <div key={stage.id} className="flex items-center gap-1 flex-1 last:flex-none">
              <button
                onClick={() => !isLocked && onStageClick(stage.id as WizardStage)}
                disabled={isLocked}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-md transition-all duration-200 relative min-w-max ${
                  isLocked ? "cursor-not-allowed" : "cursor-pointer"
                } ${
                  isActive
                    ? "bg-primary/10 text-primary ring-1 ring-primary/20"
                    : isLocked
                      ? "text-muted-foreground/30 grayscale"
                      : isCompleted
                        ? "text-foreground hover:bg-muted/50"
                        : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                }`}
              >
                {isCompleted && (
                  <CheckCircle2 className="w-5 h-5 text-primary shrink-0" />
                )}
                <span
                  className={`text-xs font-semibold tracking-wide uppercase transition-colors ${
                    isActive
                      ? "text-primary"
                      : isLocked
                        ? ""
                        : isCompleted
                          ? "text-foreground"
                          : "text-muted-foreground"
                  }`}
                >
                  {stage.label}
                </span>
                {isActive && (
                  <div className="absolute -bottom-[15px] left-0 right-0 h-0.5 bg-primary shadow-[0_0_8px_hsl(var(--primary)/0.5)]" />
                )}
              </button>
              {index < STAGES.length - 1 && (
                <div className="flex-1 flex items-center justify-center px-2 min-w-[1rem]">
                  <ChevronRight
                    className={`w-4 h-4 transition-colors duration-500 ${
                      index < currentIndex ? "text-primary/60" : "text-border"
                    }`}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
