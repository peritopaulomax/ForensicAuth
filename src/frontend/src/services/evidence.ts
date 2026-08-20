import api from "@/services/api";
import type {
  AudioTechnicalMetadata,
  Evidence,
  EvidenceDeletionPreview,
  EvidenceDeletionResult,
} from "@/types/api";

export async function listCaseEvidences(caseId: string): Promise<Evidence[]> {
  const response = await api.get<Evidence[]>(`/cases/${caseId}/evidences`);
  return response.data;
}

export async function listCaseAudioMetadata(caseId: string): Promise<AudioTechnicalMetadata[]> {
  const response = await api.get<{ items: AudioTechnicalMetadata[] }>(
    `/cases/${caseId}/audio-metadata`
  );
  return response.data.items;
}

export async function uploadEvidence(
  caseId: string,
  file: File,
  groupLabel: string,
  onProgress?: (percent: number) => void
): Promise<Evidence> {
  const formData = new FormData();
  formData.append("case_id", caseId);
  formData.append("group_label", groupLabel.trim());
  formData.append("file", file);

  const response = await api.post<Evidence>("/evidences/upload", formData, {
    // Nao forcar Content-Type: o browser define multipart com boundary.
    onUploadProgress: (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        onProgress(percent);
      }
    },
  });
  const expected = groupLabel.trim();
  const got =
    (typeof response.data.group_label === "string" && response.data.group_label.trim()) ||
    (typeof response.data.extra_metadata?.questioned_group_label === "string"
      ? String(response.data.extra_metadata.questioned_group_label).trim()
      : "");
  if (expected && got !== expected) {
    throw new Error(
      `O servidor nao gravou o rotulo "${expected}" (recebido: "${got || "Sem rotulo"}"). ` +
        "Reinicie a API (uvicorn) para carregar o codigo novo e tente de novo."
    );
  }
  return response.data;
}

export async function updateEvidenceGroupLabel(
  evidenceId: string,
  groupLabel: string
): Promise<Evidence> {
  const { data } = await api.patch<Evidence>(`/evidences/${evidenceId}/group-label`, {
    group_label: groupLabel.trim(),
  });
  return data;
}

export async function bulkUpdateEvidenceGroupLabel(
  caseId: string,
  evidenceIds: string[],
  groupLabel: string
): Promise<Evidence[]> {
  const { data } = await api.post<Evidence[]>(`/cases/${caseId}/evidences/group-label`, {
    evidence_ids: evidenceIds,
    group_label: groupLabel.trim(),
  });
  return data;
}

export async function getEvidenceDeletionPreview(
  caseId: string,
  evidenceIds: string[]
): Promise<EvidenceDeletionPreview> {
  const { data } = await api.post<EvidenceDeletionPreview>(
    `/cases/${caseId}/evidences/deletion-preview`,
    { evidence_ids: evidenceIds }
  );
  return data;
}

export async function deleteEvidences(
  caseId: string,
  evidenceIds: string[],
  includeDependentDerivatives: boolean
): Promise<EvidenceDeletionResult> {
  const { data } = await api.post<EvidenceDeletionResult>(`/cases/${caseId}/evidences/delete`, {
    evidence_ids: evidenceIds,
    include_dependent_derivatives: includeDependentDerivatives,
  });
  return data;
}

export interface ReferenceGroup {
  technique: string;
  group_label: string;
  display_label: string;
  files: Evidence[];
}

export interface GlobalReferenceGroup {
  reference_type: string;
  group_label: string;
  display_label: string;
  files: Evidence[];
}

export interface CaseReferencesResponse {
  groups: ReferenceGroup[];
  global_groups: GlobalReferenceGroup[];
}

export async function listCaseReferences(caseId: string): Promise<CaseReferencesResponse> {
  const response = await api.get<CaseReferencesResponse>(`/cases/${caseId}/references`);
  return response.data;
}

export async function uploadGlobalReference(
  caseId: string,
  file: File,
  groupLabel: string,
  referenceType: "imagem" | "video" | "audio" | "pdf",
  onProgress?: (percent: number) => void
): Promise<Evidence> {
  const formData = new FormData();
  formData.append("case_id", caseId);
  formData.append("group_label", groupLabel.trim());
  formData.append("reference_type", referenceType);
  formData.append("file", file);

  const response = await api.post<Evidence>("/evidences/global-reference-upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
    onUploadProgress: (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        onProgress(percent);
      }
    },
  });
  return response.data;
}

export async function uploadPdfStructureReference(
  caseId: string,
  file: File,
  groupLabel: string,
  onProgress?: (percent: number) => void
): Promise<Evidence> {
  const formData = new FormData();
  formData.append("case_id", caseId);
  formData.append("group_label", groupLabel.trim());
  formData.append("file", file);

  const response = await api.post<Evidence>("/evidences/pdf-structure-reference-upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
    onUploadProgress: (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        onProgress(percent);
      }
    },
  });
  return response.data;
}

export async function uploadJpegStructureReference(
  caseId: string,
  file: File,
  groupLabel: string,
  onProgress?: (percent: number) => void
): Promise<Evidence> {
  const formData = new FormData();
  formData.append("case_id", caseId);
  formData.append("group_label", groupLabel.trim());
  formData.append("file", file);

  const response = await api.post<Evidence>("/evidences/jpeg-structure-reference-upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
    onUploadProgress: (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        onProgress(percent);
      }
    },
  });
  return response.data;
}

export async function uploadIsomStructureReference(
  caseId: string,
  file: File,
  groupLabel: string,
  onProgress?: (percent: number) => void
): Promise<Evidence> {
  const formData = new FormData();
  formData.append("case_id", caseId);
  formData.append("group_label", groupLabel.trim());
  formData.append("file", file);

  const response = await api.post<Evidence>("/evidences/isom-structure-reference-upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
    onUploadProgress: (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        onProgress(percent);
      }
    },
  });
  return response.data;
}

export async function uploadPrnuReference(
  caseId: string,
  file: File,
  groupLabel: string,
  onProgress?: (percent: number) => void
): Promise<Evidence> {
  const formData = new FormData();
  formData.append("case_id", caseId);
  formData.append("group_label", groupLabel.trim());
  formData.append("file", file);

  const response = await api.post<Evidence>("/evidences/prnu-reference-upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
    onUploadProgress: (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        onProgress(percent);
      }
    },
  });
  return response.data;
}

export async function uploadReference(
  caseId: string,
  file: File,
  onProgress?: (percent: number) => void
): Promise<Evidence> {
  const formData = new FormData();
  formData.append("case_id", caseId);
  formData.append("file", file);

  const response = await api.post<Evidence>("/evidences/reference-upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
    onUploadProgress: (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        onProgress(percent);
      }
    },
  });
  return response.data;
}

export function getEvidenceFileUrl(evidenceId: string): string {
  return `/api/v1/evidences/${evidenceId}/file`;
}

export interface SaveDerivativeResult {
  evidence: Evidence;
  message: string;
}

type DerivativeSaveListener = (evidence: Evidence) => void;
const derivativeSaveListeners = new Set<DerivativeSaveListener>();

export function registerDerivativeSaveListener(listener: DerivativeSaveListener): () => void {
  derivativeSaveListeners.add(listener);
  return () => derivativeSaveListeners.delete(listener);
}

function notifyDerivativeSaved(evidence: Evidence) {
  derivativeSaveListeners.forEach((listener) => listener(evidence));
}

export async function listCaseDerivatives(caseId: string): Promise<Evidence[]> {
  const response = await api.get<Evidence[]>(`/cases/${caseId}/derivatives`);
  return response.data;
}

export async function downloadEvidenceFile(evidenceId: string, filename: string): Promise<void> {
  const response = await api.get(`/evidences/${evidenceId}/file`, { responseType: "blob" });
  const url = URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function saveDerivative(params: {
  job_id: string;
  artifact_filename?: string;
  label?: string;
  effective_parameters?: Record<string, unknown>;
}): Promise<SaveDerivativeResult> {
  const response = await api.post<SaveDerivativeResult>("/evidences/derivatives", {
    job_id: params.job_id,
    artifact_filename: params.artifact_filename ?? "heatmap.png",
    label: params.label,
    effective_parameters: params.effective_parameters,
  });
  notifyDerivativeSaved(response.data.evidence);
  return response.data;
}

export interface LineageNode {
  evidence_id: string;
  original_filename: string;
  file_type: string;
  sha256: string;
  is_derived: boolean;
  is_synthetic?: boolean | null;
  synthetic_kind?: string | null;
  technique?: string | null;
  parameters?: Record<string, unknown> | null;
  procedure_summary?: string | null;
  artifact_role?: string | null;
  derivation_outputs?: Record<string, unknown> | null;
  derivation_step?: string | null;
  source_job_id?: string | null;
  derivation_group_id?: string | null;
  legacy_provenance?: boolean | null;
  layer?: number;
  images_used?: number | null;
}

export interface LineageEdge {
  from_evidence_id: string;
  to_evidence_id: string;
  technique?: string | null;
  parameters: Record<string, unknown>;
  procedure_summary?: string | null;
  source_job_id?: string | null;
  derivation_step?: string | null;
}

export interface LineageOperation {
  id: string;
  to_evidence_id: string;
  derivation_step?: string | null;
  label: string;
  inputs: Array<{ evidence_id: string; role?: string; label?: string }>;
  outputs?: Record<string, unknown> | null;
  input_count?: number | null;
  images_used?: number | null;
}

export interface LineagePhase {
  layer: number;
  label: string;
  node_ids: string[];
  node_count?: number | null;
}

export interface DerivationGroup {
  derivation_group_id: string;
  source_job_id?: string | null;
  member_count: number;
  siblings: Array<{
    evidence_id: string;
    original_filename: string;
    artifact_role?: string | null;
    derivation_step?: string | null;
    artifact_filename?: string | null;
  }>;
}

export interface LineageGraph {
  target_id: string;
  case_id: string;
  layout?: "dag" | "chain" | "multi_parent" | "prnu_dag";
  layout_label?: string | null;
  parent_count?: number | null;
  nodes: LineageNode[];
  edges: LineageEdge[];
  operations?: LineageOperation[];
  phases?: LineagePhase[];
  derivation_groups?: DerivationGroup[];
  legacy_notes?: string[];
}

export async function getEvidenceLineage(evidenceId: string): Promise<LineageGraph> {
  const response = await api.get<LineageGraph>(`/evidences/${evidenceId}/lineage`);
  return response.data;
}
