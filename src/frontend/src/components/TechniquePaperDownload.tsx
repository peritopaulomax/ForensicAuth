import { useEffect, useState } from "react";
import { hasTechniquePaper } from "@/config/techniquePapers";
import {
  downloadTechniquePaper,
  fetchTechniquePaperMeta,
  formatPaperSize,
  type TechniquePaperMeta,
} from "@/services/references";

interface Props {
  techniqueId: string;
}

function DocumentIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M8 2h7l5 5v13a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path d="M14 2v6h6" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M9 13h6M9 17h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 3v12m0 0l4-4m-4 4l-4-4M4 19h16"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function TechniquePaperDownload({ techniqueId }: Props) {
  const [meta, setMeta] = useState<TechniquePaperMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloadingIndex, setDownloadingIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!hasTechniquePaper(techniqueId)) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchTechniquePaperMeta(techniqueId)
      .then((data) => {
        if (!cancelled) setMeta(data);
      })
      .catch(() => {
        if (!cancelled) {
          setMeta(null);
          setError("Não foi possível verificar o artigo no servidor.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [techniqueId]);

  if (!hasTechniquePaper(techniqueId)) {
    return null;
  }

  async function handleDownload(index: number, filename: string) {
    if (!meta?.available || downloadingIndex !== null) return;
    setDownloadingIndex(index);
    setError(null);
    try {
      await downloadTechniquePaper(techniqueId, filename, index);
    } catch {
      setError("Falha ao baixar o PDF. Tente novamente.");
    } finally {
      setDownloadingIndex(null);
    }
  }

  const sizeLabel = formatPaperSize(meta?.size_bytes);
  const papers =
    meta?.files && meta.files.length > 0
      ? meta.files
      : meta
        ? [
            {
              index: 0,
              title: meta.title,
              venue: meta.venue,
              available: meta.available,
              size_bytes: meta.size_bytes,
              suggested_filename: meta.suggested_filename,
            },
          ]
        : [];
  const disabled = loading || !meta?.available || downloadingIndex !== null;

  return (
    <div
      style={{
        marginTop: "0.85rem",
        padding: "0.75rem 0.9rem",
        borderRadius: 10,
        border: "1px solid #dbeafe",
        background: "linear-gradient(135deg, #f8fbff 0%, #f0f9ff 55%, #eef2ff 100%)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "1rem",
        flexWrap: "wrap",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: "0.65rem", minWidth: 0, flex: 1 }}>
        <div
          style={{
            flexShrink: 0,
            width: 40,
            height: 40,
            borderRadius: 10,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(3, 105, 161, 0.1)",
            color: "#0369a1",
          }}
        >
          <DocumentIcon />
        </div>
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontSize: "0.8rem",
              fontWeight: 600,
              color: "#0f172a",
              letterSpacing: "0.01em",
            }}
          >
            Artigo científico
          </div>
          {loading ? (
            <p style={{ margin: "0.2rem 0 0", fontSize: "0.78rem", color: "#64748b" }}>
              Verificando PDF…
            </p>
          ) : meta ? (
            <>
              <p
                style={{
                  margin: "0.2rem 0 0",
                  fontSize: "0.78rem",
                  color: "#334155",
                  lineHeight: 1.45,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                }}
                title={meta.title ?? undefined}
              >
                {meta.title}
              </p>
              <p style={{ margin: "0.25rem 0 0", fontSize: "0.72rem", color: "#64748b" }}>
                {meta.venue ? <span>{meta.venue}</span> : null}
                {meta.venue && sizeLabel ? " · " : null}
                {sizeLabel ? <span>{sizeLabel}</span> : null}
                {!meta.available ? (
                  <span style={{ color: "#b45309" }}> · PDF indisponível no servidor</span>
                ) : null}
              </p>
            </>
          ) : null}
          {error ? (
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.72rem", color: "#b45309" }}>{error}</p>
          ) : null}
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
        {papers.map((paper) => {
          const paperSize = formatPaperSize(paper.size_bytes);
          const paperDisabled = disabled || !paper.available;
          return (
            <button
              key={paper.index}
              type="button"
              onClick={() => handleDownload(paper.index, paper.suggested_filename)}
              disabled={paperDisabled}
              title={paper.title ?? undefined}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.4rem",
                padding: "0.5rem 0.95rem",
                borderRadius: 8,
                border: "none",
                background: paperDisabled ? "#94a3b8" : "linear-gradient(180deg, #0e7490 0%, #0369a1 100%)",
                color: "#fff",
                fontSize: "0.8rem",
                fontWeight: 600,
                cursor: paperDisabled ? "not-allowed" : "pointer",
                boxShadow: paperDisabled ? "none" : "0 1px 2px rgba(3, 105, 161, 0.25)",
                flexShrink: 0,
              }}
            >
              <DownloadIcon />
              {downloadingIndex === paper.index
                ? "Baixando…"
                : papers.length > 1
                  ? `PDF ${paper.index + 1}${paperSize ? ` · ${paperSize}` : ""}`
                  : "Baixar PDF"}
            </button>
          );
        })}
      </div>
    </div>
  );
}
