import api from "@/services/api";
import type {
  Case,
  CaseClosure,
  CaseDetail,
  CreateCaseRequest,
  UpdateCaseRequest,
} from "@/types/api";
import { parseApiError } from "@/lib/apiErrors";

const VCP_TRANSFER_TIMEOUT_MS = 60 * 60 * 1000;

export async function listCases(scope?: "mine" | "shared" | "all"): Promise<CaseDetail[]> {
  const response = await api.get<CaseDetail[]>("/cases", {
    params: scope ? { scope } : undefined,
  });
  return response.data;
}

export async function createCase(data: CreateCaseRequest): Promise<Case> {
  const response = await api.post<Case>("/cases", data);
  return response.data;
}

export async function getCase(caseId: string): Promise<CaseDetail> {
  const response = await api.get<CaseDetail>(`/cases/${caseId}`);
  return response.data;
}

export interface ClosureSignerStatus {
  user_id: string;
  username: string | null;
  role: string;
  signed: boolean;
  is_current_user: boolean;
}

export interface ClosureStatus {
  case_status: string;
  fully_closed: boolean;
  closure_pending: boolean;
  active_closure_id: string | null;
  required_signers: ClosureSignerStatus[];
  pending_signers: ClosureSignerStatus[];
  pending_count: number;
  all_signed: boolean;
  current_user_must_sign: boolean;
  current_user_can_initiate: boolean;
  message: string;
}

export interface CloseCaseResult {
  closure: CaseClosure;
  case_status: string;
  fully_closed: boolean;
  closure_status: ClosureStatus;
}

export async function getClosureStatus(caseId: string): Promise<ClosureStatus> {
  const { data } = await api.get<ClosureStatus>(`/cases/${caseId}/closure-status`);
  return data;
}

export async function closeCase(
  caseId: string,
  signatureMode: "system" | "icp_brasil" = "system",
  note?: string
): Promise<CloseCaseResult> {
  const { data } = await api.post<CloseCaseResult>(`/cases/${caseId}/close`, {
    signature_mode: signatureMode,
    note,
  });
  return data;
}

export async function reopenCase(caseId: string): Promise<Case> {
  const { data } = await api.post<Case>(`/cases/${caseId}/reopen`);
  return data;
}

export async function listCaseClosures(caseId: string): Promise<CaseClosure[]> {
  const { data } = await api.get<CaseClosure[]>(`/cases/${caseId}/closures`);
  return data;
}

export async function addClosureSignature(caseId: string): Promise<void> {
  await api.post(`/cases/${caseId}/close/sign`);
}

export async function updateCase(
  caseId: string,
  data: UpdateCaseRequest
): Promise<Case> {
  const response = await api.put<Case>(`/cases/${caseId}`, data);
  return response.data;
}

export async function deleteCase(caseId: string): Promise<void> {
  await api.delete(`/cases/${caseId}`);
}

export interface VcpValidationReport {
  valid: boolean;
  issues: string[];
  package: {
    protocol_number?: string;
    case_id?: string;
    exported_at?: string;
    origin?: Record<string, unknown>;
  };
  files: { ok: boolean; checked: number; missing: unknown[]; hash_mismatch: unknown[] };
  chain: { valid: boolean; records_checked: number };
  signatures: { ok: boolean; checked: number; invalid: unknown[] };
  closures: { ok: boolean; invalid: unknown[] };
  conflicts: { ok: boolean; conflicts: { type: string }[]; replaceable_tombstone?: {
    case_id?: string;
    deleted_at?: string;
    tombstone_protocol_number?: string;
    case_deleted_record_hash?: string;
  } | null };
}

export type VcpExportPhase =
  | "preparing"
  | "packaging"
  | "chain"
  | "zip"
  | "waiting"
  | "downloading"
  | "done"
  | "error";

export interface VcpExportProgress {
  percent: number;
  message: string;
  phase: VcpExportPhase;
}

function parseContentDispositionFilename(header: string | undefined): string | null {
  if (!header) return null;
  const utf8 = /filename\*=UTF-8''([^;\s]+)/i.exec(header);
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1]);
    } catch {
      return utf8[1];
    }
  }
  const plain = /filename="?([^";\n]+)"?/i.exec(header);
  return plain?.[1]?.trim() ?? null;
}

async function blobErrorMessage(data: Blob, fallback: string): Promise<string> {
  try {
    const text = await data.text();
    const parsed = JSON.parse(text) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
    if (
      parsed.detail &&
      typeof parsed.detail === "object" &&
      parsed.detail !== null &&
      "message" in parsed.detail
    ) {
      return String((parsed.detail as { message: string }).message);
    }
  } catch {
    /* not JSON */
  }
  return fallback;
}

export async function exportCaseVcp(
  caseId: string,
  options?: {
    onProgress?: (progress: VcpExportProgress) => void;
    signal?: AbortSignal;
  }
): Promise<{ blob: Blob; filename: string }> {
  try {
    const { data, headers, status } = await api.post(`/cases/${caseId}/export`, null, {
      responseType: "blob",
      signal: options?.signal,
      onDownloadProgress: (ev) => {
        if (!ev.total) return;
        const pct = 90 + Math.round((ev.loaded / ev.total) * 10);
        options?.onProgress?.({
          percent: Math.min(99, pct),
          message: "Baixando VCP…",
          phase: "downloading",
        });
      },
    });

    if (status >= 400 || !(data instanceof Blob)) {
      const msg = data instanceof Blob ? await blobErrorMessage(data, "Erro ao exportar VCP") : "Erro ao exportar VCP";
      throw new Error(msg);
    }

    const cd = headers["content-disposition"] as string | undefined;
    const filename =
      parseContentDispositionFilename(cd) ?? `caso-${caseId}.vcp.zip`;

    options?.onProgress?.({
      percent: 100,
      message: "Pacote pronto.",
      phase: "done",
    });

    return { blob: data, filename };
  } catch (err: unknown) {
    if (err && typeof err === "object" && "response" in err) {
      const resp = (err as { response?: { data?: Blob; status?: number } }).response;
      if (resp?.data instanceof Blob) {
        const msg = await blobErrorMessage(resp.data, "Erro ao exportar VCP");
        throw new Error(msg);
      }
    }
    throw err;
  }
}

export type VcpImportPhase =
  | "uploading"
  | "validating"
  | "purging"
  | "extracting"
  | "chain"
  | "done"
  | "error";

export interface VcpImportProgress {
  percent: number;
  message: string;
  phase: VcpImportPhase;
}

export interface ImportResultResponse {
  case_id: string;
  protocol_number: string;
  chain_valid: boolean;
  records_imported: number;
  evidences_imported: number;
}

export async function validateCaseVcp(
  file: File,
  options?: {
    onProgress?: (progress: VcpImportProgress) => void;
    signal?: AbortSignal;
  }
): Promise<VcpValidationReport> {
  const form = new FormData();
  form.append("file", file);
  try {
    options?.onProgress?.({
      percent: 2,
      message: "Enviando pacote para validacao…",
      phase: "uploading",
    });
    const { data } = await api.post<VcpValidationReport>("/cases/import/validate", form, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: VCP_TRANSFER_TIMEOUT_MS,
      signal: options?.signal,
      onUploadProgress: (ev) => {
        if (!ev.total) return;
        const pct = Math.min(85, Math.round((ev.loaded / ev.total) * 85));
        options?.onProgress?.({
          percent: pct,
          message: `Enviando pacote (${(ev.loaded / (1024 * 1024)).toFixed(0)} / ${(ev.total / (1024 * 1024)).toFixed(0)} MB)…`,
          phase: "uploading",
        });
      },
    });
    options?.onProgress?.({
      percent: 100,
      message: "Validacao concluida.",
      phase: "done",
    });
    return data;
  } catch (err: unknown) {
    throw new Error(parseApiError(err, "Erro na validacao do pacote"));
  }
}

export async function importCaseVcp(
  file: File,
  options?: {
    onProgress?: (progress: VcpImportProgress) => void;
    signal?: AbortSignal;
    replaceableTombstone?: boolean;
  }
): Promise<ImportResultResponse> {
  const form = new FormData();
  form.append("file", file);
  try {
    options?.onProgress?.({
      percent: 2,
      message: "Enviando VCP…",
      phase: "uploading",
    });
    const { data } = await api.post<ImportResultResponse>("/cases/import", form, {
      params: { confirm: true },
      headers: { "Content-Type": "multipart/form-data" },
      timeout: VCP_TRANSFER_TIMEOUT_MS,
      signal: options?.signal,
      onUploadProgress: (ev) => {
        if (!ev.total) return;
        const pct = Math.min(70, Math.round((ev.loaded / ev.total) * 70));
        options?.onProgress?.({
          percent: pct,
          message: `Enviando pacote (${(ev.loaded / (1024 * 1024)).toFixed(0)} / ${(ev.total / (1024 * 1024)).toFixed(0)} MB)…`,
          phase: "uploading",
        });
      },
    });
    options?.onProgress?.({
      percent: 100,
      message: "Importacao concluida.",
      phase: "done",
    });
    return data;
  } catch (err: unknown) {
    throw new Error(parseApiError(err, "Erro na importacao do VCP"));
  }
}
