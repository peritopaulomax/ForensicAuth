import EvidenceThumbnail from "@/components/EvidenceThumbnail";
import { evidenceUsesThumbnail, fileTypeIcon } from "@/lib/fileTypeIcons";

interface EvidenceFilePreviewProps {
  evidenceId: string;
  fileType?: string;
  filename?: string;
  mimeType?: string | null;
  size?: number;
  showPlayBadge?: boolean;
}

export default function EvidenceFilePreview({
  evidenceId,
  fileType,
  filename,
  mimeType,
  size = 48,
  showPlayBadge = false,
}: EvidenceFilePreviewProps) {
  if (evidenceUsesThumbnail(fileType, filename, mimeType)) {
    return (
      <EvidenceThumbnail
        evidenceId={evidenceId}
        fallback={fileTypeIcon(fileType)}
        showPlayBadge={showPlayBadge || fileType === "video"}
        size={size}
      />
    );
  }

  return (
    <span
      style={{
        width: size,
        height: size,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: size > 40 ? "1.5rem" : "1.25rem",
        background: "#f3f4f6",
        borderRadius: 4,
        border: "1px solid #e5e7eb",
        flexShrink: 0,
      }}
      aria-hidden
    >
      {fileTypeIcon(fileType)}
    </span>
  );
}
