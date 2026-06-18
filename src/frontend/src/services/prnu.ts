import api from "@/services/api";

export interface PrnuFingerprintMeta {
  id: string;
  derivative_evidence_id?: string;
  case_id: string;
  label: string;
  reference_group_label?: string;
  legacy?: boolean;
  sha256?: string;
  saved_as_derivative?: boolean;
  sigma: number;
  images_used: number;
  shape?: number[];
  evidence_ids: string[];
  evidences?: Array<{ evidence_id: string; original_filename: string }>;
  fingerprint_path?: string;
  created_at: string;
  created_by?: string;
  exists?: boolean;
}

export async function listCaseFingerprints(caseId: string): Promise<PrnuFingerprintMeta[]> {
  const res = await api.get<PrnuFingerprintMeta[]>(`/cases/${caseId}/prnu/fingerprints`);
  return res.data;
}

export async function createCaseFingerprint(
  caseId: string,
  payload: { evidence_ids: string[]; label?: string; group_label?: string; sigma: number }
): Promise<PrnuFingerprintMeta> {
  const res = await api.post<PrnuFingerprintMeta>(`/cases/${caseId}/prnu/fingerprints`, payload);
  return res.data;
}
