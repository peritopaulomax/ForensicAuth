import { useState, useEffect, useRef } from "react";
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
  const rootRef = useRef<HTMLSpanElement>(null);
  const [visible, setVisible] = useState(() => Boolean(getCachedEvidenceThumbnailUrl(evidenceId)));
  const [url, setUrl] = useState<string | null>(() => getCachedEvidenceThumbnailUrl(evidenceId) ?? null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (visible) return;
    const el = rootRef.current;
    if (!el) return;

    const cached = getCachedEvidenceThumbnailUrl(evidenceId);
    if (cached) {
      setVisible(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "120px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [evidenceId, visible]);

  useEffect(() => {
    if (!visible) return;

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
  }, [evidenceId, visible]);

  const placeholder = (
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

  if (error) {
    return <span style={{ fontSize: "1.1rem" }}>{fallback}</span>;
  }

  if (!url) {
    return (
      <span ref={rootRef} style={{ display: "inline-flex", flexShrink: 0 }}>
        {placeholder}
      </span>
    );
  }

  return (
    <span ref={rootRef} style={{ position: "relative", display: "inline-flex", flexShrink: 0 }}>
      <img
        src={url}
        alt="thumbnail"
        loading="lazy"
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
