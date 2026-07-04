import api from "@/services/api";

export interface TechniquePaperFileMeta {
  index: number;
  title: string | null;
  venue: string | null;
  available: boolean;
  size_bytes: number | null;
  suggested_filename: string;
}

export interface TechniquePaperMeta {
  technique_id: string;
  title: string | null;
  venue: string | null;
  repo_url: string | null;
  source_urls: string[];
  available: boolean;
  size_bytes: number | null;
  suggested_filename: string;
  files?: TechniquePaperFileMeta[];
}

export async function fetchTechniquePaperMeta(techniqueId: string): Promise<TechniquePaperMeta> {
  const res = await api.get<TechniquePaperMeta>(`/references/papers/imdl/${encodeURIComponent(techniqueId)}`);
  return res.data;
}

export async function downloadTechniquePaper(
  techniqueId: string,
  filename: string,
  paperIndex?: number,
): Promise<void> {
  const suffix = paperIndex == null || paperIndex === 0 ? "/file" : `/file/${paperIndex}`;
  const res = await api.get(`/references/papers/imdl/${encodeURIComponent(techniqueId)}${suffix}`, {
    responseType: "blob",
  });
  const blob = res.data as Blob;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function formatPaperSize(bytes: number | null | undefined): string | null {
  if (bytes == null || bytes <= 0) return null;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
