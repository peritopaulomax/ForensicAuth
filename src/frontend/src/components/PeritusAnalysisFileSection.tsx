import SelectablePeritusFileList from "@/components/SelectablePeritusFileList";
import { usePeritusAnalyzableFiles } from "@/hooks/usePeritusAnalyzableFiles";
import type { AnalysisMediaType } from "@/lib/peritusAnalysis";

interface Props {
  caseId: string;
  fileType: AnalysisMediaType;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  radioName: string;
  resolving?: boolean;
}

export default function PeritusAnalysisFileSection({
  caseId,
  fileType,
  selectedPath,
  onSelect,
  radioName,
  resolving = false,
}: Props) {
  const { files, loading, hasPeritusFiles } = usePeritusAnalyzableFiles(caseId, fileType);

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

  return (
    <div style={{ marginTop: "1.25rem" }}>
      <h3
        style={{
          fontSize: "0.9rem",
          color: "#4338ca",
          marginBottom: "0.5rem",
          fontWeight: 600,
        }}
      >
        Arquivos Peritus importados
      </h3>
      <p style={{ fontSize: "0.78rem", color: "#6b7280", marginTop: 0, marginBottom: "0.5rem" }}>
        Snapshot do pacote Peritus Desktop — selecione para materializar e analisar com as mesmas
        técnicas das evidências ForensicAuth.
      </p>
      {resolving && (
        <p style={{ fontSize: "0.78rem", color: "#4338ca", margin: "0 0 0.5rem" }}>
          Preparando arquivo para análise…
        </p>
      )}
      <SelectablePeritusFileList
        caseId={caseId}
        files={files}
        selectedPath={selectedPath}
        onSelect={onSelect}
        radioName={radioName}
        disabled={resolving}
      />
    </div>
  );
}
