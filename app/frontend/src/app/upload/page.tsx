"use client";

import { ChangeEvent, FormEvent, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  CheckCircle2,
  Cpu,
  FileSearch,
  FileText,
  Globe,
  Loader2,
  Search,
  Sparkles,
  UploadCloud,
  XCircle,
} from "lucide-react";

import { PageHeader } from "@/components/app/page-header";
import { InfoHint } from "@/components/info-hint";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  downloadDocument,
  getDocument,
  intakeIndianECourtsDocument,
  lookupIndianECourtsIntake,
  startCaseIntake,
  uploadDocument,
  type IndianECourtsIntakeEnvelope,
} from "@/lib/api/client";
import { cn } from "@/lib/utils";

type UploadStage = "idle" | "uploading" | "workflow" | "success" | "error";
type SupportedLanguage = "en" | "hi" | "ta" | "te" | "kn" | "ml" | "mr";

const languageOptions: Array<{ value: SupportedLanguage; label: string }> = [
  { value: "en", label: "English" },
  { value: "hi", label: "Hindi" },
  { value: "ta", label: "Tamil" },
  { value: "te", label: "Telugu" },
  { value: "kn", label: "Kannada" },
  { value: "ml", label: "Malayalam" },
  { value: "mr", label: "Marathi" },
];

type IndianECourtsMetadataRecord = {
  source_system?: string;
  ccms?: Partial<IndianECourtsIntakeEnvelope["ccms"]> | null;
  cis?: Partial<NonNullable<IndianECourtsIntakeEnvelope["cis"]>> | null;
  additional_metadata?: Record<string, unknown> | null;
};

const AI_MODES = [
  { id: "backend_default", label: "Backend default", desc: "Configured provider" },
  { id: "groq", label: "Groq", desc: "Free, fast" },
  { id: "openai", label: "OpenAI", desc: "High accuracy" },
  { id: "anthropic", label: "Anthropic", desc: "Claude models" },
  { id: "gemini", label: "Gemini", desc: "Google models" },
];

const STEPS: Array<{ id: 1 | 2 | 3 | 4; label: string; description: string }> = [
  { id: 1, label: "Pick source", description: "Upload file or fetch eCourts" },
  { id: 2, label: "Add metadata", description: "Case details and AI mode" },
  { id: 3, label: "Run extraction", description: "Pipeline processes the PDF" },
  { id: 4, label: "Open workspace", description: "Review in case workbench" },
];

function toText(value: unknown): string {
  return typeof value === "string" ? value : "";
}
function toCommaSeparatedText(value: unknown): string {
  if (!Array.isArray(value)) return "";
  return value
    .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    .join(", ");
}
function setFieldValue(form: HTMLFormElement, fieldName: string, value: string): void {
  const element = form.elements.namedItem(fieldName);
  if (
    element instanceof HTMLInputElement ||
    element instanceof HTMLSelectElement ||
    element instanceof HTMLTextAreaElement
  ) {
    element.value = value;
  }
}
function setFileValue(form: HTMLFormElement, file: File): void {
  const element = form.elements.namedItem("judgment");
  if (!(element instanceof HTMLInputElement) || element.type !== "file") return;
  const dataTransfer = new DataTransfer();
  dataTransfer.items.add(file);
  element.files = dataTransfer.files;
}
function decodeBase64ToBytes(value: string): ArrayBuffer {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}
function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const idx = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / Math.pow(1024, idx)).toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}
function applyIndianECourtsEnvelopeToForm(
  form: HTMLFormElement,
  envelope: IndianECourtsIntakeEnvelope,
): void {
  const ccms = envelope.ccms;
  const cis = envelope.cis;
  const additionalMetadata = envelope.additional_metadata;
  setFieldValue(form, "case_id", toText(cis?.case_id ?? additionalMetadata?.case_id));
  setFieldValue(form, "department", toText(additionalMetadata?.department));
  setFieldValue(form, "ccms_reference_id", toText(ccms.reference_id));
  setFieldValue(form, "ccms_delivery_timestamp", toText(ccms.delivery_timestamp));
  setFieldValue(form, "ccms_document_type", toText(ccms.document_type));
  setFieldValue(form, "ccms_source_url", toText(ccms.source_url));
  setFieldValue(form, "ccms_source_gateway", toText(ccms.source_gateway));
  setFieldValue(form, "ccms_receipt_id", toText(ccms.receipt_id));
  setFieldValue(form, "cis_case_id", toText(cis?.case_id));
  setFieldValue(form, "cis_court_name", toText(cis?.court_name));
  setFieldValue(form, "cis_court_code", toText(cis?.court_code));
  setFieldValue(form, "cis_order_date", toText(cis?.order_date));
  setFieldValue(form, "cis_bench", toText(cis?.bench));
  setFieldValue(form, "cis_parties", toCommaSeparatedText(cis?.parties));
  setFieldValue(form, "cis_petitioners", toCommaSeparatedText(cis?.petitioners));
  setFieldValue(form, "cis_respondents", toCommaSeparatedText(cis?.respondents));
  setFieldValue(form, "cis_case_type", toText(cis?.case_type));
  setFieldValue(form, "cis_filing_number", toText(cis?.filing_number));
  setFieldValue(form, "cis_diary_number", toText(cis?.diary_number));
  setFieldValue(form, "cis_judge_names", toCommaSeparatedText(cis?.judge_names));
  setFieldValue(form, "cis_hearing_stage", toText(cis?.hearing_stage));
  setFieldValue(form, "cis_state", toText(cis?.state));
  setFieldValue(form, "cis_district", toText(cis?.district));
  setFieldValue(form, "cis_department_tags", toCommaSeparatedText(cis?.department_tags));
}

const STAGE_VARIANT: Record<UploadStage, "muted" | "warn" | "good" | "destructive" | "accent"> = {
  idle: "muted",
  uploading: "accent",
  workflow: "warn",
  success: "good",
  error: "destructive",
};

const STAGE_PROGRESS: Record<UploadStage, number> = {
  idle: 0,
  uploading: 35,
  workflow: 70,
  success: 100,
  error: 100,
};

const STAGE_TO_STEP: Record<UploadStage, 1 | 2 | 3 | 4> = {
  idle: 1,
  uploading: 3,
  workflow: 3,
  success: 4,
  error: 3,
};

export default function UploadPage() {
  const router = useRouter();
  const formRef = useRef<HTMLFormElement | null>(null);
  const [stage, setStage] = useState<UploadStage>("idle");
  const [statusText, setStatusText] = useState("Pick a judgment file to start extraction.");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [duplicateExistingId, setDuplicateExistingId] = useState<string | null>(null);
  const [intakeSource, setIntakeSource] = useState<"upload" | "indian_ecourts">("upload");
  const [sourceLanguage, setSourceLanguage] = useState<string>("auto");
  const [onlineLookupId, setOnlineLookupId] = useState("");
  const [onlineLookupStatus, setOnlineLookupStatus] = useState<string | null>(null);
  const [onlineLookupError, setOnlineLookupError] = useState<string | null>(null);
  const [onlineLookupLoading, setOnlineLookupLoading] = useState(false);
  const [documentLookupId, setDocumentLookupId] = useState("");
  const [documentLookupStatus, setDocumentLookupStatus] = useState<string | null>(null);
  const [documentLookupError, setDocumentLookupError] = useState<string | null>(null);
  const [documentLookupLoading, setDocumentLookupLoading] = useState(false);
  const [selectedAiMode, setSelectedAiMode] = useState<string>("backend_default");
  const [selectedFileMeta, setSelectedFileMeta] = useState<{ name: string; size: number } | null>(
    null,
  );

  const stageLabel = useMemo(() => {
    return {
      uploading: "Uploading",
      workflow: "Workflow",
      success: "Completed",
      error: "Error",
      idle: "Ready",
    }[stage];
  }, [stage]);

  const activeStep = STAGE_TO_STEP[stage];

  function handleFileChange(event: ChangeEvent<HTMLInputElement>): void {
    const file = event.target.files?.[0];
    setSelectedFileMeta(file ? { name: file.name, size: file.size } : null);
  }

  async function handleOnlineIndianECourtsLookup(): Promise<void> {
    const identifier = onlineLookupId.trim();
    if (!identifier) {
      setOnlineLookupError("Enter a case identifier to fetch online.");
      setOnlineLookupStatus(null);
      return;
    }
    const form = formRef.current;
    if (!form) {
      setOnlineLookupError("The intake form is not ready yet.");
      setOnlineLookupStatus(null);
      return;
    }
    setOnlineLookupError(null);
    setOnlineLookupStatus("Fetching case details from Indian eCourts source…");
    setOnlineLookupLoading(true);
    const lookupResult = await lookupIndianECourtsIntake(identifier);
    if (!lookupResult.ok) {
      setOnlineLookupError(lookupResult.error.message);
      setOnlineLookupStatus(null);
      setOnlineLookupLoading(false);
      return;
    }
    const payload = lookupResult.data;
    setIntakeSource("indian_ecourts");
    setTimeout(() => {
      applyIndianECourtsEnvelopeToForm(form, payload.envelope);
      try {
        const fileBytes = decodeBase64ToBytes(payload.file_content_base64);
        const file = new File([fileBytes], payload.source_file_name, {
          type: payload.source_file_type || "application/pdf",
        });
        setFileValue(form, file);
        setSelectedFileMeta({ name: file.name, size: file.size });
        setOnlineLookupStatus(
          `Fetched ${payload.source_file_name} and prefilled the full CCMS/CIS form from ${payload.resolved_source_url}.`,
        );
      } catch {
        setOnlineLookupStatus(
          "Case metadata was fetched and prefilled, but the PDF file could not be restored automatically.",
        );
        setOnlineLookupError("Could not decode the fetched PDF payload.");
      } finally {
        setOnlineLookupLoading(false);
      }
    }, 0);
  }

  async function handleLoadDocumentById(): Promise<void> {
    const lookupId = documentLookupId.trim();
    if (!lookupId) {
      setDocumentLookupError("Enter a document id to load.");
      setDocumentLookupStatus(null);
      return;
    }
    const form = formRef.current;
    if (!form) {
      setDocumentLookupError("The intake form is not ready yet.");
      return;
    }
    setDocumentLookupError(null);
    setDocumentLookupStatus("Loading saved document…");
    setDocumentLookupLoading(true);
    const lookupResult = await getDocument(lookupId);
    if (!lookupResult.ok) {
      setDocumentLookupError(lookupResult.error.message);
      setDocumentLookupStatus(null);
      setDocumentLookupLoading(false);
      return;
    }
    const documentRecord = lookupResult.data;
    const metadata = documentRecord.metadata as IndianECourtsMetadataRecord | null;
    const ccms = metadata?.ccms ?? null;
    const cis = metadata?.cis ?? null;
    const additionalMetadata = metadata?.additional_metadata ?? null;
    const hasIndianEcourtsData =
      metadata?.source_system === "indian_ecourts_service" || Boolean(ccms || cis);
    setIntakeSource(hasIndianEcourtsData ? "indian_ecourts" : "upload");
    setTimeout(() => {
      setFieldValue(form, "case_id", toText(cis?.case_id ?? additionalMetadata?.case_id));
      setFieldValue(form, "department", toText(additionalMetadata?.department));
      setFieldValue(form, "ccms_reference_id", toText(ccms?.reference_id));
      setFieldValue(form, "ccms_delivery_timestamp", toText(ccms?.delivery_timestamp));
      setFieldValue(form, "ccms_document_type", toText(ccms?.document_type));
      setFieldValue(form, "ccms_source_url", toText(ccms?.source_url));
      setFieldValue(form, "ccms_source_gateway", toText(ccms?.source_gateway));
      setFieldValue(form, "ccms_receipt_id", toText(ccms?.receipt_id));
      setFieldValue(form, "cis_case_id", toText(cis?.case_id));
      setFieldValue(form, "cis_court_name", toText(cis?.court_name));
      setFieldValue(form, "cis_court_code", toText(cis?.court_code));
      setFieldValue(form, "cis_order_date", toText(cis?.order_date));
      setFieldValue(form, "cis_bench", toText(cis?.bench));
      setFieldValue(form, "cis_parties", toCommaSeparatedText(cis?.parties));
      setFieldValue(form, "cis_petitioners", toCommaSeparatedText(cis?.petitioners));
      setFieldValue(form, "cis_respondents", toCommaSeparatedText(cis?.respondents));
      setFieldValue(form, "cis_case_type", toText(cis?.case_type));
      setFieldValue(form, "cis_filing_number", toText(cis?.filing_number));
      setFieldValue(form, "cis_diary_number", toText(cis?.diary_number));
      setFieldValue(form, "cis_judge_names", toCommaSeparatedText(cis?.judge_names));
      setFieldValue(form, "cis_hearing_stage", toText(cis?.hearing_stage));
      setFieldValue(form, "cis_state", toText(cis?.state));
      setFieldValue(form, "cis_district", toText(cis?.district));
      setFieldValue(form, "cis_department_tags", toCommaSeparatedText(cis?.department_tags));
      try {
        downloadDocument(documentRecord.id)
          .then((downloadResult) => {
            const fileName =
              downloadResult.fileName ?? documentRecord.source_file_name ?? "document.pdf";
            const fileType =
              downloadResult.contentType ?? documentRecord.source_file_type ?? "application/pdf";
            const file = new File([downloadResult.blob], fileName, { type: fileType });
            setFileValue(form, file);
            setSelectedFileMeta({ name: file.name, size: file.size });
            setDocumentLookupStatus(
              `Loaded ${documentRecord.id} and restored ${fileName}. The form is prefilled and ready.`,
            );
          })
          .catch((error) => {
            setDocumentLookupStatus(
              `Loaded ${documentRecord.id}. The metadata is prefilled, but the PDF could not be restored automatically.`,
            );
            setDocumentLookupError(
              error instanceof Error ? error.message : "Document file load failed",
            );
          })
          .finally(() => {
            setDocumentLookupLoading(false);
          });
      } catch (error) {
        setDocumentLookupError(
          error instanceof Error ? error.message : "Document file load failed",
        );
        setDocumentLookupLoading(false);
      }
    }, 0);
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setErrorText(null);
    setDuplicateExistingId(null);

    const form = event.currentTarget;
    const formData = new FormData(form);
    const file = formData.get("judgment") as File | null;

    if (!file || file.size <= 0) {
      setStage("error");
      setErrorText("Please select a non-empty judgment file.");
      return;
    }

    const caseId = String(formData.get("case_id") ?? "").trim();
    const department = String(formData.get("department") ?? "").trim();
    const usingIndianECourts = intakeSource === "indian_ecourts";
    const selectedSourceLanguage = sourceLanguage.trim();
    const ccmsReferenceId = String(formData.get("ccms_reference_id") ?? "").trim();
    const ccmsDeliveryTimestamp = String(formData.get("ccms_delivery_timestamp") ?? "").trim();
    const ccmsDocumentType = String(formData.get("ccms_document_type") ?? "").trim();
    const ccmsSourceUrl = String(formData.get("ccms_source_url") ?? "").trim();
    const ccmsSourceGateway = String(formData.get("ccms_source_gateway") ?? "").trim();
    const ccmsReceiptId = String(formData.get("ccms_receipt_id") ?? "").trim();
    const cisCaseId = String(formData.get("cis_case_id") ?? "").trim();
    const cisCourtName = String(formData.get("cis_court_name") ?? "").trim();
    const cisCourtCode = String(formData.get("cis_court_code") ?? "").trim();
    const cisOrderDate = String(formData.get("cis_order_date") ?? "").trim();
    const cisBench = String(formData.get("cis_bench") ?? "").trim();
    const cisParties = String(formData.get("cis_parties") ?? "").trim();
    const cisPetitioners = String(formData.get("cis_petitioners") ?? "").trim();
    const cisRespondents = String(formData.get("cis_respondents") ?? "").trim();
    const cisCaseType = String(formData.get("cis_case_type") ?? "").trim();
    const cisFilingNumber = String(formData.get("cis_filing_number") ?? "").trim();
    const cisDiaryNumber = String(formData.get("cis_diary_number") ?? "").trim();
    const cisJudgeNames = String(formData.get("cis_judge_names") ?? "").trim();
    const cisHearingStage = String(formData.get("cis_hearing_stage") ?? "").trim();
    const cisState = String(formData.get("cis_state") ?? "").trim();
    const cisDistrict = String(formData.get("cis_district") ?? "").trim();
    const cisDepartmentTags = String(formData.get("cis_department_tags") ?? "").trim();
    const aiMode = selectedAiMode;
    const aiModel = String(formData.get("ai_model") ?? "").trim();
    const selectedProvider =
      aiMode === "openai" || aiMode === "anthropic" || aiMode === "gemini" || aiMode === "groq"
        ? aiMode
        : undefined;

    setStage("uploading");
    setStatusText(
      usingIndianECourts
        ? "Ingesting judgment via Indian eCourts CCMS/CIS adapter…"
        : "Uploading judgment document…",
    );

    let uploadResult;
    if (usingIndianECourts) {
      if (!ccmsReferenceId && !cisCaseId) {
        setStage("error");
        setErrorText("Provide CCMS reference id or CIS case id for Indian eCourts intake.");
        return;
      }
      const buildStringArray = (value: string): string[] | undefined => {
        const list = value
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
        return list.length > 0 ? list : undefined;
      };
      const envelope: IndianECourtsIntakeEnvelope = {
        ccms: {
          reference_id: ccmsReferenceId || undefined,
          delivery_timestamp: ccmsDeliveryTimestamp || undefined,
          document_type: ccmsDocumentType || undefined,
          source_url: ccmsSourceUrl || undefined,
          source_gateway: ccmsSourceGateway || undefined,
          receipt_id: ccmsReceiptId || undefined,
        },
        source_file_name: file.name,
        source_file_type: file.type || "application/pdf",
        additional_metadata: {
          source: "upload-page",
          channel: "indian-ecourts-ui",
          case_id: caseId || undefined,
          department: department || undefined,
        },
      };
      const cisPayload: IndianECourtsIntakeEnvelope["cis"] = {
        case_id: cisCaseId || undefined,
        court_name: cisCourtName || undefined,
        court_code: cisCourtCode || undefined,
        order_date: cisOrderDate || undefined,
        bench: cisBench || undefined,
        parties: buildStringArray(cisParties),
        petitioners: buildStringArray(cisPetitioners),
        respondents: buildStringArray(cisRespondents),
        case_type: cisCaseType || undefined,
        filing_number: cisFilingNumber || undefined,
        diary_number: cisDiaryNumber || undefined,
        judge_names: buildStringArray(cisJudgeNames),
        hearing_stage: cisHearingStage || undefined,
        state: cisState || undefined,
        district: cisDistrict || undefined,
        department_tags: buildStringArray(cisDepartmentTags),
      };
      const hasCisData = Object.values(cisPayload).some((value) => value !== undefined);
      if (hasCisData) envelope.cis = cisPayload;

      const ecourtsFormData = new FormData();
      ecourtsFormData.append("file", file);
      ecourtsFormData.append("envelope", JSON.stringify(envelope));
      if (selectedSourceLanguage && selectedSourceLanguage !== "auto") {
        ecourtsFormData.append("source_language", selectedSourceLanguage);
      }
      uploadResult = await intakeIndianECourtsDocument(ecourtsFormData);
    } else {
      const uploadFormData = new FormData();
      uploadFormData.append("file", file);
      uploadFormData.append(
        "metadata",
        JSON.stringify({
          case_id: caseId || undefined,
          department: department || undefined,
          source: "upload-page",
        }),
      );
      if (selectedSourceLanguage && selectedSourceLanguage !== "auto") {
        uploadFormData.append("source_language", selectedSourceLanguage);
      }
      uploadResult = await uploadDocument(uploadFormData);
    }

    if (!uploadResult.ok) {
      setStage("error");
      setErrorText(uploadResult.error.message);
      if (uploadResult.error.code === "duplicate_document") {
        const existingId =
          (uploadResult.error.details?.existing_document_id as string | undefined) ?? null;
        setDuplicateExistingId(existingId);
        setStatusText("This file is already in OrderFlow.");
      } else {
        setStatusText("Upload failed.");
      }
      return;
    }

    if (typeof window !== "undefined") {
      window.localStorage.setItem("orderflow:last_uploaded_document_id", uploadResult.data.id);
      window.localStorage.setItem("orderflow:last_uploaded_document_label", file.name);
      window.localStorage.setItem("orderflow:current_document_id", uploadResult.data.id);
    }

    setStage("workflow");
    setStatusText("Starting page extraction workflow...");
    const intakeResult = await startCaseIntake(uploadResult.data.id, {
      ...(selectedProvider ? { ai_provider: selectedProvider } : {}),
      ...(aiModel ? { ai_model: aiModel } : {}),
    });

    if (!intakeResult.ok) {
      setStage("error");
      setErrorText(intakeResult.error.message);
      setStatusText("Intake workflow start failed.");
      return;
    }

    setStage("success");
    setStatusText("Page extraction workflow started. Opening the case workspace...");

    if (typeof window !== "undefined") {
      window.localStorage.setItem("orderflow:last_uploaded_document_id", uploadResult.data.id);
      window.localStorage.setItem("orderflow:last_uploaded_document_label", file.name);
      window.localStorage.setItem("orderflow:current_document_id", uploadResult.data.id);
      window.localStorage.removeItem("orderflow:last_uploaded_ai_reason");
      window.localStorage.removeItem("orderflow:last_uploaded_workflow_warning");
    }

    router.push(`/case/${encodeURIComponent(uploadResult.data.id)}`);
  }

  const submitting = stage === "uploading" || stage === "workflow";

  return (
    <div className="flex flex-col gap-6 py-6">
      <PageHeader
        eyebrow={
          <span className="flex items-center gap-1.5">
            <UploadCloud className="h-3.5 w-3.5" />
            Add new case <InfoHint glossaryKey="intake" />
          </span>
        }
        title="Upload a judgment to start the workflow"
        subtitle="Pick a file or fetch from Indian eCourts. Page extraction starts automatically in the case workflow."
      />

      {/* Stepper */}
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Intake progress">
        {STEPS.map((step) => {
          const isActive = step.id === activeStep;
          const isComplete = step.id < activeStep || stage === "success";
          return (
            <li
              key={step.id}
              className={cn(
                "relative flex items-start gap-3 rounded-lg border p-3 transition-colors",
                isActive
                  ? "border-primary/40 bg-primary/10"
                  : isComplete
                    ? "border-good/40 bg-good/10"
                    : "border-border bg-card/60",
              )}
            >
              <span
                className={cn(
                  "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : isComplete
                      ? "bg-good text-good-foreground"
                      : "bg-muted text-muted-foreground",
                )}
              >
                {isComplete && step.id < activeStep ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : (
                  step.id
                )}
              </span>
              <div className="flex flex-col">
                <span
                  className={cn(
                    "text-sm font-semibold leading-tight",
                    isActive ? "text-foreground" : "text-foreground/90",
                  )}
                >
                  {step.label}
                </span>
                <span className="text-xs text-muted-foreground">{step.description}</span>
              </div>
            </li>
          );
        })}
      </ol>

      {/* Top: lookup helpers */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="card-interactive">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <span className="icon-chip">
                <Globe className="h-4 w-4" />
              </span>
              Indian eCourts fetch
            </CardTitle>
            <CardDescription>
              One Delhi High Court identifier — auto-fetch the PDF and prefill CCMS/CIS.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Label htmlFor="online_lookup_id">Case id or judgment token/URL</Label>
            <Input
              id="online_lookup_id"
              placeholder="W.P.(C) 8524/2025 or token / URL"
              value={onlineLookupId}
              onChange={(e) => setOnlineLookupId(e.target.value)}
            />
            <Button
              type="button"
              onClick={() => void handleOnlineIndianECourtsLookup()}
              disabled={!onlineLookupId.trim() || onlineLookupLoading}
            >
              {onlineLookupLoading ? <Loader2 className="animate-spin" /> : <Search />}
              {onlineLookupLoading ? "Fetching…" : "Fetch and prefill form"}
            </Button>
            {onlineLookupLoading ? (
              <div className="flex flex-col gap-2 rounded-md border border-border bg-muted/40 p-3">
                <Skeleton className="h-3 w-3/4" />
                <Skeleton className="h-3 w-2/3" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            ) : null}
            {onlineLookupStatus && !onlineLookupLoading ? (
              <Alert>
                <AlertDescription>{onlineLookupStatus}</AlertDescription>
              </Alert>
            ) : null}
            {onlineLookupError ? (
              <Alert variant="destructive">
                <AlertDescription>{onlineLookupError}</AlertDescription>
              </Alert>
            ) : null}
          </CardContent>
        </Card>

        <Card className="card-interactive">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <span className="icon-chip icon-chip-accent">
                <FileSearch className="h-4 w-4" />
              </span>
              Reload saved document
            </CardTitle>
            <CardDescription>
              Restore a previously uploaded PDF and its CCMS/CIS metadata.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Label htmlFor="document_lookup_id">Document id</Label>
            <Input
              id="document_lookup_id"
              placeholder="UUID of a saved document"
              value={documentLookupId}
              onChange={(e) => setDocumentLookupId(e.target.value)}
            />
            <Button
              type="button"
              variant="outline"
              onClick={() => void handleLoadDocumentById()}
              disabled={!documentLookupId.trim() || documentLookupLoading}
            >
              {documentLookupLoading ? <Loader2 className="animate-spin" /> : <FileSearch />}
              {documentLookupLoading ? "Loading…" : "Load and prefill form"}
            </Button>
            {documentLookupLoading ? (
              <div className="flex flex-col gap-2 rounded-md border border-border bg-muted/40 p-3">
                <Skeleton className="h-3 w-3/4" />
                <Skeleton className="h-3 w-2/3" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            ) : null}
            {documentLookupStatus && !documentLookupLoading ? (
              <Alert>
                <AlertDescription>{documentLookupStatus}</AlertDescription>
              </Alert>
            ) : null}
            {documentLookupError ? (
              <Alert variant="destructive">
                <AlertDescription>{documentLookupError}</AlertDescription>
              </Alert>
            ) : null}
          </CardContent>
        </Card>
      </div>

      {/* Intake form */}
      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle className="flex items-center gap-2 text-base">
            <span className="icon-chip">
              <UploadCloud className="h-4 w-4" />
            </span>
            Intake form
          </CardTitle>
          <CardDescription>
            All fields except the file are optional. Switch to Indian eCourts to enable CCMS/CIS
            metadata.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-6">
          <form ref={formRef} onSubmit={onSubmit} className="flex flex-col gap-6">
            {/* File dropzone */}
            <div className="flex flex-col gap-2">
              <Label htmlFor="judgment" className="text-sm font-medium">
                Judgment file
              </Label>
              <label
                htmlFor="judgment"
                className="dropzone cursor-pointer"
                data-active={selectedFileMeta ? "true" : "false"}
              >
                <input
                  id="judgment"
                  name="judgment"
                  type="file"
                  required
                  accept="application/pdf"
                  onChange={handleFileChange}
                  className="sr-only"
                />
                {selectedFileMeta ? (
                  <div className="flex w-full max-w-md items-center gap-3 rounded-md border border-primary/30 bg-primary/10 p-3 text-left">
                    <span className="icon-chip">
                      <FileText className="h-4 w-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">
                        {selectedFileMeta.name}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {formatBytes(selectedFileMeta.size)} · click to replace
                      </p>
                    </div>
                    <CheckCircle2 className="h-4 w-4 text-good" />
                  </div>
                ) : (
                  <>
                    <span className="icon-chip">
                      <UploadCloud className="h-5 w-5" />
                    </span>
                    <div className="flex flex-col gap-0.5">
                      <span className="text-sm font-medium text-foreground">
                        Click to choose a PDF
                      </span>
                      <span className="text-xs text-muted-foreground">
                        Single judgment, up to ~50 MB · application/pdf
                      </span>
                    </div>
                  </>
                )}
              </label>
            </div>

            {/* Source / case basics */}
            <div className="grid gap-4 md:grid-cols-2">
              <Field id="intake_source" label="Intake source">
                <Select
                  value={intakeSource}
                  onValueChange={(v) => {
                    if (v === "upload" || v === "indian_ecourts") setIntakeSource(v);
                  }}
                >
                  <SelectTrigger id="intake_source">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="upload">Manual upload</SelectItem>
                    <SelectItem value="indian_ecourts">Indian eCourts (CCMS/CIS)</SelectItem>
                  </SelectContent>
                </Select>
                <input type="hidden" name="intake_source" value={intakeSource} />
              </Field>
              <Field id="source_language" label="Source language">
                <Select value={sourceLanguage} onValueChange={setSourceLanguage}>
                  <SelectTrigger id="source_language">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Auto-detect</SelectItem>
                    {languageOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field id="case_id" label="Case id (optional)">
                <Input id="case_id" name="case_id" placeholder="CASE-2026-001" />
              </Field>
              <Field id="department" label="Department (optional)">
                <Input id="department" name="department" placeholder="District Administration" />
              </Field>
            </div>

            {intakeSource === "indian_ecourts" ? (
              <Card className="border-dashed bg-muted/20">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">CCMS / CIS metadata</CardTitle>
                  <CardDescription>
                    Either CCMS reference id or CIS case id is required for Indian eCourts intake.
                  </CardDescription>
                </CardHeader>
                <CardContent className="grid gap-3 md:grid-cols-2">
                  <Field id="ccms_reference_id" label="CCMS reference id">
                    <Input
                      id="ccms_reference_id"
                      name="ccms_reference_id"
                      placeholder="CCMS-REF-2026-001"
                    />
                  </Field>
                  <Field id="ccms_delivery_timestamp" label="CCMS delivery timestamp (ISO)">
                    <Input
                      id="ccms_delivery_timestamp"
                      name="ccms_delivery_timestamp"
                      placeholder="2026-04-24T10:15:00Z"
                    />
                  </Field>
                  <Field id="ccms_document_type" label="CCMS document type">
                    <Input
                      id="ccms_document_type"
                      name="ccms_document_type"
                      placeholder="final_order"
                    />
                  </Field>
                  <Field id="ccms_source_url" label="CCMS source URL">
                    <Input
                      id="ccms_source_url"
                      name="ccms_source_url"
                      placeholder="https://...pdf"
                    />
                  </Field>
                  <Field id="ccms_source_gateway" label="CCMS source gateway">
                    <Input
                      id="ccms_source_gateway"
                      name="ccms_source_gateway"
                      placeholder="indian-ecourts-service"
                    />
                  </Field>
                  <Field id="ccms_receipt_id" label="CCMS receipt id">
                    <Input
                      id="ccms_receipt_id"
                      name="ccms_receipt_id"
                      placeholder="CCMS-RECEIPT-001"
                    />
                  </Field>
                  <Field id="cis_case_id" label="CIS case id">
                    <Input id="cis_case_id" name="cis_case_id" placeholder="CIS-CASE-2026-981" />
                  </Field>
                  <Field id="cis_court_name" label="CIS court name">
                    <Input
                      id="cis_court_name"
                      name="cis_court_name"
                      placeholder="High Court of Karnataka"
                    />
                  </Field>
                  <Field id="cis_court_code" label="CIS court code">
                    <Input id="cis_court_code" name="cis_court_code" placeholder="KAHC01" />
                  </Field>
                  <Field id="cis_order_date" label="CIS order date">
                    <Input id="cis_order_date" name="cis_order_date" type="date" />
                  </Field>
                  <Field id="cis_bench" label="CIS bench">
                    <Input id="cis_bench" name="cis_bench" placeholder="Division Bench" />
                  </Field>
                  <Field id="cis_parties" label="CIS parties (comma separated)">
                    <Input id="cis_parties" name="cis_parties" placeholder="State, Petitioner" />
                  </Field>
                  <Field id="cis_petitioners" label="CIS petitioners">
                    <Input
                      id="cis_petitioners"
                      name="cis_petitioners"
                      placeholder="Petitioner 1, Petitioner 2"
                    />
                  </Field>
                  <Field id="cis_respondents" label="CIS respondents">
                    <Input
                      id="cis_respondents"
                      name="cis_respondents"
                      placeholder="Union of India, State"
                    />
                  </Field>
                  <Field id="cis_case_type" label="CIS case type">
                    <Input id="cis_case_type" name="cis_case_type" placeholder="Writ Petition" />
                  </Field>
                  <Field id="cis_filing_number" label="CIS filing number">
                    <Input
                      id="cis_filing_number"
                      name="cis_filing_number"
                      placeholder="Filing No. 1234/2025"
                    />
                  </Field>
                  <Field id="cis_diary_number" label="CIS diary number">
                    <Input
                      id="cis_diary_number"
                      name="cis_diary_number"
                      placeholder="Diary No. 9876/2025"
                    />
                  </Field>
                  <Field id="cis_judge_names" label="CIS judge names">
                    <Input
                      id="cis_judge_names"
                      name="cis_judge_names"
                      placeholder="Justice A, Justice B"
                    />
                  </Field>
                  <Field id="cis_hearing_stage" label="CIS hearing stage">
                    <Input
                      id="cis_hearing_stage"
                      name="cis_hearing_stage"
                      placeholder="Judgment pronounced"
                    />
                  </Field>
                  <Field id="cis_state" label="CIS state">
                    <Input id="cis_state" name="cis_state" placeholder="Karnataka" />
                  </Field>
                  <Field id="cis_district" label="CIS district">
                    <Input id="cis_district" name="cis_district" placeholder="Bengaluru" />
                  </Field>
                  <Field id="cis_department_tags" label="CIS department tags">
                    <Input
                      id="cis_department_tags"
                      name="cis_department_tags"
                      placeholder="Revenue, Urban Development"
                    />
                  </Field>
                </CardContent>
              </Card>
            ) : null}

            {/* AI mode */}
            <div className="flex flex-col gap-3 rounded-lg border border-border bg-muted/20 p-4">
              <div className="flex items-center gap-2">
                <span className="icon-chip icon-chip-accent">
                  <Sparkles className="h-4 w-4" />
                </span>
                <div className="flex flex-col">
                  <Label className="flex items-center gap-2 text-sm font-semibold">
                    <Cpu className="h-3.5 w-3.5" /> AI extraction mode
                  </Label>
                  <span className="text-xs text-muted-foreground">
                    Choose the model used to read and structure the judgment.
                  </span>
                </div>
              </div>
              <input type="hidden" name="ai_mode" value={selectedAiMode} />
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {AI_MODES.map((mode) => {
                  const active = selectedAiMode === mode.id;
                  return (
                    <button
                      key={mode.id}
                      type="button"
                      onClick={() => setSelectedAiMode(mode.id)}
                      className={cn(
                        "flex flex-col items-start gap-1 rounded-md border p-3 text-left transition-all",
                        active
                          ? "border-primary/60 bg-primary/15 ring-1 ring-primary/30"
                          : "border-border bg-card hover:border-primary/30 hover:bg-secondary/40",
                      )}
                      aria-pressed={active}
                    >
                      <span
                        className={cn(
                          "text-sm font-semibold",
                          active ? "text-primary" : "text-foreground",
                        )}
                      >
                        {mode.label}
                      </span>
                      <span className="text-xs text-muted-foreground">{mode.desc}</span>
                    </button>
                  );
                })}
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <Field id="ai_model" label="AI model override (optional)">
                  <Input id="ai_model" name="ai_model" placeholder="gemini-2.0-flash" />
                </Field>
              </div>
            </div>

            <div className="flex justify-end">
              <Button type="submit" size="lg" disabled={submitting}>
                {submitting ? <Loader2 className="animate-spin" /> : <UploadCloud />}
                {submitting ? "Working..." : "Ingest and start page extraction"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Pipeline status */}
      <Card
        className={cn(
          stage === "error" && "border-destructive/40",
          stage === "success" && "border-good/40",
          (stage === "uploading" || stage === "workflow") && "border-primary/40",
        )}
      >
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span
              className={cn(
                "icon-chip",
                stage === "error" && "icon-chip-destructive",
                stage === "success" && "icon-chip-good",
                stage === "workflow" && "icon-chip-warn",
                stage === "idle" && "border-border bg-muted/40 text-muted-foreground",
              )}
            >
              {stage === "error" ? (
                <XCircle className="h-4 w-4" />
              ) : stage === "success" ? (
                <CheckCircle2 className="h-4 w-4" />
              ) : submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
            </span>
            <div>
              <CardTitle className="text-base">Pipeline status</CardTitle>
              <CardDescription>{statusText}</CardDescription>
            </div>
          </div>
          <Badge variant={STAGE_VARIANT[stage]}>{stageLabel}</Badge>
        </CardHeader>
        <CardContent className="flex flex-col gap-4 pt-0">
          <Progress value={STAGE_PROGRESS[stage]} className="h-1.5" />
          {submitting ? (
            <div className="flex flex-col gap-2 rounded-md border border-border bg-muted/20 p-3">
              <Skeleton className="h-3 w-3/5" />
              <Skeleton className="h-3 w-2/5" />
              <Skeleton className="h-3 w-4/5" />
            </div>
          ) : null}
          {errorText ? (
            <Alert variant="destructive">
              <AlertTitle>Pipeline error</AlertTitle>
              <AlertDescription>{errorText}</AlertDescription>
            </Alert>
          ) : null}
          {duplicateExistingId ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                if (typeof window !== "undefined") {
                  window.localStorage.setItem("orderflow:current_document_id", duplicateExistingId);
                }
                router.push(`/case/${encodeURIComponent(duplicateExistingId)}`);
              }}
            >
              Open existing document
              <ArrowRight />
            </Button>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id} className="text-xs font-medium text-muted-foreground">
        {label}
      </Label>
      {children}
    </div>
  );
}
