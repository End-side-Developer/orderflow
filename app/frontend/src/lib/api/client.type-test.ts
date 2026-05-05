import {
  CaseIntakeStartRequest,
  ExtractionJobStatusData,
  CaseDocumentSummaryData,
  CaseActionPlanData,
  CaseDashboardData,
  CaseDashboardParams,
  CaseFinalizeRequest,
  CaseFinalizeData,
  CaseActionPlanReviewRequest,
  CaseActionPlanReviewData,
  CaseActionPlanRegenerateRequest,
  CaseActionPlanRegenerateData,
} from "./client";

// This file serves as a typecheck proof for the new contracts.
// If any of these types change in an incompatible way, this file will fail to compile.

// 1. CaseIntakeStartRequest
const intakeRequest: CaseIntakeStartRequest = {
  bypass_cache: true,
  pages_total: 10,
  current_concurrency: 2,
};

// 2. ExtractionJobStatusData
const jobStatus: ExtractionJobStatusData = {
  id: "job-123",
  document_id: "doc-456",
  stage: "pages_extracting",
  pages_total: 10,
  pages_completed: 5,
  current_page: 6,
  current_page_excerpt: { text: "excerpt" },
  percent: 50,
  status_message: "Extracting page 6 of 10.",
  current_page_cache_status: null,
  is_paused: false,
  next_action: null,
  error: null,
  retry_after_seconds: null,
  paused_until: null,
  current_concurrency: 2,
  started_at: "2026-05-04T12:00:00Z",
  finalized_at: null,
  created_at: "2026-05-04T12:00:00Z",
  updated_at: "2026-05-04T12:05:00Z",
};

// 3. CaseDocumentSummaryData
const summaryData: CaseDocumentSummaryData = {
  id: "sum-123",
  document_id: "doc-456",
  case_basics: {
    case_number: "WP-123",
    court_name: "Supreme Court",
    case_type: "Writ Petition",
    order_date: "2026-05-01",
    petitioner: "John Doe",
    respondent: "State",
    judge_name: "Hon. Judge",
    department_involved: "Health",
    disposal_status: "Disposed",
    main_subject: "Subject",
    directive_summary: "Summary",
  },
  overview: "Overview",
  key_directives: [],
  important_dates: [],
  entities_involved: [],
  responsible_departments: [],
  flow_graph: null,
  map_data: null,
  confidence: 0.9,
  prompt_version: "v1",
  ai_model: "model-1",
  ai_provider: "provider-1",
  generated_at: "2026-05-04T12:00:00Z",
  created_at: "2026-05-04T12:00:00Z",
  updated_at: "2026-05-04T12:00:00Z",
};

// 4. CaseActionPlanData
const actionPlanData: CaseActionPlanData = {
  document_id: "doc-456",
  total: 0,
  items: [],
};

// 5. CaseDashboardData and Params
const dashboardParams: CaseDashboardParams = {
  department: "Health",
  priority: "high",
  status: "active",
};

const dashboardData: CaseDashboardData = {
  document_id: "doc-456",
  total: 10,
  approved_total: 8,
  edited_total: 2,
  groups: [],
};

// 6. CaseFinalizeRequest and Data
const finalizeRequest: CaseFinalizeRequest = {
  reviewer_name: "Alice",
  comments: "Looks good",
};

const finalizeData: CaseFinalizeData = {
  document_id: "doc-456",
  stage: "finalized",
  approved_count: 8,
  edited_count: 2,
  rejected_count: 0,
  finalized_at: "2026-05-04T12:00:00Z",
};

// 7. CaseActionPlanReviewRequest and Data
const reviewRequest: CaseActionPlanReviewRequest = {
  decision: "approve",
  reviewer_name: "Alice",
  comments: "Ok",
};

const reviewData: CaseActionPlanReviewData = {
  document_id: "doc-456",
  obligation_id: "obl-789",
  decision: "approve",
  action_plan_stage: "approved",
  obligation: null,
  reviewer_name: "Alice",
  rejection_reason: null,
  reviewed_at: "2026-05-04T12:00:00Z",
  comments: "Ok",
};

// 8. CaseActionPlanRegenerateRequest and Data
const regenerateRequest: CaseActionPlanRegenerateRequest = {
  feedback: "Fix this",
  reviewer_name: "Alice",
};

const regenerateData: CaseActionPlanRegenerateData = {
  document_id: "doc-456",
  obligation_id: "obl-789",
  action_plan_stage: "in_action_plan",
  regen_count: 1,
  obligation: null,
  updated_fields: {},
  regenerated_at: "2026-05-04T12:00:00Z",
};

// Prevent unused variable warnings in some strict configurations
export {
  intakeRequest,
  jobStatus,
  summaryData,
  actionPlanData,
  dashboardParams,
  dashboardData,
  finalizeRequest,
  finalizeData,
  reviewRequest,
  reviewData,
  regenerateRequest,
  regenerateData,
};
