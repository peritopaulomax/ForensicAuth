import { useState, useEffect } from "react";
import api from "@/services/api";
import {
  fetchEvidenceThumbnailUrl,
  getCachedEvidenceThumbnailUrl,
} from "@/lib/evidenceThumbnailCache";

interface EvidenceThumbnailProps {
  evidenceId: string;
  fallback?: string;
  showPlayBadge?: boolean;
  size?: number;
}

export default function EvidenceThumbnail({
  evidenceId,
  fallback = "🖼️",
  showPlayBadge = false,
  size = 40,
}: EvidenceThumbnailProps) {
  const [url, setUrl] = useState<string | null>(() => getCachedEvidenceThumbnailUrl(evidenceId) ?? null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const cached = getCachedEvidenceThumbnailUrl(evidenceId);
    if (cached) {
      setUrl(cached);
      setError(false);
      return;
    }

    setUrl(null);
    setError(false);
    fetchEvidenceThumbnailUrl(evidenceId, () =>
      api.get(`/evidences/${evidenceId}/thumbnail`, { responseType: "blob" }).then((res) => res.data),
    )
      .then((blobUrl) => {
        if (!cancelled) setUrl(blobUrl);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });

    return () => {
      cancelled = true;
    };
  }, [evidenceId]);

  if (error) {
    return <span style={{ fontSize: "1.1rem" }}>{fallback}</span>;
  }

  if (!url) {
    return (
      <span
        style={{
          width: size,
          height: size,
          display: "inline-block",
          background: "#f3f4f6",
          borderRadius: 4,
          border: "1px solid #e5e7eb",
          flexShrink: 0,
        }}
        aria-hidden
      />
    );
  }

  return (
    <span style={{ position: "relative", display: "inline-flex", flexShrink: 0 }}>
      <img
        src={url}
        alt="thumbnail"
        style={{
          width: `${size}px`,
          height: `${size}px`,
          objectFit: "cover",
          borderRadius: "4px",
          border: "1px solid #e5e7eb",
        }}
      />
      {showPlayBadge && (
        <span
          aria-hidden
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "0.65rem",
            color: "#fff",
            textShadow: "0 0 3px rgba(0,0,0,0.8)",
            pointerEvents: "none",
          }}
        >
          ▶
        </span>
      )}
    </span>
  );
}
