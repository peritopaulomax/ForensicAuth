import { useEffect, useState, type CSSProperties } from "react";
import { listCaseAudioMetadata, listCaseEvidences } from "@/services/evidence";
import EvidenceFileGrid from "@/components/EvidenceFileGrid";
import FileListViewHeader from "@/components/FileListViewHeader";
import PeritusAnalysisFileSection from "@/components/PeritusAnalysisFileSection";
import { useFileListViewMode } from "@/lib/fileListViewMode";
import { resolvePeritusFileForAnalysis } from "@/services/peritus";
import { filterForensicAuthEvidences } from "@/lib/forensicAuthEvidence";
import type { AudioTechnicalMetadata, Evidence } from "@/types/api";
import {
  audioMetaFromEvidence,
  formatAudioBitDepth,
  formatAudioCodec,
  formatAudioDuration,
  formatAudioSampleRate,
  mergeAudioMeta,
} from "@/lib/audioMetadataFormat";
import { imageSelectorListMaxHeight, scrollableListStyle } from "@/styles/listHeights";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / k ** i).toFixed(1))} ${sizes[i]}`;
}

const GRID = "36px minmax(160px, 1.6fr) 92px 80px 68px minmax(72px, 1fr) 80px";

const cellMuted: CSSProperties = {
  fontSize: "0.8rem",
  color: "#6b7280",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

export interface AudioEvidenceSelectorProps {
  caseId: string;
  selectedId: string | null;
  onSelect: (id: string, filename: string) => void;
}

export default function AudioEvidenceSelector({ caseId, selectedId, onSelect }: AudioEvidenceSelectorProps) {
  const [evidences, setEvidences] = useState<Evidence[]>([]);
  const [metadataById, setMetadataById] = useState<Record<string, AudioTechnicalMetadata>>({});
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useFileListViewMode();
  const [selectedPeritusPath, setSelectedPeritusPath] = useState<string | null>(null);
  const [resolvingPeritus, setResolvingPeritus] = useState(false);

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    Promise.all([listCaseEvidences(caseId), listCaseAudioMetadata(caseId)])
      .then(([evs, metaItems]) => {
        setEvidences(filterForensicAuthEvidences(evs).filter((e) => e.file_type === "audio"));
        const map: Record<string, AudioTechnicalMetadata> = {};
        for (const item of metaItems) {
          map[item.evidence_id] = item;
        }
        setMetadataById(map);
      })
      .finally(() => setLoading(false));
  }, [caseId]);

  function handleSelectVa(id: string, filename: string) {
    setSelectedPeritusPath(null);
    onSelect(id, filename);
  }

  async function handleSelectPeritus(path: string) {
    setResolvingPeritus(true);
    try {
      const resolved = await resolvePeritusFileForAnalysis(caseId, path);
      setSelectedPeritusPath(path);
      onSelect(resolved.evidence_id, path.split("/").pop() || path);
    } finally {
      setResolvingPeritus(false);
    }
  }

  const vaSelectedId = selectedPeritusPath ? null : selectedId;

  if (loading) {
    return <p style={{ margin: 0, color: "#6b7280", fontSize: "0.85rem" }}>Carregando audios…</p>;
  }

  return (
    <div>
      <h3 style={{ fontSize: "0.9rem", color: "#374151", marginBottom: "0.5rem", fontWeight: 600 }}>
        Evidências ForensicAuth
      </h3>
      {evidences.length === 0 ? (
        <p style={{ margin: "0 0 0.5rem", color: "#6b7280", fontSize: "0.85rem" }}>Nenhum áudio VA neste caso.</p>
      ) : (
        <>
          <FileListViewHeader viewMode={viewMode} onViewModeChange={setViewMode} style={{ marginBottom: "0.5rem" }} />
          {viewMode === "grid" ? (
            <EvidenceFileGrid
              items={evidences}
              selected={(ev) => vaSelectedId === ev.id}
              onSelect={(ev) => handleSelectVa(ev.id, ev.original_filename)}
              maxHeight={imageSelectorListMaxHeight}
              renderFooter={(ev) => {
                const meta = mergeAudioMeta(metadataById[ev.id], audioMetaFromEvidence(ev.extra_metadata));
                return (
                  <>
                    <span style={{ fontSize: "0.68rem", color: "#6b7280" }}>
                      {formatAudioSampleRate(meta.sample_rate_hz ?? null)} ·{" "}
                      {formatAudioDuration(meta.duration_sec ?? null)}
                    </span>
                    <span style={{ fontSize: "0.68rem", color: "#9ca3af" }}>
                      {formatAudioCodec(meta.codec ?? null)} · {formatBytes(ev.file_size ?? 0)}
                    </span>
                  </>
                );
              }}
            />
          ) : (
            <div
              style={{
                border: "1px solid #e5e7eb",
                borderRadius: 8,
                overflow: "hidden",
                background: "#fff",
              }}
            >
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: GRID,
                  gap: "0.5rem",
                  padding: "0.55rem 0.75rem",
                  background: "#f9fafb",
                  borderBottom: "1px solid #e5e7eb",
                  fontSize: "0.72rem",
                  fontWeight: 600,
                  color: "#6b7280",
                  textTransform: "uppercase",
                  letterSpacing: "0.03em",
                }}
              >
                <span />
                <span>Nome</span>
                <span>Taxa</span>
                <span>Duração</span>
                <span>Bits</span>
                <span>Codec</span>
                <span>Tamanho</span>
              </div>

              <div style={{ ...scrollableListStyle, maxHeight: imageSelectorListMaxHeight }}>
                {evidences.map((ev) => {
                  const selected = vaSelectedId === ev.id;
                  const meta = mergeAudioMeta(metadataById[ev.id], audioMetaFromEvidence(ev.extra_metadata));
                  return (
                    <label
                      key={ev.id}
                      style={{
                        display: "grid",
                        gridTemplateColumns: GRID,
                        gap: "0.5rem",
                        padding: "0.55rem 0.75rem",
                        alignItems: "center",
                        background: selected ? "#e0f2fe" : "#fff",
                        borderBottom: "1px solid #f3f4f6",
                        cursor: "pointer",
                        margin: 0,
                      }}
                    >
                      <input
                        type="radio"
                        name="audio-evidence"
                        checked={selected}
                        onChange={() => handleSelectVa(ev.id, ev.original_filename)}
                        style={{ cursor: "pointer" }}
                      />
                      <span
                        style={{
                          fontSize: "0.85rem",
                          color: "#1a1a2e",
                          fontWeight: 500,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                        title={ev.original_filename}
                      >
                        🎵 {ev.original_filename}
                      </span>
                      <span style={cellMuted} title={formatAudioSampleRate(meta.sample_rate_hz ?? null)}>
                        {formatAudioSampleRate(meta.sample_rate_hz ?? null)}
                      </span>
                      <span style={cellMuted} title={formatAudioDuration(meta.duration_sec ?? null)}>
                        {formatAudioDuration(meta.duration_sec ?? null)}
                      </span>
                      <span style={cellMuted}>{formatAudioBitDepth(meta.bit_depth ?? null)}</span>
                      <span style={cellMuted} title={formatAudioCodec(meta.codec ?? null)}>
                        {formatAudioCodec(meta.codec ?? null)}
                      </span>
                      <span style={cellMuted}>{formatBytes(ev.file_size)}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}

      <PeritusAnalysisFileSection
        caseId={caseId}
        fileType="audio"
        selectedPath={selectedPeritusPath}
        onSelect={handleSelectPeritus}
        radioName="audio-peritus"
        resolving={resolvingPeritus}
      />
    </div>
  );
}
