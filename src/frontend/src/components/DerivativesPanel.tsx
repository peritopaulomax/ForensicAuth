import { useCallback, useEffect, useMemo, useState } from "react";
import { downloadEvidenceFile, listCaseDerivatives } from "@/services/evidence";
import DerivativeThumbnailPair from "@/components/DerivativeThumbnailPair";
import DerivationGraphModal from "@/components/DerivationGraphModal";
import EvidenceFilePreview from "@/components/EvidenceFilePreview";
import FileListViewHeader from "@/components/FileListViewHeader";
import { useFileListViewMode } from "@/lib/fileListViewMode";
import { evidenceUsesThumbnail } from "@/lib/fileTypeIcons";
import { EVIDENCE_TYPE_LABELS, groupEvidencesByType } from "@/lib/evidenceByType";
import type { Evidence } from "@/types/api";
import { fileGridContainerStyle, scrollableListStyle } from "@/styles/listHeights";

interface Props {
  caseId: string;
  parentEvidences: Evidence[];
  refreshKey?: number;
  initialGraphEvidenceId?: string | null;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function formatParams(meta: Record<string, unknown>): string {
  const technique = meta.technique as string | undefined;
  const params = (meta.parameters as Record<string, unknown>) || {};
  if (technique === "ela") {
    const parts: string[] = ["ELA"];
    if (params.channel_mode) parts.push(String(params.channel_mode).toUpperCase());
    if (params.quality != null) parts.push(`Q${params.quality}`);
    if (params.gain != null) parts.push(`G${params.gain}`);
    return parts.join(" · ");
  }
  if (technique === "audio_spectrogram") {
    return "Espectrograma STFT";
  }
  if (technique) return technique.toUpperCase();
  return "—";
}

export default function DerivativesPanel({
  caseId,
  parentEvidences,
  refreshKey = 0,
  initialGraphEvidenceId = null,
}: Props) {
  const [derivatives, setDerivatives] = useState<Evidence[]>([]);
  const [loading, setLoading] = useState(true);
  const [exportingId, setExportingId] = useState<string | null>(null);
  const [graphTarget, setGraphTarget] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  const [viewMode, setViewMode] = useFileListViewMode();

  useEffect(() => {
    if (!initialGraphEvidenceId || derivatives.length === 0) return;
    const match = derivatives.find((item) => item.id === initialGraphEvidenceId);
    if (match) setGraphTarget(match);
  }, [initialGraphEvidenceId, derivatives]);

  const lookup = useMemo(() => {
    const map = new Map<string, Evidence>();
    for (const e of parentEvidences) map.set(e.id, e);
    for (const d of derivatives) map.set(d.id, d);
    return map;
  }, [parentEvidences, derivatives]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await listCaseDerivatives(caseId);
      setDerivatives(data);
    } catch {
      setError("Erro ao carregar derivados");
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  async function handleExport(ev: Evidence) {
    setExportingId(ev.id);
    try {
      await downloadEvidenceFile(ev.id, ev.original_filename);
    } catch {
      setError("Erro ao exportar derivado");
    } finally {
      setExportingId(null);
    }
  }

  function parentName(parentId: string | undefined): string {
    if (!parentId) return "—";
    const p = lookup.get(parentId);
    return p?.original_filename || `${parentId.slice(0, 8)}…`;
  }

  const { grouped, types } = useMemo(() => groupEvidencesByType(derivatives), [derivatives]);

  const groupedByJob = useMemo(() => {
    const buckets = new Map<string, Evidence[]>();
    for (const ev of derivatives) {
      const meta = ev.extra_metadata || {};
      const key = String(meta.derivation_group_id || meta.source_job_id || ev.id);
      const bucket = buckets.get(key) ?? [];
      bucket.push(ev);
      buckets.set(key, bucket);
    }
    return [...buckets.entries()].filter(([, items]) => items.length > 1);
  }, [derivatives]);

  if (loading) {
    return <p style={{ color: "#6b7280", padding: "1rem 0" }}>Carregando derivados…</p>;
  }

  return (
    <div>
      <FileListViewHeader viewMode={viewMode} onViewModeChange={setViewMode} style={{ marginBottom: "1rem" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: "1.15rem", color: "#1a1a2e" }}>Derivados</h2>
          <p style={{ margin: "0.35rem 0 0", fontSize: "0.8rem", color: "#6b7280" }}>
            Arquivos registrados na cadeia de custodia. Exportacao permitida somente aqui.
          </p>
        </div>
      </FileListViewHeader>

      {error && (
        <div
          style={{
            background: "#fee2e2",
            color: "#991b1b",
            padding: "0.6rem 1rem",
            borderRadius: "6px",
            marginBottom: "1rem",
            fontSize: "0.85rem",
          }}
        >
          {error}
        </div>
      )}

      {groupedByJob.length > 0 && (
        <div
          style={{
            marginBottom: "1rem",
            padding: "0.75rem 1rem",
            borderRadius: 8,
            background: "#f8fafc",
            border: "1px solid #e2e8f0",
            fontSize: "0.8rem",
            color: "#334155",
          }}
        >
          <strong>{groupedByJob.length}</strong> pacote(s) com multiplos artefatos do mesmo job
        </div>
      )}

      {derivatives.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "2.5rem",
            color: "#9ca3af",
            border: "1px dashed #e5e7eb",
            borderRadius: "8px",
          }}
        >
          Nenhum derivado salvo ainda. Use &quot;Salvar como derivado&quot; nas analises para registrar resultados aqui.
        </div>
      ) : (
        types.map((fileType) => (
          <section key={fileType} style={{ marginBottom: "1.5rem" }}>
            <h3
              style={{
                fontSize: "0.85rem",
                fontWeight: 600,
                color: "#374151",
                marginBottom: "0.6rem",
                textTransform: "uppercase",
                letterSpacing: "0.03em",
              }}
            >
              {EVIDENCE_TYPE_LABELS[fileType] || fileType} ({grouped[fileType].length})
            </h3>
            <div
              style={
                viewMode === "grid"
                  ? {
                      ...fileGridContainerStyle,
                      gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                    }
                  : {
                      border: "1px solid #e5e7eb",
                      borderRadius: 8,
                      overflow: "hidden",
                      background: "#fff",
                      ...scrollableListStyle,
                      maxHeight: 520,
                    }
              }
            >
              {grouped[fileType].map((ev) => {
                const meta = ev.extra_metadata || {};
                const parentId = meta.parent_evidence_id as string | undefined;
                const groupId = (meta.derivation_group_id || meta.source_job_id) as string | undefined;
                const procedure =
                  (meta.procedure_summary as string) || formatParams(meta as Record<string, unknown>);
                const showThumb = evidenceUsesThumbnail(ev.file_type, ev.original_filename, ev.mime_type);

                if (viewMode === "list") {
                  return (
                    <div
                      key={ev.id}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "minmax(120px, auto) 1fr auto auto",
                        gap: "0.75rem",
                        padding: "0.65rem 0.85rem",
                        alignItems: "center",
                        borderBottom: "1px solid #f3f4f6",
                        background: "#fff",
                      }}
                    >
                      {showThumb ? (
                        <DerivativeThumbnailPair
                          parentEvidenceId={parentId}
                          derivativeEvidenceId={ev.id}
                          fileType={ev.file_type}
                          size={40}
                        />
                      ) : (
                        <EvidenceFilePreview
                          evidenceId={ev.id}
                          fileType={ev.file_type}
                          filename={ev.original_filename}
                          size={40}
                        />
                      )}
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontWeight: 600, fontSize: "0.85rem", color: "#1a1a2e" }} title={ev.original_filename}>
                          {ev.original_filename}
                        </div>
                        <div style={{ fontSize: "0.75rem", color: "#6b7280" }}>
                          {procedure} · {parentName(parentId)} · {formatBytes(ev.file_size)}
                          {groupId && (
                            <> · pacote job {groupId.slice(0, 8)}…</>
                          )}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleExport(ev)}
                        disabled={exportingId === ev.id}
                        style={{
                          padding: "0.35rem 0.6rem",
                          background: "#1a1a2e",
                          color: "#fff",
                          border: "none",
                          borderRadius: 6,
                          cursor: exportingId === ev.id ? "wait" : "pointer",
                          fontSize: "0.75rem",
                        }}
                      >
                        {exportingId === ev.id ? "…" : "Exportar"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setGraphTarget(ev)}
                        style={{
                          padding: "0.35rem 0.6rem",
                          background: "#fff",
                          color: "#1a1a2e",
                          border: "1px solid #d1d5db",
                          borderRadius: 6,
                          cursor: "pointer",
                          fontSize: "0.75rem",
                        }}
                      >
                        Grafo
                      </button>
                    </div>
                  );
                }

                return (
                  <div
                    key={ev.id}
                    style={{
                      border: "1px solid #e5e7eb",
                      borderRadius: "8px",
                      padding: "0.85rem",
                      background: "#fff",
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.5rem",
                    }}
                  >
                    <div style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start" }}>
                      {showThumb ? (
                        <DerivativeThumbnailPair
                          parentEvidenceId={parentId}
                          derivativeEvidenceId={ev.id}
                          fileType={ev.file_type}
                          size={52}
                        />
                      ) : (
                        <EvidenceFilePreview
                          evidenceId={ev.id}
                          fileType={ev.file_type}
                          filename={ev.original_filename}
                          size={52}
                        />
                      )}
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div
                          style={{
                            fontWeight: 600,
                            fontSize: "0.85rem",
                            color: "#1a1a2e",
                            wordBreak: "break-word",
                          }}
                          title={ev.original_filename}
                        >
                          {ev.original_filename}
                        </div>
                        <div style={{ fontSize: "0.75rem", color: "#6b7280", marginTop: "0.2rem" }}>
                          {formatBytes(ev.file_size)}
                        </div>
                      </div>
                    </div>

                    <div
                      style={{
                        fontSize: "0.75rem",
                        color: "#374151",
                        background: "#f9fafb",
                        borderRadius: "4px",
                        padding: "0.45rem 0.55rem",
                        lineHeight: 1.4,
                      }}
                    >
                      <div>
                        <strong>Procedimento:</strong> {procedure}
                      </div>
                      <div>
                        <strong>Origem:</strong> {parentName(parentId)}
                      </div>
                      {groupId && (
                        <div>
                          <strong>Pacote job:</strong> {groupId.slice(0, 8)}…
                        </div>
                      )}
                      <div
                        style={{
                          fontFamily: "monospace",
                          fontSize: "0.68rem",
                          color: "#9ca3af",
                          marginTop: "0.25rem",
                          wordBreak: "break-all",
                        }}
                      >
                        SHA-256: {ev.sha256}
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => handleExport(ev)}
                      disabled={exportingId === ev.id}
                      style={{
                        padding: "0.45rem 0.75rem",
                        background: "#1a1a2e",
                        color: "#fff",
                        border: "none",
                        borderRadius: "6px",
                        cursor: exportingId === ev.id ? "wait" : "pointer",
                        fontSize: "0.8rem",
                        fontWeight: 500,
                      }}
                    >
                      {exportingId === ev.id ? "Exportando…" : "Exportar"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setGraphTarget(ev)}
                      style={{
                        padding: "0.45rem 0.75rem",
                        background: "#fff",
                        color: "#1a1a2e",
                        border: "1px solid #d1d5db",
                        borderRadius: "6px",
                        cursor: "pointer",
                        fontSize: "0.8rem",
                        fontWeight: 500,
                      }}
                    >
                      Grafo de derivacao
                    </button>
                  </div>
                );
              })}
            </div>
          </section>
        ))
      )}

      {graphTarget && (
        <DerivationGraphModal
          evidenceId={graphTarget.id}
          evidenceName={graphTarget.original_filename}
          onClose={() => setGraphTarget(null)}
        />
      )}
    </div>
  );
}
