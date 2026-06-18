/** Chain-of-custody audit API. */

import api from "./api";

export interface CustodyRecord {
  id: string;
  record_type: string;
  case_id: string;
  evidence_id: string | null;
  job_id: string | null;
  user_id: string;
  sha256_input: string | null;
  sha256_output: string | null;
  sha256_params: string | null;
  details: Record<string, unknown>;
  previous_record_hash: string | null;
  record_hash: string;
  timestamp: string;
}

export interface VerifyChainResult {
  valid: boolean;
  records_checked: number;
  first_invalid: string | null;
  reason?: string | null;
}

export async function listAuditRecords(params: {
  case_id: string;
  evidence_id?: string;
  job_id?: string;
}): Promise<CustodyRecord[]> {
  const { data } = await api.get<CustodyRecord[]>("/audit", { params });
  return data;
}

export async function verifyCaseChain(caseId: string): Promise<VerifyChainResult> {
  const { data } = await api.get<VerifyChainResult>(`/audit/verify-case/${caseId}`);
  return data;
}

export async function verifyRecord(recordId: string): Promise<{ valid: boolean }> {
  const { data } = await api.get<{ valid: boolean }>(`/audit/verify/${recordId}`);
  return data;
}

export interface ForensicIntegrityReport {
  valid: boolean;
  chain: VerifyChainResult;
  signatures: { checked: number; invalid: { record_id: string; chain_sequence: number }[] };
  files: {
    checked: number;
    missing: { evidence_id: string; path: string }[];
    hash_mismatch: { evidence_id: string; expected: string; actual: string | null }[];
  };
  provenance: { issues: { evidence_id: string; issue: string }[] };
  closures: {
    closure_sequence: number;
    manifest_valid: boolean;
    signatures_valid: boolean;
  }[];
  warnings: string[];
  generated_at: string;
  timeline?: { id: string; record_type: string; timestamp: string; chain_sequence: number }[];
}

export async function verifyCaseForensic(caseId: string): Promise<ForensicIntegrityReport> {
  const { data } = await api.get<ForensicIntegrityReport>(
    `/audit/verify-case-forensic/${caseId}`
  );
  return data;
}

export async function downloadForensicReport(
  caseId: string,
  format: "json" | "html" = "json"
): Promise<Blob> {
  const { data } = await api.get(`/audit/verify-case-forensic/${caseId}/report`, {
    params: { format },
    responseType: "blob",
  });
  return data;
}

export async function downloadCustodyNarrativeReport(
  caseId: string,
  format: "html" | "md" = "html"
): Promise<Blob> {
  const { data } = await api.get(`/audit/case/${caseId}/narrative-report`, {
    params: { format },
    responseType: "blob",
  });
  return data;
}

export const RECORD_TYPE_LABELS: Record<string, string> = {
  evidence_upload: "Upload de evidencia",
  evidence_deleted: "Exclusao de evidencia",
  case_deleted: "Exclusao de caso (arquivos removidos)",
  derivative_saved: "Derivado salvo",
  report_generated: "Laudo gerado",
  case_shared: "Caso compartilhado",
  case_unshared: "Compartilhamento revogado",
  case_closed: "Caso fechado",
  case_reopened: "Caso reaberto",
  case_closure_signed: "Assinatura de fechamento",
  custody_signing_repair: "Correcao de assinaturas Ed25519 (operador)",
  case_imported: "Caso importado de outra instancia",
  case_imported_peritus: "Caso importado do Peritus Desktop",
  peritus_file_imported: "Arquivo Peritus Desktop importado",
  case_exported_peritus: "Caso Peritus exportado",
  analysis_started: "Analise iniciada (registro historico)",
  analysis_completed: "Analise concluida (registro historico)",
  analysis_failed: "Analise falhou (registro historico)",
};
