import { useState } from "react";
import PeritusFilePreview from "@/components/PeritusFilePreview";
import { usePeritusAnalyzableFiles } from "@/hooks/usePeritusAnalyzableFiles";
import { resolvePeritusFileForAnalysis } from "@/services/peritus";
import type { AnalysisMediaType } from "@/lib/peritusAnalysis";
import { imageSelectorListMaxHeight, scrollableListStyle } from "@/styles/listHeights";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / k ** i).toFixed(1))} ${sizes[i]}`;
}

interface Props {
  caseId: string;
  fileType: AnalysisMediaType;
  selectedEvidenceIds: Set<string>;
  onToggleEvidenceId: (evidenceId: string) => void;
}

/** Seleção múltipla de arquivos Peritus (materializa lazy e alterna evidence_id no conjunto). */
export default function PeritusMultiFilePicker({
  caseId,
  fileType,
  selectedEvidenceIds,
  onToggleEvidenceId,
}: Props) {
  const { files, loading, hasPeritusFiles } = usePeritusAnalyzableFiles(caseId, fileType);
  const [resolvingPath, setResolvingPath] = useState<string | null>(null);
  const [materializedIds, setMaterializedIds] = useState<Record<string, string>>({});

  const typeLabel: Record<AnalysisMediaType, string> = {
    imagem: "imagens",
    audio: "áudios",
    video: "vídeos",
    pdf: "PDFs",
  };

  if (loading) {
    return (
      <p style={{ margin: "1rem 0 0", color: "#9ca3af", fontSize: "0.85rem" }}>
        Carregando arquivos Peritus…
      </p>
    );
  }

  if (!hasPeritusFiles) {
    return null;
  }

  async function handleToggle(path: string, knownEvidenceId?: string | null) {
    const evidenceId = knownEvidenceId || materializedIds[path];
    if (evidenceId && selectedEvidenceIds.has(evidenceId)) {
      onToggleEvidenceId(evidenceId);
      return;
    }
    if (evidenceId) {
      onToggleEvidenceId(evidenceId);
      return;
    }
    setResolvingPath(path);
    try {
      const resolved = await resolvePeritusFileForAnalysis(caseId, path);
      setMaterializedIds((prev) => ({ ...prev, [path]: resolved.evidence_id }));
      onToggleEvidenceId(resolved.evidence_id);
    } finally {
      setResolvingPath(null);
    }
  }

  const selectedPeritusCount = files.filter((f) => {
    const id = f.evidence_id || materializedIds[f.path];
    return id && selectedEvidenceIds.has(id);
  }).length;

  return (
    <div style={{ marginTop: "1.25rem" }}>
      <h3 style={{ fontSize: "0.9rem", color: "#4338ca", marginBottom: "0.5rem", fontWeight: 600 }}>
        Arquivos Peritus importados
      </h3>
      <p style={{ fontSize: "0.78rem", color: "#6b7280", marginTop: 0, marginBottom: "0.5rem" }}>
        Marque os {typeLabel[fileType]} do pacote Peritus para incluir na comparação ({selectedPeritusCount}{" "}
        selecionado(s)).
      </p>
      <div
        style={{
          ...scrollableListStyle,
          maxHeight: imageSelectorListMaxHeight,
          border: "1px solid #e5e7eb",
          borderRadius: 6,
          padding: 8,
          background: "#fff",
        }}
      >
        {files.map((f) => {
          const evidenceId = f.evidence_id || materializedIds[f.path];
          const checked = Boolean(evidenceId && selectedEvidenceIds.has(evidenceId));
          const busy = resolvingPath === f.path;
          return (
            <label
              key={f.path}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                fontSize: "0.85rem",
                marginBottom: 8,
                cursor: busy ? "wait" : "pointer",
                opacity: busy ? 0.7 : 1,
              }}
            >
              <input
                type="checkbox"
                checked={checked}
                disabled={Boolean(resolvingPath)}
                onChange={() => handleToggle(f.path, f.evidence_id)}
              />
              <PeritusFilePreview
                caseId={caseId}
                path={f.path}
                fileType={f.file_type}
                filename={f.filename}
                size={36}
              />
              <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
                {f.filename}
              </span>
              <span style={{ fontSize: "0.75rem", color: "#9ca3af", whiteSpace: "nowrap" }}>
                {f.folder} · {formatBytes(f.size)}
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
}
