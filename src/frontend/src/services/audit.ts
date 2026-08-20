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

export interface VerifyRecordResult {
  valid: boolean;
  record: CustodyRecord;
  computed_hash: string;
  signature_valid: boolean | null;
}

export async function verifyRecord(recordId: string): Promise<VerifyRecordResult> {
  const { data } = await api.get<VerifyRecordResult>(`/audit/verify/${recordId}`);
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

/** Resumo curto para banner/UI quando a verificação forense falha. */
export function forensicFailureSummary(report: ForensicIntegrityReport | null | undefined): string | null {
  if (!report || report.valid) return null;
  const parts: string[] = [];
  if (report.chain && !report.chain.valid) parts.push("cadeia de custodia");
  const invalidSigs = report.signatures?.invalid?.length ?? 0;
  if (invalidSigs > 0) {
    parts.push(
      `${invalidSigs} assinatura(s) Ed25519 invalida(s) (chave do sistema ou registro alterado)`
    );
  }
  const missing = report.files?.missing?.length ?? 0;
  const mismatch = report.files?.hash_mismatch?.length ?? 0;
  if (missing > 0 || mismatch > 0) {
    parts.push("arquivos de evidencia");
  }
  if ((report.provenance?.issues?.length ?? 0) > 0) parts.push("proveniencia");
  const badClosures = (report.closures ?? []).filter(
    (c) => !c.signatures_valid || !c.manifest_valid
  );
  if (badClosures.length > 0) parts.push("fechamento(s) do caso");
  return parts.length > 0 ? parts.join("; ") : "falha nao especificada";
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
  evidence_group_label_changed: "Rotulo de questionado alterado",
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
