import api from "@/services/api";
import { parseApiError } from "@/lib/apiErrors";

const PERITUS_TRANSFER_TIMEOUT_MS = 60 * 60 * 1000;

export interface PeritusValidationReport {
  valid: boolean;
  issues: string[];
  package: {
    protocol_number?: string;
    title?: string;
    evidence_count?: number;
    derived_count?: number;
    calculation_count?: number;
    files_checked?: number;
    zip_sha256?: string;
  };
  files: {
    checked: number;
    missing_in_zip: string[];
    orphan_in_zip: string[];
    orphan_count?: number;
    hash_mismatch: { path: string; expected_hex: string; actual_hex: string }[];
  };
  conflicts: { ok: boolean; conflicts: { type: string; protocol_number?: string }[] };
}

export interface PeritusImportResult {
  case_id: string;
  protocol_number: string;
  storage_mode: string;
  evidence_count: number;
  derived_count: number;
  calculation_count: number;
  files_checked: number;
  original_zip_sha256: string;
}

export interface PeritusFileEntry {
  path: string;
  filename: string;
  folder: string;
  size: number;
  file_type: string;
  mime_type: string | null;
  sha256: string | null;
  peritus_uuid: string | null;
  is_derived: boolean;
  is_xml: boolean;
  evidence_id?: string | null;
}

export interface PeritusFilesListing {
  case_id: string;
  storage_mode: string;
  modified: boolean;
  original_zip_sha256: string | null;
  folders: string[];
  files: PeritusFileEntry[];
  file_count: number;
}

export type PeritusImportPhase =
  | "uploading"
  | "validating"
  | "extracting"
  | "done"
  | "error";

export interface PeritusImportProgress {
  percent: number;
  message: string;
  phase: PeritusImportPhase;
}

export type PeritusExportPhase =
  | "preparing"
  | "packaging"
  | "waiting"
  | "downloading"
  | "done"
  | "error";

export interface PeritusExportProgress {
  percent: number;
  message: string;
  phase: PeritusExportPhase;
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

export async function validateCasePeritus(
  file: File,
  options?: {
    onProgress?: (progress: PeritusImportProgress) => void;
    signal?: AbortSignal;
  }
): Promise<PeritusValidationReport> {
  const form = new FormData();
  form.append("file", file);
  try {
    options?.onProgress?.({
      percent: 2,
      message: "Enviando pacote Peritus Desktop para validacao…",
      phase: "uploading",
    });
    const { data } = await api.post<PeritusValidationReport>(
      "/cases/peritus/import/validate",
      form,
      {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: PERITUS_TRANSFER_TIMEOUT_MS,
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
      }
    );
    options?.onProgress?.({
      percent: 100,
      message: "Validacao concluida.",
      phase: "done",
    });
    return data;
  } catch (err: unknown) {
    throw new Error(parseApiError(err, "Erro na validacao do pacote Peritus Desktop"));
  }
}

export async function importCasePeritus(
  file: File,
  options?: {
    onProgress?: (progress: PeritusImportProgress) => void;
    signal?: AbortSignal;
  }
): Promise<PeritusImportResult> {
  const form = new FormData();
  form.append("file", file);
  try {
    options?.onProgress?.({
      percent: 2,
      message: "Enviando pacote Peritus Desktop…",
      phase: "uploading",
    });
    const { data } = await api.post<PeritusImportResult>("/cases/peritus/import", form, {
      params: { confirm: true },
      headers: { "Content-Type": "multipart/form-data" },
      timeout: PERITUS_TRANSFER_TIMEOUT_MS,
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
    throw new Error(parseApiError(err, "Erro na importacao do pacote Peritus Desktop"));
  }
}

export async function exportCasePeritus(
  caseId: string,
  options?: {
    onProgress?: (progress: PeritusExportProgress) => void;
    signal?: AbortSignal;
  }
): Promise<{ blob: Blob; filename: string }> {
  try {
    const { data, headers, status } = await api.post(
      `/cases/${caseId}/peritus/export`,
      null,
      {
        responseType: "blob",
        signal: options?.signal,
        timeout: PERITUS_TRANSFER_TIMEOUT_MS,
        onDownloadProgress: (ev) => {
          if (!ev.total) return;
          const pct = 90 + Math.round((ev.loaded / ev.total) * 10);
          options?.onProgress?.({
            percent: Math.min(99, pct),
            message: "Baixando pacote Peritus…",
            phase: "downloading",
          });
        },
      }
    );

    if (status >= 400 || !(data instanceof Blob)) {
      const msg =
        data instanceof Blob
          ? await blobErrorMessage(data, "Erro ao exportar pacote Peritus")
          : "Erro ao exportar pacote Peritus";
      throw new Error(msg);
    }

    const cd = headers["content-disposition"] as string | undefined;
    const filename =
      parseContentDispositionFilename(cd) ?? `peritus-${caseId}.zip`;

    options?.onProgress?.({
      percent: 100,
      message: "Pacote pronto.",
      phase: "done",
    });

    return { blob: data, filename };
  } catch (err: unknown) {
    if (err && typeof err === "object" && "response" in err) {
      const resp = (err as { response?: { data?: Blob } }).response;
      if (resp?.data instanceof Blob) {
        const msg = await blobErrorMessage(resp.data, "Erro ao exportar pacote Peritus");
        throw new Error(msg);
      }
    }
    throw err;
  }
}

export async function listPeritusFiles(caseId: string): Promise<PeritusFilesListing> {
  const { data } = await api.get<PeritusFilesListing>(`/cases/${caseId}/peritus/files`);
  return data;
}

export interface PeritusCaseMeta {
  case_id: string;
  storage_mode: string;
  imported_at: string | null;
  modified: boolean;
  original_zip_sha256: string | null;
  original_xml_sha256: string | null;
  peritus_chain_anchor: string | null;
  protocol_number?: string;
  file_count?: number;
  evidence_count?: number;
  derived_count?: number;
  calculation_count?: number;
  custody_files_registered?: number;
}

export async function getPeritusCaseMeta(caseId: string): Promise<PeritusCaseMeta> {
  const { data } = await api.get<PeritusCaseMeta>(`/cases/${caseId}/peritus/meta`);
  return data;
}

export async function ensurePeritusFilesCustody(caseId: string): Promise<{
  already_registered: boolean;
  files_registered: number;
}> {
  const { data } = await api.post(`/cases/${caseId}/peritus/custody/register-files`);
  return data;
}

export async function resolvePeritusFileForAnalysis(
  caseId: string,
  path: string
): Promise<{ evidence_id: string; path: string; created: boolean }> {
  const { data } = await api.post(`/cases/${caseId}/peritus/files/resolve-analysis`, { path });
  return data;
}

export function peritusFileDownloadUrl(caseId: string, path: string): string {
  const base = api.defaults.baseURL || "";
  const token = localStorage.getItem("token");
  const q = new URLSearchParams({ path });
  return `${base}/cases/${caseId}/peritus/files/download?${q.toString()}${token ? "" : ""}`;
}

export async function downloadPeritusFile(caseId: string, path: string): Promise<Blob> {
  const { data } = await api.get<Blob>(`/cases/${caseId}/peritus/files/download`, {
    params: { path },
    responseType: "blob",
  });
  return data;
}
