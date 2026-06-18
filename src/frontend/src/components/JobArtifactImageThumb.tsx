import { useEffect, useState } from "react";

interface JobArtifactImageThumbProps {
  jobId: string;
  filename: string;
  fetchBlobUrl: (jobId: string, filename: string) => Promise<string | null>;
  size?: number;
  alt?: string;
}

export default function JobArtifactImageThumb({
  jobId,
  filename,
  fetchBlobUrl,
  size = 72,
  alt = "miniatura",
}: JobArtifactImageThumbProps) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!jobId || !filename) {
      setUrl(null);
      setFailed(false);
      return;
    }
    let cancelled = false;
    setFailed(false);
    fetchBlobUrl(jobId, filename).then((blobUrl) => {
      if (cancelled) {
        if (blobUrl) URL.revokeObjectURL(blobUrl);
        return;
      }
      if (!blobUrl) {
        setFailed(true);
        setUrl(null);
        return;
      }
      setUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return blobUrl;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [jobId, filename, fetchBlobUrl]);

  useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url);
    },
    [url]
  );

  if (failed || !url) {
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
        🖼️
      </span>
    );
  }

  return (
    <img
      src={url}
      alt={alt}
      style={{
        maxWidth: size,
        maxHeight: size,
        width: "auto",
        height: "auto",
        objectFit: "contain",
        display: "block",
      }}
    />
  );
}
