export interface GlossaryEntry {
  simpleLabel: string;
  originalLabel: string;
  helpText: string;
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
  obligations: {
    simpleLabel: "Court duties",
    originalLabel: "Obligations",
    helpText: "Required actions a court has ordered. Review them and mark them done with proof.",
  },
  triage: {
    simpleLabel: "Sort by urgency",
    originalLabel: "Triage",
    helpText: "Prioritize items so the most urgent ones get attention first.",
  },
  intake: {
    simpleLabel: "Add new case",
    originalLabel: "Intake",
    helpText: "Upload a new judgment to start the workflow.",
  },
  workbench: {
    simpleLabel: "Case overview",
    originalLabel: "Workbench",
    helpText: "Summary of all your active cases in one place.",
  },
  ccms: {
    simpleLabel: "Court system details",
    originalLabel: "CCMS / CIS metadata",
    helpText: "Information from the official Indian e-Courts system.",
  },
  "extraction-mode": {
    simpleLabel: "AI reading method",
    originalLabel: "Extraction mode",
    helpText: "How the AI reads and extracts information from the document.",
  },
  "audit-trail": {
    simpleLabel: "Change history",
    originalLabel: "Audit trail",
    helpText: "Full record of every change made and who made it.",
  },
  verifications: {
    simpleLabel: "Advocate approvals",
    originalLabel: "Verifications",
    helpText: "Review and approve advocate registration requests.",
  },
  proof: {
    simpleLabel: "Evidence",
    originalLabel: "Proof",
    helpText: "Supporting document showing a duty was completed.",
  },
  departments: {
    simpleLabel: "Government offices",
    originalLabel: "Departments",
    helpText: "Performance and load across government departments.",
  },
  analyze: {
    simpleLabel: "Read documents",
    originalLabel: "Analyze",
    helpText: "View AI-generated page summaries and highlights.",
  },
  verify: {
    simpleLabel: "Approve duties",
    originalLabel: "Verify",
    helpText: "Approve, reject, or close court duties with evidence.",
  },
};
