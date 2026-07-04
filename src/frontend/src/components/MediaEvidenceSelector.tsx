import { useEffect, useState } from "react";
import { listCaseEvidences } from "@/services/evidence";
import GlobalReferencesSelector from "@/components/GlobalReferencesSelector";
import SelectableEvidenceList from "@/components/SelectableEvidenceList";
import PeritusAnalysisFileSection from "@/components/PeritusAnalysisFileSection";
import { resolvePeritusFileForAnalysis } from "@/services/peritus";
import { filterForensicAuthEvidences } from "@/lib/forensicAuthEvidence";
import type { AnalysisMediaType } from "@/lib/peritusAnalysis";
import type { Evidence } from "@/types/api";

interface Props {
  caseId: string;
  fileType: AnalysisMediaType;
  selectedId: string | null;
  onSelect: (id: string) => void;
  radioName?: string;
  title?: string;
}

export default function MediaEvidenceSelector({
  caseId,
  fileType,
  selectedId,
  onSelect,
  radioName = "media-evidence",
  title = "Selecione a evidência",
}: Props) {
  const [evidences, setEvidences] = useState<Evidence[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedPeritusPath, setSelectedPeritusPath] = useState<string | null>(null);
  const [resolvingPeritus, setResolvingPeritus] = useState(false);

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    listCaseEvidences(caseId)
      .then((evs) => {
        const filtered = filterForensicAuthEvidences(evs).filter((e) => e.file_type === fileType);
        setEvidences(filtered);
      })
      .finally(() => setLoading(false));
  }, [caseId, fileType]);

  useEffect(() => {
    if (!selectedId) {
      setSelectedPeritusPath(null);
    }
  }, [selectedId]);

  function handleSelectEvidence(id: string) {
    setSelectedPeritusPath(null);
    onSelect(id);
  }

  async function handleSelectPeritus(path: string) {
    setResolvingPeritus(true);
    try {
      const resolved = await resolvePeritusFileForAnalysis(caseId, path);
      setSelectedPeritusPath(path);
      onSelect(resolved.evidence_id);
    } finally {
      setResolvingPeritus(false);
    }
  }

  return (
    <div style={{ marginBottom: "1rem" }}>
      <h3 style={{ fontSize: "0.9rem", color: "#374151", marginBottom: "0.5rem", fontWeight: 600 }}>
        {title}
      </h3>
      {loading ? (
        <p style={{ color: "#9ca3af", fontSize: "0.85rem" }}>Carregando…</p>
      ) : (
        <SelectableEvidenceList
          sectionId={`media-${fileType}-${caseId}`}
          items={evidences}
          selectedId={selectedPeritusPath ? null : selectedId}
          selectionSource="original"
          source="original"
          onSelect={(id) => handleSelectEvidence(id)}
          radioName={radioName}
          emptyMessage={`Nenhuma evidência de ${fileType} neste caso.`}
        />
      )}
      <GlobalReferencesSelector
        caseId={caseId}
        fileType={fileType}
        selectedId={selectedPeritusPath ? null : selectedId}
        onSelect={handleSelectEvidence}
        radioName={`${radioName}-global-reference`}
      />

      <PeritusAnalysisFileSection
        caseId={caseId}
        fileType={fileType}
        selectedPath={selectedPeritusPath}
        onSelect={handleSelectPeritus}
        radioName={`${radioName}-peritus`}
        resolving={resolvingPeritus}
      />
    </div>
  );
}
