/**
 * Vocabulário de roles de artefato do scaffold — contrato YAML ↔ UI genérica.
 * Só roles listados aqui têm renderização associada; outros devem ser rejeitados no scaffold.
 */

export const ARTIFACT_ROLES = [
  // Painel esquerdo (par sincronizado)
  "original",
  "input",
  // Abas direita (imagem espacial)
  "heatmap",
  "overlay",
  "mask",
  "score_map",
  "confidence",
  "detection",
  // Relatório HTML
  "interactive",
  "report",
  // Comparison / plots
  "plot_data",
  "plot",
  "matrix",
  // Downloads / arquivos
  "json",
  "txt",
  "download",
  // Fallback imagem genérica (aba direita se for imagem)
  "other",
] as const;

export type ArtifactRole = (typeof ARTIFACT_ROLES)[number];

export const LEFT_IMAGE_ROLES = new Set<ArtifactRole>(["original", "input"]);

export const RIGHT_IMAGE_ROLES = new Set<ArtifactRole>([
  "heatmap",
  "overlay",
  "mask",
  "score_map",
  "confidence",
  "detection",
  "other",
  "plot_data",
  "plot",
  "matrix",
]);

export const INTERACTIVE_ROLES = new Set<ArtifactRole>(["interactive", "report"]);

export const DOWNLOAD_ROLES = new Set<ArtifactRole>(["json", "txt", "download"]);

export const COMPARISON_IMAGE_ROLES = new Set<ArtifactRole>([
  "plot_data",
  "plot",
  "matrix",
  "heatmap",
  "overlay",
  "mask",
  "score_map",
  "confidence",
  "detection",
]);

const IMAGE_EXT = /\.(png|jpe?g|webp|gif|bmp)$/i;
const HTML_EXT = /\.html?$/i;

export function normalizeArtifactRole(role: string | undefined | null): ArtifactRole {
  if (role && (ARTIFACT_ROLES as readonly string[]).includes(role)) {
    return role as ArtifactRole;
  }
  return "other";
}

export function isImageFilename(filename: string): boolean {
  return IMAGE_EXT.test(filename);
}

export function isHtmlFilename(filename: string): boolean {
  return HTML_EXT.test(filename);
}

export function mimeForDownloadRole(role: ArtifactRole, filename: string): string {
  if (role === "json" || filename.endsWith(".json")) return "application/json";
  if (role === "txt" || filename.endsWith(".txt")) return "text/plain";
  if (isHtmlFilename(filename)) return "text/html";
  if (isImageFilename(filename)) return "application/octet-stream";
  return "application/octet-stream";
}
