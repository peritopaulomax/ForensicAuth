import type { PeritusFileEntry } from "@/services/peritus";

export const ANALYSIS_MEDIA_TYPES = ["imagem", "audio", "video", "pdf"] as const;
export type AnalysisMediaType = (typeof ANALYSIS_MEDIA_TYPES)[number];

export function filterPeritusAnalyzable(
  files: PeritusFileEntry[],
  fileType?: AnalysisMediaType
): PeritusFileEntry[] {
  let list = files.filter(
    (f) =>
      !f.is_xml &&
      ANALYSIS_MEDIA_TYPES.includes(f.file_type as AnalysisMediaType)
  );
  if (fileType) {
    list = list.filter((f) => f.file_type === fileType);
  }
  return list;
}
