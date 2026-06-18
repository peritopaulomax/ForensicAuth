import EvidenceThumbnail from "@/components/EvidenceThumbnail";

interface Props {
  parentEvidenceId: string | undefined;
  derivativeEvidenceId: string;
  fileType?: string;
  size?: number;
}

export default function DerivativeThumbnailPair({
  parentEvidenceId,
  derivativeEvidenceId,
  fileType = "imagem",
  size = 48,
}: Props) {
  const thumbStyle = { width: size, height: size };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", flexShrink: 0 }}>
      {parentEvidenceId ? (
        <EvidenceThumbnail
          evidenceId={parentEvidenceId}
          fallback="📎"
          size={size}
          showPlayBadge={fileType === "video"}
        />
      ) : (
        <span
          style={{
            ...thumbStyle,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            background: "#f3f4f6",
            borderRadius: "4px",
            border: "1px solid #e5e7eb",
            fontSize: "1rem",
          }}
        >
          ?
        </span>
      )}
      <span style={{ color: "#9ca3af", fontSize: "0.85rem", lineHeight: 1 }} aria-hidden>
        →
      </span>
      <EvidenceThumbnail
        evidenceId={derivativeEvidenceId}
        fallback="📎"
        size={size}
        showPlayBadge={fileType === "video"}
      />
    </div>
  );
}
