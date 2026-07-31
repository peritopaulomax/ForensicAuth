export const FILE_TYPE_ICONS: Record<string, string> = {
  imagem: "🖼️",
  audio: "🎵",
  video: "🎬",
  pdf: "📄",
  documento: "📄",
};

const NON_VISUAL_EXTENSIONS = new Set([".json", ".txt", ".html", ".xml", ".npz"]);
const IMAGE_EXTENSIONS = new Set([
  ".jpg",
  ".jpeg",
  ".png",
  ".gif",
  ".webp",
  ".bmp",
  ".tif",
  ".tiff",
  ".jp2",
  ".jpx",
  ".jpx2",
]);

function fileExtension(filename?: string): string {
  if (!filename) return "";
  const lower = filename.toLowerCase();
  const dot = lower.lastIndexOf(".");
  return dot >= 0 ? lower.slice(dot) : "";
}

/** Evidencia cujo conteudo pode ser exibido como miniatura de imagem/video. */
export function isVisualImageEvidence(
  fileType?: string,
  filename?: string,
  mimeType?: string | null,
): boolean {
  if (fileType === "documento") return false;

  const ext = fileExtension(filename);
  if (NON_VISUAL_EXTENSIONS.has(ext)) return false;

  const mime = (mimeType || "").toLowerCase();
  if (mime === "application/json" || mime === "text/plain" || mime === "text/html") {
    return false;
  }
  if (mime.startsWith("image/")) return true;
  if (fileType === "video" || mime.startsWith("video/")) return true;

  if (IMAGE_EXTENSIONS.has(ext)) return true;

  return fileType === "imagem";
}

export function fileTypeIcon(fileType?: string): string {
  return (fileType && FILE_TYPE_ICONS[fileType]) || "📎";
}

export function evidenceUsesThumbnail(
  fileType?: string,
  filename?: string,
  mimeType?: string | null,
): boolean {
  return isVisualImageEvidence(fileType, filename, mimeType);
}
