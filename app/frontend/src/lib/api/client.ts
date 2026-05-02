export type ApiSuccess<T> = {
  ok: true;
  message: string;
  request_id?: string;
  data: T;
};

export type ApiFailure = {
  ok: false;
  request_id?: string;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
};

export type ApiResult<T> = ApiSuccess<T> | ApiFailure;

type ApiEnvelope<T> = {
  ok?: boolean;
  message?: string;
  request_id?: string;
  data?: T;
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
  };
  detail?: unknown;
};

export type HealthPayload = {
  service: string;
  version: string;
  environment: string;
  status: string;
  scope: string;
  uptime_seconds: number;
};

export type DocumentRecord = {
  id: string;
  source_file_name: string;
  source_file_type: string | null;
  source_file_size: number | null;
  object_key: string | null;
  checksum_sha256: string | null;
  workflow_run_id: string | null;
  status: "uploaded" | "processing" | "ready" | "failed";
  metadata: Record<string, unknown> | null;
  source_language: string;
  auto_detected_language: string | null;
  language_confidence: number;
  translated_text_stored: boolean;
  created_at: string;
  updated_at: string;
};

export type DocumentsListData = {
  total: number;
  items: DocumentRecord[];
};

export type IndianECourtsIntakeEnvelope = {
  ccms: {
    reference_id?: string;
    delivery_timestamp?: string;
    document_type?: string;
    source_url?: string;
    source_gateway?: string;
    receipt_id?: string;
  };
  cis?: {
    case_id?: string;
    court_name?: string;
    court_code?: string;
    order_date?: string;
    bench?: string;
    parties?: string[];
    petitioners?: string[];
    respondents?: string[];
    case_type?: string;
    filing_number?: string;
    diary_number?: string;
    judge_names?: string[];
    hearing_stage?: string;
    state?: string;
    district?: string;
    department_tags?: string[];
  };
  source_file_name?: string;
  source_file_type?: string;
  additional_metadata?: Record<string, unknown>;
};

export type IndianECourtsLookupPayload = {
  identifier: string;
  resolved_source_url: string;
  source_file_name: string;
  source_file_type: string;
  file_content_base64: string;
  envelope: IndianECourtsIntakeEnvelope;
  note?: string;
};

export type ObligationCitation = {
  page_number: number | null;
  clause_span: string | null;
  clause_index: number | null;
  span_start: number | null;
  span_end: number | null;
};

export type ObligationConfidenceAnnotations = {
  extractor_version: string | null;
  components: Record<string, number>;
  weights: Record<string, number>;
  rationale: string[];
  signals: Record<string, string | number | boolean | null>;
};

export type EscalationLevel = "none" | "watch" | "escalated" | "critical";

export type ObligationEscalationSignal = {
  level: EscalationLevel;
  open: boolean;
  reasons: string[];
  days_until_due: number | null;
  generated_at: string | null;
};

export type ObligationRiskFactor = {
  name: string;
  weight: number;
  contribution: number;
  detail: string;
};

export type ObligationRiskBand = "low" | "moderate" | "high" | "critical";

export type ObligationRecord = {
  id: string;
  document_id: string;
  obligation_code: string | null;
  title: string;
  description: string | null;
  owner_hint: string | null;
  due_date: string | null;
  status: "draft" | "active" | "completed" | "cancelled";
  priority: "low" | "medium" | "high" | "critical";
  review_state: "pending_review" | "approved" | "rejected";
  confidence: number | null;
  confidence_annotations: ObligationConfidenceAnnotations | null;
  escalation: ObligationEscalationSignal | null;
  citation: ObligationCitation | null;
  risk_score: number | null;
  risk_band: ObligationRiskBand | null;
  risk_factors: ObligationRiskFactor[];
  created_at: string;
  updated_at: string;
};

export type EscalationSummaryItem = {
  obligation_id: string;
  title: string;
  level: EscalationLevel;
  days_until_due: number | null;
  due_date: string | null;
  review_state: "pending_review" | "approved" | "rejected";
  priority: "low" | "medium" | "high" | "critical";
  reasons: string[];
  risk_score: number | null;
  risk_band: ObligationRiskBand | null;
  risk_factors: ObligationRiskFactor[];
};

export type EscalationsPayload = {
  document_id: string;
  total: number;
  open_total: number;
  critical_total: number;
  items: EscalationSummaryItem[];
};

export type ObligationAuditEvent = {
  id: number;
  obligation_id: string;
  action: string;
  actor_type: string;
  actor_id: string | null;
  request_id: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
};

export type ObligationAuditTrailPayload = {
  obligation_id: string;
  total: number;
  items: ObligationAuditEvent[];
};

export type ClauseRecord = {
  id: string;
  document_id: string;
  clause_index: number;
  page_number: number | null;
  span_start: number | null;
  span_end: number | null;
  text: string;
  normalized_text: string | null;
  citation_span: string | null;
  confidence: number | null;
  created_at: string;
  updated_at: string;
};

export type ObligationsPayload = {
  document_id: string | null;
  total: number;
  items: ObligationRecord[];
};

export type ClausesPayload = {
  document_id: string | null;
  page_number: number | null;
  clause_span: string | null;
  total: number;
  items: ClauseRecord[];
};

export type IntakeExtractionResult = {
  document_id: string;
  clause_count: number;
  obligation_count: number;
  extraction_mode: "deterministic" | "ai" | "ai_fallback";
  ai_provider: string | null;
  ai_model: string | null;
  ai_reason: string | null;
};

export type IntakeAiOptions = {
  enabled?: boolean;
  provider?: "openai" | "anthropic" | "gemini" | "groq";
  model?: string;
  api_key?: string;
  temperature?: number;
  max_obligations?: number;
};

export type WorkflowRunRecord = {
  id: string;
  document_id: string;
  workflow_type: string;
  workflow_id: string;
  run_id: string;
  task_queue: string;
  status: "started" | "completed" | "failed";
  metadata: Record<string, unknown> | null;
  started_at: string;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ObligationProofSubmission = {
  proof_text: string;
  proof_timestamp?: string;
  proof_bytes_sha256?: string;
  expected_sha256?: string;
  proof_pdf_metadata?: Record<string, unknown>;
  original_pdf_metadata?: Record<string, unknown>;
};

export type ObligationUpdatePayload = {
  review_state?: "pending_review" | "approved" | "rejected";
  owner_hint?: string;
  status?: "draft" | "active" | "completed" | "cancelled";
  proof?: ObligationProofSubmission;
};

export type ExportLanguage = "en" | "hi" | "ta" | "te" | "kn" | "ml" | "mr";

export type PressureLevel = "stable" | "watch" | "urgent" | "critical";
export type WorkbenchStage =
  | "intake_running"
  | "ready_for_extraction"
  | "review_gate"
  | "execution"
  | "execution_risk"
  | "closure_ready";

export type WorkbenchDocumentMetrics = {
  total_obligations: number;
  pending_review: number;
  approved: number;
  rejected: number;
  completed: number;
  open_escalations: number;
  critical_escalations: number;
};

export type WorkbenchDocumentCard = {
  document_id: string;
  source_file_name: string;
  source_language: ExportLanguage;
  status: "uploaded" | "processing" | "ready" | "failed";
  workflow_status: "started" | "completed" | "failed" | null;
  pressure_level: PressureLevel;
  stage: WorkbenchStage;
  next_action: string;
  department: string | null;
  court_name: string | null;
  created_at: string;
  updated_at: string;
  last_activity_at: string | null;
  metrics: WorkbenchDocumentMetrics;
};

export type WorkbenchSummary = {
  total_documents: number;
  ready_documents: number;
  in_flight_documents: number;
  pending_review: number;
  open_escalations: number;
  critical_escalations: number;
  total_obligations: number;
};

export type WorkbenchActivityItem = {
  title: string;
  document_id: string;
  obligation_id: string | null;
  action: string;
  actor_type: string;
  created_at: string;
  level: PressureLevel;
  detail: string | null;
};

export type WorkbenchRelatedCase = {
  document_id: string;
  source_file_name: string;
  similarity_score: number;
  overlap_count: number;
  rationale_tags: string[];
  sample_titles: string[];
  open_escalations: number;
  pressure_level: PressureLevel;
  recommended_focus: string;
};

export type WorkbenchNextAction = {
  priority: "critical" | "high" | "medium";
  title: string;
  detail: string;
};

export type WorkbenchOverviewData = {
  summary: WorkbenchSummary;
  documents: WorkbenchDocumentCard[];
  recent_activity: WorkbenchActivityItem[];
};

export type WorkbenchDocumentData = {
  document: WorkbenchDocumentCard;
  related_cases: WorkbenchRelatedCase[];
  next_actions: WorkbenchNextAction[];
  recent_activity: WorkbenchActivityItem[];
};

const apiBaseUrl = process.env.NEXT_PUBLIC_ORDERFLOW_API_BASE_URL ?? "http://localhost:8000/api/v1";

// Auth handlers registered by <AuthProvider> to avoid a circular store ↔ client import.
let _getToken: () => string | null = () => null;
let _doRefresh: () => Promise<string | null> = () => Promise.resolve(null);

export function registerAuthHandlers(
  getToken: () => string | null,
  doRefresh: () => Promise<string | null>,
): void {
  _getToken = getToken;
  _doRefresh = doRefresh;
}

function createRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  return `req-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function buildFailure(
  code: string,
  message: string,
  requestId?: string,
  details?: Record<string, unknown>,
): ApiFailure {
  return {
    ok: false,
    request_id: requestId,
    error: {
      code,
      message,
      details,
    },
  };
}

function normalizeErrorDetail(detail: unknown): string {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (typeof detail === "object" && detail !== null) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
  }

  return "Request failed";
}

async function parseResponse<T>(response: Response): Promise<ApiResult<T>> {
  let payload: ApiEnvelope<T> | null = null;

  try {
    payload = (await response.json()) as ApiEnvelope<T>;
  } catch {
    payload = null;
  }

  if (response.ok && payload?.ok === true && payload.data !== undefined) {
    return {
      ok: true,
      message: payload.message ?? "ok",
      request_id: payload.request_id,
      data: payload.data,
    };
  }

  // Automatically wrap raw data payloads that don't use ApiEnvelope
  if (response.ok && payload && typeof payload === "object" && !("ok" in payload) && !("error" in payload)) {
    return {
      ok: true,
      message: "ok",
      request_id: undefined,
      data: payload as unknown as T,
    };
  }

  if (payload?.ok === false && payload.error) {
    return {
      ok: false,
      request_id: payload.request_id,
      error: {
        code: payload.error.code ?? `http_${response.status}`,
        message: payload.error.message ?? `HTTP ${response.status}`,
        details: payload.error.details,
      },
    };
  }

  return buildFailure(
    `http_${response.status}`,
    normalizeErrorDetail(payload?.detail),
    payload?.request_id,
    payload && typeof payload.detail === "object"
      ? (payload.detail as Record<string, unknown>)
      : undefined,
  );
}

async function requestApi<T>(path: string, init: RequestInit): Promise<ApiResult<T>> {
  const url = `${apiBaseUrl}${path}`;
  const requestId = createRequestId();

  try {
    const headers = new Headers(init.headers);
    headers.set("x-request-id", requestId);
    headers.set("x-client-service", "orderflow-frontend");
    headers.set("x-client-path", path);

    const token = _getToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    const response = await fetch(url, {
      ...init,
      cache: "no-store",
      credentials: init.credentials ?? "include",
      headers,
    });

    // On 401, try a single token refresh then retry (skip for auth routes to avoid loops)
    if (response.status === 401 && token && !path.startsWith("/auth/")) {
      const newToken = await _doRefresh();
      if (newToken) {
        headers.set("Authorization", `Bearer ${newToken}`);
        const retryResponse = await fetch(url, {
          ...init,
          cache: "no-store",
          credentials: init.credentials ?? "include",
          headers,
        });
        return parseResponse<T>(retryResponse);
      }
    }

    return parseResponse<T>(response);
  } catch (error) {
    return buildFailure(
      "network_error",
      error instanceof Error ? error.message : "Network request failed",
      requestId,
    );
  }
}

export async function apiGet<T>(path: string): Promise<ApiResult<T>> {
  return requestApi<T>(path, {
    method: "GET",
    headers: {
      "content-type": "application/json",
    },
  });
}

export async function apiPostJson<TRequest, TResponse>(
  path: string,
  payload: TRequest,
): Promise<ApiResult<TResponse>> {
  return requestApi<TResponse>(path, {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function apiPostForm<TResponse>(
  path: string,
  formData: FormData,
): Promise<ApiResult<TResponse>> {
  return requestApi<TResponse>(path, {
    method: "POST",
    body: formData,
  });
}

export async function getApiHealth(): Promise<ApiResult<HealthPayload>> {
  return apiGet<HealthPayload>("/health");
}

export async function uploadDocument(formData: FormData): Promise<ApiResult<DocumentRecord>> {
  return apiPostForm<DocumentRecord>("/documents/upload", formData);
}

export async function intakeIndianECourtsDocument(
  formData: FormData,
): Promise<ApiResult<DocumentRecord>> {
  return apiPostForm<DocumentRecord>("/documents/intake/indian-ecourts", formData);
}

export async function lookupIndianECourtsIntake(
  identifier: string,
): Promise<ApiResult<IndianECourtsLookupPayload>> {
  return apiPostJson<{ identifier: string }, IndianECourtsLookupPayload>(
    "/documents/intake/indian-ecourts/lookup",
    { identifier },
  );
}

export async function getDocument(documentId: string): Promise<ApiResult<DocumentRecord>> {
  return apiGet<DocumentRecord>(`/documents/${encodeURIComponent(documentId)}`);
}

export async function listDocuments(): Promise<ApiResult<DocumentsListData>> {
  return apiGet<DocumentsListData>("/documents");
}

export async function getWorkbenchOverview(): Promise<ApiResult<WorkbenchOverviewData>> {
  return apiGet<WorkbenchOverviewData>("/workbench/overview");
}

export async function getDocumentWorkbench(
  documentId: string,
): Promise<ApiResult<WorkbenchDocumentData>> {
  return apiGet<WorkbenchDocumentData>(`/workbench/documents/${encodeURIComponent(documentId)}`);
}

export type PageAnnotation = {
  id: string;
  document_id: string;
  page_number: number;
  annotation_type: "highlight" | "note" | "obligation";
  text_content: string | null;
  bbox: { x: number; y: number; width: number; height: number } | null;
  color: string | null;
  tooltip_text: string | null;
  ai_generated: boolean;
  created_at: string;
  updated_at: string;
};

export type PageAnnotationsListData = {
  document_id: string;
  total_annotations: number;
  items: PageAnnotation[];
};

export async function listAnnotations(
  documentId: string,
): Promise<ApiResult<PageAnnotationsListData>> {
  return apiGet<PageAnnotationsListData>(`/annotations/${documentId}`);
}

export async function generateAnnotations(
  documentId: string,
): Promise<ApiResult<PageAnnotationsListData>> {
  return apiPostJson<object, PageAnnotationsListData>(`/annotations/${documentId}/generate`, {});
}

export async function generatePageSummaries(
  documentId: string,
): Promise<ApiResult<unknown>> {
  return apiPostJson<object, unknown>(`/summaries/${documentId}/generate`, {});
}

export type AnnotationBboxUpdate = {
  annotation_id: string;
  bbox: { x: number; y: number; width: number; height: number };
};

export async function updateAnnotationCoordinates(
  documentId: string,
  updates: AnnotationBboxUpdate[],
): Promise<ApiResult<{ updated_count: number }>> {
  return apiPostJson<{ updates: AnnotationBboxUpdate[] }, { updated_count: number }>(
    `/annotations/${documentId}/coordinates`,
    { updates },
  );
}

export type DocumentDownloadResult = {
  blob: Blob;
  fileName: string | null;
  contentType: string | null;
};

function parseContentDispositionFilename(value: string | null): string | null {
  if (!value) {
    return null;
  }

  const match = value.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i);
  const encodedName = match?.[1];
  const plainName = match?.[2];
  if (encodedName) {
    try {
      return decodeURIComponent(encodedName);
    } catch {
      return encodedName;
    }
  }

  return plainName ?? null;
}

export async function downloadDocument(documentId: string): Promise<DocumentDownloadResult> {
  const path = `/documents/${encodeURIComponent(documentId)}/download`;
  const url = `${apiBaseUrl}${path}`;
  const requestId = createRequestId();

  try {
    const response = await fetch(url, {
      method: "GET",
      cache: "no-store",
      headers: {
        "x-request-id": requestId,
        "x-client-service": "orderflow-frontend",
        "x-client-path": path,
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return {
      blob: await response.blob(),
      fileName: parseContentDispositionFilename(response.headers.get("content-disposition")),
      contentType: response.headers.get("content-type"),
    };
  } catch (error) {
    throw new Error(error instanceof Error ? error.message : "Document download request failed");
  }
}

export type ActionPlanDownloadResult = {
  blob: Blob;
  fileName: string | null;
  contentType: string | null;
};

export async function downloadActionPlan(
  documentId: string,
  language: ExportLanguage,
  format: "markdown" | "json" = "markdown",
): Promise<ActionPlanDownloadResult> {
  const query = new URLSearchParams({
    document_id: documentId,
    language,
    format,
  });

  const path = `/exports/action-plan?${query.toString()}`;
  const url = `${apiBaseUrl}${path}`;
  const requestId = createRequestId();

  try {
    const response = await fetch(url, {
      method: "GET",
      cache: "no-store",
      headers: {
        "x-request-id": requestId,
        "x-client-service": "orderflow-frontend",
        "x-client-path": path,
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return {
      blob: await response.blob(),
      fileName: parseContentDispositionFilename(response.headers.get("content-disposition")),
      contentType: response.headers.get("content-type"),
    };
  } catch (error) {
    throw new Error(error instanceof Error ? error.message : "Action plan download request failed");
  }
}

export async function runIntakeExtraction(
  documentId: string,
  aiOptions?: IntakeAiOptions,
): Promise<ApiResult<IntakeExtractionResult>> {
  const payload: { document_id: string; ai?: IntakeAiOptions } = {
    document_id: documentId,
  };
  if (aiOptions) {
    payload.ai = aiOptions;
  }

  return apiPostJson<{ document_id: string; ai?: IntakeAiOptions }, IntakeExtractionResult>(
    "/extractions/intake/run",
    payload,
  );
}

export async function startIntakeWorkflow(
  documentId: string,
): Promise<ApiResult<WorkflowRunRecord>> {
  return apiPostJson<{ document_id: string }, WorkflowRunRecord>("/workflows/intake/start", {
    document_id: documentId,
  });
}

export async function getIntakeWorkflowStatus(
  documentId: string,
): Promise<ApiResult<WorkflowRunRecord>> {
  const query = new URLSearchParams({ document_id: documentId });
  return apiGet<WorkflowRunRecord>(`/workflows/intake/status?${query.toString()}`);
}

export async function getWorkflowRun(runId: string): Promise<ApiResult<WorkflowRunRecord>> {
  return apiGet<WorkflowRunRecord>(`/workflows/runs/${encodeURIComponent(runId)}`);
}

export async function listObligations(documentId: string): Promise<ApiResult<ObligationsPayload>> {
  const query = new URLSearchParams({ document_id: documentId });
  return apiGet<ObligationsPayload>(`/obligations?${query.toString()}`);
}

export async function listAllObligations(): Promise<ApiResult<ObligationsPayload>> {
  return apiGet<ObligationsPayload>("/obligations");
}

export async function listClauses(
  documentId: string,
  options?: { pageNumber?: number; clauseSpan?: string },
): Promise<ApiResult<ClausesPayload>> {
  const query = new URLSearchParams({ document_id: documentId });
  if (typeof options?.pageNumber === "number") {
    query.set("page_number", String(options.pageNumber));
  }
  if (options?.clauseSpan) {
    query.set("clause_span", options.clauseSpan);
  }

  return apiGet<ClausesPayload>(`/clauses?${query.toString()}`);
}

export async function listEscalations(documentId: string): Promise<ApiResult<EscalationsPayload>> {
  const query = new URLSearchParams({ document_id: documentId });
  return apiGet<EscalationsPayload>(`/escalations?${query.toString()}`);
}

export async function getObligationAuditTrail(
  obligationId: string,
): Promise<ApiResult<ObligationAuditTrailPayload>> {
  return apiGet<ObligationAuditTrailPayload>(
    `/obligations/${encodeURIComponent(obligationId)}/audit`,
  );
}

export async function updateObligation(
  obligationId: string,
  payload: ObligationUpdatePayload,
): Promise<ApiResult<ObligationRecord>> {
  return requestApi<ObligationRecord>(`/obligations/${encodeURIComponent(obligationId)}`, {
    method: "PATCH",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

// ──── Department-Aware Routing (P1-1) ────

export type DepartmentMatch = {
  code: string;
  name: string;
  confidence: number;
  matched_aliases: string[];
};

export type OfficerSuggestion = {
  id: string;
  name: string;
  designation: string;
  department_code: string;
  jurisdiction: string;
  contact: string;
};

export type RouteDirectiveData = {
  primary: DepartmentMatch | null;
  candidates: DepartmentMatch[];
  suggested_officers: OfficerSuggestion[];
  multi_department: boolean;
  rationale: string;
};

export async function routeDirective(
  text: string,
): Promise<ApiResult<RouteDirectiveData>> {
  return requestApi<RouteDirectiveData>("/routing/route", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

// ──── Department Health Scoring (P1-2) ────

export type DepartmentHealthBand = "excellent" | "healthy" | "watch" | "at_risk";

export type DepartmentHealthItem = {
  code: string;
  name: string;
  total_obligations: number;
  completed: number;
  overdue: number;
  pending_review: number;
  open_escalations: number;
  critical_escalations: number;
  avg_risk_score: number;
  compliance_rate: number;
  breach_rate: number;
  health_score: number;
  band: DepartmentHealthBand;
  rationale: string[];
};

export type DepartmentHealthData = {
  total_departments: number;
  avg_health_score: number;
  items: DepartmentHealthItem[];
};

export async function listDepartmentHealth(): Promise<
  ApiResult<DepartmentHealthData>
> {
  return apiGet<DepartmentHealthData>("/departments/health");
}

// ──── Public-Trust Mode (P1-4) ────

export type PublicObligationItem = {
  id: string;
  document_id: string;
  title: string;
  description: string;
  owner_role: string | null;
  due_date: string | null;
  status: string | null;
  priority: string | null;
  review_state: string | null;
  risk_score: number | null;
  risk_band: ObligationRiskBand | null;
  redaction: Record<string, number>;
};

export type PublicObligationsData = {
  total: number;
  redacted_count_summary: Record<string, number>;
  items: PublicObligationItem[];
};

export async function listPublicObligations(
  limit = 200,
): Promise<ApiResult<PublicObligationsData>> {
  return apiGet<PublicObligationsData>(`/public/obligations?limit=${limit}`);
}

// ──── Page-Level Obligation Extraction (LangGraph HITL) ────

export type SourceHighlightData = {
  text: string;
  start: number;
  end: number;
};

export type ConfidenceComponentData = {
  directive_signal: number;
  entity_presence: number;
  temporal_signal: number;
  overall: number;
};

export type ExtractedObligation = {
  obligation_code: string;
  title: string;
  description: string;
  confidence: number;
  confidence_components: ConfidenceComponentData;
  source_highlights: SourceHighlightData[];
  page_number: number;
  owner_hint: string;
  due_date: string | null;
  priority: "low" | "medium" | "high" | "critical";
  review_state: "pending_review" | "approved" | "rejected";
};

export type ExtractObligationsData = {
  document_id: string;
  page_number: number;
  obligations: ExtractedObligation[];
  average_confidence: number;
  gate_decision: string;
  requires_human_review: boolean;
  extraction_mode: string;
  ai_provider: string | null;
  ai_model: string | null;
};

export type ExtractObligationsRequest = {
  document_id: string;
  page_number: number;
  text: string;
  confidence_threshold?: number;
};

export async function extractPageObligations(
  payload: ExtractObligationsRequest,
): Promise<ApiResult<ExtractObligationsData>> {
  return apiPostJson<ExtractObligationsRequest, ExtractObligationsData>(
    "/intelligence/extract-obligations",
    payload,
  );
}

export type ReviewObligationRequest = {
  obligation_code: string;
  review_decision: "approved" | "rejected";
  edited_title?: string | null;
  edited_description?: string | null;
  review_note?: string | null;
};

export type ReviewObligationData = {
  obligation_code: string;
  review_decision: string;
  review_note: string | null;
  edited_title: string | null;
  edited_description: string | null;
  message: string;
};

export async function reviewObligation(
  payload: ReviewObligationRequest,
): Promise<ApiResult<ReviewObligationData>> {
  return apiPostJson<ReviewObligationRequest, ReviewObligationData>(
    "/intelligence/review-obligation",
    payload,
  );
}

// ──── Judgment Decision Intelligence (Theme 11 Core) ────

export type DirectiveItem = {
  text: string;
  page: number | null;
  urgency: "immediate" | "within_deadline" | "standard";
};

export type ComplianceDecision = {
  recommendation: "comply" | "appeal" | "partial_comply" | "legal_review_required";
  rationale: string;
  directives: DirectiveItem[];
};

export type AppealAnalysis = {
  should_appeal: boolean;
  appeal_grounds: string[];
  limitation_period: string | null;
  limitation_basis: string | null;
  filing_deadline: string | null;
  risk_if_not_appealed: string | null;
};

export type ResponsibleAuthority = {
  authority: string;
  department: string;
  role: string;
  action_required: string;
};

export type CriticalAction = {
  action: string;
  deadline: string | null;
  owner: string;
  priority: "critical" | "high" | "medium";
  consequence_if_missed: string | null;
};

export type CaseSummaryData = {
  case_type: string | null;
  parties: string | null;
  court: string | null;
  order_date: string | null;
  disposition: string | null;
};

export type ActionPlanItem = {
  action_id: string;
  title: string;
  description: string;
  nature_of_action: string;
  compliance_requirement: string | null;
  appeal_consideration: string | null;
  timeline: string | null;
  timeline_type: string;
  responsible_department: string | null;
  responsible_officer: string | null;
  legal_basis: string | null;
  risk_level: string;
  risk_if_delayed: string | null;
  dependencies: string[];
  verification_method: string | null;
  source_page: number | null;
  source_quote: string | null;
};

export type ActionPlanSummary = {
  total_actions: number;
  critical_count: number;
  compliance_actions: number;
  appeal_actions: number;
  earliest_deadline: string | null;
  departments_involved: string[];
  items: ActionPlanItem[];
};

export type ReproducibilityFootprint = {
  prompt_version: string;
  prompt_sha: string;
  model: string;
  temperature: number;
  provider: string;
  rule_engine_version: string;
};

export type JudgmentDecisionData = {
  document_id: string;
  compliance_decision: ComplianceDecision;
  appeal_analysis: AppealAnalysis;
  responsible_authorities: ResponsibleAuthority[];
  critical_actions: CriticalAction[];
  action_plan: ActionPlanSummary;
  case_summary: CaseSummaryData;
  ai_provider: string | null;
  ai_model: string | null;
  extraction_mode: string;
  reproducibility: ReproducibilityFootprint | null;
};

export type JudgmentDecisionRequest = {
  document_id: string;
  full_text: string;
  page_count: number;
};

export async function getJudgmentDecisions(
  payload: JudgmentDecisionRequest,
): Promise<ApiResult<JudgmentDecisionData>> {
  return apiPostJson<JudgmentDecisionRequest, JudgmentDecisionData>(
    "/intelligence/judgment-decisions",
    payload,
  );
}

// ──── Page Insight (Gemini per-page enrichment) ────

export type PageInsightKeyEntity = { name: string; role: string };
export type PageInsightImportantDate = { date: string; description: string };
export type PageInsightStatItem = { label: string; value: string };
export type PageInsightFlowStep = { step: number; title: string; detail: string };

export type PageInsightData = {
  brief: string;
  risks: string[];
  suggested_action: string | null;
  key_entities: PageInsightKeyEntity[];
  important_dates: PageInsightImportantDate[];
  statistics: PageInsightStatItem[];
  procedural_flow: PageInsightFlowStep[];
  page_category: string | null;
  complexity_score: number | null;
};

export type PageInsightRequest = {
  document_id: string;
  page_number: number;
  text: string;
};

export async function getPageInsight(
  payload: PageInsightRequest,
): Promise<ApiResult<PageInsightData>> {
  return apiPostJson<PageInsightRequest, PageInsightData>(
    "/intelligence/page-insight",
    payload,
  );
}

// ──── Adversarial Verifier (Devil's Advocate second-pass) ────

export type VerifierConcern = {
  severity: "critical" | "high" | "medium" | "low";
  category: string;
  title: string;
  detail: string;
  related_action_id: string | null;
};

export type VerifierData = {
  document_id: string;
  concerns: VerifierConcern[];
  overall_verdict: "looks_solid" | "concerns_found" | "major_gaps";
  extraction_mode: string;
  ai_provider: string | null;
  ai_model: string | null;
  reproducibility: ReproducibilityFootprint | null;
};

export type VerifierRequest = {
  document_id: string;
  full_text: string;
  action_plan_summary: string;
};

export async function verifyJudgmentDecision(
  payload: VerifierRequest,
): Promise<ApiResult<VerifierData>> {
  return apiPostJson<VerifierRequest, VerifierData>(
    "/intelligence/verify-judgment-decision",
    payload,
  );
}

// ──── Auth ────

export type UserRole = "citizen" | "advocate" | "judge" | "government";
export type UserStatus = "active" | "pending_verification" | "suspended" | "disabled";

export type AuthUserRecord = {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  status: UserStatus;
  preferred_language: string;
  phone: string | null;
  email_verified_at: string | null;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AdvocateJurisdiction = {
  level: "supreme" | "high" | "district" | "tribunal" | "other";
  name: string;
  state?: string;
};

export type AdvocateProfileCreatePayload = {
  bar_council_id: string;
  registration_number?: string;
  bio?: string;
  years_of_experience?: number;
  languages?: string[];
  specializations?: string[];
  jurisdictions?: AdvocateJurisdiction[];
  consultation_fee_min_inr?: number;
  consultation_fee_max_inr?: number;
};

export type RegisterRequest = {
  email: string;
  password: string;
  full_name: string;
  role: "citizen" | "advocate";
  phone?: string;
  advocate_profile?: AdvocateProfileCreatePayload;
};

export type RegisterData = { user: AuthUserRecord };
export type LoginData = {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUserRecord;
};

export async function registerUser(payload: RegisterRequest): Promise<ApiResult<RegisterData>> {
  return apiPostJson<RegisterRequest, RegisterData>("/auth/register", payload);
}

export async function loginUser(
  email: string,
  password: string,
): Promise<ApiResult<LoginData>> {
  return apiPostJson<{ email: string; password: string }, LoginData>("/auth/login", {
    email,
    password,
  });
}

export async function logoutUser(): Promise<ApiResult<{ message: string }>> {
  return requestApi<{ message: string }>("/auth/logout", {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
  });
}

export async function getMe(): Promise<ApiResult<AuthUserRecord>> {
  return apiGet<AuthUserRecord>("/auth/me");
}

export async function changePassword(
  current_password: string,
  new_password: string,
): Promise<ApiResult<{ message: string }>> {
  return apiPostJson<{ current_password: string; new_password: string }, { message: string }>(
    "/auth/password",
    { current_password, new_password },
  );
}

export async function getUserById(id: string): Promise<ApiResult<AuthUserRecord>> {
  return apiGet<AuthUserRecord>(`/users/${encodeURIComponent(id)}`);
}

export async function updateUser(
  id: string,
  payload: { full_name?: string; phone?: string; preferred_language?: string },
): Promise<ApiResult<AuthUserRecord>> {
  return requestApi<AuthUserRecord>(`/users/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ──── Advocate Directory ────

export type AdvocateProfile = {
  user_id: string;
  bar_council_id: string;
  registration_number: string | null;
  photo_url: string | null;
  bio: string | null;
  years_of_experience: number | null;
  languages: string[];
  specializations: string[];
  jurisdictions: AdvocateJurisdiction[];
  verification_status: "pending" | "verified" | "rejected";
  verified_at: string | null;
  rejection_reason: string | null;
  ratings_avg: number | null;
  ratings_count: number;
  consultation_fee_min_inr: number | null;
  consultation_fee_max_inr: number | null;
  created_at: string;
  updated_at: string;
};

export type AdvocateDirectoryItem = {
  id: string;
  full_name: string | null;
  email: string;
  phone: string | null;
  profile: AdvocateProfile;
};

export type AdvocatesListData = {
  total: number;
  items: AdvocateDirectoryItem[];
};

export interface AiChatRequest {
  message: string;
  context?: "navigation" | "legal_term" | "case_help";
}

export interface AiChatResponse {
  reply: string;
  model: string;
}

export async function postAiChat(payload: AiChatRequest): Promise<ApiResult<AiChatResponse>> {
  return apiPostJson<AiChatRequest, AiChatResponse>("/ai/chat", payload);
}

export type AdvocateListParams = {
  q?: string;
  specialization?: string;
  jurisdiction_level?: string;
  jurisdiction_state?: string;
  language?: string;
  min_experience?: number;
  max_fee?: number;
  sort?: "ratings" | "experience" | "name";
  limit?: number;
  offset?: number;
};

export type AdvocateUpdateRequest = {
  bio?: string;
  years_of_experience?: number;
  languages?: string[];
  specializations?: string[];
  jurisdictions?: AdvocateJurisdiction[];
  consultation_fee_min_inr?: number;
  consultation_fee_max_inr?: number;
  availability?: Record<string, unknown>;
  contact_preferences?: Record<string, unknown>;
};

export async function listAdvocatesDirectory(
  params?: AdvocateListParams,
): Promise<ApiResult<AdvocatesListData>> {
  const query = new URLSearchParams();
  if (params?.q) query.set("q", params.q);
  if (params?.specialization) query.set("specialization", params.specialization);
  if (params?.jurisdiction_level) query.set("jurisdiction_level", params.jurisdiction_level);
  if (params?.jurisdiction_state) query.set("jurisdiction_state", params.jurisdiction_state);
  if (params?.language) query.set("language", params.language);
  if (params?.min_experience !== undefined) query.set("min_experience", String(params.min_experience));
  if (params?.max_fee !== undefined) query.set("max_fee", String(params.max_fee));
  if (params?.sort) query.set("sort", params.sort);
  if (params?.limit !== undefined) query.set("limit", String(params.limit));
  if (params?.offset !== undefined) query.set("offset", String(params.offset));
  const qs = query.toString();
  return apiGet<AdvocatesListData>(`/advocates${qs ? `?${qs}` : ""}`);
}

export async function getAdvocate(id: string): Promise<ApiResult<AdvocateDirectoryItem>> {
  return apiGet<AdvocateDirectoryItem>(`/advocates/${encodeURIComponent(id)}`);
}

export async function updateAdvocateMe(
  payload: AdvocateUpdateRequest,
): Promise<ApiResult<AdvocateDirectoryItem>> {
  return requestApi<AdvocateDirectoryItem>("/advocates/me", {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function verifyAdvocate(id: string): Promise<ApiResult<AdvocateDirectoryItem>> {
  return apiPostJson<Record<string, never>, AdvocateDirectoryItem>(
    `/advocates/${encodeURIComponent(id)}/verify`,
    {},
  );
}

export async function rejectAdvocate(
  id: string,
  reason: string,
): Promise<ApiResult<AdvocateDirectoryItem>> {
  return apiPostJson<{ reason: string }, AdvocateDirectoryItem>(
    `/advocates/${encodeURIComponent(id)}/reject`,
    { reason },
  );
}

export async function listPendingAdvocates(): Promise<ApiResult<AdvocatesListData>> {
  return apiGet<AdvocatesListData>("/advocates/pending");
}
