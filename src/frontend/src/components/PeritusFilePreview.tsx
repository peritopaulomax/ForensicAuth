import { useEffect, useState } from "react";
import api from "@/services/api";
import { fileTypeIcon, evidenceUsesThumbnail } from "@/lib/fileTypeIcons";

interface Props {
  caseId: string;
  path: string;
  fileType?: string;
  filename?: string;
  size?: number;
  showPlayBadge?: boolean;
}

export default function PeritusFilePreview({
  caseId,
  path,
  fileType,
  filename,
  size = 48,
  showPlayBadge = false,
}: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!evidenceUsesThumbnail(fileType, filename)) {
      setUrl(null);
      setError(false);
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    api
      .get(`/cases/${caseId}/peritus/files/thumbnail`, {
        params: { path },
        responseType: "blob",
      })
      .then((res) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [caseId, path, fileType, filename]);

  if (!evidenceUsesThumbnail(fileType, filename) || error || !url) {
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
        }}
      >
        {fileTypeIcon(fileType)}
      </span>
    );
  }

  return (
    <span style={{ position: "relative", display: "inline-flex" }}>
      <img
        src={url}
        alt=""
        style={{
          width: size,
          height: size,
          objectFit: "cover",
          borderRadius: 4,
          border: "1px solid #e5e7eb",
        }}
      />
      {showPlayBadge && (
        <span
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "1.1rem",
            color: "#fff",
            textShadow: "0 1px 3px rgba(0,0,0,0.6)",
          }}
        >
          ▶
        </span>
      )}
    </span>
  );
}
