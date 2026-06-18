import api from "@/services/api";
import type { AudioTechnicalMetadata, Evidence } from "@/types/api";

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
  onProgress?: (percent: number) => void
): Promise<Evidence> {
  const formData = new FormData();
  formData.append("case_id", caseId);
  formData.append("file", file);

  const response = await api.post<Evidence>("/evidences/upload", formData, {
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

export interface ReferenceGroup {
  technique: string;
  group_label: string;
  display_label: string;
  files: Evidence[];
}

export interface CaseReferencesResponse {
  groups: ReferenceGroup[];
}

export async function listCaseReferences(caseId: string): Promise<CaseReferencesResponse> {
  const response = await api.get<CaseReferencesResponse>(`/cases/${caseId}/references`);
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
  return response.data;
}

export interface LineageNode {
  evidence_id: string;
  original_filename: string;
  file_type: string;
  sha256: string;
  is_derived: boolean;
  technique?: string | null;
  parameters?: Record<string, unknown> | null;
  procedure_summary?: string | null;
  artifact_role?: string | null;
  derivation_outputs?: Record<string, unknown> | null;
  derivation_step?: string | null;
  layer?: number;
  images_used?: number | null;
}

export interface LineageEdge {
  from_evidence_id: string;
  to_evidence_id: string;
  technique?: string | null;
  parameters: Record<string, unknown>;
  procedure_summary?: string | null;
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
}

export async function getEvidenceLineage(evidenceId: string): Promise<LineageGraph> {
  const response = await api.get<LineageGraph>(`/evidences/${evidenceId}/lineage`);
  return response.data;
}
